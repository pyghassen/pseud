import threading
import uuid

import msgpack
import pytest
import zmq


def test_client_creation():
    from pybidirpc import SyncClient
    from pybidirpc import auth, heartbeat  # NOQA
    client = SyncClient()
    assert client.security_plugin == 'noop_auth_backend'


def test_client_can_bind():
    from pybidirpc import SyncClient
    from pybidirpc import auth, heartbeat  # NOQA
    endpoint = 'inproc://{}'.format(__name__)
    client = SyncClient()
    client.bind(endpoint)
    client.stop()


def test_client_can_connect():
    from pybidirpc import SyncClient
    from pybidirpc import auth, heartbeat  # NOQA
    endpoint = 'inproc://{}'.format(__name__)
    client = SyncClient()
    client.connect(endpoint)
    client.stop()


def make_one_server_thread(context, identity, endpoint, callback):
    router_sock = context.socket(zmq.ROUTER)
    router_sock.identity = identity
    router_sock.bind(endpoint)
    response = router_sock.recv_multipart()
    callback(router_sock, response)


def make_one_client(timeout=5):
    from pybidirpc import SyncClient
    from pybidirpc import auth, heartbeat  # NOQA
    client = SyncClient(timeout=timeout)
    return client


def test_client_method_wrapper():
    from pybidirpc.common import AttributeWrapper
    from pybidirpc import auth, heartbeat  # NOQA
    endpoint = 'inproc://{}'.format(__name__)
    client = make_one_client()
    method_name = 'a.b.c.d'
    with pytest.raises(RuntimeError):
        # If not connected can not call anything
        wrapper = getattr(client, method_name)
    client.connect(endpoint)
    wrapper = getattr(client, method_name)
    assert isinstance(wrapper, AttributeWrapper)
    assert wrapper._part_names == method_name.split('.')
    assert wrapper.name == method_name
    # with pytest.raises(TimeoutError):
    #     wrapper()
    client.stop()


def test_job_executed():
    from pybidirpc.interfaces import OK, VERSION, WORK
    from pybidirpc import auth, heartbeat  # NOQA
    context = zmq.Context.instance()
    endpoint = 'ipc://{}'.format(__name__)
    peer_identity = 'server'

    def server_callback(socket, request):
        peer_id, _, version, uid, message_type, message = request
        assert _ == ''
        assert version == VERSION
        assert uid
        # check it is a real uuid
        uuid.UUID(bytes=uid)
        assert message_type == WORK
        locator, args, kw = msgpack.unpackb(message)
        assert locator == 'please.do_that_job'
        assert args == [1, 2, 3]
        assert kw == {'b': 4}
        reply = [peer_id, _, version, uid, OK, msgpack.packb(True)]
        socket.send_multipart(reply)

    thread = threading.Thread(target=make_one_server_thread,
                              args=(context, peer_identity, endpoint,
                                    server_callback))
    thread.start()
    client = make_one_client()
    client.connect(endpoint)

    result = client.please.do_that_job(1, 2, 3, b=4)
    assert result is True
    client.stop()
    thread.join()


def test_job_server_never_reply():
    from pybidirpc.interfaces import TimeoutError, VERSION, WORK
    from pybidirpc import auth, heartbeat  # NOQA
    context = zmq.Context.instance()
    endpoint = 'ipc://{}'.format(__name__)
    peer_identity = 'server'

    def server_callback(socket, request):
        peer_id, _, version, uid, message_type, message = request
        assert _ == ''
        assert version == VERSION
        assert uid
        # check it is a real uuid
        uuid.UUID(bytes=uid)
        assert message_type == WORK
        locator, args, kw = msgpack.unpackb(message)
        assert locator == 'please.do_that_job'
        assert args == [1, 2]
        assert kw == {'b': 5}

    thread = threading.Thread(target=make_one_server_thread,
                              args=(context, peer_identity, endpoint,
                                    server_callback))
    thread.start()
    client = make_one_client(timeout=.2)
    client.connect(endpoint)

    with pytest.raises(TimeoutError):
        client.please.do_that_job(1, 2, b=5)
    client.stop()
    thread.join()

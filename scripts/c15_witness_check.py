# Explicit loopback transport acceptance runner; separate from globally offline
# unit-test collection. External connections remain denied in this process.
import ipaddress
import socket
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import dotenv

dotenv.load_dotenv = lambda *a, **k: False
original_connect = socket.socket.connect
original_resolve = socket.getaddrinfo


def require_loopback(host):
    if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
        raise AssertionError("external transport denied")


def connect(sock, address):
    require_loopback(address[0])
    return original_connect(sock, address)


def resolve(host, *a, **k):
    require_loopback(host)
    return original_resolve(host, *a, **k)


socket.socket.connect = connect
socket.getaddrinfo = resolve

"""Real loopback authority transport; synthetic external-to-restore files."""
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from app.privacy_checkpoint import LocalCheckpointStore
from app.privacy_content import ContentBlocked
from app.privacy_witness import HTTPCheckpointStore, local_authority


def test_external_authority_cas_readonly_stale_and_outage(tmp_path):
    key = secrets.token_bytes(32)
    env, dataset = str(uuid4()), str(uuid4())
    reader, writer = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    store = LocalCheckpointStore(
        tmp_path / "authority.sqlite",
        tmp_path / "independent-anchor.sqlite",
        key,
        env,
        dataset,
    )
    store.initialize("a" * 64)
    operator = secrets.token_urlsafe(32)
    server = local_authority(store, reader, writer, operator_token=operator)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    client = HTTPCheckpointStore(url, writer, key, env, dataset, local_rehearsal=True)
    readonly = HTTPCheckpointStore(url, reader, key, env, dataset, local_rehearsal=True)
    try:
        with readonly.locked() as old:
            record = readonly.read(old)
            assert record["head"] == "a" * 64
            with pytest.raises(ContentBlocked):
                readonly.write(old, {**record, "sequence": 1, "head": "b" * 64})
        # Both independent coordinators read the same head. Exactly one CAS wins.
        barrier = threading.Barrier(2)

        def race(head):
            peer = HTTPCheckpointStore(
                url, writer, key, env, dataset, local_rehearsal=True
            )
            with peer.locked() as slot:
                new = {**peer.read(slot), "sequence": 1, "head": head}
                barrier.wait(timeout=5)
                try:
                    peer.write(slot, new)
                    return True
                except ContentBlocked:
                    return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(race, ["b" * 64, "c" * 64])) == [False, True]
        with pytest.raises(ContentBlocked):
            client.write(
                old, record
            )  # Restored client/checkpoint cannot roll back head.
        wrong = HTTPCheckpointStore(
            url, reader, key, str(uuid4()), dataset, local_rehearsal=True
        )
        with pytest.raises(ContentBlocked), wrong.locked():
            pass
        tampered = HTTPCheckpointStore(
            url, reader, secrets.token_bytes(32), env, dataset, local_rehearsal=True
        )
        with pytest.raises(ContentBlocked), tampered.locked():
            pass
        with pytest.raises(ContentBlocked):
            client.authorize_restore(1, str(uuid4()), str(uuid4()))
        operator_client = HTTPCheckpointStore(
            url, operator, key, env, dataset, local_rehearsal=True
        )
        operator_client.authorize_restore(1, str(uuid4()), str(uuid4()))
        with readonly.locked() as slot:
            assert readonly.read(slot)["sequence"] == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    with pytest.raises(ContentBlocked), readonly.locked():
        pass
    assert not thread.is_alive()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="c15-owned-witness-") as owned:
        test_external_authority_cas_readonly_stale_and_outage(Path(owned))
    print("loopback witness acceptance: passed; owned files/listener removed")

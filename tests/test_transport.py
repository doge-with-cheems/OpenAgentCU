import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from oacu.config import DEFAULTS, Settings
from oacu.errors import TransportError
from oacu.store import Store
from oacu.transport import send_ir, serve_forever

SAMPLE_IR = {
    "version": "1.0",
    "trace_id": "trace-1",
    "snapshot_id": 1,
    "steps": [{"op": "click", "token": "t0001", "at": 0}],
}


def fake_handler(request, store, settings):
    if request.get("type") == "ping":
        return {"ok": True, "pong": True}
    return {"ok": True, "results": [{"index": 0, "op": "click", "ok": True, "ms": 1}]}


class TransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "t.db")
        self.settings = Settings(json=True, db=Path(self.tmp.name) / "t.db",
                                 backend="fake", timeout=2.0, verbose=False, config=dict(DEFAULTS))
        self.port = 0
        self.ready = threading.Event()
        self.thread = threading.Thread(
            target=serve_forever,
            args=("127.0.0.1", 0, self.store, self.settings),
            kwargs={"handler": fake_handler, "ready": self._on_ready, "max_connections": 1},
            daemon=True,
        )

    def _on_ready(self, port: int) -> None:
        self.port = port
        self.ready.set()

    def tearDown(self) -> None:
        if self.thread.ident is not None:
            self.thread.join(timeout=3)
        self.store.close()
        self.tmp.cleanup()

    def test_send_and_receive(self) -> None:
        self.thread.start()
        self.assertTrue(self.ready.wait(3))
        results = send_ir(SAMPLE_IR, port=self.port, timeout=3)
        self.assertEqual(results[0]["op"], "click")
        self.assertTrue(results[0]["ok"])

    def test_connection_refused_message(self) -> None:
        with self.assertRaises(TransportError) as ctx:
            send_ir(SAMPLE_IR, port=1, timeout=1)
        self.assertIn("oacu serve", str(ctx.exception))

    def test_invalid_json_response(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        def respond():
            conn, _ = server.accept()
            with conn:
                conn.recv(65536)
                conn.sendall(b"not json\n")
            server.close()

        thread = threading.Thread(target=respond, daemon=True)
        thread.start()
        with self.assertRaises(TransportError) as ctx:
            send_ir(SAMPLE_IR, port=port, timeout=3)
        self.assertIn("非 JSON", str(ctx.exception))
        thread.join(timeout=3)


class ServerPingTests(unittest.TestCase):
    def test_ping_through_socket(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        store = Store(Path(tmp.name) / "p.db")
        settings = Settings(json=True, db=Path(tmp.name) / "p.db", backend="fake",
                            timeout=2.0, verbose=False, config=dict(DEFAULTS))
        port_holder = {}
        ready = threading.Event()

        def on_ready(port: int) -> None:
            port_holder["port"] = port
            ready.set()

        thread = threading.Thread(
            target=serve_forever,
            args=("127.0.0.1", 0, store, settings),
            kwargs={"handler": fake_handler, "ready": on_ready, "max_connections": 1},
            daemon=True,
        )
        thread.start()
        self.assertTrue(ready.wait(3))
        with socket.create_connection(("127.0.0.1", port_holder["port"]), timeout=3) as sock:
            sock.sendall(json.dumps({"type": "ping"}).encode() + b"\n")
            line = sock.makefile("rb").readline()
        self.assertTrue(json.loads(line)["pong"])
        thread.join(timeout=3)
        store.close()
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()

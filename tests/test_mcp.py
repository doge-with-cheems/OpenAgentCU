import json
import os
import tempfile
import unittest
from pathlib import Path

from oacu.config import DEFAULTS, Settings
from oacu.mcp.protocol import PROTOCOL_VERSION, handle, tool_definitions
from oacu.store import Store

FIXTURE = str(Path(__file__).resolve().parents[1] / "tools" / "fixture_desktop.json")


def text_of(reply: dict) -> str:
    return reply["result"]["content"][0]["text"]


def payload_of(reply: dict) -> dict:
    return json.loads(text_of(reply))


class MCPProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("OACU_HOME")
        os.environ["OACU_HOME"] = self.tmp.name
        self.store = Store(Path(self.tmp.name) / "mcp.db")
        self.settings = Settings(json=True, db=Path(self.tmp.name) / "mcp.db",
                                 backend="fake", timeout=5.0, verbose=False, config=dict(DEFAULTS))

    def tearDown(self) -> None:
        self.store.close()
        if self.old_home is None:
            os.environ.pop("OACU_HOME", None)
        else:
            os.environ["OACU_HOME"] = self.old_home
        self.tmp.cleanup()

    def test_initialize(self) -> None:
        reply = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"}, self.store, self.settings)
        self.assertEqual(reply["result"]["protocolVersion"], PROTOCOL_VERSION)
        self.assertEqual(reply["result"]["serverInfo"]["name"], "opencu")
        self.assertIn("tools", reply["result"]["capabilities"])

    def test_tools_list(self) -> None:
        reply = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, self.store, self.settings)
        tools = reply["result"]["tools"]
        names = [t["name"] for t in tools]
        for expected in ("desktop_scan", "desktop_tokens", "desktop_find", "desktop_summary",
                         "launch_app", "open_url", "search_web", "win_run",
                         "computer_act", "mouse_move", "mouse_click", "mouse_drag", "mouse_scroll",
                         "key_press", "key_hold", "type_text", "screen_info", "mouse_position"):
            self.assertIn(expected, names)
        self.assertEqual(len(tool_definitions()), 18)
        self.assertTrue(all("inputSchema" in tool for tool in tools))

    def test_screen_info_tool(self) -> None:
        reply = handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                        "params": {"name": "screen_info", "arguments": {}}}, self.store, self.settings)
        payload = payload_of(reply)
        self.assertTrue(payload["ok"])
        self.assertGreater(payload["width"], 0)
        self.assertGreater(payload["height"], 0)

    def test_mouse_position_tool(self) -> None:
        reply = handle({"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                        "params": {"name": "mouse_position", "arguments": {}}}, self.store, self.settings)
        payload = payload_of(reply)
        self.assertTrue(payload["ok"])
        self.assertIsInstance(payload["x"], int)

    def test_notification_has_no_reply(self) -> None:
        reply = handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, self.store, self.settings)
        self.assertIsNone(reply)

    def test_unknown_tool_is_error_result(self) -> None:
        reply = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "nope", "arguments": {}}}, self.store, self.settings)
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("unknown tool", reply["result"]["content"][0]["text"])

    def test_desktop_tokens_without_snapshot(self) -> None:
        reply = handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                        "params": {"name": "desktop_tokens", "arguments": {}}}, self.store, self.settings)
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("no snapshot", text_of(reply))

    def test_computer_act_dry_run(self) -> None:
        reply = handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                        "params": {"name": "computer_act",
                                   "arguments": {"instruction": "点击七", "dry_run": True,
                                                 "fixture": FIXTURE}}},
                       self.store, self.settings)
        self.assertFalse(reply["result"]["isError"])
        payload = payload_of(reply)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["tokens"], 7)

    def test_desktop_scan_is_compact(self) -> None:
        reply = handle({"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                        "params": {"name": "desktop_scan", "arguments": {"fixture": FIXTURE}}},
                       self.store, self.settings)
        text = text_of(reply)
        self.assertIn("7 tokens", text)
        self.assertIn("shown: 7/7", text)
        self.assertIn("fields: id|name|type|x|y|w|h|win", text)
        self.assertEqual(len(text.splitlines()), 3 + 7)
        self.assertNotIn("structuredContent", reply["result"])
        self.assertNotIn("text:", text)

    def test_desktop_tokens_paging(self) -> None:
        handle({"jsonrpc": "2.0", "id": 11, "method": "tools/call",
                "params": {"name": "desktop_scan", "arguments": {"fixture": FIXTURE}}},
               self.store, self.settings)
        reply = handle({"jsonrpc": "2.0", "id": 12, "method": "tools/call",
                        "params": {"name": "desktop_tokens",
                                   "arguments": {"limit": 2, "offset": 1}}},
                       self.store, self.settings)
        text = text_of(reply)
        self.assertIn("2/7 tokens", text)
        self.assertEqual(len(text.splitlines()), 2 + 2)

    def test_desktop_find(self) -> None:
        handle({"jsonrpc": "2.0", "id": 13, "method": "tools/call",
                "params": {"name": "desktop_scan", "arguments": {"fixture": FIXTURE}}},
               self.store, self.settings)
        reply = handle({"jsonrpc": "2.0", "id": 14, "method": "tools/call",
                        "params": {"name": "desktop_find", "arguments": {"query": "七"}}},
                       self.store, self.settings)
        text = text_of(reply)
        self.assertIn("matches for", text)
        self.assertIn("七", text)

    def test_desktop_summary(self) -> None:
        handle({"jsonrpc": "2.0", "id": 15, "method": "tools/call",
                "params": {"name": "desktop_scan", "arguments": {"fixture": FIXTURE}}},
               self.store, self.settings)
        reply = handle({"jsonrpc": "2.0", "id": 16, "method": "tools/call",
                        "params": {"name": "desktop_summary", "arguments": {}}},
                       self.store, self.settings)
        text = text_of(reply)
        self.assertIn("7 tokens", text)
        self.assertIn("windows:", text)

    def test_computer_act_compact_result(self) -> None:
        reply = handle({"jsonrpc": "2.0", "id": 17, "method": "tools/call",
                        "params": {"name": "computer_act",
                                   "arguments": {"instruction": "等待 1 毫秒",
                                                 "fixture": FIXTURE}}},
                       self.store, self.settings)
        payload = payload_of(reply)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["steps"], 1)
        self.assertEqual(len(payload["results"][0]), 5)
        self.assertNotIn("plan", payload)
        self.assertNotIn("ir", payload)
        self.assertNotIn("instruction", payload)

    def test_method_not_found(self) -> None:
        reply = handle({"jsonrpc": "2.0", "id": 6, "method": "nope/nope"}, self.store, self.settings)
        self.assertEqual(reply["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()

"""可選的 browser checks：使用本機已安裝的 Playwright／Chromium。"""

import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest

from test_export_codex_conversations import exporter

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(sync_playwright, "本機未安裝可選 Playwright")
class AnnotationPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.root = Path(cls.directory.name)
        page = Path(__file__).resolve().parents[1] / "tools" / "annotation" / "index.html"
        shutil.copy2(page, cls.root / "index.html")
        cls.data = {
            "schema_version": 1, "dataset_id": "synthetic", "generated_at": "2026-10-25T01:00:00Z",
            "requested_turns": 1000, "available_turns": 8, "stats": {},
            "turns": [{"id": f"t{i}", "session_id": "session-a", "turn_id": str(i), "timestamp": f"2026-10-25T01:{i:02}:00Z", "messages": [
                {"id": f"u{i}", "role": "user", "timestamp": f"2026-10-25T01:{i:02}:00Z", "text": f"topic-{i} 請記住這個偏好", "image_count": 0},
                {"id": f"a{i}", "role": "assistant", "phase": "final_answer", "timestamp": f"2026-10-25T01:{i:02}:01Z", "text": "<img src=x onerror=window.injected=true>" + "原文" * (1200 if i == 7 else 1), "image_count": 0},
            ]} for i in range(8)],
        }
        exporter.write_bundle(cls.data, cls.root / "conversations.js")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(cls.root)))
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.server.shutdown)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        try:
            cls.browser = cls.playwright.chromium.launch()
        except Exception as error:
            raise unittest.SkipTest(f"Chromium 無法啟動：{error}")
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.context = self.browser.new_context(accept_downloads=True)
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.goto(self.url)

    def pick(self, identifier, label):
        self.page.locator(f"[data-message-id={identifier}] input[value='{label}']").check()

    def download(self):
        with self.page.expect_download() as info:
            self.page.locator("#download").click()
        return json.loads(Path(info.value.path()).read_text())

    def test_selection_reload_and_clear(self):
        self.pick("u7", 1)
        self.pick("a7", 2)
        self.pick("u6", 3)
        self.page.reload()
        for identifier, label in [("u7", 1), ("a7", 2), ("u6", 3)]:
            self.assertTrue(self.page.locator(f"[data-message-id={identifier}] input[value='{label}']").is_checked())
        self.assertEqual(self.page.locator("#reviewed-count").inner_text(), "3")
        stored = self.page.evaluate("localStorage.getItem(STORAGE_KEY)")
        self.assertNotIn("topic-7", stored)
        self.page.locator("[data-message-id=u7] .clear").click()
        self.assertEqual(self.page.locator("#reviewed-count").inner_text(), "2")
        self.assertEqual(self.errors, [])

    def test_download_keeps_all_messages_and_nulls_despite_filters(self):
        self.pick("u7", 1)
        self.pick("a7", 2)
        self.page.locator("#filter").select_option("1")
        self.page.locator("#role").select_option("user")
        output = self.download()
        self.assertEqual(output["turn_count"], 8)
        self.assertEqual(output["message_count"], 16)
        self.assertEqual(output["reviewed_count"], 2)
        self.assertEqual(output["unreviewed_count"], 14)
        latest = output["turns"][-1]["messages"]
        self.assertEqual(latest[0]["label"], 1)
        self.assertEqual(latest[1]["label"], 2)
        self.assertEqual(latest[1]["text"], self.data["turns"][-1]["messages"][1]["text"])
        self.assertIsNone(output["turns"][0]["messages"][0]["label"])
        self.assertEqual(output["label_schema"], {"1": "confirmed", "2": "candidate", "3": "skip"})

    def test_search_role_filters_pagination_and_literal_html(self):
        self.assertEqual(self.page.locator(".turn").count(), 6)
        self.page.locator(".next").first.click()
        self.assertEqual(self.page.locator(".turn").count(), 2)
        self.page.locator(".previous").first.click()
        self.page.locator("#search").fill("topic-5")
        self.assertEqual(self.page.locator(".message").count(), 1)
        self.page.locator("#search").fill("")
        self.page.locator("#role").select_option("assistant")
        self.assertEqual(self.page.locator(".message[data-role=user]").count(), 0)
        self.assertIn("<img", self.page.locator(".message-text").first.inner_text())
        self.assertEqual(self.page.locator(".message img").count(), 0)
        self.assertIsNone(self.page.evaluate("window.injected"))
        self.assertIn("全部 8 個可用", self.page.locator("#notice").inner_text())
        self.assertEqual(self.errors, [])

    def test_storage_failure_does_not_drop_in_memory_labels(self):
        self.page.evaluate("() => { Storage.prototype.setItem = () => { throw new Error('quota'); }; }")
        self.pick("u7", 1)
        self.pick("a7", 2)
        self.pick("u6", 3)
        self.assertIn("請下載 JSON", self.page.locator("#save-status").inner_text())
        self.assertEqual(self.download()["reviewed_count"], 3)

    def test_corrupt_storage_is_not_overwritten(self):
        self.page.evaluate("localStorage.setItem(STORAGE_KEY, '{broken')")
        self.page.reload()
        self.pick("u7", 1)
        self.assertEqual(self.page.evaluate("localStorage.getItem(STORAGE_KEY)"), "{broken")
        self.assertEqual(self.download()["reviewed_count"], 1)
        self.assertIn("未覆寫", self.page.locator("#notice").inner_text())

    def test_mobile_layout_has_no_horizontal_overflow(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.assertTrue(self.page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        self.pick("u7", 1)
        self.assertEqual(self.page.locator("#reviewed-count").inner_text(), "1")


if __name__ == "__main__":
    unittest.main()

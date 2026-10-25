import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_codex_conversations.py"
spec = importlib.util.spec_from_file_location("export_codex", SCRIPT)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def event(kind, payload, timestamp="2026-10-25T01:00:00Z"):
    return {"type": kind, "payload": payload, "timestamp": timestamp}


def meta(session="root", source="vscode"):
    return event("session_meta", {"id": session, "source": source})


def start(turn):
    return event("event_msg", {"type": "task_started", "turn_id": turn})


def message(role, text, identifier, **extra):
    return event("response_item", {"type": "message", "role": role, "id": identifier, "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}], **extra})


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def log(self, name, records):
        path = self.root / name
        path.write_text("\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8")
        return path

    def test_groups_visible_messages_and_excludes_internals(self):
        self.log("root.jsonl", [meta(), start("t1"),
            message("developer", "secret config", "d"),
            message("user", "<environment_context>hidden</environment_context>", "env"),
            message("user", "請用繁中", "u1"),
            event("response_item", {"type": "reasoning", "summary": "private"}),
            event("response_item", {"type": "function_call_output", "output": "secret"}),
            message("assistant", "處理中", "a1", phase="commentary"),
            message("assistant", "完成", "a2", phase="final_answer"),
            start("t2"), message("user", "下一個", "u2")])
        data = exporter.export_dataset(self.root)
        self.assertEqual(data["turn_count"], 2)
        self.assertEqual([m["text"] for m in data["turns"][0]["messages"]], ["請用繁中", "處理中", "完成"])

    def test_excludes_subagent_files(self):
        self.log("child.jsonl", [meta("child", {"subagent": {"thread_spawn": {}}}), start("t"), message("user", "internal ticket", "u")])
        data = exporter.export_dataset(self.root)
        self.assertEqual(data["turn_count"], 0)
        self.assertEqual(data["stats"]["subagent_files"], 1)

    def test_preserves_text_after_environment_and_marks_images(self):
        item = message("user", "<environment_context>x</environment_context>\n真正提問", "u")
        item["payload"]["content"].append({"type": "input_image", "image_url": "data:image/png;base64,PRIVATE"})
        self.log("images.jsonl", [meta(), start("t"), item])
        result = exporter.export_dataset(self.root)["turns"][0]["messages"][0]
        self.assertEqual(result["text"], "真正提問")
        self.assertEqual(result["image_count"], 1)
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_filters_instruction_block_without_losing_other_blocks(self):
        item = message("user", "# AGENTS.md instructions\n<INSTRUCTIONS>config</INSTRUCTIONS>", "u")
        item["payload"]["content"].append({"type": "input_text", "text": "真的問題"})
        self.log("instructions.jsonl", [meta(), start("t"), item])
        result = exporter.export_dataset(self.root)["turns"][0]["messages"][0]
        self.assertEqual(result["text"], "真的問題")

    def test_replayed_ids_do_not_duplicate_and_keep_latest_content(self):
        self.log("replay.jsonl", [meta(), start("t1"), message("user", "問", "u"), message("assistant", "部分", "a"), start("t2"), message("assistant", "完整回覆", "a"), message("user", "又問", "u2")])
        data = exporter.export_dataset(self.root)
        self.assertEqual(data["message_count"], 3)
        self.assertEqual(data["turns"][0]["messages"][1]["text"], "完整回覆")

    def test_limits_by_timestamp_and_keeps_stable_message_ids(self):
        older = message("user", "舊", "u")
        older["timestamp"] = "2026-10-24T01:00:00Z"
        self.log("z-old.jsonl", [meta("old"), start("t"), older])
        self.log("a-new.jsonl", [meta("new"), start("t"), message("user", "新", "u")])
        all_data = exporter.export_dataset(self.root)
        recent = exporter.export_dataset(self.root, 1)
        self.assertEqual(recent["available_turns"], 2)
        self.assertEqual(recent["turns"][0]["session_id"], "new")
        self.assertEqual(recent["turns"][0]["messages"][0]["id"], all_data["turns"][-1]["messages"][0]["id"])

    def test_legacy_messages_create_individual_turns(self):
        self.log("legacy.jsonl", [meta(), message("user", "一", "u1"), message("assistant", "答", "a"), message("user", "二", "u2")])
        self.assertEqual(exporter.export_dataset(self.root)["turn_count"], 2)

    def test_malformed_tail_reported_and_orphan_assistant_excluded(self):
        path = self.log("partial.jsonl", [meta(), message("assistant", "orphan", "a"), start("t"), message("user", "保留", "u")])
        with path.open("a") as target:
            target.write("{unfinished")
        result = exporter.export_dataset(self.root)
        self.assertEqual(result["message_count"], 1)
        self.assertEqual(result["stats"]["malformed_lines"], 1)

    def test_bundle_escapes_html_but_preserves_full_text(self):
        text = "</script><script>alert(1)</script>\n" + "資料" * 3000
        self.log("text.jsonl", [meta(), start("t"), message("user", text, "u")])
        data = exporter.export_dataset(self.root)
        bundle = self.root / "bundle.js"
        exporter.write_bundle(data, bundle)
        content = bundle.read_text()
        self.assertNotIn("</script>", content)
        decoded = json.loads(content.removeprefix("window.CODEX_ANNOTATION_DATA = ").removesuffix(";\n"))
        self.assertEqual(decoded["turns"][0]["messages"][0]["text"], text)


if __name__ == "__main__":
    unittest.main()

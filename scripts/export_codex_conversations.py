"""匯出本機 Codex 主對話，供靜態頁標註；不匯出工具或 reasoning。"""

import argparse
import hashlib
import json
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
TEXT_TYPES = {"input_text", "output_text", "text"}
IMAGE_TYPES = {"input_image", "image"}
WRAPPERS = ("environment_context", "turn_aborted", "user_instructions")


def visible_text(payload):
    parts = []
    images = 0
    for block in payload.get("content", []):
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind in IMAGE_TYPES:
            images += 1
        if kind not in TEXT_TYPES:
            continue
        text = block.get("text", "").strip()
        if payload.get("role") == "user":
            if text.startswith("# AGENTS.md instructions"):
                text = text.split("</INSTRUCTIONS>", 1)[-1].strip() if "</INSTRUCTIONS>" in text else ""
            for tag in WRAPPERS:
                text = re.sub(rf"\A\s*<{tag}>.*?</{tag}>\s*", "", text, flags=re.S).strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts), images


def time_key(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return 0


def parse_session(path, stats):
    meta = None
    turns = {}
    seen_messages = {}
    active_turn = None
    has_turn_events = False
    source_name = path.name

    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                stats["malformed_lines"] += 1
                continue
            payload = record.get("payload", {})
            if not isinstance(payload, dict):
                continue
            if record.get("type") == "session_meta":
                if meta is None:
                    meta = payload
                    origin = meta.get("source")
                    if isinstance(origin, dict) and "subagent" in origin:
                        stats["subagent_files"] += 1
                        return []
                    stats["root_session_files"] += 1
                continue
            if meta is None:
                continue

            if record.get("type") in {"event_msg", "turn_context"}:
                if payload.get("type") == "task_started":
                    active_turn = payload.get("turn_id") or payload.get("root_turn_id")
                    has_turn_events = True
                elif record.get("type") == "turn_context" and payload.get("turn_id"):
                    active_turn = payload["turn_id"]
                continue
            if record.get("type") != "response_item" or payload.get("type") != "message":
                continue
            role = payload.get("role")
            if role not in {"user", "assistant"}:
                continue
            phase = payload.get("phase")
            if role == "assistant" and phase not in {None, "final", "final_answer", "commentary"}:
                continue
            text, image_count = visible_text(payload)
            if not text and not image_count:
                continue

            session_id = str(meta.get("session_id") or meta.get("id") or path.stem)
            timestamp = record.get("timestamp") or meta.get("timestamp", "")
            native_id = payload.get("id") or f"{line_number}:{timestamp}:{role}"
            message_id = f"{session_id}:{native_id}"
            if message_id in seen_messages:
                # 同一 ID 的 replay 不多算一則；保留最後完整版本。
                seen_messages[message_id].update(text=text, image_count=image_count, phase=phase)
                stats["replayed_messages"] += 1
                continue
            if role == "user" and not has_turn_events:
                active_turn = f"message-{native_id}"
            if active_turn is None:
                # 無法找到 user 起點的 assistant 不自行併入下一輪。
                continue
            turn_key = f"{session_id}:{active_turn}"
            turn = turns.setdefault(turn_key, {
                "id": turn_key,
                "session_id": session_id,
                "turn_id": str(active_turn),
                "timestamp": timestamp,
                "cwd": meta.get("cwd", ""),
                "source_file": source_name,
                "messages": [],
            })
            message = {
                "id": message_id,
                "role": role,
                "phase": phase,
                "timestamp": timestamp,
                "text": text,
                "image_count": image_count,
                "source_line": line_number,
            }
            seen_messages[message_id] = message
            turn["messages"].append(message)

    if meta is None:
        stats["files_without_metadata"] += 1
    return [turn for turn in turns.values() if any(m["role"] == "user" for m in turn["messages"])]


def export_dataset(sessions_dir, limit=1000):
    if limit < 1:
        raise ValueError("limit 必須大於 0")
    if not sessions_dir.is_dir():
        raise FileNotFoundError(f"找不到 Codex sessions：{sessions_dir}")
    stats = Counter()
    turns = []
    for path in sorted(sessions_dir.rglob("*.jsonl")):
        stats["session_files"] += 1
        turns.extend(parse_session(path, stats))
    # 依 user 回合開始時間選最近紀錄，不以檔案 mtime 判斷。
    turns.sort(key=lambda turn: (time_key(turn["timestamp"]), turn["id"]))
    unique = {turn["id"]: turn for turn in turns}
    available = len(unique)
    selected = list(unique.values())[-limit:]
    fingerprint = hashlib.sha256(json.dumps(selected, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    return {
        "schema_version": 1,
        "dataset_id": fingerprint,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requested_turns": limit,
        "available_turns": available,
        "turn_count": len(selected),
        "message_count": sum(len(t["messages"]) for t in selected),
        "session_count": len({t["session_id"] for t in selected}),
        "stats": dict(stats),
        "turns": selected,
    }


def write_bundle(dataset, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(dataset, ensure_ascii=False, separators=(",", ":"))
    for char, escaped in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"), ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        encoded = encoded.replace(char, escaped)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, prefix=".codex-export-", delete=False) as target:
        target.write("window.CODEX_ANNOTATION_DATA = " + encoded + ";\n")
        temporary = Path(target.name)
    temporary.chmod(0o600)
    temporary.replace(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions-dir", type=Path, default=Path.home() / ".codex" / "sessions")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=ROOT / "tools" / "annotation" / "conversations.js")
    args = parser.parse_args()
    try:
        dataset = export_dataset(args.sessions_dir, args.limit)
        write_bundle(dataset, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f"匯出失敗：{error}\n")
    print(f"已匯出 {dataset['turn_count']}／{dataset['available_turns']} 回合、{dataset['message_count']} 則訊息、{dataset['session_count']} 個 sessions。")
    print(f"本機資料：{args.output}")
    print(f"略過 subagent files：{dataset['stats'].get('subagent_files', 0)}；不完整紀錄：{dataset['stats'].get('malformed_lines', 0)}。")


if __name__ == "__main__":
    main()

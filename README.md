# Personal Memory MCP

Codex 與 Hermes 共用、以 `owner_id` 隔離的個人記憶服務。

## MVP 資料模型

第一版只有兩個 collection：

- `personal_memories`：已確認、可直接影響 Agent 行為的長期偏好、目標、習慣與約束。
- `personal_information`：關於 owner 的背景與原始資訊，供檢索使用；不會自動成為偏好或指令。

`RAG` 是檢索機制，不是第三張資料表。

## 文件

- [專案結構](docs/structure.md)

## Port 配置

| 元件 | 位址 | 狀態 | 用途 |
|---|---:|---|---|
| `laya-serve` | `127.0.0.1:8000` | 目前 smoke test | 本機 Laya HTTP endpoint |
| Personal Memory MCP | 無 port（`stdio`） | MVP 預設 | MCP host 直接啟動本機 process |
| Personal Memory MCP | `127.0.0.1:8001` | 未來選項 | 供 Codex + Hermes 共用的 Streamable HTTP endpoint |
| PostgreSQL + pgvector | `127.0.0.1:5432` | 已建立 | `personal_memory_mcp`；`DATABASE_URL` 在 `.env` |

預設不要暴露到 LAN。直接 import Laya 時沒有 Laya port。

## 本機 Laya smoke test

確認 Python 環境：

```zsh
.venv/bin/python -I -c "import mcp, laya; print('environment ready')"
```

啟動 Laya test server：

```zsh
LAYA_HOST=127.0.0.1 \
LAYA_PORT=8000 \
LAYA_MODELS=multilingual \
LAYA_PRELOAD=1 \
.venv/bin/laya-serve
```

這只驗證 runtime；進 write path 前仍須 fixtures／eval。

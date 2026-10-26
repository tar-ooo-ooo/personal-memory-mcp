# Personal Memory MCP

Codex 與 Hermes 共用、以 `owner_id` 隔離的個人記憶服務。

## MVP 資料模型

第一版只有兩個 collection：

- `personal_memories`：已確認、可直接影響 Agent 行為的長期偏好、目標、習慣與約束。
- `personal_information`：關於 owner 的背景與原始資訊，供檢索使用；不會自動成為偏好或指令。

`RAG` 是檢索機制，不是第三張資料表。

## 文件

- [專案結構](docs/structure.md)

## 對話標註

用 VS Code 開啟 `tools/annotation/index.html`，右鍵 **Open with Live Server**。
每則提問／回覆選 `1 confirmed`、`2 candidate` 或 `3 skip`，自動存入 localStorage，再下載 JSON。

| 項目 | 規則 |
|---|---|
| 對話來源 | `~/.codex/sessions` 的最近 1,000 個主對話回合；不足就載入實際數量 |
| 匯出內容 | user／assistant 可見文字與圖片標記；不匯出工具、reasoning 或 subagent |
| 私有資料 | `tools/annotation/conversations.js` 與 `codex-labels-*.json` 已忽略，不 commit |
| 標註進度 | 綁定目前瀏覽器與網址；重新匯出以穩定 message ID 保留既有標註 |
| JSON | 包含完整原文、角色、session／turn ID、標籤與時間；未標註為 `null` |
| 匯入標註 | 可匯入先前下載的 JSON；按 message ID 合併，保留較新標註與未涵蓋的項目 |
| 模型訓練 | 本頁只做訊息標註；訓練時仍須按 session 分組，寫入內容／目標表可後續補標 |
| 測試 | `python3 -m unittest discover -s tests -v`；browser checks 使用已安裝的 Playwright，未安裝則略過 |

只有要更新對話快照時才執行：

```zsh
python3 scripts/export_codex_conversations.py --limit 1000
```

固定用同一個 Live Server 網址標註；不同 port 不共用 localStorage。也可直接開 HTML。

## Cloud Run 標註頁

[開啟標註頁](https://personal-memory-annotation-355216536623.asia-east1.run.app)。換網址或裝置時，先下載舊標註 JSON，再到新頁面匯入。

| 項目 | 設定 |
|---|---|
| Cloud Run | `skill-ai-474905`／`asia-east1`／`personal-memory-annotation` |
| 範圍 | 公開靜態 HTML＋對話快照，取得網址的人可讀原文；標註仍只存在瀏覽器 |
| Dockerfile | `tools/annotation/Dockerfile.finetune-test`，只用於標註測試頁 |
| Build 設定 | `tools/annotation/cloudbuild.finetune-test.yaml`，明確指定 Dockerfile 名稱 |
| 上傳範圍 | `.gcloudignore` 白名單；不包含 `.env` 或其他 repo 檔案 |

更新對話快照後，從 repo 根目錄重新部署：

```zsh
gcloud builds submit tools/annotation \
  --config tools/annotation/cloudbuild.finetune-test.yaml \
  --project skill-ai-474905 --region asia-east1

gcloud run deploy personal-memory-annotation \
  --image asia-east1-docker.pkg.dev/skill-ai-474905/cloud-run-source-deploy/personal-memory-annotation \
  --project skill-ai-474905 --region asia-east1 \
  --service-account personal-memory-annotation@skill-ai-474905.iam.gserviceaccount.com \
  --allow-unauthenticated --port 8080 \
  --cpu 1 --memory 128Mi --min-instances 0 --max-instances 1
```

## Port 配置

| 元件 | 位址 | 狀態 | 用途 |
|---|---:|---|---|
| `laya-serve` | `127.0.0.1:8000` | 目前 smoke test | 本機 Laya HTTP endpoint |
| Personal Memory MCP | 無 port（`stdio`） | MVP 預設 | MCP host 直接啟動本機 process |
| Personal Memory MCP | `127.0.0.1:8001` | 未來選項 | 供 Codex + Hermes 共用的 Streamable HTTP endpoint |
| PostgreSQL + pgvector | `127.0.0.1:5432` | 已建立 | `personal_memory_mcp`；`DATABASE_URL` 在 `.env` |
| 對話標註頁 | 依 Live Server 網址 | 本機靜態頁 | 開啟 `tools/annotation/index.html` |

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

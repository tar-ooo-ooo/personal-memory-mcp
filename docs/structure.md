# 專案結構

只列出應 version control 的檔案；`.venv/`、`.vscode/` 與 `.env` 不在其中。

```text
personal-memory-mcp/
├── AGENTS.md
├── README.md
├── .gitignore
├── docs/
│   └── structure.md
├── scripts/
│   └── export_codex_conversations.py  # 本機對話匯出
├── tests/
│   ├── test_annotation_page.py       # 可選 Playwright browser checks
│   └── test_export_codex_conversations.py
└── tools/
    └── annotation/
        ├── .dockerignore
        ├── .gcloudignore
        ├── Dockerfile.finetune-test  # 標註測試頁專用
        ├── cloudbuild.finetune-test.yaml
        └── index.html               # 標註頁；conversations.js 不 commit
```

# 專案指示

## 文件

- 文件使用繁中，以 Ponytail 的簡潔口吻撰寫。
- code、path、table name、protocol name 與 endpoint name 保持英文。
- 優先用短 tree、table 或 command，避免多餘解釋。
- 只記錄現況；未來決策要明確標註，不虛構尚不存在的檔案。

## Commit

- 格式固定為 `<type>(<module>): <summary>`。
- `<module>` 使用受影響的英文模組名稱，例如 `Laya`、`MemoryMCP`、`Router`、`Storage`、`Docs`。
- 一個 commit 只放一個可說清楚的變更。
- 例：`feat(Laya): add local smoke test`

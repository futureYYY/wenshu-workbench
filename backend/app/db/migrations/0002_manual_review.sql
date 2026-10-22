-- 0002：人工复核（01 RES-06、RES-11；03 第 3 节 job_items 的“人工校对”字段、第 8 节迁移）
-- manual_summary：人工修改后的摘要主旨，NULL 表示没有修改（要点保持模型输出）
-- manual_at：最近一次人工修正（意图或摘要）的时间；没有修正时为 NULL
ALTER TABLE job_items ADD COLUMN manual_summary TEXT;
ALTER TABLE job_items ADD COLUMN manual_at TEXT;

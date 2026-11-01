# 记忆框架：自测结果与横向对比

> 2026-10-31 · 对象：`neuron_memory`（本项目）vs Mem0 / Zep·Graphiti / Letta(MemGPT) / LangMem

## 一、自测结果

### 1. 功能自测（19/19 通过）

`python -m scripts.selftest` 覆盖：

- 写入/召回/去重合并
- 否定冲突 → supersede → 召回排除旧条 → restore 回滚
- 自检索冷却、用户提及不受限、长期层晋升
- 衰减基准（最近访问不降、长期未访问降）
- 合并后 embedding 重算
- 桥接幂等（重复导入 0 新增）
- 空文本报错、空库召回、缓存冷热一致
- 旧库 schema 自动迁移（**测试中发现并修复了一个真 bug**：旧库建索引早于加列，导致迁移失败）

### 2. 检索评测（自建 20 条改写查询）

| 后端 | hit@1 | hit@3 | MRR@5 |
|---|---|---|---|
| hash 字符向量（兜底） | 0.35 | 0.55 | 0.466 |
| fastembed bge-small-zh-v1.5 | 0.55 | 0.75 | 0.653 |

### 3. 性能（3000 条记忆）

- 插入 0.6s；recall warm ≈123ms、cold ≈834ms
- numpy 向量化 + 按 `updated_at` 失效的向量缓存 + SQL 索引

## 二、横向对比

| 维度 | 本项目 neuron_memory | Mem0 | Zep / Graphiti | Letta (MemGPT) | LangMem |
|---|---|---|---|---|---|
| 定位 | 自用原子记忆库 | 记忆层 SDK/平台 | 时序知识图谱框架 | 有状态 agent 运行时 | 记忆工具库 |
| 记忆结构 | 原子笔记 + 关联图 | user/session/agent 分层记忆 | 实体-关系-事实（带有效期）+ episode 溯源 | 核心记忆块 + 回忆/归档存储 | 任意 store 中的键值记忆 |
| 写入方式 | 规则 + 嵌入；**不调用 LLM** | LLM 单次 ADD-only 抽取 + 实体链接 | LLM 抽取成图（结构化输出） | agent 自编辑记忆工具 | LLM 热路径工具 / 后台管理器 |
| 检索 | 语义 + 字面 + S/freq + 图扩散 | 语义 + BM25 + 实体，时间推理 | 语义 + BM25 + 图遍历 | 检索工具调用 | 语义搜索 + 工具 |
| 遗忘/更新 | 双因子衰减、长期层、supersede、归档可恢复 | 新算法只追加不覆盖 | 事实失效留痕（双时序） | 上下文淘汰 | 后台合并/更新 |
| 外部依赖 | 无（可选 fastembed） | LLM + 向量库 | LLM + Neo4j/FalkorDB 等 | LLM | LLM + LangGraph store |
| 评测 | 自建 20 条（hit@1 0.55） | LoCoMo 92.5 / LongMemEval 94.4 | 论文（arXiv 2501.13956） | 论文（MemGPT） | 文档示例 |
| 集成 | CLI | SDK / 服务 / MCP | MCP/REST 参考实现 | App Server / channels | LangGraph |
| 许可 | 自用 | Apache-2.0 | Apache-2.0（Graphiti）+ 商业 Zep | 开源 | 开源 |

## 三、我们在哪

**优势（相对大佬）**

1. **确定性、可审计**：写入不依赖 LLM，每次写入的原文和信号都进 `raw_events`，冲突覆盖可追溯、可回滚。
2. **零外部依赖、单文件**：SQLite 一库即记忆，删文件夹即清空；断网可用。
3. **写入零成本**：不需要 API key，也不怕抽取模型抖动。
4. **遗忘机制是显式的**：双因子衰减 + 长期层 + 保底，不像多数框架只做「检索最近」或「全量保留」。

**差距（大佬强的地方）**

1. **没有标准评测**：Mem0 用 LoCoMo/LongMemEval，我们只有 20 条自建查询，数字不可比。
2. **不会自己从对话里抽记忆**：我们靠手写 `remember` 或 bridge 导入；Mem0/Graphiti/LangMem 都是 LLM 自动抽取。
3. **没有时序有效期窗口**：Graphiti 每条事实带 `valid_from/valid_to`，我们只有「被取代」标记，不能回答「去年这时候是什么情况」。
4. **没有 MCP/HTTP 服务**：集成只能走 CLI。
5. **没有多租户/多 agent 隔离**。

## 四、值得抄的 3 个设计

1. **ADD-only 抽取**（Mem0 新算法）：只追加不覆盖，历史全部保留——我们已有 supersede，但可以再放宽「覆盖」的判定。
2. **双时序事实**（Graphiti）：给笔记加 `valid_from/valid_to`，支持「历史上某个时刻的真相」。
3. **MCP 服务**（Graphiti/Mem0 都有参考实现）：挂一个 MCP server，任何 agent 都能直连，不必手动调 CLI。

## 五、参考

- Mem0 README / 基准：https://github.com/mem0ai/mem0
- Graphiti README（时序上下文图）：https://github.com/getzep/graphiti
- Zep 论文：https://arxiv.org/abs/2501.13956
- Letta / MemGPT：https://github.com/letta-ai/letta
- LangMem：https://github.com/langchain-ai/langmem
- Mem0 论文：https://arxiv.org/abs/2504.19413

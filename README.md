# neuron-memory · AI 神经元记忆框架（M1 原型）

自用 agent 记忆层：`remember / recall / forget / consolidate` 四个动词。
工程骨架 + 神经元隐喻（突触=边权、扩散激活=图检索、遗忘=衰减、巩固=摘要合并）。

## 位置与删除

- 整个框架（代码 + 依赖 + 模型 + 数据）都在这个文件夹：`D:\DeepSeek harness工作区\AI神经元记忆框架`。
- 不想用了：直接删掉这个文件夹即可，彻底清除、不留残留。
- 想换位置：整个文件夹剪切到别处也能跑（路径全相对）。

## 两种运行方式

- **真向量（推荐）**：项目内 `.venv` 已装好 fastembed + `BAAI/bge-small-zh-v1.5`，模型缓存在 `data/models`。
- **轻量兜底**：DSH 自带 Python 没装 fastembed，会自动回落到哈希字符向量，零依赖也能跑。

```powershell
cd "D:\DeepSeek harness工作区\AI神经元记忆框架"

# 真向量
& ".venv\Scripts\python.exe" -m neuron_memory recall "老大喝什么"

# 轻量（自带 python）
$py = "C:\Users\Lenovo\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py -m neuron_memory recall "老大喝什么"
```

模型下载被墙时设 `$env:HF_ENDPOINT = "https://hf-mirror.com"` 再跑。

## 日常用法

```powershell
& ".venv\Scripts\python.exe" -m neuron_memory remember "老大周五要交底座标注报告" --type todo --importance 0.9
& ".venv\Scripts\python.exe" -m neuron_memory recall "标注报告"
& ".venv\Scripts\python.exe" -m neuron_memory recall "标注报告" --as-of 2026-03-01
& ".venv\Scripts\python.exe" -m neuron_memory mention --id 3 --source self   # 自检索 +0.4
& ".venv\Scripts\python.exe" -m neuron_memory rehearse                      # 巩固复习 +0.5
& ".venv\Scripts\python.exe" -m neuron_memory history --id 3                # 看原始写入记录
& ".venv\Scripts\python.exe" -m neuron_memory bridge --dry-run              # 只读桥接：导入 DSH 记忆事实
& ".venv\Scripts\python.exe" -m neuron_memory extract --file chat.txt --apply  # 从对话抽事实（规则版）
& ".venv\Scripts\python.exe" -m neuron_memory restore --id 3                # 恢复归档/被取代
& ".venv\Scripts\python.exe" -m neuron_memory forget --stale --dry-run
& ".venv\Scripts\python.exe" -m neuron_memory consolidate
& ".venv\Scripts\python.exe" -m neuron_memory backup                 # 在线备份到 <db目录>/backups/
& ".venv\Scripts\python.exe" -m neuron_memory restore-db backup.db --yes  # 覆盖前自动留安全备份
& ".venv\Scripts\python.exe" -m neuron_memory demo
```

数据库默认在项目内 `data/neuron.db`，可用 `--db <path>` 指定（demo 用 `./data/demo.db`）。所有数据都留在项目文件夹里。

**备份与恢复**

```powershell
& ".venv\Scripts\python.exe" -m neuron_memory backup --db "D:\DeepSeek harness工作区\.neuron-memory\neuron.db"
& ".venv\Scripts\python.exe" -m neuron_memory restore-db "backups\neuron-xxxxxxxx.db" --db "...\neuron.db" --yes
```

`backup` 用 SQLite 在线备份 API；`restore-db` 覆盖前会先在同目录留 `*.bak-时间戳.db`。

## 评测

`scripts/eval.py`：20 条种子记忆 + 20 条改写查询，量 hit@1 / hit@3 / MRR。

| 后端 | hit@1 | hit@3 | MRR@5 |
|---|---|---|---|
| hash-char-ngram（兜底） | 0.35 | 0.55 | 0.466 |
| fastembed bge-small-zh-v1.5 | **0.55** | **0.70** | **0.627** |

`scripts/sweep.py` 用来扫打分权重配置。`scripts/bench.py` 是检索性能基准（numpy 向量化 + 缓存 + 索引）。

**一键回归**：

```powershell
& ".venv\Scripts\python.exe" -m scripts.regress
```

跑 selftest / 脑区 / 冲突 / hash 版 eval，和 `data/regress_baseline.json` 比；低于阈值返回非零。`--update` 用当前结果刷新基线（只在确认变好时用）。加 `--locomo` 会多跑一遍 LoCoMo 2 样本子集（约 2 分钟，固定用 bge-small-en）。

### LoCoMo 标准评测（检索口径）

`scripts/locomo_eval.py` 把 LoCoMo10 的对话 turn 装进记忆，测 QA 的 evidence 是否被召回（**不调用 LLM**，不是回答准确率）：

```powershell
$env:NEURON_MODEL="BAAI/bge-small-en-v1.5"
& ".venv\Scripts\python.exe" -m scripts.locomo_eval --limit 10 --embedder fastembed --k 10
```

结果（1986 QA，2026-10-31）：hit@1 0.151、hit@3 0.276、hit@5 0.362、hit@10 **0.495**、MRR 0.243；分类：时间 0.670 / 多跳 0.567 / 单跳 0.493 / 开放域 0.375 / 对抗 0.352。
注意：这是「evidence 召回」，与 Mem0 公布的 LoCoMo 回答准确率（92.5）不可直接比较；数据在 `data/locomo10.json`。

**混合检索后**（BM25 + 实体 + 时间加权）：hit@1 **0.295**、hit@3 **0.469**、hit@5 **0.549**、hit@10 **0.635**、MRR **0.402**；分类：时间 0.726 / 单跳 0.675 / 对抗 0.608 / 多跳 0.539 / 开放域 0.385。

## 性能

- 3000 条记忆：插入 0.6s；recall warm ≈123ms、cold ≈834ms（冷启动大头是 embedding JSON 解析，下一轮可改二进制存储）
- SQL 索引：`notes(archived, superseded_by)`、`links(src)`、`links(dst)`
- 向量缓存：按 `updated_at` 失效，避免重复 JSON 解析

## 设计要点

- **存储**：SQLite。`notes`（记忆条目）+ `links`（带权关联边）。
- **嵌入**：fastembed ONNX（bge-small-zh-v1.5，512 维），查询侧单独走 query 接口；没装就回落哈希字符向量。
- **remember**：切分 → 高相似去重合并（0.92 / 兜底 0.95）→ 与近邻建边（0.45 / 兜底 0.15）→ 存储。
- **recall**：向量召回 + BM25 + 实体匹配 + 时间加权 → `score = 0.35·sim + 0.25·bm25 + 0.08·实体 + 0.10·S + 0.05·recency + 0.12·字面命中 + 0.05·时间`（S = 重要度 × 复述增益 × 时间衰减，长期层更慢）→ 从 top-3 种子沿边扩一跳（衰减 0.25）。numpy 向量化 + 向量缓存。
- **forget**：重要度按 90 天半衰期衰减，低于 0.15 且 60 天未用 → 归档（不删）。`--id` 才是硬删。
- **多尺度**：短期层 τ0=20 分钟；`n_eff` 初始 1.0，用户提及 +1.0、自检索 +0.4、巩固 +0.3、隐式 +0.1；`n_eff ≥ 3` 或重要度 ≥0.8 晋升长期层（半衰期 365 天，遗忘保底 0.1，不会被轻易归档）。即约 2 次用户提及或 5 次自检索。
- **提及来源**：用户 1.0 / 自检索 0.4（5 分钟冷却）/ 巩固 0.3 / 隐式 0.1；`recall` 返回的记忆自动记 0.4 自检索。`rehearse` 对重要记忆做一次 +0.5 巩固。
- **冲突与覆盖**：相似度 ≥0.75 且命中「否定极性 / 数字 / 星期 / 改写词（改成、改为…）」信号时，新记忆自动 `supersede` 旧记忆（旧条默认不参与检索，可 `restore` 回滚）；`raw_events` 表保留每次写入原文与信号，`history --id` 可查。
- **时序有效期**：每条记忆带 `valid_from/valid_to`；被覆盖时旧条 `valid_to` 定格，`recall --as-of <时间>` 可以按历史时点回溯「当时什么是真的」。`restore` 会清空 `valid_to`。
- **规则抽取**：`extract` 从对话文本抽候选事实（含说话人前缀剥离、问句/指令/客套过滤），`--apply` 直接入库；不依赖 LLM。
- **只读桥接**：`bridge` 从 DSH 记忆库（`~/.memory` 的 markdown 页面）抽取 bullet 事实导入本库，按文本幂等，源目录只读不写回；跳过硬编码系统文件与「相关页面」链接行。
- **consolidate**：相似度 ≥0.90 的重复条目合并（合并后重算 embedding）。

## 路线图

- M1（完成）：存储 + 检索 + 基础衰减/巩固，CLI 可用。
- 第一步优化（完成）：接真向量 bge-small-zh，评测 hit@1 0.35 → 0.55。
- 多尺度 + 自检索（完成）：短期/长期两层、提及来源权重、巩固复习（详见实验台结论）。
- M2：换更大中文模型（jina-v2-base-zh）对比、多跳扩散、LLM 重要度打分/切分。
- M3：`consolidate` 接入 LLM 摘要、挂进 DSH 当工具。

## 记忆看板（viewer/）

主框架只读看板：读 `neuron.db`，3D 展示记忆/链接/层级，附艾宾浩斯遗忘曲线对照。

```powershell
& ".venv\Scripts\python.exe" -m viewer.server --db data/neuron.db --port 8420
```

打开 `http://127.0.0.1:8420`：

- **真 3D 力导向**：球面簇心 + 斥力/弹簧，透视景深 + 远处雾化；拖拽旋转、滚轮缩放，自转默认关闭
- **星云粒子背景** + **节点呼吸光** + **连线粒子流**（动效可关）
- **焦点高亮**：点选节点后，它和直接邻居高亮并显示文本标签，其余压暗
- 搜索 + 类型过滤 + 只看长期层 + 显示全部连线；适应视角/重置
- 右侧统计 + 选中详情 + 艾宾浩斯曲线（n/τ 滑块）

看板只读（SQLite `mode=ro`），不会改动记忆库。旧版留档：`viewer/ui2d.html`（2D 星图）、`viewer/ui3d.html`（早期神经元 3D）。

**打开方式**

- 网页：`python -m viewer.server --db data/neuron.db --port 8420` → `http://127.0.0.1:8420`
- 独立窗口：双击 `viewer/launch.bat`（自动起服务 + Edge `--app` 模式，像桌面应用）
- 单文件快照：`python -m scripts.export_snapshot` → 双击 `viewer/snapshot.html`，无需服务（数据为导出时静态，不自动刷新）3D 效果参考 [3d-force-graph](https://github.com/vasturiano/3d-force-graph) 的力导向布局/轨道相机/自动巡航思路，用原生 canvas 实现。

## 重排（可选 rerank）

```powershell
python -m neuron_memory recall "多跳问题" --rerank -k 10
```

- 先混合召回 top-30，再用 cross-encoder（默认 `BAAI/bge-reranker-base`）重排取 top-k
- LoCoMo 子集实测：多跳 hit@10 **0.539 → 0.642**；混合子集 overall **0.618 → 0.691**（多跳 0.512 / 时间 0.905 / 开放域 0.462 / 单跳 0.667 / 对抗 0.690，全类别均提升）
- 代价：CPU 约 1.5–2 秒/QA；首次要下载模型，可用 `NEURON_RERANK_CACHE` 指定缓存目录
- 默认关闭；插件自带运行时没有 fastembed，`--rerank` 会提示不可用并自动回退

## 脑区与分区参数

- 映射：`preference → 情感区`、`decision/project → 前额叶`、`concept/skill → 语义区`、`tier=long → 深层记忆区`，其余 `fact/event/utterance/todo → 海马体`
- 检索：`query_regions()` 按查询线索（偏好/计划/概念/久远）给命中区加 `region_boost=0.03`，权重很轻，不改变主排序
- 衰减：`REGION_DECAY` 给时间常数乘系数——情感区 1.25、前额叶 1.10、语义区 1.05、深层区 1.50，海马体 1.0
- 可视化：星图按同一映射聚成五个脑区，圈上标名称和条数

## 记忆周期实验台（experiment/）

三维放射可视化 + 双因子记忆值 + 提及加深 + 静默期 + 遗忘检查，标准库实现、零依赖。

```powershell
$py = "C:\Users\Lenovo\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py -m experiment.server --port 8410
```

打开 `http://127.0.0.1:8410`：

- **开始实验**：10 分钟互动期；点节点 → 右侧「提及 +1」，超过 2 次加深（金色）
- 10 分钟后自动进入 **5 分钟静默期**，禁止提及/检索
- 15 分钟**第一次遗忘检查**：提及 >2 次 → 保留并缩短（绿色）；≤2 次 → 遗忘（淡红）
- 15–45 分钟 **观察期**：无复述，看记忆值自然衰减
- 45 分钟**二次检查**：保留记忆里 S < θ(0.15) 的再遗忘，验证「高频保留」是否持久
- **多尺度**：短期层（τ0=20min）→ 有效复述 ≥3 晋升长期层（τ=90 天）；点节点看「短期/长期」与「有效复述」数
- **提及来源与权重**：用户提及 1.0、自检索 0.4（同条 5 分钟冷却）、巩固复习 0.3、上下文隐式 0.1；卡片上有「提及 +1」和「自检索」两个按钮
- **离线模拟脚本**：`python -m experiment.simulate`（τ0 对照）、`longterm`（1 年生存对照）、`selfrecall`（自检索对照）
- 点节点可看该记忆的**记忆值曲线**；「导出 CSV」拿全部数据（含 `cluster` 列）
- **三维**：星尘背景、加深节点发光、悬停显示文本、自动巡航开关（可暂停）
- **TOKEN 估算 HUD**：左下角显示「记忆 ≈ N tokens · 选中 ≈ N tokens」（按 CJK 1 token、英文词 1.3 估算；真实 API 用量需接 LLM 统计）
- **聚类分叉**：记忆按字符相似度聚成 2~4 簇，画成「中心 → 簇枢纽 → 记忆」的树状分叉；点簇枢纽看存活/平均记忆值（标签是自动抽的粗词，后续可人工命名或接真向量）
- **60× 快进测试**：约 1 分半看完整个 45 分钟流程（自动演示提及）
- 聊天里也能计数：`& $py -m experiment.cli mention --id 3`（服务器在跑时）
- 状态存 `experiment/data/state.json`，删文件夹一并清除

配置（阈值/时长/双因子参数）在 `experiment/engine.py` 的 `CFG_DEFAULT`。

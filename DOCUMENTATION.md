# 工业数据智能分析系统 — 完整技术文档

> **版本**: v4.0 综合版（合并 DOCS.md + SKILL.md，删除过时内容）
> **定位**: 基于 MCP (Model Context Protocol) 的工业数据智能分析技能系统
> **核心理念**: LLM 是认知大脑，Skills 是原子工具箱，Code Agent 是动态执行器
> **触发关键词**: 工业数据、数据分析、传感器、异常检测、故障诊断、特征选择、训练模型、生成报告

---

## 目录

1. [项目概述](#1-项目概述)
2. [技术架构](#2-技术架构)
3. [技能体系](#3-技能体系)
4. [标准调用流程](#4-标准调用流程)
5. [工具速查](#5-工具速查)
6. [洞察与建议规范](#6-洞察与建议规范)
7. [红线与反模式](#7-红线与反模式)
8. [数据格式与安全](#8-数据格式与安全)
9. [算法速查](#9-算法速查)
10. [多模型评测](#10-多模型评测)
11. [故障排查](#11-故障排查)
12. [附录](#12-附录)

---

## 1. 项目概述

### 1.1 系统能力

- **复杂意图解析**: 精准识别故障诊断、能耗预测、异常检测、时序预测等分析意图
- **双模式执行**: 标准化分析走预定义 Skills（Tool Agent），复杂场景走动态代码生成（Code Agent）
- **多源数据连接**: 支持 CSV/Excel/Parquet 文件和 MySQL/PostgreSQL 数据库
- **自动化 ML 流水线**: 特征选择 → 多模型训练 → 评估选优
- **混合特征检测**: 传统图像特征 + 深度学习（钢材缺陷检测）
- **安全护栏系统**: 参数校验、数据溯源、敏感脱敏、洞察质量检查
- **多模型隔离输出**: 每个 LLM 输出隔离到 `outputs/{model}/{dataset}/` 目录

### 1.2 核心入口文件

| 文件 | 作用 |
|------|------|
| `mcp_server.py` | MCP Server，Claude Code 通过 MCP 协议调用原子工具 |
| `skills/industrial-data-analyst/SKILL.md` | 技能定义文件，含工具 Schema 与规范 |
| `scripts/*.py` | 原子技能工具的具体实现 |

### 1.3 输出隔离规则

- 每个模型输出到独立目录: `outputs/{model}/{dataset}/`
- `{model}` 固定取值: `kimi` / `claude` / `glm` / `deepseek` / `qwen` / `wenxin`
- 由调用方通过 `model` 参数传入模型名
- **严禁** 跨模型读取其他 LLM 目录的输出
- **严禁** 将 `.py` 脚本写到项目根目录或 `scripts/` 目录，必须放入 `generated_code/`

---

## 2. 技术架构

### 2.1 三层架构

```
用户自然语言输入
       ↓
┌─────────────────────────────────────────────┐
│  推理层（GLM / Kimi / Claude / DeepSeek / Qwen）  │
│                                              │
│  ReAct 闭环（LLM 自主执行，系统仅提供原子工具）   │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌────────┐ │
│  │  Think  │→│   Act   │→│ Observe │→│Reflect │→...│
│  │  思考   │ │  行动   │ │  观察   │ │  反思  │   │
│  └─────────┘ └─────────┘ └─────────┘ └────────┘ │
└─────────────────────────────────────────────┘
       ↓ MCP 协议（HTTPS + JSON Schema + Function Calling）
┌─────────────────────────────────────────────┐
│       技能注册与调度层 (mcp_server.py)          │
│  执行类: load_data / select_features / train_model │
│          run_anomaly / run_timeseries             │
│  观察类: list_outputs / read_output               │
│  决策类: profile_dataset / save_insight            │
│          save_recommendation / plot_chart          │
│          quality_check_report / assemble_report    │
└─────────────────────────────────────────────┘
       ↓ 自动脱敏（mask_sensitive 中间件）
┌─────────────────────────────────────────────┐
│           执行层 (scripts/*.py)                │
├──────────┬──────────┬──────────┬──────────┤
│ 数据连接 │ 特征工程 │ 模型训练 │ 分析诊断 │
├──────────┼──────────┼──────────┼──────────┤
│ 可视化   │ 报告拼装 │ 代码沙箱 │ 知识库   │
└──────────┴──────────┴──────────┴──────────┘
       ↓ 护栏与隔离
┌─────────────────────────────────────────────┐
│              护栏层 (Guardrails)               │
├──────────────┬──────────────┬──────────────┤
│ 代码沙箱     │ 输入/输出校验 │ 数据泄露检测 │
├──────────────┼──────────────┼──────────────┤
│ 数据溯源     │ 敏感脱敏     │ 洞察质检     │
└──────────────┴──────────────┴──────────────┘
```

### 2.2 架构契约: ReAct 分层责任

| 阶段 | 实现位置 | 系统角色 |
|------|----------|---------|
| Think（思考） | 推理层 LLM | 提供 tool schemas 供 LLM 规划 |
| Act（行动） | 推理层 LLM + MCP 协议 | `mcp_server.py` 路由到 `scripts/*.py` |
| Observe（观察） | 推理层 LLM | `list_outputs` / `read_output` 打开视野 |
| Reflect（反思） | 推理层 LLM | 本地不干预，由 LLM 自主决断下一步 |

> **设计原则**: LLM 本身就是最强推理引擎，强制本地循环反而限制其自主规划能力。系统专注于**工具原子性、幂等性、JSON Schema 严格描述**。

### 2.3 双模式执行策略

| 模式 | 适用场景 | LLM 角色 | 执行方式 |
|------|----------|----------|---------|
| **Tool Agent** | 标准化分析（画像、异常检测、特征选择、模型训练、时序预测） | 决策参数、选择工具 | 调用预注册 MCP 工具 |
| **Code Agent** | 复杂/非标准化分析（自定义时序分解、多表关联、特定算法） | 生成 Python 代码 | `execute_code_sandbox` 动态执行 |

---

## 3. 技能体系

### 3.1 技能分类（6 大类别）

| 类别 | 包含工具 | 说明 |
|------|----------|------|
| **1. 数据预处理** | `load_data`、`desensitize_data` | 数据清洗、缺失值检测、敏感字段脱敏、类型转换 |
| **2. 统计分析** | `profile_dataset`、`query_database`、`select_features` | 描述性统计、相关性分析、特征重要性排序 |
| **3. 异常检测** | `run_anomaly` | Z-Score/IQR / Isolation Forest / LOF / DBSCAN |
| **4. 时序预测** | `run_timeseries` | STL 趋势分解、FFT 周期性识别、ARIMA/Prophet 预测 |
| **5. 可视化报告** | `plot_chart`、`save_insight`、`save_recommendation`、`assemble_report` | 图表生成、洞察落盘、报告拼装 |
| **6. 原子工具链** | `extract_time_features`、`extract_fft_features`、`extract_envelope_features`、`merge_feature_files`、`train_classifier` | 细粒度特征提取与分类器训练，LLM 自主选择 |

### 3.2 原子工具链（模型自主决策）

将特征提取与模型训练拆分为细粒度原子操作，**LLM 自主决定**提取哪些特征、用什么算法。

| 工具 | 功能 | LLM 决策点 |
|------|------|-----------|
| `extract_time_features(data_path, value_col, group_col)` | 时域特征：RMS、峭度、峰值因子等 11 维 | 是否提取、按什么列分组 |
| `extract_fft_features(...)` | 频域特征：主频、频带能量比等 9 维 | 是否提取、频带数量、采样率 |
| `extract_envelope_features(...)` | 包络谱特征：BPFO/BPFI/BSF/FTF 能量等 6 维 | 是否提取、转速参数 |
| `merge_feature_files(feature_files, label_col)` | 合并多个特征文件 | 选择合并哪些特征 |
| `train_classifier(...)` | 训练分类器（LR/SVM/RF/GB 自动选最优） | 指定模型或让系统自选 |

**验证目标**:
- 工具层一致性：相同特征提取工具在相同数据上输出完全相同的数值
- 模型层差异性：不同 LLM 的特征选择策略、算法偏好、最终精度存在差异

---

## 4. 标准调用流程

### 4.1 典型 ReAct 闭环流程

```
[1] profile_dataset(data_path)
    → LLM 阅读数据画像（行列数、列类型、时间列、目标候选、敏感列）
    → 判断：是时序还是表格？要做什么分析？

[2] (可选) desensitize_data(...)
    → 若 profile 提示有敏感列，先脱敏

[3] LLM 根据画像判断选择性执行（非强制全做）：
    ├─ 简单/标准化分析 → 调用预定义 Skills
    │   - load_data(...)            加载并落盘
    │   - run_anomaly(...)          【可选】画像显示有传感器/时序/多变量数据时执行
    │   - select_features(...)      【可选】有明确目标列、维度>5 时执行
    │   - train_model(...)          【可选】有分类/回归目标且样本充足时执行
    │   - run_timeseries(...)       【可选】是时序数据且需预测未来值时执行
    │   - plot_chart(...)           【建议】每步分析后画图，带业务标注
    │
    └─ 复杂/非标准化分析 → Code Agent
        - LLM 生成 Python 分析代码
        - 沙箱执行、结果回传、LLM 解读

[4] 每完成一段分析，写洞察：
    save_insight(model, dataset, step, title=...,
                 phenomenon="具体数值描述",  # 必须含数字
                 pattern="规律",
                 root_cause="根因",
                 impact="业务影响")

[5] 关键发现配建议（选做）：
    save_recommendation(model, dataset, step, title=..., action=...,
                        target=..., method=..., gain="数值化收益", cycle="2周")

[6] quality_check_report(model, dataset)
    → 自检：洞察 ≥ 5、建议 ≥ 3、4 要素齐全
    → 只检查实际执行的步骤

[7] assemble_report(model, dataset, sections_json=[...])
    → 拼成 docx。所有章节标题、正文、图表标注必须为中文
```

### 4.2 决策示例

| 数据特征 | 推荐执行路径 |
|----------|-------------|
| 只做 EDA + 异常检测 | skip `select_features` + `train_model` |
| 只做时序趋势分析 | skip `run_anomaly` + `train_model`，用 `run_timeseries` |
| 无标签数据 | skip `train_model`（只做无监督异常检测） |
| 数据只有 3 列 | skip `select_features`（维度已低） |

---

## 5. 工具速查

### 5.1 探查阶段（决策依据）

| 工具 | 作用 | LLM 何时调用 |
|------|------|-------------|
| `profile_dataset(data_path)` | 生成数据画像 | **每次任务的第一个工具** |
| `read_output(relative_path)` | 读取已生成的 JSON/文本 | 检查中间结果时 |
| `list_outputs(model, dataset)` | 列出已生成文件 | 自检产物齐全度 |
| `list_standards()` | 列出可引用的工业标准 | 写报告前 |

### 5.2 执行阶段（原子分析）

| 工具 | 关键参数 | 技能类别 |
|------|---------|----------|
| `load_data(source, source_type, model)` | 数据来源 | 数据预处理 |
| `desensitize_data(data_path, auto_detect)` | 敏感字段脱敏 | 数据预处理 |
| `query_database(sql, dialect, ...)` | SQL 查询（仅 SELECT） | 统计分析 |
| `select_features(data_path, target, method, top_k)` | method ∈ tree/mi/pca | 统计分析 |
| `run_anomaly(...)` | method ∈ isolation_forest/lof/dbscan/zscore/iqr | 异常检测 |
| `run_timeseries(...)` | task ∈ trend_decomposition/fft_periodicity/forecast | 时序预测 |
| `train_model(...)` | task ∈ auto/classification/regression | 统计分析 |
| `execute_code_sandbox(code)` | Code Agent 模式：LLM 生成 Python 代码 | 动态执行 |

### 5.3 可视化阶段

`plot_chart` 支持 12 种 `chart_type`：

| 场景 | chart_type |
|------|-----------|
| 时序趋势 | `line` |
| 时序+异常 | `anomaly_overlay`（需 `extra={"anomaly_indices":[...]}`） |
| 时序波动 | `rolling_band` |
| 双指标对比 | `dual_axis` |
| 频谱分析 | `fft_spectrum` |
| 单变量分布 | `hist` / `kde` / `cdf` |
| 多变量分布 | `box` / `violin` |
| 关系/相关 | `scatter` / `heatmap` |
| 类别对比 | `bar` / `stacked_bar` / `area` |

**业务标注**:
```json
annotations_json: [{"x":"2024-03-15", "y":18.5, "text":"故障突变点", "arrow":true}]
vlines_json:      [{"x":"2024-03-15", "label":"停机维护", "style":"--"}]
hlines_json:      [{"y":4.5, "label":"GB/T 6075 报警线", "color":"#c62828"}]
shaded_regions_json: [{"x_start":"22:00", "x_end":"06:00", "label":"夜班"}]
```

**配色主题**: `industrial`（默认）/ `modern` / `scientific` / `dark`

### 5.4 落盘 & 组装阶段

| 工具 | 作用 | 校验机制 |
|------|------|---------|
| `save_insight(...)` | 落盘 1 条洞察 | 空话/缺要素/不含数值 → 自动拒绝 |
| `save_recommendation(...)` | 落盘 1 条建议 | 收益无数字/周期无单位 → 自动拒绝 |
| `quality_check_report(...)` | 自检产物齐全度 | 洞察<5 / 建议<3 → 报警 |
| `assemble_report(...)` | 把 LLM 写的章节拼成 docx | 章节<30字 / 空话 → 拒绝 |
| `validate_insight(...)` | 单独校验 4 要素 | 用于 LLM 自查 |
| `critique_report(...)` | 内容级评判已生成报告 | 反馈"哪里不达标 + 怎么改" |

### 5.5 参数选择指南

**异常检测 `run_anomaly` 的 `method` 选择**:

| 数据特征 | 推荐 method | 参数建议 |
|---------|-----------|---------|
| 多变量、高维、全局分布异常 | `isolation_forest` | contamination 0.01~0.1，排除 ID/序号列 |
| 局部密度差异明显 | `lof` | contamination 0.01~0.1，n_neighbors 10~50 |
| 聚类型异常 | `dbscan` | contamination 0.01~0.1 |
| 单变量、近似正态分布 | `zscore` | 阈值默认 3σ |
| 单变量、偏态分布 | `iqr` | 1.5×IQR |

**时序预测 `run_timeseries` 的 `task` 选择**:

| 数据特征 | 推荐 task | 参数建议 |
|---------|-----------|---------|
| 分解趋势+季节+残差 | `trend_decomposition`（STL） | period: 日周期=96，周周期=672 |
| 识别主导周期 | `fft_periodicity` | 自动标注 top-3 频率 |
| 短期数值预测 | `forecast` | arima / prophet；horizon 默认 24 |
| 复杂非线性时序 | — | 转 Code Agent `execute_code_sandbox` |

**特征选择 `select_features` 的 `method` 选择**:

| 数据特征 | 推荐 method |
|---------|-----------|
| 有明确目标列、需重要性排序 | `tree`（默认，随机森林） |
| 连续型特征与目标相关性 | `mi`（互信息） |
| 高维降维后再选 | `pca` |

---

## 6. 洞察与建议规范

### 6.1 洞察 4 要素（必填）

每条 `save_insight` 必须填满 4 个字段，否则工具自动拒绝：

| 要素 | 字段名 | 写作要求 | 反面教材（会被拒） |
|------|-------|---------|-----------------|
| 现象 | `phenomenon` | **必须含具体数值**（百分比/计数/阈值） | "数据质量良好" ❌ |
| 模式 | `pattern` | 数据呈现的规律 | "存在异常" ❌ |
| 根因 | `root_cause` | 可能的原因解释 | "未知" ❌ |
| 影响 | `impact` | 对业务的具体影响 | "需要进一步分析" ❌ |

**合格示例**:
```json
{
  "title": "夜间能耗异常聚集",
  "phenomenon": "凌晨 02:00-04:00 时段共检测到 287 个异常点，占总异常数 68.3%，平均功率 18.5kW（白班均值 12.1kW 的 1.53 倍）",
  "pattern": "异常呈日周期性聚集，每日凌晨规律出现，与设备空转模式高度吻合",
  "root_cause": "怀疑夜班操作员未严格执行设备关停 SOP，或某台老旧空压机泄漏导致补气频繁启停",
  "impact": "若按全年 365 天估算，夜间空转额外能耗约 6.7 万 kWh/年，电费成本 5.4 万元/年"
}
```

### 6.2 建议 5 要素（必填）

每条 `save_recommendation` 必须填满 5 个字段：

| 要素 | 字段名 | 写作要求 |
|------|-------|---------|
| 动作 | `action` | 动词开头（"部署"/"调整"/"启用"...） |
| 对象 | `target` | 具体设备/工艺/参数 |
| 方法 | `method` | 包含具体阈值/参数 |
| 收益 | `gain` | **必须数值化**（节省 X%、降低 X 元） |
| 周期 | `cycle` | **必须含时间单位**（X 天/X 周/X 月） |

**合格示例**:
```json
{
  "title": "夜间峰谷电价 + 设备关停 SOP 优化",
  "action": "部署夜间设备自动关停策略并启用峰谷电价",
  "target": "3 号车间空压机组（编号 AC-301~303）+ 22:00-06:00 时段",
  "method": "在 PLC 加入 22:30 自动关停指令，6:00 提前预热；峰谷电价签约价差 0.62 元/kWh",
  "gain": "预计年节省电费 5.4 万元（占该车间能耗 8.3%），投资回收期 < 4 个月",
  "cycle": "实施 2 周（含 PLC 改造 + 试运行），第 1 个月可见效"
}
```

---

## 7. 红线与反模式

### 7.1 绝对禁止（违反即失败）

1. ❌ **跳过 `profile_dataset` 直接调分析工具** — 必须先看数据画像
2. ❌ **凭想象编造数据** — 必须真实运行工具得到结果
3. ❌ **用空话写洞察/建议** — 工具会自动拒绝
4. ❌ **现象字段不含具体数值**
5. ❌ **收益字段不含数值，周期字段不含时间单位**
6. ❌ **跨模型读取其他 LLM 目录的输出**
7. ❌ **把任务生成的 `.py` 写到项目根目录** — 应放 `outputs/{model}/{dataset}/generated_code/`
8. ❌ **偷看其他模型的 `generated_code/`** — 公平性约束
9. ❌ **所有输出中出现英文** — 报告、洞察、建议、图表标题/标注必须为中文

### 7.2 强制要求

1. ✅ 第一个工具必须是 `profile_dataset`
2. ✅ 每条 insight 通过 4 要素校验后才落盘
3. ✅ 每条 recommendation 通过 5 要素校验后才落盘
4. ✅ `assemble_report` 前必须先 `quality_check_report` 通过
5. ✅ 所有输出落 `outputs/{model}/{dataset}/`，model 由 LLM 在调用时填入自身标识

### 7.3 反模式示例

**反模式 1：不看数据就分析**
```python
# ❌ 错
run_anomaly(data_path, model="claude", method="isolation_forest", contamination=0.1)

# ✅ 对
profile = profile_dataset(data_path)
# LLM 看到 profile：50000 行时序数据，目标列是 quality，数值列分布偏态严重
# → 决定 contamination=0.02、columns 排除 ID 列
run_anomaly(data_path, model="claude", method="isolation_forest",
            columns=["temperature","pressure","vibration"], contamination=0.02)
```

**反模式 2：写空话洞察**
```python
# ❌ 错（会被工具拒绝）
save_insight(..., phenomenon="数据存在异常", pattern="规律性",
             root_cause="未知", impact="需要进一步分析")

# ✅ 对
save_insight(...,
    phenomenon="检测到 287 个异常点，集中在凌晨 02:00-04:00（占 68.3%）",
    pattern="异常呈日周期聚集",
    root_cause="夜间设备空转 / 关停 SOP 执行不严",
    impact="年额外能耗约 6.7 万 kWh，电费 5.4 万元/年")
```

**反模式 3：让工具替你想内容**
```python
# ❌ 错：assemble_report 不会"自动写章节"
assemble_report(model, dataset, sections_json=[])  # 空 sections 会被拒绝

# ✅ 对：LLM 自己写完每个章节再传入
sections = [
    {"title": "1 数据概况", "content_md": "本数据集共 35040 行..."},
    {"title": "2 时序特征", "content_md": "FFT 分析显示..."},
]
assemble_report(model, dataset, sections_json=json.dumps(sections))
```

**反模式 4：图表不带业务标注**
```python
# ❌ 错：只画一条折线，看不出洞察
plot_chart(model, dataset, data_path, chart_type="line", x="time", y="vibration")

# ✅ 对：加国标线 + 故障点标注 + 维护期阴影
plot_chart(model, dataset, data_path, chart_type="line", x="time", y="vibration",
    title="3# 风机振动趋势 + GB/T 6075 评判",
    hlines_json='[{"y":4.5,"label":"GB/T 6075 II级报警线","color":"#c62828"}]',
    annotations_json='[{"x":"2024-03-15","y":6.2,"text":"突变点","arrow":true}]',
    shaded_regions_json='[{"x_start":"2024-03-20","x_end":"2024-03-22","label":"计划停机维护"}]')
```

---

## 8. 数据格式与安全

### 8.1 支持的数据源

| 类型 | 说明 | 示例 |
|------|------|------|
| 文件 | CSV/JSON/Excel/Parquet/Pickle/HDF5 | `connector.load("data.csv")` |
| MySQL | 关系型数据库 | `query_database(sql="SELECT * FROM ...", dialect="mysql")` |
| PostgreSQL | 关系型数据库 | `query_database(sql="...", dialect="postgresql")` |

### 8.2 数据库默认配置

`config/db_config.json`：

```json
{
  "mysql": {
    "host": "localhost", "port": 3306,
    "user": "root", "password": "12345",
    "database": "industrial"
  },
  "postgresql": {
    "host": "localhost", "port": 5432,
    "user": "postgres", "password": "123456",
    "database": "postgres"
  }
}
```

### 8.3 数据格式规范

**时序数据**:
```csv
timestamp,value,device_id,metric_name
2024-01-01 00:00:00,23.5,DEV001,temperature
```

**振动数据**:
```csv
timestamp,vibration,sampling_rate
2024-01-01 00:00:00.000,0.0023,10000
```

**支持的时间格式**:
- ISO 8601: `2024-01-01T10:30:00`
- 标准格式: `2024-01-01 10:30:00`
- Unix 时间戳: `1704103800`

**数据质量红线**:
- 缺失率 > 10% → 先插补或删除，不要直接建模
- 连续缺失 > 5 个采样点 → 视为传感器断线，标注在洞察中
- 编码非 UTF-8 → 用 `encoding='gbk'` 或 `'gb2312'` 重读

### 8.4 敏感数据与安全

**敏感字段自动识别清单**:

| 类别 | 关键词示例 |
|------|-----------|
| 身份标识 | `password`, `secret`, `token`, `api_key` |
| 人员信息 | `employee_id`, `id_card`, `phone`, `email` |
| 设备标识 | `serial_number`, `device_id`, `mac_address` |
| 业务敏感 | `customer_name`, `supplier_name` |

**脱敏方法**:
- 完全遮蔽: `***已脱敏***`
- 部分遮蔽: 保留前后各 2 位，中间用 `***` 替代
- 语义类型覆盖: 字段名匹配敏感关键词时，强制覆盖数值推断，只输出存在性

**合规标准**:
- 《中华人民共和国网络安全法》
- 《中华人民共和国数据安全法》
- 《中华人民共和国个人信息保护法》

---

## 9. 算法速查

### 9.1 时序预测

| 数据特征 | 推荐算法 | 理由 |
|---------|---------|------|
| 数据量小（<100点） | 简单移动平均 | 避免过拟合 |
| 平稳时序 | ARIMA | 理论成熟 |
| 季节性明显 | Prophet | 自动处理季节性 |
| 复杂非线性 | LSTM/Transformer | 捕捉复杂模式（Code Agent） |

**ARIMA 参数**: `p`(0-5), `d`(0-2), `q`(0-5)

### 9.2 异常检测

| 数据特征 | 推荐算法 | 参数 | 理由 |
|---------|---------|------|------|
| 单变量 | IQR | threshold: 1.5-3.0 | 简单快速 |
| 多变量 | Isolation Forest | n_estimators: 100-200, contamination: 0.01-0.1 | 适合高维 |
| 密度异常 | LOF | n_neighbors: 10-50 | 检测局部异常 |

### 9.3 故障诊断（分类）

| 场景 | 推荐算法 | 理由 |
|------|---------|------|
| 规则明确 | 决策树 | 可解释性强 |
| 数据充足 | 随机森林 | 准确率高，抗过拟合 |
| 追求极致性能 | XGBoost | 性能最优，支持并行 |

### 9.4 图像分析（钢材缺陷）

- **传统方法**: Canny 边缘检测、Sobel 梯度、形态学操作
- **深度学习**: ResNet/EfficientNet
- **混合模式**: 传统特征 30% + 深度学习 70%（默认启用）

**支持缺陷类型**: 龟裂(Crazing)、夹杂(Inclusion)、斑块(Patches)、麻点(Pitted Surface)、轧入氧化皮(Rolled-in Scale)、划痕(Scratches)

---

## 10. 多模型评测

### 10.1 6 大评估维度

| 维度 | 权重 | 检查重点 |
|------|------|---------|
| 流程合规性 | 15% | 是否先调 profile_dataset、输出目录是否正确 |
| 分析深度 | 25% | 业务解释是否合理、是否区分统计异常 vs 业务异常 |
| 算法选择 | 15% | 方法是否适合数据特征、参数设定合理性 |
| 报告质量 | 25% | 摘要清晰度、洞察深度、建议可执行性 |
| 性能指标 | 10% | 执行时间、Token 消耗、错误次数 |
| 一致性 | 10% | 多次运行结果是否稳定、多数据集泛化能力 |

### 10.2 对比方法

```powershell
# 检查输出完整性
ls outputs/glm/steel_energy/
ls outputs/kimi/steel_energy/

# 检查报告是否生成
foreach ($model in @("glm", "deepseek", "kimi", "qwen")) {
    $report = "outputs/$model/steel_energy/report_*.docx"
    if (Test-Path $report) { Write-Host "$model OK" } else { Write-Host "$model 缺失" }
}
```

---

## 11. 故障排查

### 11.1 依赖安装

```bash
# 升级 pip
python -m pip install --upgrade pip

# 使用国内镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 11.2 PyTorch / GPU

```bash
# CPU 版本
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# 验证 GPU
python -c "import torch; print(torch.cuda.is_available())"
```

### 11.3 编码与时间格式

```python
# 编码错误
from scripts.data_loader import DataLoader
loader = DataLoader()
loader.load("data.csv", encoding="gbk")  # 或 "gb2312", "utf-8-sig"

# 时间格式解析
loader.convert_datetime(columns=["timestamp"], format="%Y/%m/%d %H:%M:%S")
```

### 11.4 内存不足

```python
import pandas as pd

# 分块读取
chunks = pd.read_csv("large_file.csv", chunksize=10000)
for chunk in chunks:
    process(chunk)

# 或指定数据类型减少内存
dtypes = {"col1": "float32", "col2": "int16"}
df = pd.read_csv("data.csv", dtype=dtypes)
```

### 11.5 常见错误代码

| 代码 | 含义 | 解决方案 |
|------|------|---------|
| `E001` | 数据文件不存在 | 检查文件路径 |
| `E002` | 数据格式错误 | 检查列名/分隔符/编码 |
| `E003` | 必需列缺失 | 调用 `profile_dataset` 确认列名映射 |
| `E004` | 模型文件缺失 | 下载或训练模型 |
| `E005` | API 密钥无效 | 更新 `config/llm_config.json` |
| `E006` | 内存不足 | 减少数据量或分块处理 |
| `E007` | GPU 不可用 | 使用 CPU 模式 |

### 11.6 日志与诊断

- 日志位置: `logs/` 目录
- 运行诊断: `python scripts/diagnostic.py`
- 查看日志: `type logs\analysis.log`（Windows）
- 搜索错误: `findstr "ERROR" logs\analysis.log`

---

## 12. 附录

### 12.1 输出目录结构

```
D:/aaaend/industrial-data-analyst1/outputs/{model}/{dataset}/
├── step1_data_quality/
│   ├── data_summary.json
│   ├── sensitive_fields.json
│   └── insights.json
├── step2_eda/
│   ├── correlation_*.png
│   ├── distribution_*.png
│   ├── insights.json
│   └── recommendations.json
├── step3_feature_selection/
├── step4_anomaly/
│   ├── anomaly_indices_*.json
│   └── anomaly_overlay_*.png
├── step5_model_training/
├── workflow_log/
│   └── quality_check.json
├── generated_code/
│   └── *.py
└── report_YYYYMMDD_HHMMSS.docx
```

### 12.2 工业标准引用

调用 `lookup_standard` 前确认可用 domain：

| domain | 用途 | 典型参数 |
|--------|------|---------|
| `vibration` | 机械振动合规判定 | `value` (mm/s), `machine_class` (I/II/III/IV) |
| `steel_surface` | 钢材表面质量 | `defect_type`, `severity` |
| `energy` | 能耗诊断 | `consumption` (kWh/吨), `industry_type` |

引用格式：
> "根据 GB/T 6075 标准，本次测得振动有效值 7.2 mm/s 已超出 II 类机械 B 区上限（2.8 mm/s），处于 C 区警告状态，建议 30 天内停机检修。"

### 12.3 调用 Checklist

- [ ] 调用 `profile_dataset(data_path)` 看数据画像
- [ ] LLM 阅读画像，判断分析方向
- [ ] 若有敏感列，调 `desensitize_data` 先脱敏
- [ ] LLM 判断任务复杂度，选择 Tool Agent 或 Code Agent
- [ ] 用 `plot_chart` 画图，带上业务标注
- [ ] 每段分析结束，写 `save_insight`（满足 4 要素）
- [ ] 关键发现配 `save_recommendation`（满足 5 要素）
- [ ] 调用 `quality_check_report` 自检
- [ ] 调用 `assemble_report` 生成最终报告

---

*本文档由 DOCS.md v3.0 + SKILL.md 合并而成，已清理所有过时内容与重复章节。*

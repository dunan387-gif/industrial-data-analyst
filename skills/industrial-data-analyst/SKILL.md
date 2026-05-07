---
name: industrial-data-analyst
description: |
  工业数据智能分析技能。触发关键词：工业数据、数据分析、传感器、异常检测、故障诊断、特征选择、训练模型、生成报告。

  【设计哲学】LLM 作为核心认知引擎，通过 ReAct 机制驱动"思考→调用→观察→修正"闭环。
  - LLM 负责自然语言理解、意图识别、任务规划、参数决策与结果解读
  - 执行层支持双模式：预定义 Skills 原子调用（Tool Agent）+ 动态代码生成执行（Code Agent）
  - 业务洞察 / 建议 / 报告章节文本，全部由 LLM 自主撰写，工具只做执行/落盘/拼装

  【强制规范】
  (1) 第一步必须调用 profile_dataset 看数据画像
  (2) 业务洞察按【现象/模式/根因/影响】4 要素写，建议按【动作/对象/方法/收益/周期】5 要素写
  (3) 现象必须含具体数值，收益必须数值化，周期必须含时间单位
  (4) 禁止空话："数据质量良好"、"建议进一步分析"、"准确率较高" 等（save_insight 工具会自动拒绝）
  (5) 输出落到 D:/aaaend/industrial-data-analyst1/outputs/{model}/{dataset}/，禁止跨模型读取
  (6) **所有输出报告、洞察、建议、图表标题/标注必须为中文**。禁止在面向用户的产物中出现英文（代码注释除外）
---

# 工业数据智能分析 Skill

> **核心理念**：LLM 是认知大脑，Skills 是原子工具箱，Code Agent 是动态执行器。  
> 所有"智能决策"由 LLM 做出；简单分析走预定义 Skills，复杂场景走 Code Agent 生成代码。  
> LLM 必须每步看结果再决定下一步（ReAct 闭环）。

---

## 🎯 推荐调用模式（典型流程）

```
[1] profile_dataset(data_path)
    → LLM 阅读数据画像（行列数、列类型、时间列、目标候选、敏感列）
    → 判断：是时序还是表格？要做什么分析？

[2] (可选) desensitize_data(...)
    → 若 profile 提示有敏感列，先脱敏

[3] LLM 根据画像判断**选择性执行**（非强制全做）：
    ├─ 简单/标准化分析 → 调用预定义 Skills（Tool Agent 模式）
    │   - load_data(...)            加载并落盘（通常需要）
    │   - run_anomaly(...)          【可选】异常检测：画像显示有传感器/时序/多变量数据时执行
    │   - select_features(...)      【可选】特征选择：画像显示有明确目标列、维度>5 时执行
    │   - train_model(...)          【可选】模型训练：画像显示有分类/回归目标且样本充足时执行
    │   - run_timeseries(...)       【可选】时序预测：画像确认是时序数据且需预测未来值时执行
    │   - plot_chart(...)           【建议】每步分析后画图，带业务标注
    │
    └─ 复杂/非标准化分析 → Code Agent 生成代码（execute_code_sandbox）
        - LLM 根据意图生成 Python 分析代码
        - 沙箱执行、结果回传、LLM 解读
    
    **决策示例**：
    - 只做 EDA + 异常检测 → skip `select_features` + `train_model`
    - 只做时序趋势分析 → skip `run_anomaly` + `train_model`，用 `run_timeseries`
    - 无标签数据 → skip `train_model`（只做无监督异常检测）
    - 数据只有 3 列 → skip `select_features`（维度已低）

[4] 每完成**一段**分析，LLM 写一条洞察：
    save_insight(model, dataset, step,
                 title=...,
                 phenomenon="具体数值描述",  # 必须含数字
                 pattern="规律",
                 root_cause="根因",
                 impact="业务影响")
    → 做了哪几步，就写哪几步的洞察（不要求每步都有）

[5] 关键发现配一条建议（选做：收益不明确的发现可跳过）：
    save_recommendation(model, dataset, step,
                        title=..., action=..., target=...,
                        method=..., gain="数值化收益",
                        cycle="2周/1月")

[6] quality_check_report(model, dataset)
    → 自检：洞察 ≥ 5、建议 ≥ 3、4 要素齐全
    → **只检查实际执行的步骤**，未执行的 step 目录不检查

[7] assemble_report(model, dataset, sections_json=[
        {"title":"数据概况", "content_md":"LLM 用中文写的章节正文", "figures":[...]},
        ...
    ])
    → 拼成 docx。**所有章节标题、正文、图表标注必须为中文**
```

---

## 🏗 总体技术架构（三层架构）

本系统采用三层架构设计，与论文开题报告一致：

| 层级 | 组件 | 职责 |
|------|------|------|
| **1. 大模型推理层** | GLM-4 / Kimi / Claude 等 LLM API | 自然语言理解、意图识别、任务规划、ReAct 推理闭环（思考→调用→观察→修正）、结果解读与报告生成 |
| **2. 技能注册与调度层** | Agent Skills 中间件（MCP Server） | JSON Schema 规范定义技能接口；技能动态注册、版本管理；根据任务复杂度智能调度（Tool Agent / Code Agent） |
| **3. 执行环境层** | 原子工具集 + 代码沙箱 | 预定义 Skills（SQL 提取、统计分析、异常检测、时序预测、可视化）+ `execute_code_sandbox` 安全隔离执行 |

### 双模式执行策略

| 模式 | 适用场景 | LLM 角色 | 执行方式 |
|------|----------|----------|----------|
| **Tool Agent** | 标准化分析（画像、异常检测、特征选择、模型训练、时序预测） | 决策参数、选择工具 | 调用预注册 MCP 工具 |
| **Code Agent** | 复杂/非标准化分析（自定义时序分解、多表关联、特定算法） | 生成 Python 代码 | `execute_code_sandbox` 动态执行 |

---

## 📦 技能分类（5 大类别）

与论文开题报告的工业数据智能分析 Skills 构建方案对齐：

| 类别 | 包含工具 | 说明 |
|------|----------|------|
| **1. 数据预处理技能** | `load_data`、`desensitize_data` | 数据清洗、缺失值检测、敏感字段脱敏、类型转换 |
| **2. 统计分析技能** | `profile_dataset`、`query_database`、`select_features` | 描述性统计、相关性分析、特征重要性排序 |
| **3. 异常检测技能** | `run_anomaly` | 统计方法（Z-Score/IQR）+ 机器学习方法（Isolation Forest/LOF/DBSCAN） |
| **4. 时序预测技能** | `run_timeseries` | 趋势分解（STL）、周期性识别（FFT）、短期预测（ARIMA/Prophet） |
| **5. 可视化报告技能** | `plot_chart`、`save_insight`、`save_recommendation`、`assemble_report` | 图表生成（12 种类型）、洞察落盘、报告拼装 |
| **6. 原子工具链（模型自主决策）** | `extract_time_features`、`extract_fft_features`、`extract_envelope_features`、`merge_feature_files`、`train_classifier` | 细粒度特征提取与分类器训练，LLM 自主选择特征组合与算法 |

---

## 🧪 原子工具链（模型自主决策对比验证）

本工具链将特征提取与模型训练拆分为细粒度原子操作，**LLM 自主决定**提取哪些特征、用什么算法，体现不同模型的决策差异。

### 工具列表

| 工具 | 功能 | LLM 决策点 |
|------|------|-----------|
| `extract_time_features(data_path, value_col, group_col)` | 时域特征：RMS、峭度、峰值因子等 11 维 | 是否提取、按什么列分组 |
| `extract_fft_features(data_path, value_col, sampling_rate, group_col, n_bands)` | 频域特征：主频、频带能量比等 9 维 | 是否提取、频带数量、采样率 |
| `extract_envelope_features(data_path, value_col, sampling_rate, rotation_speed, group_col)` | 包络谱特征：BPFO/BPFI/BSF/FTF 能量等 6 维 | 是否提取、转速参数 |
| `merge_feature_files(feature_files, label_col)` | 合并多个特征文件为完整矩阵 | 选择合并哪些特征 |
| `train_classifier(feature_file, label_col, model_type, test_ratio)` | 训练分类器（LR/SVM/RF/GB 自动选最优） | 指定模型或让系统自选 |

### 典型调用流程

```
[1] profile_dataset(data_path)
    → LLM 发现 fault_type 列有 4 类标签，判断为分类任务

[2] LLM 自主决定提取哪些特征（以下为示例，不同模型选择不同）：
    ├─ Claude 可能：时域 + 频域 + 包络 全提取
    ├─ GLM 可能：只做 FFT 频域特征
    └─ Kimi 可能：时域 + 包络

[3] 若提取多种特征，调用 merge_feature_files 合并
    merge_feature_files("time_features.csv,fft_features.csv,envelope_features.csv", label_col="_group")

[4] 训练分类器
    train_classifier(feature_file="merged_features.csv", label_col="_group", model_type="auto")
    → 自动对比 LR/SVM/RF/GB，输出最优模型及准确率、F1、混淆矩阵

[5] LLM 解读结果，写洞察和建议
```

### 验证目标

- **工具层一致性**：相同特征提取工具在相同数据上输出完全相同的数值
- **模型层差异性**：不同 LLM 的特征选择策略、算法偏好、最终精度存在差异
- **论文呈现**：对比三个模型的决策路径与最终分类准确率

---

## 🛠 工具速查（按使用阶段分组）

### A. 探查阶段（决策依据）

| 工具 | 作用 | LLM 何时调用 |
|------|------|---------------|
| `profile_dataset(data_path)` | 生成数据画像（形状/列分布/时间列/目标候选/敏感列） | **每次任务的第一个工具** |
| `read_output(relative_path)` | 读取已生成的 JSON/文本 | 检查中间结果时 |
| `list_outputs(model, dataset)` | 列出已生成文件 | 自检产物齐全度 |
| `list_standards()` | 列出可引用的工业标准 | 写报告前 |

### B. 执行阶段（原子分析）

| 工具 | 关键参数（**LLM 决定**） | 技能类别 |
|------|------------------------|----------|
| `load_data(source, source_type, model)` | 数据来源 | 数据预处理 |
| `desensitize_data(data_path, auto_detect)` | 敏感字段脱敏 | 数据预处理 |
| `profile_dataset(data_path)` | 数据画像 | 统计分析 |
| `query_database(sql, dialect, ...)` | SQL 查询（仅 SELECT） | 统计分析 |
| `select_features(data_path, target, method, top_k, model)` | method ∈ tree/mi/pca | 统计分析 |
| `run_anomaly(data_path, model, dataset, method, columns, contamination, n_neighbors)` | 异常检测：method ∈ isolation_forest/lof/dbscan/zscore/iqr | 异常检测 |
| `run_timeseries(data_path, model, dataset, task, target, freq)` | 时序预测：task ∈ trend_decomposition/fft_periodicity/forecast(ARIMA/Prophet) | 时序预测 |
| `train_model(data_path, target, task, model)` | 模型训练：task ∈ auto/classification/regression | 统计分析 |
| `plot_chart(model, dataset, data_path, chart_type, ...)` | 12 种图表类型 | 可视化报告 |
| `execute_code_sandbox(code)` | **Code Agent 模式**：LLM 生成 Python 代码，沙箱执行 | 动态执行（跨类别） |

### C. 可视化阶段（LLM 控制图表内容）

`plot_chart(model, dataset, data_path, chart_type, x, y, ...)` 支持下列 `chart_type`：

| 场景 | chart_type | 典型用法 |
|------|-----------|---------|
| 时序趋势 | `line` | 单/多列折线 |
| 时序+异常 | `anomaly_overlay` | 折线上叠加红色异常点（需 `extra={"anomaly_indices":[..]}`） |
| 时序波动 | `rolling_band` | 滚动均值±σ 带状图（异常预警） |
| 双指标对比 | `dual_axis` | 双 Y 轴折线（如温度+功率） |
| 频谱分析 | `fft_spectrum` | FFT 频谱（自动标 top-3 频率） |
| 单变量分布 | `hist` / `kde` / `cdf` | 直方/核密度/累积分布 |
| 多变量分布 | `box` / `violin` | 箱线/小提琴对比 |
| 关系/相关 | `scatter` / `heatmap` | 散点/相关矩阵热力图 |
| 类别对比 | `bar` / `stacked_bar` / `area` | 柱状/堆叠/面积 |

**业务标注（让图有"灵魂"）**：

```json
annotations_json: [{"x":"2024-03-15", "y":18.5, "text":"故障突变点", "arrow":true}]
vlines_json:      [{"x":"2024-03-15", "label":"3月停机维护", "style":"--"}]
hlines_json:      [{"y":4.5, "label":"GB/T 6075 报警线 4.5mm/s", "color":"#c62828"}]
shaded_regions_json: [{"x_start":"22:00", "x_end":"06:00", "label":"夜班"}]
```

**配色主题**：`industrial`（默认，工业蓝橙）/ `modern`（明快）/ `scientific`（matplotlib 标准）/ `dark`（深色背景）

### D. 知识阶段（写报告时引用）

| 工具 | 作用 |
|------|------|
| `lookup_standard(domain, value, ...)` | 查工业标准（GB/T、ISO）做合规判定 |

### E. 落盘 & 组装阶段

| 工具 | 作用 | 校验机制 |
|------|------|---------|
| `save_insight(model, dataset, step, title, phenomenon, pattern, root_cause, impact)` | 落盘 1 条洞察 | 命中空话/缺要素/不含数值 → 自动拒绝 |
| `save_recommendation(model, dataset, step, title, action, target, method, gain, cycle)` | 落盘 1 条建议 | 收益不含数字/周期不含时间单位 → 自动拒绝 |
| `quality_check_report(model, dataset)` | 自检产物齐全度 | 洞察<5 / 建议<3 / 无报告 → 报警 |
| `assemble_report(model, dataset, sections_json, title, output_format)` | 把 LLM 写的章节拼成 docx/md | 章节<30字 / 命中空话 → 拒绝 |
| `validate_insight(insights_json, ...)` | 单独校验 4 要素 | 用于 LLM 自查 |
| `critique_report(report_dir, ...)` | 内容级评判已生成报告 | 反馈"哪里不达标 + 怎么改" |

---

## 📋 业务洞察写作规范（4 要素）

每条 `save_insight` 必须填满 4 个字段，**否则会被工具自动拒绝**：

| 要素 | 字段名 | 写作要求 | 反面教材（会被拒） |
|------|-------|---------|-----------------|
| 现象 | `phenomenon` | **必须含具体数值**（百分比/计数/阈值） | "数据质量良好" ❌ |
| 模式 | `pattern` | 数据呈现的规律 | "存在异常" ❌（太空） |
| 根因 | `root_cause` | 可能的原因解释 | "未知" ❌ |
| 影响 | `impact` | 对业务的具体影响 | "需要进一步分析" ❌ |

✅ **合格示例**：
```json
{
  "title": "夜间能耗异常聚集",
  "phenomenon": "凌晨 02:00-04:00 时段共检测到 287 个异常点，占总异常数 68.3%，平均功率 18.5kW（白班均值 12.1kW 的 1.53 倍）",
  "pattern": "异常呈日周期性聚集，每日凌晨规律出现，与设备空转模式高度吻合",
  "root_cause": "怀疑夜班操作员未严格执行设备关停 SOP，或某台老旧空压机泄漏导致补气频繁启停",
  "impact": "若按全年 365 天估算，夜间空转额外能耗约 6.7 万 kWh/年，电费成本 5.4 万元/年"
}
```

---

## 📋 业务建议写作规范（5 要素）

每条 `save_recommendation` 必须填满 5 个字段：

| 要素 | 字段名 | 写作要求 |
|------|-------|---------|
| 动作 | `action` | 动词开头（"部署"/"调整"/"启用"...） |
| 对象 | `target` | 具体设备/工艺/参数 |
| 方法 | `method` | 包含具体阈值/参数 |
| 收益 | `gain` | **必须数值化**（节省 X%、降低 X 元） |
| 周期 | `cycle` | **必须含时间单位**（X 天/X 周/X 月） |

✅ **合格示例**：
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

## 🚨 红线（违反即视为失败）

### ❌ 8 条绝对禁止

1. ❌ 跳过 `profile_dataset` 直接调分析工具（必须先看数据画像）
2. ❌ 凭想象编造数据（必须真实运行工具得到结果）
3. ❌ 用空话写洞察 / 建议（工具会自动拒绝）
4. ❌ 现象字段不含具体数值
5. ❌ 收益字段不含数值，周期字段不含时间单位
6. ❌ 跨模型读取其他 LLM 目录的输出
7. ❌ 把任务生成的 `.py` 写到项目根目录（应放 `outputs/{model}/{dataset}/generated_code/`）
8. ❌ 偷看其他模型的 `generated_code/`（公平性约束）

### ✅ 5 条强制要求

1. ✅ 第一个工具必须是 `profile_dataset`
2. ✅ 每条 insight 通过 4 要素校验后才落盘
3. ✅ 每条 recommendation 通过 5 要素校验后才落盘
4. ✅ `assemble_report` 前必须先 `quality_check_report` 通过
5. ✅ 所有输出落 `outputs/{model}/{dataset}/`，model 由 LLM 在调用时填入自身标识（如 `"kimi"`/`"claude"`）
6. ✅ 所有报告、洞察、建议、图表标题/标注必须为中文

---

## 📂 标准输出目录结构（绝对路径）

所有分析产物必须落入以下根目录，并按 **模型隔离** 存放，禁止混用：

```
D:/aaaend/industrial-data-analyst1/outputs/{model}/{dataset}/
```

- `{model}` 为当前执行 LLM 的标识，固定取值：`kimi` / `claude` / `glm` / `deepseek` / `qwen` / `wenxin`
- `{dataset}` 为数据集名称，如 `steel_energy`、`gas_temp`、`hydraulic_system`
- **严禁** 将 `.py` 脚本写到项目根目录或 `scripts/` 目录，必须放入 `generated_code/`
- **严禁** 跨模型读取其他 LLM 目录下的输出（如 kimi 不可读取 `outputs/claude/`）

完整目录树：

```
D:/aaaend/industrial-data-analyst1/outputs/{model}/{dataset}/
├── step1_data_quality/
│   ├── data_summary.json
│   ├── sensitive_fields.json     # 敏感字段检测结果
│   ├── insights.json              # ← LLM 写的洞察
│   └── ...
├── step2_eda/
│   ├── correlation_*.png
│   ├── distribution_*.png
│   ├── insights.json
│   └── recommendations.json       # ← LLM 写的建议
├── step3_feature_selection/
├── step4_anomaly/
│   ├── anomaly_indices_*.json     # run_anomaly 落盘的索引
│   └── anomaly_overlay_*.png      # plot_chart 画的叠加图
├── step5_model_training/
├── workflow_log/
│   └── quality_check.json
├── generated_code/                # 任务生成的 .py 文件（严禁放根目录）
│   └── *.py
└── report_YYYYMMDD_HHMMSS.docx    # 最终报告
```

---

## 💡 反模式（不要这样做）

### ❌ 反模式 1：不看数据就分析
```python
# ❌ 错
run_anomaly(data_path, model="claude", method="isolation_forest", contamination=0.1)

# ✅ 对
profile = profile_dataset(data_path)
# LLM 看到 profile：50000 行时序数据，目标列是 quality，
# 数值列分布偏态严重 → 决定 contamination=0.02、columns 排除 ID 列
run_anomaly(data_path, model="claude", method="isolation_forest",
            columns=["temperature","pressure","vibration"],
            contamination=0.02)
```

### ❌ 反模式 2：写空话洞察
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

### ❌ 反模式 3：让工具替你想内容
```python
# ❌ 错：assemble_report 不会"自动写章节"
assemble_report(model, dataset, sections_json=[])  # 空 sections 会被拒绝

# ✅ 对：LLM 自己写完每个章节再传入
sections = [
    {"title": "1 数据概况", "content_md": "本数据集共 35040 行..."},
    {"title": "2 时序特征", "content_md": "FFT 分析显示..."},
    ...
]
assemble_report(model, dataset, sections_json=json.dumps(sections))
```

### ❌ 反模式 4：图表不带业务标注
```python
# ❌ 错：只画一条折线，看不出洞察
plot_chart(model, dataset, data_path,
           chart_type="line", x="time", y="vibration")

# ✅ 对：加国标线 + 故障点标注 + 维护期阴影
plot_chart(model, dataset, data_path,
           chart_type="line", x="time", y="vibration",
           title="3# 风机振动趋势 + GB/T 6075 评判",
           hlines_json='[{"y":4.5,"label":"GB/T 6075 II级报警线","color":"#c62828"}]',
           annotations_json='[{"x":"2024-03-15","y":6.2,"text":"突变点","arrow":true}]',
           shaded_regions_json='[{"x_start":"2024-03-20","x_end":"2024-03-22","label":"计划停机维护"}]')
```

---

## 🧭 调用 Checklist（ReAct 闭环）

LLM 按"思考 → 调用 → 观察 → 修正"闭环执行：

- [ ] 调用 `profile_dataset(data_path)` 看数据画像
- [ ] LLM 阅读画像，判断分析方向（时序？分类？回归？聚类？）
- [ ] 若有敏感列，调 `desensitize_data` 先脱敏
- [ ] **LLM 判断任务复杂度，选择执行模式**：
  - 标准化分析 → 调用预定义 Skills：`run_anomaly` / `run_timeseries` / `select_features` / `train_model` / `plot_chart`
  - 复杂/非标准化分析 → Code Agent：`execute_code_sandbox` 生成 Python 代码
- [ ] 用 `plot_chart` 画图，带上业务标注（参考线/异常点/阴影）
- [ ] 每段分析结束，写一条 `save_insight`（满足 4 要素）
- [ ] 关键发现配一条 `save_recommendation`（满足 5 要素）

### 异常检测 `run_anomaly` 的 `method` 选择

| 数据特征 | 推荐 method | 参数建议 |
|---------|-----------|---------|
| 多变量、高维、全局分布异常 | `isolation_forest` | `contamination` 0.01~0.1，排除 ID/序号列 |
| 局部密度差异明显 | `lof` | `contamination` 0.01~0.1，`n_neighbors` 10~50 |
| 聚类型异常 | `dbscan` | `contamination` 0.01~0.1 |
| 单变量、已知近似正态分布 | `zscore` | `contamination` 隐式由阈值决定（默认 3σ） |
| 单变量、偏态分布 | `iqr` | `contamination` 隐式由 1.5×IQR 决定 |

> **contamination 设定原则**：先看画像中的异常比例预估（如 profile 提示 2% 离群 → 设 0.02），不要盲目用 0.1。

### 时序预测 `run_timeseries` 的 `task` 选择

| 数据特征 | 推荐 task | 参数建议 |
|---------|-----------|---------|
| 需分解趋势+季节+残差分量 | `trend_decomposition`（STL） | `period` 根据画像推断频率（日周期=96，周周期=672） |
| 需识别主导周期/频率 | `fft_periodicity` | 自动标注 top-3 频率及对应周期 |
| 需短期数值预测（未来 N 步） | `forecast` | 方法 ∈ `arima` / `prophet`；`horizon` 默认 24 步 |
| 复杂非线性时序（需深度学习） | — | 超出预定义 Skills，转 **Code Agent** `execute_code_sandbox` 自定义 LSTM/Transformer |

### 特征选择 `select_features` 的 `method` 选择

| 数据特征 | 推荐 method |
|---------|-----------|
| 有明确目标列、需要重要性排序 | `tree`（默认，基于随机森林） |
| 连续型特征与目标的相关性 | `mi`（互信息） |
| 高维降维后再选 | `pca`（PCA 载荷排序） |

### 模型训练 `train_model` 的 `task` 选择

| 画像特征 | 推荐 task |
|---------|---------|
| 目标列是离散类别（如 normal/fault） | `classification` |
| 目标列是连续数值（如 energy_kwh） | `regression` |
| 不确定时让工具自动判断 | `auto` |

---

## 🗄 数据库默认连接配置

`query_database` 未提供连接参数时，使用以下默认值（已写入 `config/db_config.json`）：

| 方言 | host | port | user | password | database |
|------|------|------|------|----------|----------|
| `mysql` | localhost | 3306 | root | `12345` | industrial |
| `postgresql` | localhost | 5432 | postgres | `123456` | postgres |

> 若用户提供了自定义连接信息，优先使用用户提供的值。

---

## 🔒 敏感字段自动识别清单

`profile_dataset` 若检测到以下列名/关键词，会提示敏感。LLM 应优先调 `desensitize_data` 脱敏后再分析：

| 类别 | 关键词示例 |
|------|-----------|
| 身份标识 | `password`, `secret`, `token`, `api_key` |
| 人员信息 | `employee_id`, `id_card`, `phone`, `email` |
| 设备标识 | `serial_number`, `device_id`, `mac_address` |
| 业务敏感 | `customer_name`, `supplier_name` |

---

## 📏 工业标准引用速查

调用 `lookup_standard` 前，先确认可用 domain：

| domain | 用途 | 典型参数 |
|--------|------|---------|
| `vibration` | 机械振动合规判定 | `value` (mm/s), `machine_class` (I/II/III/IV) |
| `steel_surface` | 钢材表面质量 | `defect_type`, `severity` |
| `energy` | 能耗诊断 | `consumption` (kWh/吨), `industry_type` |

引用格式（写入报告）：
> "根据 GB/T 6075 标准，本次测得振动有效值 7.2 mm/s 已超出 II 类机械 B 区上限（2.8 mm/s），处于 C 区警告状态，建议 30 天内停机检修。"

---

## 🆘 常见错误代码速查

| 代码 | 含义 | LLM 应对 |
|------|------|-----------|
| `E001` | 数据文件不存在 | LLM 检查路径拼写、确认文件已上传 |
| `E002` | 数据格式错误 | LLM 参考"数据格式规范"检查列名/分隔符/编码 |
| `E003` | 必需列缺失 | 调用 `profile_dataset` 确认列名映射 |
| `E004` | 模型文件缺失 | 提示用户需先训练或从 task2 复制 `.pth` |
| `E005` | API 密钥无效 | 检查 `config/llm_config.json` |
| `E006` | 内存不足 | 建议分块处理或减少数据集 |
| `E007` | GPU 不可用 | 切换 CPU 模式运行 |

---

## 📐 数据格式规范（LLM 判断用）

### 时间列识别

`profile_dataset` 会标识时间列。若时间格式不标准，LLM 应先用 `execute_code_sandbox` 转换：

| 原始格式 | 转换方法 |
|---------|---------|
| `2024/01/01 10:30:00` | `pd.to_datetime(df['timestamp'], format='%Y/%m/%d %H:%M:%S')` |
| `1704103800` (Unix) | `pd.to_datetime(df['timestamp'], unit='s')` |
| `2024-01-01T10:30:00` (ISO 8601) | `pd.to_datetime(df['timestamp'])`（自动识别） |

### 数据质量红线

- 缺失率 > 10% → 先插补或删除，不要直接建模
- 连续缺失 > 5 个采样点 → 视为传感器断线，标注在洞察中
- 编码非 UTF-8 → 用 `encoding='gbk'` 或 `'gb2312'` 重读

---

## 📂 标准输出目录结构（绝对路径）

所有分析产物必须落入以下根目录，并按 **模型隔离** 存放，禁止混用：

```
D:/aaaend/industrial-data-analyst1/outputs/{model}/{dataset}/
```

- `{model}` 为当前执行 LLM 的标识，固定取值：`kimi` / `claude` / `glm` / `deepseek` / `qwen` / `wenxin`
- `{dataset}` 为数据集名称，如 `steel_energy`、`gas_temp`、`hydraulic_system`
- **严禁** 将 `.py` 脚本写到项目根目录或 `scripts/` 目录，必须放入 `generated_code/`
- **严禁** 跨模型读取其他 LLM 目录下的输出（如 kimi 不可读取 `outputs/claude/`）

完整目录树：

```
D:/aaaend/industrial-data-analyst1/outputs/{model}/{dataset}/
├── step1_data_quality/
│   ├── data_summary.json
│   ├── sensitive_fields.json     # 敏感字段检测结果
│   ├── insights.json              # ← LLM 写的洞察
│   └── ...
├── step2_eda/
│   ├── correlation_*.png
│   ├── distribution_*.png
│   ├── insights.json
│   └── recommendations.json       # ← LLM 写的建议
├── step3_feature_selection/
├── step4_anomaly/
│   ├── anomaly_indices_*.json     # run_anomaly 落盘的索引
│   └── anomaly_overlay_*.png      # plot_chart 画的叠加图
├── step5_model_training/
├── workflow_log/
│   └── quality_check.json
├── generated_code/                # 任务生成的 .py 文件（严禁放根目录）
│   └── *.py
└── report_YYYYMMDD_HHMMSS.docx    # 最终报告
```

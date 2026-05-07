# 工业数据智能分析技能 — 技术文档

> **版本**: v3.0  
> **定位**: 本项目是**工业数据智能分析技能库**，基于 **Anthropic MCP (Model Context Protocol)** 构建。  
> **核心理念**: Claude 是大脑，skill 是工具箱。所有"智能决策"由 Claude 做出，工具只负责执行/落盘/拼装。  
> **触发关键词**: 工业数据、数据分析、传感器、异常检测、故障诊断、特征选择、训练模型、生成报告。

---

## 1. 项目概述

本项目专为工业互联网和 MES 系统设计，集成：

- **复杂意图解析**: 精准识别故障诊断、能耗预测、异常检测等分析意图
- **多源数据连接**: 支持文件和多种数据库（MySQL/PostgreSQL/InfluxDB/MongoDB）
- **自动化 ML 流水线**: 特征选择 → 多模型训练 → 评估选优
- **混合特征检测**: 传统图像特征 + 深度学习（钢材缺陷检测）
- **安全护栏系统**: 输入校验、输出校验、幻觉检测、数据泄露检测
- **多模型隔离输出**: 每个 LLM 输出隔离到 `outputs/{model}/{dataset}/` 目录

### 核心入口

- **技能流程文档**: `skills/industrial-data-analyst/SKILL.md`（**Claude 必读**，含工具速查、洞察规范、红线）
- **本技术文档**: `DOCS.md`（架构、算法、数据库、排错等参考）
- **MCP Server**: `mcp_server.py`（Claude Code 通过 MCP 协议调用原子工具）

### 输出隔离规则

- 每个模型输出到独立目录: `outputs/{model}/{dataset}/`
- 由调用方（Claude Code）通过 `model` 参数传入模型名（如 `claude`、`glm`、`deepseek`、`kimi`、`qwen`）
- 禁止跨模型读取其他 LLM 目录的输出

---

## 2. 技术架构

```
用户自然语言输入
       ↓
┌──────────────────────────────────────────────────────────
│       推理层（Claude Code / GLM / Kimi / DeepSeek / Qwen）     │
│                                                             │
│  ReAct 闭环（由 LLM 自主执行，本项目仅提供原子工具）          │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐     │
│  │  Think  │ → │   Act   │ → │ Observe │ → │ Reflect │ → ...│
│  │ 思考   │   │ 行动   │   │ 观察   │   │ 反思   │     │
│  └─────────┘   └─────────┘   └─────────┘   └─────────┘     │
└───────────────────────────────────────────────────────────┘
       ↓ MCP 协议（HTTPS + JSON Schema + Function Calling）
┌──────────────────────────────────────────────────────────┐
│           技能注册与调度层 (mcp_server.py)                 │
│  执行类 tool: load_data / select_features / train_model /      │
│               run_anomaly                                       │
│  观察类 tool: list_outputs / read_output                        │
│  决策类 tool: profile_dataset / save_insight / save_recommendation│
│               plot_chart / quality_check_report / assemble_report│
└──────────────────────────────────────────────────────────┘
       ↓ 自动脱敏（mask_sensitive 中间件）
┌──────────────────────────────────────────────────────────┐
│                 执行层 (scripts/*.py)                        │
├──────────┬──────────┬──────────┬──────────┬─────────────┤
│ 数据连接 │ 特征工程 │ 模型训练 │ 分析诊断 │  报告拼装   │
└──────────┴──────────┴──────────┴──────────┴─────────────┘
       ↓ 护栏与隔离
┌──────────────────────────────────────────────────────────┐
│                    护栏层 (Guardrails)                       │
├──────────────┬──────────────┬──────────────┬─────────────┤
│ Trail 沙箱   │ 输入/输出校验 │ 数据泄露检测 │ 模型隔离   │
└──────────────┴──────────────┴──────────────┴─────────────┘
```

### 架构契约: ReAct 分层责任

| 阶段 | 实现位置 | 本项目角色 |
|------|----------|-------------|
| Think （思考）| 推理层 LLM | 提供 tool schemas 供 LLM 规划 |
| Act   （行动）| 推理层 LLM + MCP 协议 | `mcp_server.py` 路由到 `scripts/*.py` |
| Observe（观察）| 推理层 LLM | `list_outputs` / `read_output` 打开视野 |
| Reflect（反思）| 推理层 LLM | 本地不干预，由 LLM 自主决断下一步 |

> 为何不在本地实现 ReAct 循环？  
> LLM 本身就是最强推理引擎，强制本地循环反而限制其自主规划能力。MCP 协议通过 Function Calling 实现标准化桥接，本项目专注于**工具原子性、幂等性、JSON Schema 严格描述**。

---

## 3. 依赖与安装

### 必需依赖

```
python >= 3.8
numpy >= 1.20.0
pandas >= 1.3.0
scipy >= 1.7.0
scikit-learn >= 1.0.0
```

### 可选依赖

| 依赖 | 用途 | 安装命令 |
|------|------|----------|
| torch, torchvision | 深度学习模型（钢材缺陷检测） | `pip install torch torchvision` |
| matplotlib, seaborn | 可视化图表 | `pip install matplotlib seaborn` |
| Pillow | 图像处理 | `pip install Pillow` |
| opencv-python | 高级图像处理 | `pip install opencv-python` |
| prophet | 时序预测 | `pip install prophet` |
| statsmodels | ARIMA 模型 | `pip install statsmodels` |
| pymysql | MySQL 连接 | `pip install pymysql` |
| psycopg2-binary | PostgreSQL 连接 | `pip install psycopg2-binary` |
| influxdb-client | InfluxDB 连接 | `pip install influxdb-client` |
| pymongo | MongoDB 连接 | `pip install pymongo` |
| xgboost | XGBoost 模型 | `pip install xgboost` |
| lightgbm | LightGBM 模型 | `pip install lightgbm` |

### 快速安装

```bash
# 安装必需依赖
pip install numpy pandas scipy scikit-learn

# 环境诊断
python scripts/diagnostic.py
```

---

## 4. 数据库接入

### 4.1 支持的数据源

| 类型 | 说明 | 示例 |
|------|------|------|
| 文件 | CSV/JSON/Excel/Parquet/Pickle/HDF5 | `connector.load("data.csv")` |
| MySQL | 关系型数据库 | `query_database(sql="SELECT * FROM ...", dialect="mysql")` |
| PostgreSQL | 关系型数据库 | `query_database(sql="...", dialect="postgresql")` |
| InfluxDB | 时序数据库（工业常用） | `connector.connect_database("influxdb", ...)` |
| MongoDB | 文档数据库 | `connector.connect_database("mongodb", ...)` |

### 4.2 PostgreSQL 配置

数据库配置文件: `config/db_config.json`

```json
{
  "mysql": {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "12345",
    "database": "industrial"
  },
  "postgresql": {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "password": "123456",
    "database": "postgres"
  }
}
```

### 4.3 导入数据到 PostgreSQL

**方法1: pgAdmin 图形界面**

1. 打开 pgAdmin，连接到 PostgreSQL 服务器
2. 右键点击 "Databases" → "Create" → "Database"，名填 `industrial_data`
3. 在 Query Tool 中打开 `scripts/create_tables_pgadmin.sql` 并执行
4. 右键点击表 → "Import/Export Data" → 选择 CSV 导入

**方法2: Python 脚本**

```bash
python scripts/import_to_postgres.py \
    --csv data/steel_energy/Steel_industry_data.csv \
    --table steel_energy
# 自动读取 config/db_config.json 中的配置
```

**方法3: psql 命令行**

```bash
psql -U postgres -d industrial_data
\i scripts/create_tables_pgadmin.sql
COPY steel_energy FROM '.../Steel_industry_data.csv'
WITH (FORMAT csv, HEADER true, DELIMITER ',', ENCODING 'UTF8');
```

### 4.4 验证导入

```sql
-- 查看表结构
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;

-- 统计行数
SELECT COUNT(*) FROM steel_energy;

-- 查看样例数据
SELECT * FROM steel_energy LIMIT 5;
```

### 4.5 MCP SQL 查询工具

```python
query_database(
    sql="SELECT * FROM steel_energy WHERE usage_kwh > 100 LIMIT 10",
    dialect="postgresql",
    host="localhost",
    database="industrial_data",
    user="postgres",
    password="123456"
)
```

---

## 5. 算法速查

### 5.1 时序预测

| 数据特征 | 推荐算法 | 理由 |
|---------|---------|------|
| 数据量小（<100点） | 简单移动平均 | 避免过拟合 |
| 平稳时序 | ARIMA | 理论成熟，效果好 |
| 季节性明显 | Prophet | 自动处理季节性 |
| 复杂非线性 | LSTM | 捕捉复杂模式 |

**ARIMA 参数**: `p`(0-5), `d`(0-2), `q`(0-5)

**Prophet 参数**: `growth`(linear/logistic), `seasonality_mode`(additive/multiplicative), `changepoint_prior_scale`(0.001-0.5)

### 5.2 异常检测

| 数据特征 | 推荐算法 | 参数 | 理由 |
|---------|---------|------|------|
| 单变量 | IQR | `threshold`: 1.5-3.0 | 简单快速 |
| 多变量 | Isolation Forest | `n_estimators`: 100-200, `contamination`: 0.01-0.1 | 适合高维 |
| 密度异常 | LOF | `n_neighbors`: 10-50, `contamination`: 0.01-0.1 | 检测局部异常 |

### 5.3 故障诊断（分类）

| 场景 | 推荐算法 | 理由 |
|------|---------|------|
| 规则明确 | 决策树 | 可解释性强 |
| 数据充足 | 随机森林 | 准确率高，抗过拟合 |
| 追求极致性能 | XGBoost | 性能最优，支持并行 |

### 5.4 振动分析

- **FFT**: 频域分析，识别特征频率
- **小波变换**: 时频分析，瞬态信号
- **包络分析**: 轴承故障诊断（Hilbert 变换）

### 5.5 图像分析（钢材缺陷）

- **传统方法**: Canny 边缘检测、Sobel 梯度、形态学操作
- **深度学习**: ResNet/EfficientNet，支持 GPU 加速
- **混合模式**: 传统特征 30% + 深度学习 70%（默认启用）

---

## 6. 数据格式规范

### 6.1 时序数据

```csv
timestamp,value,device_id,metric_name
2024-01-01 00:00:00,23.5,DEV001,temperature
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| timestamp | datetime | 是 | ISO 8601 或 `YYYY-MM-DD HH:MM:SS` |
| value | float | 是 | 数值型指标值 |
| device_id | string | 否 | 设备标识符 |
| metric_name | string | 否 | 指标名称 |

### 6.2 振动数据

```csv
timestamp,vibration,sampling_rate
2024-01-01 00:00:00.000,0.0023,10000
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| vibration | float | 是 | 振动幅值（mm/s 或 g） |
| sampling_rate | int | 是 | 采样率（Hz） |

### 6.3 多传感器故障数据

```csv
timestamp,temperature,pressure,vibration,current,status
2024-01-01 10:00:00,65.2,101.3,2.1,15.3,normal
```

### 6.4 支持的时间格式

- ISO 8601: `2024-01-01T10:30:00`
- 标准格式: `2024-01-01 10:30:00`
- 日期格式: `2024-01-01`
- Unix 时间戳: `1704103800`

### 6.5 数据质量要求

- 时序数据缺失率应 < 10%
- 连续缺失不超过 5 个采样点
- 文件编码：UTF-8（推荐）或 GBK
- CSV 分隔符：逗号（,）
- 数值精度：浮点数保留 6 位有效数字

---

## 7. 数据安全

### 7.1 敏感数据类型

- **个人身份信息（PII）**: 员工ID、姓名、身份证号、联系方式
- **设备标识信息**: 设备序列号、MAC 地址
- **业务敏感信息**: 客户信息、供应商信息
- **认证凭据**: 密码、API 密钥、访问令牌

### 7.2 自动脱敏

系统自动识别并脱敏以下字段：

```python
SENSITIVE_FIELDS = [
    "password", "secret", "token", "api_key",
    "employee_id", "id_card", "phone", "email",
    "serial_number", "device_id", "customer_name"
]
```

脱敏方法：
- **完全遮蔽**: `***已脱敏***`
- **部分遮蔽**: 保留前后各2位，中间用 `***` 替代
- **哈希替换**: 使用 SHA256 哈希值

### 7.3 数据传输与存储

- API 调用使用 **HTTPS/TLS 1.3**
- 数据库连接使用 **SSL/TLS**
- 敏感数据使用 **AES-256** 加密存储
- 审计日志保留期：**至少 90 天**

### 7.4 合规标准

- 《中华人民共和国网络安全法》
- 《中华人民共和国数据安全法》
- 《中华人民共和国个人信息保护法》
- GB/T 35273-2020（个人信息安全规范）
- GB/T 22239-2019（网络安全等级保护）
- ISO/IEC 27001

---

## 8. 使用示例

### 8.1 异常检测（Python 直接调用）

```python
from scripts.fault_diagnosis import FaultDiagnosisAnalyzer

analyzer = FaultDiagnosisAnalyzer()
analyzer.load_data("data/equipment_metrics.csv")

result = analyzer.detect_anomalies(
    method="isolation_forest",
    columns=["temperature", "vibration", "current"],
    contamination=0.05
)

print(f"检测到 {result['anomaly_count']} 个异常点")
print(f"异常率: {result['anomaly_rate']:.2%}")
```

### 8.2 多方法对比

```python
methods = ["isolation_forest", "lof", "zscore", "iqr"]
for method in methods:
    result = analyzer.detect_anomalies(method=method)
    print(f"{method}: {result['anomaly_count']} 个异常 ({result['anomaly_rate']:.2%})")
```

### 8.3 时序预测

```python
from scripts.time_series_forecast import TimeSeriesAnalyzer

analyzer = TimeSeriesAnalyzer()
analyzer.load_data("data/energy_consumption.csv", time_col="date", value_col="kwh")

# 趋势分析
trend = analyzer.analyze_trend()

# 预测未来 30 天
forecast = analyzer.forecast(periods=30, method="prophet")
```

### 8.4 特征选择

```python
from scripts.feature_selector import FeatureSelector

selector = FeatureSelector()
selector.load_data("sensor_data.csv", target_col="fault_type")
selected = selector.auto_select(method="tree", top_k=10)
```

### 8.5 数据脱敏

```python
from scripts.data_masking import DataMasker

masker = DataMasker()
masker.load_data("data/production_log.csv")

sensitive_cols = masker.detect_sensitive_columns()
masker.mask_all_sensitive(method="mask")
masker.save("data/production_log_masked.csv")
```

### 8.6 通过 MCP 工具（Claude Code 调用）

```python
# 第一步：数据画像
profile_dataset(data_path="data/sensor_data.csv")

# 第二步：异常检测（Claude 根据画像决定参数）
run_anomaly(
    data_path="data/sensor_data.csv",
    model="claude",
    method="isolation_forest",
    columns=["temperature", "vibration", "current"],
    contamination=0.02
)

# 第三步：画图（带业务标注）
plot_chart(
    model="claude", dataset="sensor_data",
    data_path="data/sensor_data.csv",
    chart_type="anomaly_overlay",
    x="timestamp", y="temperature",
    title="温度异常点叠加",
    hlines_json='[{"y":80,"label":"报警线 80°C","color":"#c62828"}]'
)

# 第四步：保存洞察
save_insight(
    model="claude", dataset="sensor_data", step="step4_anomaly",
    title="高温异常聚集",
    phenomenon="检测到 23 个异常点，温度 > 80°C（占总数 0.8%）",
    pattern="异常集中在午后 14:00-16:00",
    root_cause="冷却系统散热不足或环境温度升高",
    impact="若持续运行，设备寿命预计缩短 15%"
)
```

---

## 9. 钢材缺陷检测

### 9.1 支持的缺陷类型

1. **Crazing (龟裂)** - 表面细小裂纹
2. **Inclusion (夹杂)** - 钢材内部杂质
3. **Patches (斑块)** - 表面不规则斑块
4. **Pitted Surface (麻点)** - 表面凹陷点
5. **Rolled-in Scale (轧入氧化皮)** - 轧制中氧化皮压入
6. **Scratches (划痕)** - 表面划痕

### 9.2 快速使用

```bash
# 单张图片检测（默认启用混合特征）
python scripts/steel_defect_detector.py image.jpg

# 指定模型
python scripts/steel_defect_detector.py image.jpg --model resnet18

# 禁用混合特征，仅深度学习
python scripts/steel_defect_detector.py image.jpg --no-hybrid

# 批量检测
python scripts/steel_defect_detector.py ./images --batch --output results.json

# 生成 HTML 报告
python scripts/steel_defect_detector.py image.jpg --format html --output report.html
```

### 9.3 Python 调用

```python
from scripts.steel_defect_detector import SteelDefectDetector

detector = SteelDefectDetector(model_name='resnet18', use_hybrid=True)
result = detector.predict('steel_image.jpg')

print(f"缺陷类型: {result['defect_type']} ({result['defect_type_cn']})")
print(f"置信度: {result['confidence']:.1f}%")
print(f"检测方法: {result['method']}")  # 'hybrid' 或 'deep_learning_only'
```

### 9.4 可用模型

| 模型 | 精度 | 速度 | 推荐场景 |
|------|------|------|---------|
| resnet18 | ★★★☆☆ | ★★★★★ | 快速检测 |
| resnet34 | ★★★★☆ | ★★★★☆ | 平衡性能 |
| resnet50 | ★★★★★ | ★★★☆☆ | 高精度要求 |
| efficientnet_b0 | ★★★★☆ | ★★★★☆ | 推荐使用 |
| efficientnet_b1 | ★★★★★ | ★★★☆☆ | 高精度 |
| efficientnet_b2 | ★★★★★ | ★★☆☆☆ | 最高精度 |

### 9.5 模型文件

- 存放位置: `models/steel_defect/`
- 已包含: `resnet18_best.pth`, `efficientnet_b0_best.pth`
- 如需其他模型，从原 task2 项目复制: `models/steel_defect/{model_name}_best.pth`

---

## 10. 故障排查

### 10.1 依赖安装失败

```bash
# 升级 pip
python -m pip install --upgrade pip

# 使用国内镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 10.2 PyTorch / GPU 问题

```bash
# CPU 版本
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# CUDA 11.8 版本
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# 验证 GPU
python -c "import torch; print(torch.cuda.is_available())"
```

### 10.3 编码错误

```python
from scripts.data_loader import DataLoader
loader = DataLoader()
loader.load("data.csv", encoding="gbk")  # 或 "gb2312", "utf-8-sig"
```

### 10.4 时间格式解析失败

```python
loader.convert_datetime(
    columns=["timestamp"],
    format="%Y/%m/%d %H:%M:%S"  # 指定实际格式
)
```

### 10.5 内存不足

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

### 10.6 异常检测结果不准确

```python
# 调整 contamination 参数
result = analyzer.detect_anomalies(
    method="isolation_forest",
    contamination=0.01  # 降低到 1%
)

# 或尝试其他方法
result = analyzer.detect_anomalies(method="zscore", threshold=3.5)
```

### 10.7 模型文件不存在

```bash
# 从 task2 复制模型文件
copy task2\steel_defect_classification\output\models\*.pth models\steel_defect\
```

### 10.8 常见错误代码

| 错误代码 | 含义 | 解决方案 |
|----------|------|----------|
| E001 | 数据文件不存在 | 检查文件路径 |
| E002 | 数据格式错误 | 参考第 6 节数据格式规范 |
| E003 | 必需列缺失 | 检查数据列名 |
| E004 | 模型文件缺失 | 下载或训练模型 |
| E005 | API 密钥无效 | 更新 config/llm_config.json |
| E006 | 内存不足 | 减少数据量或分块处理 |
| E007 | GPU 不可用 | 使用 CPU 模式 |

### 10.9 日志与诊断

- 日志位置: `logs/` 目录
- 运行诊断: `python scripts/diagnostic.py`
- 查看日志: `type logs\analysis.log`（Windows）
- 搜索错误: `findstr "ERROR" logs\analysis.log`

---

## 11. 工业领域知识库

### 11.1 目录结构

```
knowledge/
├── standards/                          # 国家标准 / 国际标准
│   ├── GB_T_6075_机械振动.json          # 机械振动评价（=ISO 10816）
│   ├── GB_T_15166_钢材表面缺陷.json     # 钢材表面质量国标
│   └── GB_T_2589_能耗诊断.json          # 综合能耗计算通则
└── domain_rules/
    └── bearing_fault_diagnosis.json    # 滚动轴承故障诊断
```

### 11.2 使用方式

**通过 MCP tool（推荐）**:

```python
lookup_standard(metric="vibration", value=7.2, machine_class="II")
# → 返回: 根据 GB/T 6075 II 类机械，7.2 mm/s 处于 C 区（警告），建议 30 天内停机维护
```

**Python API**:

```python
from scripts.knowledge_loader import KnowledgeLoader
loader = KnowledgeLoader()

verdict = loader.evaluate_vibration(rms=7.2, machine_class="II")
# → {"zone": "C", "action": "30天内停机维护", "standard_ref": "GB/T 6075"}
```

### 11.3 报告引用规范

```
"根据 GB/T 6075 标准，本次测得振动有效值 7.2 mm/s 已超出 II 类机械
B 区上限（2.8 mm/s），处于 C 区警告状态，建议 30 天内停机检修。"
```

---

## 12. 多模型评测指南

用于对比 GLM、DeepSeek、Kimi、Qwen 等不同 LLM 在调用 `industrial-data-analyst` 技能时的表现差异。

### 12.1 测试数据集

| 数据集 | 类型 | 测试目的 |
|--------|------|---------|
| `data/gas_sensor.csv` | 高维分类（13910×129） | 测试**特征选择能力** |
| `data/industrial_simple.csv` | 低维分类（含 target） | 测试**模型训练能力** |
| `data/hydraulic_system/` | 多文件时序 | 测试**复杂数据处理能力** |
| `data/breast_cancer.csv` | 标准小数据集 | 测试**基线一致性** |

### 12.2 6 大评估维度

| 维度 | 权重 | 检查重点 |
|------|------|---------|
| 流程合规性 | 15% | 是否先调 profile_dataset、输出目录是否正确 |
| 分析深度 | 25% | 业务解释是否合理、是否区分统计异常 vs 业务异常 |
| 算法选择 | 15% | 方法是否适合数据特征、参数设定合理性 |
| 报告质量 | 25% | 摘要清晰度、洞察深度、建议可执行性 |
| 性能指标 | 10% | 执行时间、Token 消耗、错误次数 |
| 一致性 | 10% | 多次运行结果是否稳定、多数据集泛化能力 |

### 12.3 对比方法

```powershell
# 检查输出完整性
ls glm/gas_sensor/
ls deepseek/gas_sensor/

# 对比中间结果
Compare-Object (Get-Content glm/gas_sensor/step3_feature_selection/selected_features.json) `
              (Get-Content deepseek/gas_sensor/step3_feature_selection/selected_features.json)

# 检查报告是否生成
foreach ($model in @("glm", "deepseek", "kimi", "qwen")) {
    $report = "$model/gas_sensor/final_report/comprehensive_analysis_report.docx"
    if (Test-Path $report) { Write-Host "$model OK" } else { Write-Host "$model 缺失" }
}
```

---

## 13. 重构设计（v3.0 — 已完成）

### 13.1 改造前问题

| 问题 | 位置 | 处理方式 |
|------|------|---------|
| 假 LLM 启发式 | `scripts/llm_strategy_advisor.py` | **已删除** — if-else 冒充智能，误导 Claude |
| 一键自动跑黑盒 | `mcp_server.py` 的 `run_full_workflow` | **已删除** — 不让 Claude 看中间结果 |
| 5 个固定 scope | `workflow_executor.py` 的 `SCOPE_STEPS` | **已删除** — 流程由 Claude 临场决定 |
| 报告模板套话 | `scripts/llm_report_generator.py` | **已删除** — 文本由 Claude 写，工具只做 docx 拼装 |
| 图表硬编码 | 各步骤里 `plt.savefig` | **已改造** — `plot_chart` 由 Claude 决定类型/标注 |

### 13.2 改造后架构

| 维度 | 改造前 | 改造后 |
|------|-------|-------|
| 流程控制 | `run_full_workflow` 一键跑 7 步 | Claude 主动编排原子工具 |
| 决策来源 | `LLMStrategyAdvisor` 假装 LLM | Claude 看 profile 自己决定 |
| 报告内容 | `_fallback_generate` 模板套话 | Claude 自己写每个章节 |
| 洞察生成 | 启发式自动凑数 | Claude 写完调 `save_insight` 落盘 |
| 图表 | 固定 matplotlib 模板 | Claude 决定画什么、标注什么 |
| 给 Claude Code 体验 | 黑盒一键跑，不可控 | 可观察、可干预、可组合 |

### 13.3 新增核心文件

| 文件 | 作用 |
|------|------|
| `scripts/chart_engine.py` | 14 种图表类型 + 4 套主题 + 业务标注 |
| `mcp_server.py` 中 `run_anomaly` | 参数化异常检测（暴露 contamination/columns/n_neighbors） |
| `mcp_server.py` 中 `plot_chart` | Claude 控制图表类型/配色/业务标注 |

---

*本文档由 12 个历史文档合并而成，已清理所有过时内容。*

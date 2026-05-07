# 工业数据智能分析技能 (Industrial Data Analyst)

一个专为工业互联网的智能数据分析技能，集成了复杂意图解析、自动化分析执行和智能决策反馈三大核心模块。

## 特性

- **复杂意图解析**：自动识别故障诊断、能耗预测、趋势分析等多种分析意图
- **自动化分析执行**：动态调用统计模型、时序算法和数据挖掘工具
- **智能决策反馈**：生成包含自然语言解读和可视化图表的综合分析报告
- **国产大模型集成**：支持智谱 GLM、文心一言、Kimi 等国产大模型
- **数据安全保护**：自动脱敏敏感数据，符合数据安全法规要求
- **结果校验机制**：防止大模型"幻觉"，确保分析结论有数据支撑

## 支持的分析类型

- 故障诊断分析
- 趋势预测分析
- 剩余使用寿命（RUL）预测
- 表面缺陷检测
- 振动分析
- 相关性分析
- 异常检测
- 能耗分析
- 性能分析

## 快速开始

### 1. 安装依赖

```bash
cd D:\AI工作区\projects\industrial-data-analyst1
python scripts/setup.py
```

或手动安装：

```bash
pip install numpy pandas scipy matplotlib seaborn
pip install scikit-learn xgboost
pip install statsmodels prophet
pip install requests
```

### 2. 配置 API 密钥

编辑 `config/llm_config.json`，填入你的 API 密钥：

```json
{
  "zhipu": {
    "api_key": "your_zhipu_api_key_here"
  },
  "wenxin": {
    "api_key": "your_api_key:your_secret_key"
  },
  "kimi": {
    "api_key": "your_kimi_api_key_here"
  }
}
```

### 3. 使用示例

> 本项目是供 Claude Code 调用的 skill，LLM 由外部接入（GLM/DeepSeek/Kimi/Qwen 等）。
> 推荐通过自然语言调用，或使用 `run_skill.py` CLI。

#### 示例 1：Claude Code 调用（推荐）

在 Claude Code 中接入任意国产 LLM，直接提问：

```
对 data/hydraulic_system 这个工业数据进行分析
```

技能将自动按 7 步工作流执行，输出隔离在 `{model}/{dataset}/` 目录下。

#### 示例 2：CLI 调用单个技能

```bash
# 加载数据
python run_skill.py run-skill --name load_data \
    --params '{"source": "data/breast_cancer.csv"}' --model glm

# 运行完整流水线
python run_skill.py run-pipeline --name industrial_analysis \
    --data data/breast_cancer.csv --target target --model glm
```

#### 示例 3：意图解析（可选预处理）

```python
from scripts.intent_parser import IntentParser

parser = IntentParser()
intent = parser.parse("5号机床的轴承振动有点大，还能用多久？")
print(intent)
# 返回：{"intent": "rul_prediction", "entities": {...}}
```

## 目录结构

```
industrial-data-analyst1/
├── skills/industrial-data-analyst/SKILL.md  # 技能入口（Claude Code 读取）
├── TECHNICAL.md                # 技术参考文档
├── README.md                   # 本文件
├── run_skill.py                # CLI 入口
├── mcp_server.py               # MCP Server（供 Claude 调用）
├── audit_model.py              # 模型执行审计工具
├── model_comparison/           # 多模型对比评估
├── scripts/                    # 核心分析脚本
│   ├── intent_parser.py        # 意图解析器
│   ├── data_loader.py          # 数据加载
│   ├── correlation_analyzer.py # 相关性分析
│   ├── feature_selector.py     # 特征选择
│   ├── fault_diagnosis.py      # 异常检测/故障诊断
│   ├── auto_trainer.py         # 自动训练
│   ├── time_series_forecast.py # 时序预测
│   ├── result_validator.py     # 结果校验器
│   └── setup.py                # 安装脚本
├── references/                 # 参考文档
│   ├── algorithms.md           # 算法库说明
│   ├── data_security.md        # 数据安全策略
│   └── examples.md             # 使用示例
├── config/                     # 配置文件
│   └── llm_config.json         # 大模型配置
├── evals/                      # 测试用例
│   └── evals.json              # 评估标准
└── assets/                     # 资源文件
```

## 核心模块说明

### 1. 意图解析模块

自动识别用户查询中的分析意图和关键实体：

- 支持的意图类型：故障诊断、趋势预测、根因分析、异常检测等
- 实体提取：时间范围、设备ID、产线编号、指标名称等
- 置信度评估：计算解析结果的可信度

### 2. 自动化分析执行模块

根据意图动态调用相应的分析算法：

- **时序分析**：ARIMA、Prophet、LSTM
- **异常检测**：IQR、Isolation Forest、LOF
- **故障诊断**：决策树、随机森林、XGBoost
- **振动分析**：FFT、小波变换、包络分析
- **图像分析**：边缘检测、CNN、YOLO

### 3. 智能决策反馈模块

生成包含自然语言解读的综合分析报告：

- 执行摘要：关键发现的简洁总结
- 详细分析：统计信息、趋势详情、预测结果
- 趋势研判：短期和长期趋势预测
- 决策建议：可直接落地的行动建议
- 可视化图表：时序图、分布图、热力图等

## 数据安全

本技能严格遵循数据安全策略：

- **自动脱敏**：识别并脱敏敏感字段（员工ID、设备序列号等）
- **隐私保护**：调用大模型 API 前自动过滤敏感信息
- **访问控制**：支持基于角色的访问控制（RBAC）
- **审计日志**：记录所有数据访问操作
- **加密传输**：所有 API 调用使用 HTTPS/TLS

详见 `references/data_security.md`

## 性能优化

- **异步处理**：耗时任务支持异步执行，避免前端超时
- **结果缓存**：自动缓存大模型响应，减少重复调用
- **并行计算**：支持多核并行处理大规模数据
- **批处理**：大数据分批处理，降低内存占用

## 测试

运行测试用例：

```bash
# 运行所有测试
python -m pytest tests/

# 运行特定测试
python -m pytest tests/test_intent_parser.py
```

查看测试覆盖率：

```bash
pytest --cov=scripts tests/
```

## 常见问题

### Q1: 如何切换大模型提供商？

在调用时指定 `provider` 参数：

```python
client = LLMClient(provider="wenxin")  # 或 "zhipu", "kimi"
```

### Q2: 如何处理大规模数据？

使用异步处理模式：

```python
from scripts.async_executor import AsyncAnalyzer

analyzer = AsyncAnalyzer()
task_id = analyzer.submit_task(task_type="time_series_forecast", data_path="large_data.csv")
```

### Q3: 如何自定义脱敏规则？

编辑 `config/data_masking_rules.json`，添加自定义规则。

### Q4: 预测结果不准确怎么办？

1. 检查数据质量（缺失值、异常值）
2. 增加历史数据量
3. 尝试不同的预测算法
4. 调整算法参数

## 贡献指南

欢迎贡献代码、报告问题或提出建议！

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 许可证

本项目采用 MIT 许可证。详见 `LICENSE` 文件。

## 联系方式

- 项目主页：[GitHub](https://github.com/your-org/industrial-data-analyst1)
- 问题反馈：[Issues](https://github.com/your-org/industrial-data-analyst1/issues)
- 邮箱：dunan387@gmail

## 致谢

感谢以下开源项目：

- [scikit-learn](https://scikit-learn.org/)
- [statsmodels](https://www.statsmodels.org/)
- [Prophet](https://facebook.github.io/prophet/)
- [XGBoost](https://xgboost.readthedocs.io/)

---

**版本**：v1.0
**最后更新**：2025-01-15

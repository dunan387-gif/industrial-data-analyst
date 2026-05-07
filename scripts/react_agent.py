#!/usr/bin/env python3
"""
ReAct Agent — Python 级离线 Runner

用途：在无 Claude / 外部 LLM 的环境下，用 Python 直接驱动 MCP 工具完成
      Think → Act → Observe → Reflect 闭环，主要用于：
        - 单元测试 / CI 自动化验证
        - 不依赖 LLM API 的本地快速验证
        - 调试新技能工具的输入输出格式

设计原则：
  - 本模块【不替代】LLM 的推理决策，仅模拟调用序列
  - 真实生产环境中 ReAct 闭环由 LLM（Claude/GLM/Kimi 等）通过 MCP 协议驱动
  - 所有步骤结果写入 outputs/{model}/{dataset}/ 与 MCP 调用保持一致

用法：
    python scripts/react_agent.py \\
        --data data/steel_energy.csv \\
        --model glm \\
        --steps profile anomaly features train report

    python scripts/react_agent.py --data data/hydraulic_system --model kimi --steps all
"""

import os
import sys
import json
import argparse
import logging
import time
from typing import List, Dict, Any, Optional

# 将项目根目录加入路径
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("react_agent")

# ── 步骤常量 ────────────────────────────────────────────────
STEP_PROFILE  = "profile"
STEP_ANOMALY  = "anomaly"
STEP_FEATURES = "features"
STEP_TRAIN    = "train"
STEP_TIMESERIES = "timeseries"
STEP_REPORT   = "report"
ALL_STEPS = [STEP_PROFILE, STEP_ANOMALY, STEP_FEATURES, STEP_TRAIN, STEP_REPORT]


class ReActAgent:
    """
    Python 级 ReAct 离线 Runner。

    每个 step 对应一次 Act + Observe 循环：
      1. Think  — 根据上一步 observation 决定下一步调用哪个工具、用什么参数
      2. Act    — 直接调用 scripts/ 下的分析模块（不经 MCP 网络层）
      3. Observe— 读取返回的 JSON 结果并打印摘要
      4. Reflect— 将结果写入 self.context，供下一步 Think 使用
    """

    def __init__(self, data_path: str, model: str = "react_agent",
                 dataset: str = "", target: str = ""):
        self.data_path = os.path.abspath(data_path)
        self.model = model
        self.dataset = dataset or os.path.splitext(os.path.basename(data_path))[0]
        self.target = target
        self.context: Dict[str, Any] = {}   # Reflect 阶段积累的上下文
        self.execution_log: List[Dict] = []  # 每步执行记录

        # 输出根目录
        self.output_root = os.path.join(_ROOT, "outputs", self.model, self.dataset)
        os.makedirs(self.output_root, exist_ok=True)
        logger.info(f"ReActAgent 初始化 | data={self.data_path} | model={self.model} | dataset={self.dataset}")

    # ── 内部工具：记录执行日志 ────────────────────────────────

    def _log_step(self, step: str, action: str, result: Any,
                  elapsed: float, status: str = "ok"):
        entry = {
            "step": step,
            "action": action,
            "status": status,
            "elapsed_s": round(elapsed, 3),
            "result_summary": str(result)[:300] if result else "",
        }
        self.execution_log.append(entry)
        self._save_log()

    def _save_log(self):
        log_dir = os.path.join(self.output_root, "workflow_log")
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, "react_execution_log.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.execution_log, f, ensure_ascii=False, indent=2)

    # ── Think 阶段：根据上下文决定参数 ───────────────────────

    def _think_anomaly_params(self) -> Dict[str, Any]:
        """根据画像决定异常检测参数（离线版，使用保守默认值）"""
        profile = self.context.get("profile", {})
        n_rows = profile.get("shape", {}).get("rows", 10000)
        # 行数越多，contamination 可以小一点（减少误报）
        contamination = 0.03 if n_rows > 20000 else 0.05
        return {"method": "isolation_forest", "contamination": contamination}

    def _think_target(self) -> str:
        """从画像中推断目标列，或使用用户指定值"""
        if self.target:
            return self.target
        profile = self.context.get("profile", {})
        candidates = profile.get("target_candidates", [])
        if candidates:
            target = candidates[0]
            logger.info(f"  [Think] 自动选择目标列: {target}")
            return target
        return ""

    # ── Step 1: profile_dataset ───────────────────────────────

    def step_profile(self) -> bool:
        logger.info("=" * 55)
        logger.info(f"[Act]  profile_dataset  →  {self.data_path}")
        t0 = time.time()
        try:
            from scripts.dataset_profiler import DatasetProfiler
            profiler = DatasetProfiler()
            result = profiler.profile(self.data_path, max_sample_rows=5)
            elapsed = time.time() - t0

            # Observe
            shape = result.get("shape", {})
            logger.info(f"[Obs]  行={shape.get('rows')}  列={shape.get('cols')}  "
                        f"时序={result.get('time_column')}  "
                        f"敏感字段={result.get('sensitive_columns', [])}")

            # Reflect：写入上下文
            self.context["profile"] = result
            out_dir = os.path.join(self.output_root, "step1_data_quality")
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, "profile.json"), "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)

            self._log_step(STEP_PROFILE, "profile_dataset", result, elapsed)
            return True
        except Exception as e:
            elapsed = time.time() - t0
            logger.error(f"[Error] profile_dataset 失败: {e}")
            self._log_step(STEP_PROFILE, "profile_dataset", None, elapsed, status="error")
            return False

    # ── Step 2: run_anomaly ───────────────────────────────────

    def step_anomaly(self) -> bool:
        logger.info("=" * 55)
        params = self._think_anomaly_params()
        logger.info(f"[Think] 异常检测参数 → {params}")
        logger.info(f"[Act]   run_anomaly  method={params['method']}  contamination={params['contamination']}")
        t0 = time.time()
        try:
            from scripts.fault_diagnosis import FaultDiagnosisAnalyzer
            analyzer = FaultDiagnosisAnalyzer()
            analyzer.load_data(self.data_path)
            result = analyzer.detect_anomalies(
                method=params["method"],
                contamination=params["contamination"],
            )
            elapsed = time.time() - t0

            anomaly_count = result.get("anomaly_count", 0)
            anomaly_rate  = result.get("anomaly_rate", 0)
            logger.info(f"[Obs]   异常点={anomaly_count}  异常率={anomaly_rate:.1%}")

            self.context["anomaly"] = result
            out_dir = os.path.join(self.output_root, "step4_anomaly")
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, f"anomaly_indices_{params['method']}.json"),
                      "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)

            self._log_step(STEP_ANOMALY, "run_anomaly", result, elapsed)
            return True
        except Exception as e:
            elapsed = time.time() - t0
            logger.error(f"[Error] run_anomaly 失败: {e}")
            self._log_step(STEP_ANOMALY, "run_anomaly", None, elapsed, status="error")
            return False

    # ── Step 3: select_features ───────────────────────────────

    def step_features(self) -> bool:
        logger.info("=" * 55)
        target = self._think_target()
        if not target:
            logger.warning("[Think] 未找到目标列，跳过特征选择")
            return True
        logger.info(f"[Act]   select_features  target={target}  method=tree")
        t0 = time.time()
        try:
            from scripts.feature_selector import FeatureSelector
            selector = FeatureSelector()
            result = selector.select(
                data_path=self.data_path,
                target=target,
                method="tree",
                top_k=10,
            )
            elapsed = time.time() - t0

            top_features = result.get("selected_features", [])[:5]
            logger.info(f"[Obs]   Top-5 特征: {top_features}")

            self.context["features"] = result
            self.context["selected_target"] = target
            out_dir = os.path.join(self.output_root, "step3_feature_selection")
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, "feature_importance.json"),
                      "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)

            self._log_step(STEP_FEATURES, "select_features", result, elapsed)
            return True
        except Exception as e:
            elapsed = time.time() - t0
            logger.error(f"[Error] select_features 失败: {e}")
            self._log_step(STEP_FEATURES, "select_features", None, elapsed, status="error")
            return False

    # ── Step 4: train_model ───────────────────────────────────

    def step_train(self) -> bool:
        logger.info("=" * 55)
        target = self.context.get("selected_target") or self._think_target()
        if not target:
            logger.warning("[Think] 无目标列，跳过模型训练")
            return True
        logger.info(f"[Act]   train_model  target={target}  task=auto")
        t0 = time.time()
        try:
            from scripts.auto_trainer import AutoTrainer
            trainer = AutoTrainer()
            result = trainer.train(
                data_path=self.data_path,
                target=target,
                task="auto",
            )
            elapsed = time.time() - t0

            best = result.get("best_model", {})
            logger.info(f"[Obs]   最优模型={best.get('name')}  "
                        f"R²={best.get('test_r2', best.get('test_accuracy', 'N/A'))}  "
                        f"RMSE={best.get('rmse', 'N/A')}")

            self.context["model"] = result
            out_dir = os.path.join(self.output_root, "step5_model_training")
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, "model_comparison.json"),
                      "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)

            self._log_step(STEP_TRAIN, "train_model", result, elapsed)
            return True
        except Exception as e:
            elapsed = time.time() - t0
            logger.error(f"[Error] train_model 失败: {e}")
            self._log_step(STEP_TRAIN, "train_model", None, elapsed, status="error")
            return False

    # ── Step 5: timeseries（可选）─────────────────────────────

    def step_timeseries(self) -> bool:
        logger.info("=" * 55)
        time_col = self.context.get("profile", {}).get("time_column")
        if not time_col:
            logger.warning("[Think] 未检测到时间列，跳过时序分析")
            return True
        logger.info(f"[Act]   run_timeseries  time_col={time_col}  task=trend_decomposition")
        t0 = time.time()
        try:
            from scripts.timeseries_analyzer import TimeSeriesAnalyzer
            analyzer = TimeSeriesAnalyzer(self.data_path)
            # 取数值列中第一个非时间列作为分析目标
            profile = self.context.get("profile", {})
            numeric_cols = [c for c in profile.get("columns", {})
                            if profile["columns"][c].get("dtype", "").startswith("float")
                            or profile["columns"][c].get("dtype", "").startswith("int")]
            target_col = numeric_cols[0] if numeric_cols else None
            if not target_col:
                logger.warning("[Think] 无数值列，跳过时序分析")
                return True

            result = analyzer.decompose_trend(col=target_col)
            elapsed = time.time() - t0
            logger.info(f"[Obs]   STL 趋势分解完成  col={target_col}")

            self.context["timeseries"] = result
            out_dir = os.path.join(self.output_root, "step2_eda")
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, "timeseries_decomposition.json"),
                      "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)

            self._log_step(STEP_TIMESERIES, "run_timeseries", result, elapsed)
            return True
        except Exception as e:
            elapsed = time.time() - t0
            logger.error(f"[Error] run_timeseries 失败: {e}")
            self._log_step(STEP_TIMESERIES, "run_timeseries", None, elapsed, status="error")
            return False

    # ── Step 6: 生成摘要报告（JSON，不调 LLM）────────────────

    def step_report(self) -> bool:
        logger.info("=" * 55)
        logger.info("[Act]   assemble_summary_report（离线版，无 LLM 文本）")
        t0 = time.time()
        summary = {
            "model": self.model,
            "dataset": self.dataset,
            "data_path": self.data_path,
            "profile":   self.context.get("profile", {}).get("shape"),
            "anomaly": {
                "count": self.context.get("anomaly", {}).get("anomaly_count"),
                "rate":  self.context.get("anomaly", {}).get("anomaly_rate"),
            },
            "top_features": self.context.get("features", {}).get("selected_features", [])[:5],
            "best_model":   self.context.get("model", {}).get("best_model", {}),
            "execution_log": self.execution_log,
            "note": "离线 ReAct 摘要报告；业务洞察与建议由 LLM 在真实 MCP 调用中生成",
        }
        elapsed = time.time() - t0

        report_path = os.path.join(self.output_root, "react_agent_summary.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

        logger.info(f"[Obs]   摘要报告已写入 → {report_path}")
        self._log_step(STEP_REPORT, "assemble_summary", summary, elapsed)
        return True

    # ── 主运行入口 ────────────────────────────────────────────

    def run(self, steps: List[str]) -> Dict[str, Any]:
        """
        按指定步骤列表顺序执行 ReAct 闭环。

        Args:
            steps: 步骤列表，如 ["profile", "anomaly", "features", "train", "report"]
                   传入 ["all"] 等同于 ALL_STEPS

        Returns:
            执行摘要字典
        """
        if steps == ["all"]:
            steps = ALL_STEPS

        logger.info(f"ReActAgent 开始运行 | 步骤: {steps}")
        total_start = time.time()
        results: Dict[str, bool] = {}

        step_map = {
            STEP_PROFILE:    self.step_profile,
            STEP_ANOMALY:    self.step_anomaly,
            STEP_FEATURES:   self.step_features,
            STEP_TRAIN:      self.step_train,
            STEP_TIMESERIES: self.step_timeseries,
            STEP_REPORT:     self.step_report,
        }

        for step in steps:
            if step not in step_map:
                logger.warning(f"未知步骤 '{step}'，已跳过")
                continue
            results[step] = step_map[step]()

        total_elapsed = time.time() - total_start
        passed = sum(1 for v in results.values() if v)
        logger.info("=" * 55)
        logger.info(f"完成  {passed}/{len(results)} 步成功  总耗时={total_elapsed:.1f}s")
        logger.info(f"输出目录 → {self.output_root}")

        return {
            "passed": passed,
            "total":  len(results),
            "results": results,
            "elapsed_s": round(total_elapsed, 2),
            "output_dir": self.output_root,
        }


# ── CLI 入口 ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ReAct Agent — Python 级工业数据分析离线 Runner",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--data",    required=True, help="数据文件路径或目录")
    parser.add_argument("--model",   default="react_agent", help="模型标识（用于输出目录隔离）")
    parser.add_argument("--dataset", default="", help="数据集名称（默认从文件名推断）")
    parser.add_argument("--target",  default="", help="目标列名（回归/分类任务）")
    parser.add_argument(
        "--steps",
        nargs="+",
        default=["all"],
        choices=[*ALL_STEPS, STEP_TIMESERIES, "all"],
        help=(
            "执行步骤列表（空格分隔）：\n"
            "  profile    数据画像\n"
            "  anomaly    异常检测\n"
            "  features   特征选择\n"
            "  train      模型训练\n"
            "  timeseries 时序分析（可选）\n"
            "  report     生成摘要报告\n"
            "  all        全部步骤（默认）"
        ),
    )
    args = parser.parse_args()

    agent = ReActAgent(
        data_path=args.data,
        model=args.model,
        dataset=args.dataset,
        target=args.target,
    )
    summary = agent.run(steps=args.steps)

    print("\n" + "=" * 55)
    print(f"  执行完成  {summary['passed']}/{summary['total']} 步成功")
    print(f"  总耗时   {summary['elapsed_s']}s")
    print(f"  输出目录  {summary['output_dir']}")
    print("=" * 55)
    sys.exit(0 if summary["passed"] == summary["total"] else 1)


if __name__ == "__main__":
    main()

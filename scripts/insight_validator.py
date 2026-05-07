#!/usr/bin/env python3
"""
业务洞察校验器 (Insight Validator)

强制约束 LLM 生成的业务洞察符合：
1. 4 要素结构：现象 / 模式 / 根因 / 影响 缺一不可
2. 禁用空话：拒绝"数据质量良好"、"准确率较高"等模糊表述
3. 数字溯源：报告中所有数字必须能在中间产物 JSON 里找到出处（防 LLM 幻觉）
4. 量化要求：每条洞察至少含 1 个具体数值（数字/百分比/单位）

使用：
    from scripts.insight_validator import InsightValidator
    validator = InsightValidator(intermediate_dir="outputs/kimi/dataset/")
    result = validator.validate_insight({
        "phenomenon": "上周3号产线日均能耗 850 kWh",
        "pattern": "周末 vs 工作日差异 30%",
        "root_cause": "夜班空载运行",
        "impact": "年浪费 18 万元"
    })
"""

import json
import os
import re
from typing import Dict, List, Tuple, Any


# 禁用空话词表（LLM 偷懒高频用语）
BANNED_PHRASES = [
    "数据质量良好", "数据质量较好", "整体良好",
    "准确率较高", "效果较好", "表现优秀",
    "建议使用模型监测", "建议使用模型分析", "建议进一步分析",
    "需要进一步分析", "需要更多数据", "有待研究",
    "可能存在问题", "可能需要", "或许可以",
    "分析结果良好", "分析结果不错",
    "无明显异常", "未发现明显",
    "建议关注", "值得关注",  # 太空，必须说"建议关注 XX 指标，因为 XX"
]

# 4 要素必填字段
REQUIRED_FIELDS = ["phenomenon", "pattern", "root_cause", "impact"]

# 字段最小字数要求（防止只写"高"、"低"这种）
MIN_FIELD_LENGTH = {
    "phenomenon": 8,
    "pattern": 8,
    "root_cause": 6,
    "impact": 6,
}

# 必须含数字的字段（强制量化）
NUMERIC_REQUIRED_FIELDS = ["phenomenon", "impact"]


class InsightValidator:
    """洞察质量校验器"""

    def __init__(self, intermediate_dir: str = ""):
        """
        Args:
            intermediate_dir: 中间产物目录，用于数字溯源校验
                              通常是 outputs/{model}/{dataset}/
        """
        self.intermediate_dir = intermediate_dir
        self._intermediate_numbers: List[float] = []
        if intermediate_dir and os.path.isdir(intermediate_dir):
            self._load_intermediate_numbers()

    def _load_intermediate_numbers(self):
        """提取中间产物 JSON 中所有出现过的数字（含小数）"""
        for root, _, files in os.walk(self.intermediate_dir):
            for fn in files:
                if not fn.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(root, fn), "r", encoding="utf-8") as f:
                        text = f.read()
                    # 提取所有数字（含小数和负数）
                    nums = re.findall(r"-?\d+\.?\d*", text)
                    for n in nums:
                        try:
                            self._intermediate_numbers.append(float(n))
                        except ValueError:
                            pass
                except (IOError, json.JSONDecodeError):
                    continue

    # ------------------------------------------------------------------
    # 单条洞察校验
    # ------------------------------------------------------------------

    def validate_insight(self, insight: Dict[str, str]) -> Dict[str, Any]:
        """
        校验单条洞察是否符合 4 要素结构 + 量化 + 无空话。

        Returns:
            {valid: bool, errors: [...], warnings: [...]}
        """
        errors: List[str] = []
        warnings: List[str] = []

        # 1. 4 要素必填检查
        for field in REQUIRED_FIELDS:
            if field not in insight or not str(insight[field]).strip():
                errors.append(f"缺失必填字段「{field}」（4 要素：现象/模式/根因/影响）")

        # 2. 字段长度检查
        for field, min_len in MIN_FIELD_LENGTH.items():
            if field in insight:
                content = str(insight[field]).strip()
                if 0 < len(content) < min_len:
                    errors.append(
                        f"字段「{field}」过短（{len(content)} 字 < 最小 {min_len} 字）"
                        f"，内容：'{content}'"
                    )

        # 3. 禁用空话检查
        full_text = " ".join(str(v) for v in insight.values())
        for phrase in BANNED_PHRASES:
            if phrase in full_text:
                errors.append(f"包含禁用空话「{phrase}」，必须用具体描述替换")

        # 4. 必须含数字的字段检查
        for field in NUMERIC_REQUIRED_FIELDS:
            if field in insight and insight[field]:
                if not re.search(r"\d", str(insight[field])):
                    errors.append(
                        f"字段「{field}」必须含具体数值（数字/百分比/单位），"
                        f"当前内容：'{insight[field]}'"
                    )

        # 5. 数字溯源（如果加载了中间产物）
        if self._intermediate_numbers:
            cited_nums = re.findall(r"\d+\.?\d*", full_text)
            for cn in cited_nums:
                try:
                    cn_val = float(cn)
                except ValueError:
                    continue
                # 跳过过小的常量（如年份、ID）
                if cn_val < 0.01 or cn_val > 1e9:
                    continue
                # 容忍 1% 浮点误差
                matched = any(
                    abs(cn_val - x) < max(0.01, abs(x) * 0.01)
                    for x in self._intermediate_numbers
                )
                if not matched:
                    warnings.append(
                        f"数字 {cn} 在中间产物中未找到溯源（可能是 LLM 编造）。"
                        f"请核实是否真实存在。"
                    )

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "insight": insight,
        }

    # ------------------------------------------------------------------
    # 批量校验
    # ------------------------------------------------------------------

    def validate_insights(self, insights: List[Dict[str, str]],
                          min_count: int = 5) -> Dict[str, Any]:
        """
        批量校验多条洞察 + 数量要求。

        Args:
            insights: 洞察列表
            min_count: 最少需要的有效洞察条数（SKILL.md 红线 ≥ 5 条）
        """
        results = [self.validate_insight(i) for i in insights]
        valid_count = sum(1 for r in results if r["valid"])

        all_errors = []
        all_warnings = []
        for idx, r in enumerate(results):
            for e in r["errors"]:
                all_errors.append(f"[第 {idx+1} 条] {e}")
            for w in r["warnings"]:
                all_warnings.append(f"[第 {idx+1} 条] {w}")

        # 数量门槛
        count_pass = valid_count >= min_count
        if not count_pass:
            all_errors.append(
                f"有效洞察数量不足：{valid_count} < 最低要求 {min_count} 条"
            )

        return {
            "total": len(insights),
            "valid_count": valid_count,
            "min_required": min_count,
            "passed": count_pass and len(all_errors) == 0,
            "errors": all_errors,
            "warnings": all_warnings,
            "per_insight": results,
        }

    # ------------------------------------------------------------------
    # 报告级数字溯源
    # ------------------------------------------------------------------

    def trace_numbers_in_report(self, report_text: str,
                                 tolerance_pct: float = 1.0) -> Dict[str, Any]:
        """
        校验报告中所有数字是否能在中间产物中找到出处。

        Args:
            report_text: 报告全文
            tolerance_pct: 浮点误差容忍度（默认 1%）

        Returns:
            {total_numbers, traced, untraced, untraced_list}
        """
        if not self._intermediate_numbers:
            return {"error": "未加载中间产物，无法溯源"}

        # 提取报告中所有数字
        nums_in_report = re.findall(r"\d+\.?\d*", report_text)
        # 过滤过小或过大的（年份、ID 等噪声）
        meaningful = []
        for n in nums_in_report:
            try:
                v = float(n)
                if 0.01 < v < 1e9:
                    meaningful.append(v)
            except ValueError:
                continue

        traced = []
        untraced = []
        for v in meaningful:
            tol = max(0.01, abs(v) * tolerance_pct / 100)
            if any(abs(v - x) < tol for x in self._intermediate_numbers):
                traced.append(v)
            else:
                untraced.append(v)

        return {
            "total_numbers": len(meaningful),
            "traced": len(traced),
            "untraced": len(untraced),
            "untraced_values": untraced[:20],  # 最多列前 20 个
            "trace_rate": (
                round(len(traced) / len(meaningful) * 100, 1)
                if meaningful else 100.0
            ),
            "verdict": "PASS" if len(untraced) == 0 else "FAIL",
        }


def validate_insight_batch(insights_json_path: str,
                           intermediate_dir: str = "",
                           min_count: int = 5) -> Dict[str, Any]:
    """便捷函数：从 JSON 文件加载洞察并批量校验"""
    with open(insights_json_path, "r", encoding="utf-8") as f:
        insights = json.load(f)
    if isinstance(insights, dict):
        insights = insights.get("insights", [])

    validator = InsightValidator(intermediate_dir)
    return validator.validate_insights(insights, min_count=min_count)


if __name__ == "__main__":
    # 自测试
    validator = InsightValidator()

    # 案例 1：合格洞察
    good = {
        "phenomenon": "上周 3 号产线日均能耗 850 kWh",
        "pattern": "周末 vs 工作日能耗差异 30%",
        "root_cause": "夜班期间设备空载运行未及时停机",
        "impact": "年浪费约 18 万元",
    }
    print("=== 合格洞察 ===")
    print(json.dumps(validator.validate_insight(good), ensure_ascii=False, indent=2))

    # 案例 2：空话洞察
    bad = {
        "phenomenon": "数据质量良好",
        "pattern": "整体表现优秀",
        "root_cause": "可能存在问题",
        "impact": "需要进一步分析",
    }
    print("\n=== 空话洞察 ===")
    print(json.dumps(validator.validate_insight(bad), ensure_ascii=False, indent=2))

    # 案例 3：缺字段
    incomplete = {"phenomenon": "异常率 12.3%"}
    print("\n=== 缺字段 ===")
    print(json.dumps(validator.validate_insight(incomplete), ensure_ascii=False, indent=2))

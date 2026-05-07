#!/usr/bin/env python3
"""
分析结果校验器
防止大模型"幻觉"，确保分析结论有充分的数据支撑
"""

import json
import argparse
from typing import Dict, List, Any, Tuple


class ResultValidator:
    """结果校验器"""

    def __init__(self):
        self.validation_errors = []
        self.validation_warnings = []

    def validate(self, analysis_result: Dict[str, Any], validation_rules: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        校验分析结果

        Args:
            analysis_result: 分析结果
            validation_rules: 校验规则（可选）

        Returns:
            校验结果
        """
        self.validation_errors = []
        self.validation_warnings = []

        # 执行各项校验
        self._validate_data_support(analysis_result)
        self._validate_parameter_legality(analysis_result)
        self._validate_logical_consistency(analysis_result)
        self._calculate_confidence(analysis_result)

        # 应用自定义规则
        if validation_rules:
            self._apply_custom_rules(analysis_result, validation_rules)

        return {
            "is_valid": len(self.validation_errors) == 0,
            "errors": self.validation_errors,
            "warnings": self.validation_warnings,
            "confidence_score": self._calculate_overall_confidence(analysis_result),
            "recommendations": self._generate_fix_recommendations()
        }

    def _validate_data_support(self, result: Dict[str, Any]):
        """验证数据支撑"""
        # 检查是否有足够的数据点
        if "anomaly_detection" in result:
            total_points = result["anomaly_detection"].get("total_points", 0)
            if total_points < 10:
                self.validation_warnings.append(f"数据点数量较少（{total_points}），可能影响分析准确性")

        # 检查预测是否有历史数据支撑
        if "forecast" in result:
            forecast = result["forecast"]
            if forecast.get("confidence", 0) < 0.5:
                self.validation_warnings.append("预测置信度较低，建议增加历史数据")

    def _validate_parameter_legality(self, result: Dict[str, Any]):
        """验证参数合法性"""
        # 检查统计值的合理性
        if "anomaly_detection" in result:
            stats = result["anomaly_detection"].get("statistics", {})

            # 检查标准差
            std = stats.get("std", 0)
            mean = stats.get("mean", 0)
            if mean != 0 and std / abs(mean) > 10:
                self.validation_warnings.append("数据波动性极大，可能存在数据质量问题")

            # 检查异常率
            anomaly_rate = result["anomaly_detection"].get("anomaly_rate", 0)
            if anomaly_rate > 0.5:
                self.validation_errors.append(f"异常率过高（{anomaly_rate*100:.1f}%），数据可能不可靠")

        # 检查预测值的合理性
        if "forecast" in result:
            forecast_data = result["forecast"].get("forecast", [])
            for item in forecast_data:
                value = item.get("value", 0)
                lower = item.get("lower", 0)
                upper = item.get("upper", 0)

                if not (lower <= value <= upper):
                    self.validation_errors.append(f"预测值 {value} 不在置信区间 [{lower}, {upper}] 内")

    def _validate_logical_consistency(self, result: Dict[str, Any]):
        """验证逻辑一致性"""
        # 检查趋势与预测的一致性
        if "trend_analysis" in result and "forecast" in result:
            trend_direction = result["trend_analysis"].get("trend_direction", "")
            forecast_data = result["forecast"].get("forecast", [])

            if len(forecast_data) >= 2:
                first_value = forecast_data[0].get("value", 0)
                last_value = forecast_data[-1].get("value", 0)

                forecast_trend = "increasing" if last_value > first_value else "decreasing" if last_value < first_value else "stable"

                if trend_direction != forecast_trend and trend_direction != "stable":
                    self.validation_warnings.append(
                        f"趋势分析（{trend_direction}）与预测趋势（{forecast_trend}）不一致"
                    )

    def _calculate_confidence(self, result: Dict[str, Any]):
        """计算置信度"""
        # 为每个分析模块计算置信度
        if "anomaly_detection" in result:
            anomaly = result["anomaly_detection"]
            total_points = anomaly.get("total_points", 0)

            # 数据点越多，置信度越高
            confidence = min(total_points / 100, 1.0)
            anomaly["confidence"] = confidence

        if "trend_analysis" in result:
            trend = result["trend_analysis"]
            volatility = trend.get("volatility", 1.0)

            # 波动性越小，置信度越高
            confidence = max(0, 1 - volatility)
            trend["confidence"] = confidence

    def _calculate_overall_confidence(self, result: Dict[str, Any]) -> float:
        """计算总体置信度"""
        confidences = []

        for key in ["anomaly_detection", "trend_analysis", "forecast"]:
            if key in result and "confidence" in result[key]:
                confidences.append(result[key]["confidence"])

        if not confidences:
            return 0.5

        # 计算加权平均
        return sum(confidences) / len(confidences)

    def _apply_custom_rules(self, result: Dict[str, Any], rules: Dict[str, Any]):
        """应用自定义校验规则"""
        for rule_name, rule_config in rules.items():
            rule_type = rule_config.get("type", "")
            threshold = rule_config.get("threshold", 0)

            if rule_type == "max_anomaly_rate":
                if "anomaly_detection" in result:
                    rate = result["anomaly_detection"].get("anomaly_rate", 0)
                    if rate > threshold:
                        self.validation_errors.append(f"违反规则 {rule_name}: 异常率 {rate:.2%} 超过阈值 {threshold:.2%}")

            elif rule_type == "min_confidence":
                overall_confidence = self._calculate_overall_confidence(result)
                if overall_confidence < threshold:
                    self.validation_warnings.append(f"违反规则 {rule_name}: 置信度 {overall_confidence:.2%} 低于阈值 {threshold:.2%}")

    def _generate_fix_recommendations(self) -> List[str]:
        """生成修正建议"""
        recommendations = []

        if any("数据点数量较少" in w for w in self.validation_warnings):
            recommendations.append("建议收集更多历史数据以提高分析准确性")

        if any("异常率过高" in e for e in self.validation_errors):
            recommendations.append("建议检查数据采集系统，排查数据质量问题")

        if any("置信度较低" in w for w in self.validation_warnings):
            recommendations.append("建议使用更复杂的模型或增加特征工程")

        if any("不一致" in w for w in self.validation_warnings):
            recommendations.append("建议重新检查分析逻辑，确保各模块结论一致")

        return recommendations if recommendations else ["分析结果通过校验，无需修正"]


def main():
    parser = argparse.ArgumentParser(description="分析结果校验器")
    parser.add_argument("--analysis-result", required=True, help="分析结果 JSON 文件")
    parser.add_argument("--validation-rules", help="校验规则 JSON 文件（可选）")
    parser.add_argument("--output", help="输出文件路径")

    args = parser.parse_args()

    # 加载分析结果
    with open(args.analysis_result, 'r', encoding='utf-8') as f:
        analysis_result = json.load(f)

    # 加载校验规则
    validation_rules = None
    if args.validation_rules:
        with open(args.validation_rules, 'r', encoding='utf-8') as f:
            validation_rules = json.load(f)

    # 执行校验
    validator = ResultValidator()
    validation_result = validator.validate(analysis_result, validation_rules)

    # 输出结果
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(validation_result, f, ensure_ascii=False, indent=2)
        print(f"校验结果已保存到: {args.output}")
    else:
        print(json.dumps(validation_result, ensure_ascii=False, indent=2))

    # 打印摘要
    print(f"\n校验状态: {'通过' if validation_result['is_valid'] else '失败'}")
    print(f"错误数: {len(validation_result['errors'])}")
    print(f"警告数: {len(validation_result['warnings'])}")
    print(f"置信度分数: {validation_result['confidence_score']:.2%}")


if __name__ == "__main__":
    main()

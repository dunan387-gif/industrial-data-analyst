#!/usr/bin/env python3
"""
工业数据分析意图解析器
识别用户查询中的分析意图、关键实体和数据源类型
"""

import json
import re
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Any


class IntentParser:
    """意图解析器"""

    # 分析类型关键词映射
    INTENT_KEYWORDS = {
        "fault_diagnosis": ["故障", "异常", "停机", "报警", "错误", "失效", "损坏"],
        "trend_forecast": ["预测", "预计", "趋势", "未来", "下个月", "明年"],
        "root_cause_analysis": ["原因", "为什么", "根因", "导致"],
        "anomaly_detection": ["异常", "不正常", "突然", "波动"],
        "correlation_analysis": ["关系", "影响", "相关", "关联"],
        "rul_prediction": ["寿命", "还能用", "剩余", "更换"],
        "defect_detection": ["缺陷", "瑕疵", "质量", "表面"],
        "vibration_analysis": ["振动", "震动", "频率", "轴承"],
        "energy_analysis": ["能耗", "用电", "功率", "电量"],
        "performance_analysis": ["效率", "产能", "性能", "OEE"]
    }

    # 实体类型正则表达式
    ENTITY_PATTERNS = {
        "production_line": r"(\d+号?产线|产线\d+|生产线\d+)",
        "equipment": r"(\d+号?[机床设备]|[机床设备]\d+)",
        "time_range": r"(昨天|今天|上月|本月|去年|上周|最近\d+天|\d+月\d+日)",
        "metric": r"(温度|压力|振动|能耗|用电|产量|效率|转速|电流)",
    }

    def __init__(self):
        pass

    def parse(self, query: str) -> Dict[str, Any]:
        """
        解析用户查询

        Args:
            query: 用户的原始查询文本

        Returns:
            解析结果字典
        """
        result = {
            "original_query": query,
            "intents": self._identify_intents(query),
            "entities": self._extract_entities(query),
            "data_source_type": self._infer_data_source(query),
            "priority": self._calculate_priority(query),
            "confidence": 0.0
        }

        # 计算置信度
        result["confidence"] = self._calculate_confidence(result)

        return result

    def _identify_intents(self, query: str) -> List[str]:
        """识别分析意图"""
        intents = []
        query_lower = query.lower()

        for intent, keywords in self.INTENT_KEYWORDS.items():
            if any(keyword in query_lower for keyword in keywords):
                intents.append(intent)

        # 如果没有识别到任何意图，默认为通用分析
        if not intents:
            intents.append("general_analysis")

        return intents

    def _extract_entities(self, query: str) -> Dict[str, Any]:
        """提取关键实体"""
        entities = {}

        for entity_type, pattern in self.ENTITY_PATTERNS.items():
            matches = re.findall(pattern, query)
            if matches:
                entities[entity_type] = matches[0] if len(matches) == 1 else matches

        # 提取数值
        numbers = re.findall(r'\d+\.?\d*', query)
        if numbers:
            entities["numbers"] = [float(n) for n in numbers]

        return entities

    def _infer_data_source(self, query: str) -> List[str]:
        """推断数据源类型"""
        data_sources = []
        query_lower = query.lower()

        source_keywords = {
            "time_series": ["历史", "趋势", "时序", "连续"],
            "image": ["图像", "图片", "照片", "表面", "缺陷"],
            "vibration": ["振动", "频率", "轴承"],
            "log": ["日志", "记录", "报警"],
            "sensor": ["传感器", "监测", "实时"]
        }

        for source_type, keywords in source_keywords.items():
            if any(keyword in query_lower for keyword in keywords):
                data_sources.append(source_type)

        # 默认为时序数据
        if not data_sources:
            data_sources.append("time_series")

        return data_sources

    def _calculate_priority(self, query: str) -> str:
        """计算任务优先级"""
        high_priority_keywords = ["紧急", "立即", "马上", "停机", "故障"]
        medium_priority_keywords = ["尽快", "今天", "本周"]

        query_lower = query.lower()

        if any(keyword in query_lower for keyword in high_priority_keywords):
            return "high"
        elif any(keyword in query_lower for keyword in medium_priority_keywords):
            return "medium"
        else:
            return "normal"

    def _calculate_confidence(self, result: Dict[str, Any]) -> float:
        """计算解析置信度"""
        confidence = 0.0

        # 识别到意图 +0.4
        if result["intents"] and "general_analysis" not in result["intents"]:
            confidence += 0.4

        # 提取到实体 +0.3
        if result["entities"]:
            confidence += 0.3

        # 推断出数据源 +0.3
        if result["data_source_type"]:
            confidence += 0.3

        return min(confidence, 1.0)


def main():
    parser = argparse.ArgumentParser(description="工业数据分析意图解析器")
    parser.add_argument("--query", required=True, help="用户查询文本")
    parser.add_argument("--output", help="输出JSON文件路径")

    args = parser.parse_args()

    # 解析意图
    intent_parser = IntentParser()
    result = intent_parser.parse(args.query)

    # 输出结果
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"解析结果已保存到: {args.output}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

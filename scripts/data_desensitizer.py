#!/usr/bin/env python3
"""
敏感字段脱敏处理模块

支持：
- 自动识别敏感字段（设备编号、工厂位置、操作人员、IP地址等）
- 多种脱敏策略（掩码、哈希、泛化、置换）
- 脱敏日志记录
- 可逆/不可逆脱敏
"""

import os
import re
import json
import hashlib
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime


class DataDesensitizer:
    """数据脱敏处理器"""

    # 敏感字段识别规则
    SENSITIVE_PATTERNS = {
        # 人员信息
        "person_name": {
            "column_patterns": ["name", "姓名", "操作员", "operator", "user", "员工", "worker"],
            "strategy": "mask",
            "risk_level": "high"
        },
        "phone": {
            "column_patterns": ["phone", "tel", "mobile", "电话", "手机"],
            "value_pattern": r"1[3-9]\d{9}",
            "strategy": "partial_mask",
            "risk_level": "high"
        },
        "id_card": {
            "column_patterns": ["id_card", "身份证", "idcard"],
            "value_pattern": r"\d{17}[\dXx]",
            "strategy": "partial_mask",
            "risk_level": "critical"
        },
        "email": {
            "column_patterns": ["email", "邮箱", "mail"],
            "value_pattern": r"[\w.-]+@[\w.-]+\.\w+",
            "strategy": "partial_mask",
            "risk_level": "medium"
        },

        # 设备/位置信息
        "device_id": {
            "column_patterns": ["device_id", "设备编号", "machine_id", "equipment", "serial"],
            "strategy": "hash",
            "risk_level": "medium"
        },
        "factory": {
            "column_patterns": ["factory", "工厂", "plant", "site", "location", "地点", "车间", "workshop"],
            "strategy": "generalize",
            "risk_level": "medium"
        },
        "ip_address": {
            "column_patterns": ["ip", "ip_address", "host"],
            "value_pattern": r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
            "strategy": "partial_mask",
            "risk_level": "medium"
        },

        # 业务敏感
        "order_id": {
            "column_patterns": ["order", "订单", "batch", "批次"],
            "strategy": "hash",
            "risk_level": "low"
        },
        "price": {
            "column_patterns": ["price", "cost", "价格", "成本", "金额"],
            "strategy": "range",
            "risk_level": "medium"
        }
    }

    def __init__(self, salt: str = "industrial_skill_2024"):
        """
        Args:
            salt: 哈希脱敏的盐值
        """
        self.salt = salt
        self.desensitization_log: List[Dict] = []
        self.mapping: Dict[str, Dict] = {}  # 可逆脱敏的映射表

    def detect_sensitive_columns(self, df: pd.DataFrame) -> Dict[str, Dict]:
        """
        自动检测敏感列

        Returns:
            {
                "column_name": {
                    "type": "person_name",
                    "risk_level": "high",
                    "strategy": "mask",
                    "sample_values": [...]
                }
            }
        """
        sensitive_cols = {}

        for col in df.columns:
            col_lower = col.lower()

            for sens_type, config in self.SENSITIVE_PATTERNS.items():
                # 检查列名匹配
                for pattern in config.get("column_patterns", []):
                    if pattern.lower() in col_lower:
                        sensitive_cols[col] = {
                            "type": sens_type,
                            "risk_level": config["risk_level"],
                            "strategy": config["strategy"],
                            "match_reason": f"列名包含 '{pattern}'",
                            "sample_values": df[col].dropna().head(3).tolist()
                        }
                        break

                # 检查值模式匹配
                if col not in sensitive_cols and "value_pattern" in config:
                    pattern = config["value_pattern"]
                    sample = df[col].dropna().astype(str).head(100)
                    match_count = sample.str.contains(pattern, regex=True, na=False).sum()
                    if match_count > len(sample) * 0.5:  # 超过50%匹配
                        sensitive_cols[col] = {
                            "type": sens_type,
                            "risk_level": config["risk_level"],
                            "strategy": config["strategy"],
                            "match_reason": f"值匹配模式 '{pattern}'",
                            "sample_values": df[col].dropna().head(3).tolist()
                        }

        return sensitive_cols

    def desensitize(self, df: pd.DataFrame, columns: Dict[str, str] = None,
                    auto_detect: bool = True) -> Tuple[pd.DataFrame, Dict]:
        """
        执行脱敏处理

        Args:
            df: 原始数据
            columns: 指定列和策略 {"col_name": "mask|hash|generalize|range"}
            auto_detect: 是否自动检测敏感列

        Returns:
            (脱敏后的 DataFrame, 脱敏报告)
        """
        df_masked = df.copy()
        report = {
            "timestamp": datetime.now().isoformat(),
            "original_rows": len(df),
            "original_columns": len(df.columns),
            "desensitized_columns": [],
            "risk_summary": {"critical": 0, "high": 0, "medium": 0, "low": 0}
        }

        # 自动检测
        if auto_detect:
            detected = self.detect_sensitive_columns(df)
            if columns:
                # 合并手动指定和自动检测
                for col, strategy in columns.items():
                    if col in detected:
                        detected[col]["strategy"] = strategy
                    else:
                        detected[col] = {"strategy": strategy, "type": "manual", "risk_level": "medium"}
            columns_to_process = detected
        else:
            columns_to_process = {col: {"strategy": strategy, "type": "manual", "risk_level": "medium"}
                                  for col, strategy in (columns or {}).items()}

        # 执行脱敏
        for col, config in columns_to_process.items():
            if col not in df_masked.columns:
                continue

            strategy = config.get("strategy", "mask")
            risk = config.get("risk_level", "medium")

            original_sample = df_masked[col].dropna().head(3).tolist()

            if strategy == "mask":
                df_masked[col] = self._mask(df_masked[col])
            elif strategy == "partial_mask":
                df_masked[col] = self._partial_mask(df_masked[col])
            elif strategy == "hash":
                df_masked[col] = self._hash(df_masked[col])
            elif strategy == "generalize":
                df_masked[col] = self._generalize(df_masked[col])
            elif strategy == "range":
                df_masked[col] = self._range(df_masked[col])
            elif strategy == "shuffle":
                df_masked[col] = self._shuffle(df_masked[col])

            masked_sample = df_masked[col].dropna().head(3).tolist()

            report["desensitized_columns"].append({
                "column": col,
                "type": config.get("type", "unknown"),
                "strategy": strategy,
                "risk_level": risk,
                "original_sample": original_sample,
                "masked_sample": masked_sample
            })
            report["risk_summary"][risk] = report["risk_summary"].get(risk, 0) + 1

        self.desensitization_log.append(report)
        return df_masked, report

    def _mask(self, series: pd.Series) -> pd.Series:
        """完全掩码：用 *** 替换"""
        return series.apply(lambda x: "***" if pd.notna(x) else x)

    def _partial_mask(self, series: pd.Series) -> pd.Series:
        """部分掩码：保留首尾，中间用 * 替换"""
        def mask_value(val):
            if pd.isna(val):
                return val
            s = str(val)
            if len(s) <= 4:
                return s[0] + "*" * (len(s) - 1)
            return s[:2] + "*" * (len(s) - 4) + s[-2:]
        return series.apply(mask_value)

    def _hash(self, series: pd.Series) -> pd.Series:
        """哈希脱敏：MD5 哈希（不可逆）"""
        def hash_value(val):
            if pd.isna(val):
                return val
            h = hashlib.md5((str(val) + self.salt).encode()).hexdigest()[:8]
            return f"H_{h}"
        return series.apply(hash_value)

    def _generalize(self, series: pd.Series) -> pd.Series:
        """泛化：用类别代替具体值"""
        unique_vals = series.dropna().unique()
        mapping = {v: f"类别_{i+1}" for i, v in enumerate(unique_vals)}
        self.mapping[series.name] = mapping
        return series.map(lambda x: mapping.get(x, x) if pd.notna(x) else x)

    def _range(self, series: pd.Series) -> pd.Series:
        """范围化：数值转为区间"""
        if not pd.api.types.is_numeric_dtype(series):
            return series

        def to_range(val):
            if pd.isna(val):
                return val
            if val < 100:
                return "0-100"
            elif val < 1000:
                return "100-1000"
            elif val < 10000:
                return "1000-10000"
            else:
                return ">10000"
        return series.apply(to_range)

    def _shuffle(self, series: pd.Series) -> pd.Series:
        """置换：随机打乱顺序（保留分布）"""
        values = series.dropna().values.copy()
        np.random.shuffle(values)
        result = series.copy()
        result[series.notna()] = values
        return result

    def save_report(self, output_path: str) -> str:
        """保存脱敏报告"""
        report_file = os.path.join(output_path, "desensitization_report.json")
        os.makedirs(output_path, exist_ok=True)

        with open(report_file, "w", encoding="utf-8") as f:
            json.dump({
                "logs": self.desensitization_log,
                "total_operations": len(self.desensitization_log)
            }, f, ensure_ascii=False, indent=2)

        return report_file


def desensitize_file(input_path: str, output_path: str = None,
                     auto_detect: bool = True) -> Tuple[str, Dict]:
    """
    便捷函数：脱敏文件

    Args:
        input_path: 输入 CSV 文件路径
        output_path: 输出路径（默认在原文件名后加 _masked）
        auto_detect: 是否自动检测敏感列

    Returns:
        (输出文件路径, 脱敏报告)
    """
    df = pd.read_csv(input_path)
    desensitizer = DataDesensitizer()
    df_masked, report = desensitizer.desensitize(df, auto_detect=auto_detect)

    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_masked{ext}"

    df_masked.to_csv(output_path, index=False)
    return output_path, report

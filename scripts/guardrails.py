#!/usr/bin/env python3
"""
自学习护栏系统
实现输入校验、输出校验、异常拦截和自适应规则学习
"""

import os
import re
import json
import hashlib
from typing import Dict, List, Any, Optional, Callable, Union
from datetime import datetime
from enum import Enum


class ValidationLevel(Enum):
    """校验级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidationResult:
    """校验结果"""
    
    def __init__(self, passed: bool, level: ValidationLevel = ValidationLevel.INFO,
                 message: str = "", details: Optional[Dict] = None):
        self.passed = passed
        self.level = level
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return {
            "passed": self.passed,
            "level": self.level.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp
        }


class InputGuardrail:
    """输入护栏"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.rules: List[Dict] = []
        self.history: List[Dict] = []
        
        # 默认规则
        self._init_default_rules()
    
    def _init_default_rules(self):
        """初始化默认规则"""
        # SQL 注入检测
        self.add_rule(
            name="sql_injection",
            pattern=r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER)\b.*\b(FROM|INTO|TABLE|WHERE)\b)",
            level=ValidationLevel.CRITICAL,
            message="检测到潜在的 SQL 注入"
        )
        
        # 路径遍历检测
        self.add_rule(
            name="path_traversal",
            pattern=r"(\.\.\/|\.\.\\|%2e%2e%2f)",
            level=ValidationLevel.CRITICAL,
            message="检测到路径遍历攻击"
        )
        
        # 命令注入检测
        self.add_rule(
            name="command_injection",
            pattern=r"(\||;|`|\$\(|&&|\|\|)",
            level=ValidationLevel.WARNING,
            message="检测到潜在的命令注入字符"
        )
        
        # 敏感信息检测
        self.add_rule(
            name="sensitive_keywords",
            pattern=r"\b(password|secret|token|api_key|private_key)\b",
            level=ValidationLevel.WARNING,
            message="输入包含敏感关键词"
        )
    
    def add_rule(self, name: str, pattern: str, level: ValidationLevel,
                 message: str, enabled: bool = True):
        """添加校验规则"""
        self.rules.append({
            "name": name,
            "pattern": pattern,
            "level": level,
            "message": message,
            "enabled": enabled,
            "hit_count": 0
        })
    
    def validate(self, input_data: Union[str, Dict]) -> ValidationResult:
        """校验输入"""
        if isinstance(input_data, dict):
            input_str = json.dumps(input_data, ensure_ascii=False)
        else:
            input_str = str(input_data)
        
        violations = []
        max_level = ValidationLevel.INFO
        
        for rule in self.rules:
            if not rule["enabled"]:
                continue
            
            if re.search(rule["pattern"], input_str, re.IGNORECASE):
                rule["hit_count"] += 1
                violations.append({
                    "rule": rule["name"],
                    "level": rule["level"].value,
                    "message": rule["message"]
                })
                
                if rule["level"].value > max_level.value:
                    max_level = rule["level"]
        
        passed = len(violations) == 0 or max_level in [ValidationLevel.INFO, ValidationLevel.WARNING]
        
        result = ValidationResult(
            passed=passed,
            level=max_level,
            message=f"检测到 {len(violations)} 个问题" if violations else "输入校验通过",
            details={"violations": violations}
        )
        
        self.history.append({
            "input_hash": hashlib.md5(input_str.encode()).hexdigest()[:8],
            "result": result.to_dict()
        })
        
        return result
    
    def validate_data_schema(self, data: Dict, schema: Dict) -> ValidationResult:
        """校验数据 schema"""
        violations = []
        
        # 检查必需字段
        for field in schema.get("required", []):
            if field not in data:
                violations.append({
                    "field": field,
                    "issue": "missing_required_field"
                })
        
        # 检查字段类型
        for field, expected_type in schema.get("types", {}).items():
            if field in data:
                actual_type = type(data[field]).__name__
                if actual_type != expected_type:
                    violations.append({
                        "field": field,
                        "issue": "type_mismatch",
                        "expected": expected_type,
                        "actual": actual_type
                    })
        
        # 检查值范围
        for field, constraints in schema.get("constraints", {}).items():
            if field in data:
                value = data[field]
                if "min" in constraints and value < constraints["min"]:
                    violations.append({
                        "field": field,
                        "issue": "below_minimum",
                        "value": value,
                        "min": constraints["min"]
                    })
                if "max" in constraints and value > constraints["max"]:
                    violations.append({
                        "field": field,
                        "issue": "above_maximum",
                        "value": value,
                        "max": constraints["max"]
                    })
        
        passed = len(violations) == 0
        
        return ValidationResult(
            passed=passed,
            level=ValidationLevel.ERROR if not passed else ValidationLevel.INFO,
            message=f"Schema 校验{'通过' if passed else '失败'}",
            details={"violations": violations}
        )


class OutputGuardrail:
    """输出护栏"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.validators: List[Callable] = []
        self.history: List[Dict] = []
        
        # 默认校验器
        self._init_default_validators()
    
    def _init_default_validators(self):
        """初始化默认校验器"""
        # 空结果检测
        self.add_validator(
            name="empty_result",
            func=lambda x: x is not None and (not isinstance(x, (list, dict, str)) or len(x) > 0),
            message="输出结果为空"
        )
        
        # NaN/Inf 检测
        def check_nan_inf(data):
            import numpy as np
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                        return False
            return True
        
        self.add_validator(
            name="nan_inf_check",
            func=check_nan_inf,
            message="输出包含 NaN 或 Inf 值"
        )
    
    def add_validator(self, name: str, func: Callable, message: str,
                      level: ValidationLevel = ValidationLevel.WARNING):
        """添加校验器"""
        self.validators.append({
            "name": name,
            "func": func,
            "message": message,
            "level": level
        })
    
    def validate(self, output_data: Any) -> ValidationResult:
        """校验输出"""
        violations = []
        max_level = ValidationLevel.INFO
        
        for validator in self.validators:
            try:
                if not validator["func"](output_data):
                    violations.append({
                        "validator": validator["name"],
                        "message": validator["message"],
                        "level": validator["level"].value
                    })
                    if validator["level"].value > max_level.value:
                        max_level = validator["level"]
            except Exception as e:
                violations.append({
                    "validator": validator["name"],
                    "message": f"校验器执行失败: {e}",
                    "level": ValidationLevel.WARNING.value
                })
        
        passed = len(violations) == 0 or max_level in [ValidationLevel.INFO, ValidationLevel.WARNING]
        
        result = ValidationResult(
            passed=passed,
            level=max_level,
            message=f"输出校验{'通过' if passed else '失败'}",
            details={"violations": violations}
        )
        
        self.history.append(result.to_dict())
        
        return result
    
    def validate_consistency(self, output: Dict, expected_schema: Dict) -> ValidationResult:
        """校验输出一致性"""
        violations = []
        
        # 检查必需字段
        for field in expected_schema.get("required_fields", []):
            if field not in output:
                violations.append({
                    "field": field,
                    "issue": "missing_field"
                })
        
        # 检查置信度
        if "confidence" in output:
            conf = output["confidence"]
            if not (0 <= conf <= 1):
                violations.append({
                    "field": "confidence",
                    "issue": "invalid_range",
                    "value": conf
                })
        
        passed = len(violations) == 0
        
        return ValidationResult(
            passed=passed,
            level=ValidationLevel.ERROR if not passed else ValidationLevel.INFO,
            message=f"一致性校验{'通过' if passed else '失败'}",
            details={"violations": violations}
        )


class HallucinationDetector:
    """幻觉检测器（检测 LLM 输出中的不一致/虚构内容）"""
    
    def __init__(self):
        self.known_facts: Dict[str, Any] = {}
        self.detection_history: List[Dict] = []
    
    def register_fact(self, key: str, value: Any):
        """注册已知事实"""
        self.known_facts[key] = value
    
    def detect(self, llm_output: str, context: Optional[Dict] = None) -> ValidationResult:
        """检测幻觉"""
        issues = []
        
        # 检查数值一致性
        import re
        numbers_in_output = re.findall(r'\b\d+\.?\d*\b', llm_output)
        
        if context:
            context_numbers = []
            for v in context.values():
                if isinstance(v, (int, float)):
                    context_numbers.append(str(v))
            
            # 检查输出中的数字是否来自上下文
            for num in numbers_in_output:
                if num not in context_numbers and float(num) > 100:
                    issues.append({
                        "type": "unverified_number",
                        "value": num,
                        "message": "输出中的数字无法从上下文验证"
                    })
        
        # 检查与已知事实的冲突
        for key, fact in self.known_facts.items():
            if key in llm_output.lower():
                fact_str = str(fact)
                if fact_str not in llm_output:
                    issues.append({
                        "type": "fact_conflict",
                        "key": key,
                        "expected": fact_str,
                        "message": f"输出可能与已知事实 '{key}' 冲突"
                    })
        
        passed = len(issues) == 0
        
        result = ValidationResult(
            passed=passed,
            level=ValidationLevel.WARNING if issues else ValidationLevel.INFO,
            message=f"检测到 {len(issues)} 个潜在幻觉" if issues else "未检测到明显幻觉",
            details={"issues": issues}
        )
        
        self.detection_history.append(result.to_dict())
        
        return result


class GuardrailSystem:
    """统一护栏系统"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.input_guardrail = InputGuardrail(config)
        self.output_guardrail = OutputGuardrail(config)
        self.hallucination_detector = HallucinationDetector()
        self.blocked_count = 0
        self.passed_count = 0
        self.learning_enabled = config.get("learning_enabled", True)
        self.learned_rules: List[Dict] = []
    
    def check_input(self, input_data: Union[str, Dict]) -> ValidationResult:
        """检查输入"""
        result = self.input_guardrail.validate(input_data)
        
        if result.passed:
            self.passed_count += 1
        else:
            self.blocked_count += 1
            if self.learning_enabled:
                self._learn_from_block("input", input_data, result)
        
        return result
    
    def check_output(self, output_data: Any, context: Optional[Dict] = None) -> ValidationResult:
        """检查输出"""
        result = self.output_guardrail.validate(output_data)
        
        # 如果是 LLM 输出，额外检查幻觉
        if isinstance(output_data, str) and len(output_data) > 50:
            hallucination_result = self.hallucination_detector.detect(output_data, context)
            if not hallucination_result.passed:
                result.details["hallucination"] = hallucination_result.details
                result.level = max(result.level, hallucination_result.level, 
                                  key=lambda x: x.value if hasattr(x, 'value') else 0)
        
        if result.passed:
            self.passed_count += 1
        else:
            self.blocked_count += 1
            if self.learning_enabled:
                self._learn_from_block("output", output_data, result)
        
        return result
    
    def _learn_from_block(self, block_type: str, data: Any, result: ValidationResult):
        """从拦截中学习"""
        self.learned_rules.append({
            "timestamp": datetime.now().isoformat(),
            "type": block_type,
            "data_sample": str(data)[:100],
            "violations": result.details.get("violations", []),
            "level": result.level.value
        })
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = self.passed_count + self.blocked_count
        return {
            "total_checks": total,
            "passed": self.passed_count,
            "blocked": self.blocked_count,
            "block_rate": self.blocked_count / total if total > 0 else 0,
            "learned_rules": len(self.learned_rules),
            "input_rule_hits": {
                rule["name"]: rule["hit_count"]
                for rule in self.input_guardrail.rules
            }
        }
    
    def export_learned_rules(self, path: str):
        """导出学习到的规则"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.learned_rules, f, ensure_ascii=False, indent=2)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="护栏系统测试")
    parser.add_argument("--input", help="测试输入")
    parser.add_argument("--output", help="测试输出")
    parser.add_argument("--stats", action="store_true", help="显示统计")
    
    args = parser.parse_args()
    
    guardrails = GuardrailSystem()
    
    if args.input:
        result = guardrails.check_input(args.input)
        print(f"输入校验: {'通过' if result.passed else '拦截'}")
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    
    if args.output:
        result = guardrails.check_output(args.output)
        print(f"输出校验: {'通过' if result.passed else '拦截'}")
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    
    if args.stats:
        print("\n统计信息:")
        print(json.dumps(guardrails.get_statistics(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

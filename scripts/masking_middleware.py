#!/usr/bin/env python3
"""
脱敏中间件 (Data Masking Middleware)

根据 config/llm_config.json 的 privacy_protection.sensitive_fields 配置，
自动拦截 MCP tool 返回值中的敏感字段，替换为脱敏占位符。

设计要点：
- 磁盘上的 outputs/ 保留原始数据（便于离线审计）
- 发送给 LLM 推理层的返回值强制脱敏（API 侧隐私保护）
- 基于装饰器 @mask_sensitive，非侵入式接入所有 MCP tool
"""

import json
import os
import re
from functools import wraps
from typing import Any, Callable, Dict, List, Set

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "llm_config.json",
)

# 敏感值的正则模式（按字段名无法匹配时作为兜底）
_VALUE_PATTERNS = {
    "phone": re.compile(r"\b1[3-9]\d{9}\b"),
    "id_card": re.compile(r"\b\d{17}[\dXx]\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
}

_MASK = "***"


def _load_sensitive_fields() -> Set[str]:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        fields = cfg.get("privacy_protection", {}).get("sensitive_fields", [])
        enabled = cfg.get("privacy_protection", {}).get("enabled", True)
        if not enabled:
            return set()
        return {f.lower() for f in fields}
    except Exception:
        # 配置缺失时保守启用默认字段
        return {"password", "secret", "token", "api_key", "id_card", "phone", "email"}


_SENSITIVE_FIELDS = _load_sensitive_fields()


def _mask_value(value: Any) -> Any:
    """对字符串值应用正则脱敏（字段名未命中时的兜底）"""
    if not isinstance(value, str):
        return value
    masked = value
    for pat in _VALUE_PATTERNS.values():
        masked = pat.sub(_MASK, masked)
    return masked


def _should_mask_key(key: str) -> bool:
    if not isinstance(key, str):
        return False
    key_low = key.lower()
    return any(sf in key_low for sf in _SENSITIVE_FIELDS)


def mask_data(data: Any) -> Any:
    """
    递归脱敏任意嵌套结构（dict / list / str / 其他）
    - dict：按 key 名命中则整值替换为 ***
    - list：逐项递归
    - str ：应用正则模式（手机号/身份证/邮箱）
    """
    if isinstance(data, dict):
        return {
            k: (_MASK if _should_mask_key(k) else mask_data(v))
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [mask_data(x) for x in data]
    if isinstance(data, str):
        return _mask_value(data)
    return data


def mask_sensitive(func: Callable) -> Callable:
    """
    装饰器：自动脱敏 MCP tool 返回值。

    使用方式：
        @mcp.tool()
        @mask_sensitive
        def load_data(...) -> dict:
            ...

    注意：装饰器顺序——@mask_sensitive 必须在 @mcp.tool() 之后（即更靠近函数），
    这样 FastMCP 拿到的仍是原函数签名，脱敏发生在返回值阶段。
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        # 字符串 JSON 也要脱敏
        if isinstance(result, str):
            try:
                obj = json.loads(result)
                masked = mask_data(obj)
                return json.dumps(masked, ensure_ascii=False, indent=2)
            except (json.JSONDecodeError, TypeError):
                return _mask_value(result)
        return mask_data(result)

    return wrapper


def get_sensitive_fields() -> List[str]:
    """对外暴露当前生效的敏感字段清单（便于审计）"""
    return sorted(_SENSITIVE_FIELDS)

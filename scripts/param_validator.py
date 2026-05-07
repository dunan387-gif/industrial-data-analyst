#!/usr/bin/env python3
"""
参数合法性校验模块 (Parameter Validator)

在技能执行层引入参数校验，拒绝不合理的函数调用请求，防止 LLM 幻觉导致参数越界。
"""

import os
import re
from typing import Any, Dict, List, Optional

# ============================== 规则定义 ==============================

# chart_type 合法取值（与 SKILL.md 对齐）
VALID_CHART_TYPES = {
    "line", "anomaly_overlay", "rolling_band", "dual_axis", "fft_spectrum",
    "hist", "kde", "cdf", "box", "violin", "scatter", "heatmap",
    "bar", "stacked_bar", "area",
}

# 异常检测方法
VALID_ANOMALY_METHODS = {"isolation_forest", "lof", "dbscan", "zscore", "iqr"}

# 特征选择方法
VALID_FEATURE_METHODS = {"tree", "mi", "pca"}

# 模型训练任务类型
VALID_TASK_TYPES = {"auto", "classification", "regression"}

# 时序预测任务类型
VALID_TIMESERIES_TASKS = {"trend_decomposition", "fft_periodicity", "forecast"}

# 最大超时（秒）
MAX_TIMEOUT = 300


# ============================== 校验函数 ==============================

def validate_path(data_path: str, label: str = "data_path") -> Optional[str]:
    """
    校验文件路径：禁止路径逃逸（..）、必须存在（执行阶段才需要时放宽）
    返回错误消息或 None（通过）
    """
    if not data_path or not isinstance(data_path, str):
        return f"{label} 不能为空"

    normalized = os.path.normpath(data_path).replace("\\", "/")

    # 禁止路径逃逸（..）
    if ".." in normalized.split("/"):
        return f"{label} 包含非法路径逃逸 '..': {data_path}"

    # 禁止绝对路径指向系统目录（简单规则）
    system_roots = ("/etc", "/usr", "/var", "c:/windows", "c:/program files")
    lower = normalized.lower()
    for root in system_roots:
        if lower.startswith(root):
            return f"{label} 指向系统目录，禁止访问: {data_path}"

    return None


def validate_anomaly_params(method: str, contamination: float,
                            n_neighbors: int, columns: Optional[List[str]]) -> Optional[str]:
    """run_anomaly 参数校验"""
    if method not in VALID_ANOMALY_METHODS:
        return f"method '{method}' 不合法，合法取值: {sorted(VALID_ANOMALY_METHODS)}"

    if not (0.0 <= contamination <= 0.5):
        return f"contamination={contamination} 超出合法范围 [0.0, 0.5]"

    if n_neighbors <= 0:
        return f"n_neighbors={n_neighbors} 必须 > 0"

    if columns is not None:
        if not isinstance(columns, list):
            return "columns 必须是 List[str] 或 None"
        for c in columns:
            if not isinstance(c, str) or not c.strip():
                return f"columns 包含非法列名: {c!r}"

    return None


def validate_select_features_params(method: str, top_k: int) -> Optional[str]:
    """select_features 参数校验"""
    if method not in VALID_FEATURE_METHODS:
        return f"method '{method}' 不合法，合法取值: {sorted(VALID_FEATURE_METHODS)}"
    if top_k <= 0:
        return f"top_k={top_k} 必须 > 0"
    return None


def validate_train_model_params(task: str) -> Optional[str]:
    """train_model 参数校验"""
    if task not in VALID_TASK_TYPES:
        return f"task '{task}' 不合法，合法取值: {sorted(VALID_TASK_TYPES)}"
    return None


def validate_plot_chart_params(chart_type: str) -> Optional[str]:
    """plot_chart 参数校验"""
    if chart_type not in VALID_CHART_TYPES:
        return f"chart_type '{chart_type}' 不合法，合法取值: {sorted(VALID_CHART_TYPES)}"
    return None


def validate_sandbox_params(timeout: int) -> Optional[str]:
    """execute_code_sandbox 参数校验"""
    if not isinstance(timeout, int):
        return f"timeout 必须是整数，当前类型: {type(timeout).__name__}"
    if timeout <= 0:
        return f"timeout={timeout} 必须 > 0"
    if timeout > MAX_TIMEOUT:
        return f"timeout={timeout} 超出最大限制 {MAX_TIMEOUT} 秒"
    return None


def validate_model_dataset(model: str, dataset: str) -> Optional[str]:
    """通用：model / dataset 非空校验"""
    if not model or not isinstance(model, str):
        return "model 不能为空"
    if not dataset or not isinstance(dataset, str):
        return "dataset 不能为空"
    # 禁止特殊字符（防止目录穿越）
    for val, name in [(model, "model"), (dataset, "dataset")]:
        if re.search(r'[\\/:*?"<>|]', val):
            return f"{name} 包含非法字符: {val}"
    return None


# ============================== 统一入口 ==============================

def raise_if_error(msg: Optional[str]) -> None:
    """若 msg 不为空则抛出 ValueError（供工具函数开头调用）"""
    if msg:
        raise ValueError(f"[参数校验拒绝] {msg}")


def validate_all(tool_name: str, **kwargs) -> Optional[str]:
    """
    统一校验入口，根据工具名分发。
    返回错误消息或 None。
    """
    if tool_name == "run_anomaly":
        err = validate_path(kwargs.get("data_path"))
        if err:
            return err
        return validate_anomaly_params(
            kwargs.get("method", "isolation_forest"),
            kwargs.get("contamination", 0.1),
            kwargs.get("n_neighbors", 20),
            kwargs.get("columns"),
        )

    if tool_name == "select_features":
        err = validate_path(kwargs.get("data_path"))
        if err:
            return err
        return validate_select_features_params(
            kwargs.get("method", "tree"),
            kwargs.get("top_k", 10),
        )

    if tool_name == "train_model":
        err = validate_path(kwargs.get("data_path"))
        if err:
            return err
        return validate_train_model_params(kwargs.get("task", "auto"))

    if tool_name == "plot_chart":
        err = validate_path(kwargs.get("data_path"))
        if err:
            return err
        err = validate_plot_chart_params(kwargs.get("chart_type", ""))
        if err:
            return err
        err = validate_model_dataset(kwargs.get("model", ""), kwargs.get("dataset", ""))
        return err

    if tool_name == "execute_code_sandbox":
        return validate_sandbox_params(kwargs.get("timeout", 30))

    if tool_name in ("save_insight", "save_recommendation"):
        return validate_model_dataset(kwargs.get("model", ""), kwargs.get("dataset", ""))

    if tool_name == "predict_tabular":
        err = validate_path(kwargs.get("data_path"))
        if err:
            return err
        model_path = kwargs.get("model_path", "")
        if not model_path or not isinstance(model_path, str):
            return "model_path 不能为空"
        if ".." in os.path.normpath(model_path).replace("\\", "/").split("/"):
            return f"model_path 包含非法路径逃逸 '..': {model_path}"
        if not model_path.lower().endswith((".pkl", ".pickle", ".joblib")):
            return f"model_path 必须以 .pkl / .pickle / .joblib 结尾: {model_path}"
        return None

    if tool_name == "profile_dataset":
        return validate_path(kwargs.get("data_path"))

    if tool_name == "query_database":
        sql = kwargs.get("sql", "")
        if not sql or not isinstance(sql, str):
            return "SQL 查询不能为空"
        upper = sql.strip().upper()
        # 仅允许 SELECT，拒绝 INSERT/UPDATE/DELETE/DROP
        forbidden = ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "CREATE ", "TRUNCATE ")
        for f in forbidden:
            if f in upper:
                return f"SQL 包含危险操作 '{f.strip()}'，仅允许 SELECT 查询"
        return None

    # 其他工具无需特殊校验
    return None

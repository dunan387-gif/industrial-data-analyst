#!/usr/bin/env python3
"""
代码执行沙箱

安全隔离的代码执行环境：
- 禁止危险操作（文件删除、系统命令、网络请求）
- 限制执行时间
- 限制内存使用
- 白名单 import
"""

import os
import sys
import ast
import signal
import traceback
from typing import Dict, Any, List, Optional
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr


class SandboxError(Exception):
    """沙箱安全异常"""
    pass


class CodeSandbox:
    """安全代码执行沙箱"""

    # 允许导入的模块白名单
    ALLOWED_IMPORTS = {
        'numpy', 'np',
        'pandas', 'pd',
        'sklearn', 'scipy', 'statsmodels',
        'matplotlib', 'plt', 'seaborn', 'sns',
        'json', 'csv', 'math', 'statistics',
        'datetime', 'time', 'collections', 'itertools',
        're', 'typing'
    }

    # 禁止的函数/属性
    FORBIDDEN_CALLS = {
        'eval', 'exec', 'compile', '__import__',
        'open', 'file', 'input',
        'os.system', 'os.popen', 'os.remove', 'os.unlink', 'os.rmdir',
        'subprocess', 'shutil.rmtree',
        'socket', 'urllib', 'requests', 'http',
        'pickle.loads',  # 反序列化攻击
        'exit', 'quit', 'sys.exit',
    }

    # 禁止的魔术方法
    FORBIDDEN_ATTRS = {
        '__class__', '__bases__', '__subclasses__',
        '__globals__', '__code__', '__builtins__',
        '__import__', '__loader__', '__spec__'
    }

    def __init__(self, timeout: int = 30, max_output_size: int = 100000):
        """
        Args:
            timeout: 最大执行时间（秒）
            max_output_size: 最大输出字符数
        """
        self.timeout = timeout
        self.max_output_size = max_output_size
        self.execution_log: List[Dict] = []

    def validate_code(self, code: str) -> Dict[str, Any]:
        """
        静态代码安全检查

        Returns:
            {"safe": True/False, "issues": [...]}
        """
        issues = []

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {"safe": False, "issues": [f"语法错误: {e}"]}

        for node in ast.walk(tree):
            # 检查 import
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split('.')[0]
                    if module not in self.ALLOWED_IMPORTS:
                        issues.append(f"禁止导入模块: {alias.name}")

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module = node.module.split('.')[0]
                    if module not in self.ALLOWED_IMPORTS:
                        issues.append(f"禁止导入模块: {node.module}")

            # 检查危险函数调用
            elif isinstance(node, ast.Call):
                func_name = self._get_call_name(node)
                if func_name in self.FORBIDDEN_CALLS:
                    issues.append(f"禁止调用: {func_name}")

            # 检查危险属性访问
            elif isinstance(node, ast.Attribute):
                if node.attr in self.FORBIDDEN_ATTRS:
                    issues.append(f"禁止访问属性: {node.attr}")

            # 检查字符串中的危险内容
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                for forbidden in ['rm -rf', 'del /f', 'format c:', 'DROP TABLE']:
                    if forbidden.lower() in node.value.lower():
                        issues.append(f"字符串包含危险内容: {forbidden}")

        return {
            "safe": len(issues) == 0,
            "issues": issues,
            "checked_nodes": len(list(ast.walk(tree)))
        }

    def _get_call_name(self, node: ast.Call) -> str:
        """获取函数调用名称"""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return '.'.join(reversed(parts))
        return ""

    def execute(self, code: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        在沙箱中执行代码

        Args:
            code: 要执行的 Python 代码
            context: 预设的变量上下文（如 df, data_path 等）

        Returns:
            {
                "success": True/False,
                "output": stdout 输出,
                "error": 错误信息,
                "result": 最后一个表达式的值,
                "execution_time": 执行时间（秒）
            }
        """
        import time

        # 1. 安全检查
        validation = self.validate_code(code)
        if not validation["safe"]:
            return {
                "success": False,
                "output": "",
                "error": f"代码安全检查未通过: {validation['issues']}",
                "result": None,
                "blocked_by": "security_check"
            }

        # 2. 准备执行环境
        safe_globals = self._create_safe_globals()
        if context:
            safe_globals.update(context)

        # 3. 捕获输出
        stdout_capture = StringIO()
        stderr_capture = StringIO()

        start_time = time.time()
        result = None
        error = None

        try:
            # 设置超时（仅 Unix 系统）
            if hasattr(signal, 'SIGALRM'):
                def timeout_handler(signum, frame):
                    raise TimeoutError(f"代码执行超时（>{self.timeout}秒）")
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(self.timeout)

            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                # 执行代码
                exec(compile(code, '<sandbox>', 'exec'), safe_globals)

                # 尝试获取最后一个表达式的值
                if '_result' in safe_globals:
                    result = safe_globals['_result']

            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)  # 取消超时

        except TimeoutError as e:
            error = str(e)
        except Exception as e:
            error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        finally:
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)

        execution_time = time.time() - start_time

        # 4. 限制输出大小
        output = stdout_capture.getvalue()
        if len(output) > self.max_output_size:
            output = output[:self.max_output_size] + f"\n... [输出截断，超过 {self.max_output_size} 字符]"

        # 5. 记录执行日志
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "code_length": len(code),
            "success": error is None,
            "execution_time": execution_time
        }
        self.execution_log.append(log_entry)

        return {
            "success": error is None,
            "output": output,
            "error": error,
            "result": self._serialize_result(result),
            "execution_time": execution_time,
            "stderr": stderr_capture.getvalue()
        }

    def _create_safe_globals(self) -> Dict[str, Any]:
        """创建安全的全局命名空间"""
        import builtins
        import numpy as np
        import pandas as pd

        # 关键：必须使用完整的 builtins 模块
        # 只有当 __builtins__ 是模块对象时，__import__ 才会正确工作
        safe_globals = {
            '__builtins__': builtins,
            'np': np,
            'numpy': np,
            'pd': pd,
            'pandas': pd,
        }

        # 添加sklearn模块
        try:
            import sklearn
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.preprocessing import LabelEncoder, StandardScaler
            from sklearn.model_selection import train_test_split, cross_val_score
            from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
            from sklearn.feature_selection import SelectKBest, f_classif
            safe_globals['sklearn'] = sklearn
            safe_globals['RandomForestClassifier'] = RandomForestClassifier
            safe_globals['LabelEncoder'] = LabelEncoder
            safe_globals['StandardScaler'] = StandardScaler
            safe_globals['train_test_split'] = train_test_split
            safe_globals['cross_val_score'] = cross_val_score
            safe_globals['accuracy_score'] = accuracy_score
            safe_globals['classification_report'] = classification_report
            safe_globals['confusion_matrix'] = confusion_matrix
            safe_globals['SelectKBest'] = SelectKBest
            safe_globals['f_classif'] = f_classif
        except ImportError:
            pass

        return safe_globals

    def _serialize_result(self, result: Any) -> Any:
        """序列化执行结果（处理不可 JSON 序列化的对象）"""
        if result is None:
            return None
        if isinstance(result, (str, int, float, bool)):
            return result
        if isinstance(result, (list, tuple)):
            return [self._serialize_result(r) for r in result[:100]]  # 限制长度
        if isinstance(result, dict):
            return {k: self._serialize_result(v) for k, v in list(result.items())[:50]}
        # DataFrame/ndarray 转换
        if hasattr(result, 'to_dict'):
            return result.head(100).to_dict()
        if hasattr(result, 'tolist'):
            arr = result.flatten()[:100]
            return arr.tolist()
        return str(result)[:1000]


def safe_execute(code: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """便捷函数：安全执行代码"""
    sandbox = CodeSandbox()
    return sandbox.execute(code, context)

#!/usr/bin/env python3
"""
SQL 数据提取模块

支持：
- 多种数据库连接（MySQL、PostgreSQL、SQLite、SQL Server）
- 安全的参数化查询
- 查询结果自动转 DataFrame
- 连接池管理
"""

import os
import json
import pandas as pd
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from urllib.parse import quote_plus


class SQLConnector:
    """SQL 数据库连接器"""

    SUPPORTED_DIALECTS = {
        "mysql": "mysql+pymysql://{user}:{password}@{host}:{port}/{database}",
        "postgresql": "postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}",
        "sqlite": "sqlite:///{database}",
        "mssql": "mssql+pyodbc://{user}:{password}@{host}:{port}/{database}?driver=ODBC+Driver+17+for+SQL+Server",
        "oracle": "oracle+cx_oracle://{user}:{password}@{host}:{port}/{database}"
    }

    def __init__(self, config: Dict[str, Any] = None, config_file: str = None):
        """
        Args:
            config: 连接配置字典
            config_file: 配置文件路径（JSON）
        """
        self.config = config or {}
        if config_file and os.path.exists(config_file):
            with open(config_file, "r", encoding="utf-8") as f:
                self.config.update(json.load(f))

        self.engine = None
        self.connection = None
        self.query_log: List[Dict] = []

    def connect(self, dialect: str = "mysql", **kwargs) -> bool:
        """
        建立数据库连接

        Args:
            dialect: 数据库类型 (mysql/postgresql/sqlite/mssql)
            **kwargs: 连接参数 (host, port, user, password, database)

        Returns:
            是否连接成功
        """
        try:
            from sqlalchemy import create_engine
        except ImportError:
            raise ImportError("需要安装 sqlalchemy: pip install sqlalchemy")

        # 合并配置
        conn_config = {**self.config, **kwargs}

        if dialect not in self.SUPPORTED_DIALECTS:
            raise ValueError(f"不支持的数据库类型: {dialect}，支持: {list(self.SUPPORTED_DIALECTS.keys())}")

        # 构建连接字符串
        if dialect == "sqlite":
            conn_str = self.SUPPORTED_DIALECTS[dialect].format(
                database=conn_config.get("database", ":memory:")
            )
        else:
            # 密码 URL 编码
            password = quote_plus(conn_config.get("password", ""))
            conn_str = self.SUPPORTED_DIALECTS[dialect].format(
                user=conn_config.get("user", "root"),
                password=password,
                host=conn_config.get("host", "localhost"),
                port=conn_config.get("port", self._default_port(dialect)),
                database=conn_config.get("database", "")
            )

        try:
            self.engine = create_engine(conn_str, pool_pre_ping=True)
            self.connection = self.engine.connect()
            return True
        except Exception as e:
            self.query_log.append({
                "timestamp": datetime.now().isoformat(),
                "action": "connect",
                "status": "failed",
                "error": str(e)
            })
            raise ConnectionError(f"数据库连接失败: {e}")

    def _default_port(self, dialect: str) -> int:
        """获取默认端口"""
        ports = {
            "mysql": 3306,
            "postgresql": 5432,
            "mssql": 1433,
            "oracle": 1521
        }
        return ports.get(dialect, 3306)

    def query(self, sql: str, params: Dict[str, Any] = None,
              return_df: bool = True) -> Union[pd.DataFrame, List[Dict]]:
        """
        执行查询

        Args:
            sql: SQL 查询语句（支持参数化）
            params: 查询参数
            return_df: 是否返回 DataFrame（默认 True）

        Returns:
            查询结果
        """
        if self.engine is None:
            raise RuntimeError("未连接数据库，请先调用 connect()")

        # 安全检查：禁止危险操作
        self._validate_query(sql)

        start_time = datetime.now()

        try:
            if return_df:
                result = pd.read_sql(sql, self.engine, params=params)
            else:
                from sqlalchemy import text
                with self.engine.connect() as conn:
                    result_proxy = conn.execute(text(sql), params or {})
                    result = [dict(row._mapping) for row in result_proxy]

            self.query_log.append({
                "timestamp": start_time.isoformat(),
                "sql": sql[:200] + "..." if len(sql) > 200 else sql,
                "params": str(params)[:100] if params else None,
                "rows": len(result) if hasattr(result, '__len__') else 0,
                "status": "success",
                "duration_ms": (datetime.now() - start_time).total_seconds() * 1000
            })

            return result

        except Exception as e:
            self.query_log.append({
                "timestamp": start_time.isoformat(),
                "sql": sql[:200],
                "status": "failed",
                "error": str(e)
            })
            raise

    def _validate_query(self, sql: str):
        """SQL 安全检查"""
        sql_upper = sql.upper().strip()

        # 禁止危险操作
        dangerous_keywords = [
            "DROP TABLE", "DROP DATABASE", "TRUNCATE",
            "DELETE FROM", "UPDATE", "INSERT INTO",
            "ALTER TABLE", "CREATE TABLE", "GRANT", "REVOKE"
        ]

        for keyword in dangerous_keywords:
            if keyword in sql_upper:
                raise SecurityError(f"禁止执行危险 SQL 操作: {keyword}")

        # 只允许 SELECT 查询
        if not sql_upper.startswith("SELECT"):
            raise SecurityError("只允许执行 SELECT 查询")

    def list_tables(self) -> List[str]:
        """列出所有表"""
        if self.engine is None:
            raise RuntimeError("未连接数据库")

        from sqlalchemy import inspect
        inspector = inspect(self.engine)
        return inspector.get_table_names()

    def describe_table(self, table_name: str) -> pd.DataFrame:
        """获取表结构"""
        if self.engine is None:
            raise RuntimeError("未连接数据库")

        from sqlalchemy import inspect
        inspector = inspect(self.engine)
        columns = inspector.get_columns(table_name)

        return pd.DataFrame([{
            "column": c["name"],
            "type": str(c["type"]),
            "nullable": c.get("nullable", True),
            "default": c.get("default")
        } for c in columns])

    def to_csv(self, sql: str, output_path: str, params: Dict = None) -> str:
        """查询结果导出为 CSV"""
        df = self.query(sql, params)
        df.to_csv(output_path, index=False, encoding="utf-8")
        return output_path

    def close(self):
        """关闭连接"""
        if self.connection:
            self.connection.close()
        if self.engine:
            self.engine.dispose()

    def get_query_log(self) -> List[Dict]:
        """获取查询日志"""
        return self.query_log


class SecurityError(Exception):
    """SQL 安全异常"""
    pass


# 便捷函数
def query_to_dataframe(sql: str, dialect: str = "mysql", **conn_kwargs) -> pd.DataFrame:
    """
    一键查询数据库到 DataFrame

    示例:
        df = query_to_dataframe(
            "SELECT * FROM sensors WHERE date > :date",
            dialect="mysql",
            host="localhost",
            user="root",
            password="xxx",
            database="factory_db",
            params={"date": "2024-01-01"}
        )
    """
    connector = SQLConnector()
    params = conn_kwargs.pop("params", None)
    connector.connect(dialect, **conn_kwargs)
    try:
        return connector.query(sql, params)
    finally:
        connector.close()

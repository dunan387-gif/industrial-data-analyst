#!/usr/bin/env python3
"""
数据库连接模块
支持多种数据库类型的统一连接与数据读取
"""

import os
import json
import argparse
import pandas as pd
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from abc import ABC, abstractmethod


class BaseConnector(ABC):
    """数据库连接器基类"""
    
    @abstractmethod
    def connect(self) -> bool:
        """建立连接"""
        pass
    
    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass
    
    @abstractmethod
    def query(self, query: str, params: Optional[Dict] = None) -> pd.DataFrame:
        """执行查询"""
        pass
    
    @abstractmethod
    def test_connection(self) -> bool:
        """测试连接"""
        pass


class MySQLConnector(BaseConnector):
    """MySQL 数据库连接器"""
    
    def __init__(self, host: str, port: int = 3306, user: str = "root",
                 password: str = "", database: str = ""):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.connection = None
        
    def connect(self) -> bool:
        try:
            import pymysql
            self.connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset='utf8mb4'
            )
            return True
        except ImportError:
            print("错误: 请安装 pymysql: pip install pymysql")
            return False
        except Exception as e:
            print(f"MySQL 连接失败: {e}")
            return False
    
    def disconnect(self):
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def query(self, query: str, params: Optional[Dict] = None) -> pd.DataFrame:
        if not self.connection:
            self.connect()
        return pd.read_sql(query, self.connection, params=params)
    
    def test_connection(self) -> bool:
        try:
            self.connect()
            self.disconnect()
            return True
        except:
            return False


class PostgreSQLConnector(BaseConnector):
    """PostgreSQL 数据库连接器"""
    
    def __init__(self, host: str, port: int = 5432, user: str = "postgres",
                 password: str = "", database: str = ""):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.connection = None
        
    def connect(self) -> bool:
        try:
            import psycopg2
            self.connection = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database
            )
            return True
        except ImportError:
            print("错误: 请安装 psycopg2: pip install psycopg2-binary")
            return False
        except Exception as e:
            print(f"PostgreSQL 连接失败: {e}")
            return False
    
    def disconnect(self):
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def query(self, query: str, params: Optional[Dict] = None) -> pd.DataFrame:
        if not self.connection:
            self.connect()
        return pd.read_sql(query, self.connection, params=params)
    
    def test_connection(self) -> bool:
        try:
            self.connect()
            self.disconnect()
            return True
        except:
            return False


class InfluxDBConnector(BaseConnector):
    """InfluxDB 时序数据库连接器（工业常用）"""
    
    def __init__(self, host: str, port: int = 8086, token: str = "",
                 org: str = "", bucket: str = ""):
        self.host = host
        self.port = port
        self.token = token
        self.org = org
        self.bucket = bucket
        self.client = None
        
    def connect(self) -> bool:
        try:
            from influxdb_client import InfluxDBClient
            self.client = InfluxDBClient(
                url=f"http://{self.host}:{self.port}",
                token=self.token,
                org=self.org
            )
            return True
        except ImportError:
            print("错误: 请安装 influxdb-client: pip install influxdb-client")
            return False
        except Exception as e:
            print(f"InfluxDB 连接失败: {e}")
            return False
    
    def disconnect(self):
        if self.client:
            self.client.close()
            self.client = None
    
    def query(self, query: str, params: Optional[Dict] = None) -> pd.DataFrame:
        """执行 Flux 查询"""
        if not self.client:
            self.connect()
        
        query_api = self.client.query_api()
        result = query_api.query_data_frame(query)
        
        if isinstance(result, list):
            return pd.concat(result, ignore_index=True) if result else pd.DataFrame()
        return result
    
    def query_range(self, measurement: str, start: str = "-1h",
                    stop: str = "now()") -> pd.DataFrame:
        """查询时间范围数据"""
        flux_query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {start}, stop: {stop})
            |> filter(fn: (r) => r._measurement == "{measurement}")
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''
        return self.query(flux_query)
    
    def test_connection(self) -> bool:
        try:
            self.connect()
            health = self.client.health()
            self.disconnect()
            return health.status == "pass"
        except:
            return False


class MongoDBConnector(BaseConnector):
    """MongoDB 文档数据库连接器"""
    
    def __init__(self, host: str, port: int = 27017, user: str = "",
                 password: str = "", database: str = ""):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.client = None
        self.db = None
        
    def connect(self) -> bool:
        try:
            from pymongo import MongoClient
            
            if self.user and self.password:
                uri = f"mongodb://{self.user}:{self.password}@{self.host}:{self.port}"
            else:
                uri = f"mongodb://{self.host}:{self.port}"
            
            self.client = MongoClient(uri)
            self.db = self.client[self.database]
            return True
        except ImportError:
            print("错误: 请安装 pymongo: pip install pymongo")
            return False
        except Exception as e:
            print(f"MongoDB 连接失败: {e}")
            return False
    
    def disconnect(self):
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
    
    def query(self, collection: str, filter: Optional[Dict] = None,
              projection: Optional[Dict] = None, limit: int = 0) -> pd.DataFrame:
        """查询集合"""
        if not self.db:
            self.connect()
        
        filter = filter or {}
        cursor = self.db[collection].find(filter, projection)
        if limit > 0:
            cursor = cursor.limit(limit)
        
        return pd.DataFrame(list(cursor))
    
    def test_connection(self) -> bool:
        try:
            self.connect()
            self.client.server_info()
            self.disconnect()
            return True
        except:
            return False


class DataConnector:
    """统一数据连接器 - 支持文件和数据库"""
    
    SUPPORTED_DB_TYPES = ['mysql', 'postgresql', 'influxdb', 'mongodb']
    SUPPORTED_FILE_TYPES = ['csv', 'json', 'excel', 'parquet', 'pickle']
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.connector = None
        self.data = None
        
    def connect_database(self, db_type: str, **kwargs) -> bool:
        """连接数据库"""
        db_type = db_type.lower()
        
        if db_type == 'mysql':
            self.connector = MySQLConnector(**kwargs)
        elif db_type == 'postgresql':
            self.connector = PostgreSQLConnector(**kwargs)
        elif db_type == 'influxdb':
            self.connector = InfluxDBConnector(**kwargs)
        elif db_type == 'mongodb':
            self.connector = MongoDBConnector(**kwargs)
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}")
        
        return self.connector.connect()
    
    def load_from_database(self, query: str, **kwargs) -> pd.DataFrame:
        """从数据库加载数据"""
        if not self.connector:
            raise ValueError("请先连接数据库")
        
        self.data = self.connector.query(query, **kwargs)
        print(f"从数据库加载 {len(self.data)} 行数据")
        return self.data
    
    def load_from_file(self, file_path: str, **kwargs) -> pd.DataFrame:
        """从文件加载数据"""
        ext = file_path.split('.')[-1].lower()
        
        if ext == 'csv':
            self.data = pd.read_csv(file_path, **kwargs)
        elif ext == 'json':
            self.data = pd.read_json(file_path, **kwargs)
        elif ext in ['xls', 'xlsx', 'excel']:
            self.data = pd.read_excel(file_path, **kwargs)
        elif ext == 'parquet':
            self.data = pd.read_parquet(file_path, **kwargs)
        elif ext in ['pkl', 'pickle']:
            self.data = pd.read_pickle(file_path, **kwargs)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")
        
        print(f"从文件加载 {len(self.data)} 行数据")
        return self.data
    
    def load(self, source: str, source_type: str = "auto", **kwargs) -> pd.DataFrame:
        """
        统一加载接口
        
        Args:
            source: 数据源（文件路径或数据库查询）
            source_type: 数据源类型（auto/file/mysql/postgresql/influxdb/mongodb）
            **kwargs: 额外参数
        """
        if source_type == "auto":
            # 自动判断：如果是文件路径则加载文件
            if os.path.exists(source) or '.' in source.split('/')[-1]:
                return self.load_from_file(source, **kwargs)
            else:
                raise ValueError("无法自动判断数据源类型，请指定 source_type")
        elif source_type == "file":
            return self.load_from_file(source, **kwargs)
        elif source_type in self.SUPPORTED_DB_TYPES:
            # 需要先连接数据库
            if not self.connector:
                raise ValueError(f"请先调用 connect_database('{source_type}', ...) 连接数据库")
            return self.load_from_database(source, **kwargs)
        else:
            raise ValueError(f"不支持的数据源类型: {source_type}")
    
    def disconnect(self):
        """断开数据库连接"""
        if self.connector:
            self.connector.disconnect()
            self.connector = None
    
    def get_schema(self) -> Dict[str, Any]:
        """获取数据 schema"""
        if self.data is None:
            return {}
        
        return {
            "columns": list(self.data.columns),
            "dtypes": {col: str(dtype) for col, dtype in self.data.dtypes.items()},
            "shape": self.data.shape,
            "memory_usage": self.data.memory_usage(deep=True).sum()
        }


def load_db_config(config_path: str = "config/db_config.json") -> Dict:
    """加载数据库配置"""
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def main():
    parser = argparse.ArgumentParser(description="数据连接器")
    parser.add_argument("--source", required=True, help="数据源（文件路径或SQL查询）")
    parser.add_argument("--type", default="auto", 
                        choices=["auto", "file", "mysql", "postgresql", "influxdb", "mongodb"])
    parser.add_argument("--host", help="数据库主机")
    parser.add_argument("--port", type=int, help="数据库端口")
    parser.add_argument("--user", help="数据库用户名")
    parser.add_argument("--password", help="数据库密码")
    parser.add_argument("--database", help="数据库名")
    parser.add_argument("--output", help="输出文件路径")
    parser.add_argument("--test", action="store_true", help="测试连接")
    
    args = parser.parse_args()
    
    connector = DataConnector()
    
    if args.type in DataConnector.SUPPORTED_DB_TYPES:
        db_params = {
            "host": args.host or "localhost",
            "port": args.port,
            "user": args.user or "",
            "password": args.password or "",
            "database": args.database or ""
        }
        # 移除 None 值
        db_params = {k: v for k, v in db_params.items() if v is not None}
        
        if args.test:
            connector.connect_database(args.type, **db_params)
            success = connector.connector.test_connection()
            print(f"连接测试: {'成功' if success else '失败'}")
            return
        
        connector.connect_database(args.type, **db_params)
        data = connector.load_from_database(args.source)
    else:
        data = connector.load(args.source, args.type)
    
    print(f"\n数据 Schema:")
    print(json.dumps(connector.get_schema(), ensure_ascii=False, indent=2, default=str))
    
    if args.output:
        if args.output.endswith('.csv'):
            data.to_csv(args.output, index=False)
        elif args.output.endswith('.json'):
            data.to_json(args.output, orient='records', force_ascii=False)
        print(f"\n数据已保存到: {args.output}")
    
    connector.disconnect()


if __name__ == "__main__":
    main()

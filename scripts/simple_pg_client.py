#!/usr/bin/env python3
"""
纯 Python PostgreSQL 简易客户端（不依赖任何外部库）

支持:
- 密码认证 (MD5)
- 简单查询 (SELECT)
- COPY FROM STDIN 导入 CSV
- 数据库/表创建

用法:
    python scripts/simple_pg_client.py test_connection --password postgres
    python scripts/simple_pg_client.py create_db --password postgres --database industrial_data
    python scripts/simple_pg_client.py import_csv --password postgres --database industrial_data --table steel_energy --csv data/steel_energy/Steel_industry_data.csv
"""

import socket
import struct
import hashlib
import argparse
import csv
import io
import sys
from datetime import datetime


def md5_hash(s: str) -> str:
    """MD5 哈希，返回 hex 字符串"""
    return hashlib.md5(s.encode('utf-8')).hexdigest()


def md5_auth(user: str, password: str, salt: bytes) -> str:
    """PostgreSQL MD5 认证: md5(md5(password+user)+salt)"""
    inner = md5_hash(password + user)
    outer = hashlib.md5(inner.encode('ascii') + salt).hexdigest()
    return "md5" + outer


class SimplePGClient:
    """纯 Socket PostgreSQL 客户端"""

    def __init__(self, host: str = "localhost", port: int = 5432):
        self.host = host
        self.port = port
        self.sock = None
        self.authenticated = False
        self.server_version = ""

    def connect(self):
        """建立 TCP 连接"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect((self.host, self.port))

    def close(self):
        """关闭连接"""
        if self.sock:
            try:
                self.send_terminate()
            except:
                pass
            self.sock.close()
            self.sock = None

    def _read_n(self, n: int) -> bytes:
        """读取 n 字节"""
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("连接断开")
            data += chunk
        return data

    def _read_message(self) -> tuple:
        """读取一条 PostgreSQL 消息 (type, payload)"""
        msg_type = self.sock.recv(1)
        if not msg_type:
            return (b"", b"")
        length = struct.unpack(">I", self._read_n(4))[0]
        payload = self._read_n(length - 4)
        return (msg_type, payload)

    def _send_message(self, msg_type: bytes, payload: bytes):
        """发送一条 PostgreSQL 消息"""
        length = struct.pack(">I", 4 + len(payload))
        self.sock.sendall(msg_type + length + payload)

    def send_terminate(self):
        """发送终止消息"""
        if self.sock:
            self.sock.sendall(b"X\x00\x00\x00\x04")

    def startup(self, user: str, database: str = "postgres"):
        """
        发送 StartupMessage，处理认证
        Returns: True if authenticated
        """
        # StartupMessage: int32 length, int32 protocol(3,0), key-value pairs
        params = b"\x00".join([
            b"user\x00" + user.encode(),
            b"database\x00" + database.encode(),
            b"application_name\x00simple_pg_client\x00\x00"
        ])
        length = struct.pack(">I", 8 + len(params))
        self.sock.sendall(length + b"\x00\x03\x00\x00" + params)

        while True:
            msg_type, payload = self._read_message()

            if msg_type == b"R":  # Authentication
                auth_type = struct.unpack(">I", payload[:4])[0]
                if auth_type == 0:  # AuthenticationOK
                    print("  -> 认证成功 (trust/无密码)")
                    self.authenticated = True
                elif auth_type == 3:  # AuthenticationCleartextPassword
                    raise NotImplementedError("需要明文密码认证，暂不支持")
                elif auth_type == 5:  # AuthenticationMD5Password
                    salt = payload[4:8]
                    return salt  # 需要后续处理
                elif auth_type == 10:  # AuthenticationSASL
                    raise NotImplementedError("需要 SASL/SCRAM 认证，请使用 pgAdmin 或 psycopg2")
                else:
                    raise ConnectionError(f"不支持的认证方式: {auth_type}")

            elif msg_type == b"K":  # BackendKeyData
                pass
            elif msg_type == b"Z":  # ReadyForQuery
                if self.authenticated:
                    return True
            elif msg_type == b"E":  # ErrorResponse
                error_msg = self._parse_error(payload)
                raise ConnectionError(f"服务器错误: {error_msg}")
            elif msg_type == b"N":  # NoticeResponse
                pass

    def authenticate_md5(self, user: str, password: str, salt: bytes):
        """完成 MD5 认证"""
        password_hash = md5_auth(user, password, salt)
        # PasswordMessage
        pwd_payload = password_hash.encode() + b"\x00"
        self._send_message(b"p", pwd_payload)

        while True:
            msg_type, payload = self._read_message()
            if msg_type == b"R":
                auth_type = struct.unpack(">I", payload[:4])[0]
                if auth_type == 0:
                    self.authenticated = True
                    print("  -> MD5 认证成功")
                else:
                    raise ConnectionError(f"MD5 认证失败，服务器返回: {auth_type}")
            elif msg_type == b"K":
                pass
            elif msg_type == b"Z":
                if self.authenticated:
                    return True
            elif msg_type == b"E":
                error_msg = self._parse_error(payload)
                raise ConnectionError(f"认证错误: {error_msg}")

    def _parse_error(self, payload: bytes) -> str:
        """解析错误消息"""
        parts = {}
        idx = 0
        while idx < len(payload):
            field_type = payload[idx:idx+1]
            if field_type == b"\x00":
                break
            end = payload.index(b"\x00", idx + 1)
            parts[field_type] = payload[idx+1:end].decode('utf-8', errors='ignore')
            idx = end + 1
        return parts.get(b"M", "未知错误")

    def execute(self, sql: str) -> list:
        """执行 SQL 查询，返回结果列表"""
        if not self.authenticated:
            raise RuntimeError("未认证")

        # Query message
        self._send_message(b"Q", sql.encode() + b"\x00")

        rows = []
        columns = []
        in_result = False

        while True:
            msg_type, payload = self._read_message()

            if msg_type == b"T":  # RowDescription
                # 解析列信息
                col_count = struct.unpack(">H", payload[:2])[0]
                idx = 2
                for _ in range(col_count):
                    end = payload.index(b"\x00", idx)
                    col_name = payload[idx:end].decode()
                    columns.append(col_name)
                    idx = end + 1 + 18  # 跳过类型OID等
                in_result = True

            elif msg_type == b"D":  # DataRow
                col_count = struct.unpack(">H", payload[:2])[0]
                idx = 2
                row = {}
                for i in range(col_count):
                    length = struct.unpack(">i", payload[idx:idx+4])[0]
                    idx += 4
                    if length == -1:
                        val = None
                    else:
                        val = payload[idx:idx+length].decode('utf-8', errors='ignore')
                        idx += length
                    if i < len(columns):
                        row[columns[i]] = val
                rows.append(row)

            elif msg_type == b"C":  # CommandComplete
                pass

            elif msg_type == b"Z":  # ReadyForQuery
                break

            elif msg_type == b"E":  # ErrorResponse
                error_msg = self._parse_error(payload)
                raise RuntimeError(f"SQL 错误: {error_msg}")

        return rows

    def copy_from_csv(self, csv_path: str, table: str, delimiter: str = ",",
                      has_header: bool = True, encoding: str = "utf-8"):
        """
        使用 COPY FROM STDIN 导入 CSV
        """
        if not self.authenticated:
            raise RuntimeError("未认证")

        sql = f"COPY {table} FROM STDIN WITH (FORMAT csv, DELIMITER '{delimiter}', HEADER {'true' if has_header else 'false'}, ENCODING '{encoding}')"
        self._send_message(b"Q", sql.encode() + b"\x00")

        # 等待 CopyInResponse
        while True:
            msg_type, payload = self._read_message()
            if msg_type == b"G":  # CopyInResponse
                break
            elif msg_type == b"E":
                error_msg = self._parse_error(payload)
                raise RuntimeError(f"COPY 错误: {error_msg}")

        # 发送 CSV 数据
        with open(csv_path, "rb") as f:
            data = f.read()

        # 分块发送
        chunk_size = 8192
        for i in range(0, len(data), chunk_size):
            chunk = data[i:i+chunk_size]
            self.sock.sendall(b"d" + struct.pack(">I", 4 + len(chunk)) + chunk)

        # 发送终止标记
        self.sock.sendall(b"c\x00\x00\x00\x04")

        # 等待完成
        while True:
            msg_type, payload = self._read_message()
            if msg_type == b"C":
                pass
            elif msg_type == b"Z":
                break
            elif msg_type == b"E":
                error_msg = self._parse_error(payload)
                raise RuntimeError(f"COPY 完成错误: {error_msg}")

        print(f"  -> CSV 导入完成: {csv_path} -> {table}")


def test_connection(host: str, port: int, user: str, password: str, database: str = "postgres"):
    """测试连接"""
    print(f"测试连接 PostgreSQL {host}:{port} ...")
    client = SimplePGClient(host, port)
    try:
        client.connect()
        salt = client.startup(user, database)
        if salt is True:
            print("✅ 连接成功 (trust 认证)")
        else:
            client.authenticate_md5(user, password, salt)
            print("✅ 连接成功 (MD5 认证)")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False
    finally:
        client.close()
    return True


def create_database(host: str, port: int, user: str, password: str, database: str):
    """创建数据库"""
    print(f"创建数据库: {database} ...")
    client = SimplePGClient(host, port)
    try:
        client.connect()
        salt = client.startup(user, "postgres")
        if salt is not True:
            client.authenticate_md5(user, password, salt)

        # 检查数据库是否存在
        result = client.execute(f"SELECT 1 FROM pg_database WHERE datname = '{database}'")
        if result:
            print(f"  -> 数据库 '{database}' 已存在")
            return

        client.execute(f"CREATE DATABASE {database}")
        print(f"✅ 数据库 '{database}' 创建成功")
    except Exception as e:
        print(f"❌ 创建失败: {e}")
    finally:
        client.close()


def create_table_and_import(host: str, port: int, user: str, password: str,
                            database: str, table: str, csv_path: str):
    """创建表并导入数据"""
    print(f"导入 CSV 到 {database}.{table} ...")
    client = SimplePGClient(host, port)
    try:
        client.connect()
        salt = client.startup(user, database)
        if salt is not True:
            client.authenticate_md5(user, password, salt)

        # 先读取 CSV 获取列名
        import csv as csv_mod
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv_mod.reader(f)
            headers = next(reader)
            first_row = next(reader)

        # 生成 CREATE TABLE SQL（全部用 TEXT 类型，简化处理）
        col_defs = ", ".join([f'"{h.replace("\"", "\"\"")}" TEXT' for h in headers])
        create_sql = f"DROP TABLE IF EXISTS {table}; CREATE TABLE {table} ({col_defs});"

        client.execute(create_sql)
        print(f"  -> 表 '{table}' 创建成功")

        # 使用 COPY 导入
        client.copy_from_csv(csv_path, table)

        # 验证行数
        result = client.execute(f"SELECT COUNT(*) AS cnt FROM {table}")
        count = result[0]["cnt"] if result else "?"
        print(f"✅ 导入完成，表 {table} 共有 {count} 行")

    except Exception as e:
        print(f"❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description="纯 Python PostgreSQL 客户端")
    subparsers = parser.add_subparsers(dest="command")

    # test
    test_parser = subparsers.add_parser("test_connection", help="测试连接")
    test_parser.add_argument("--host", default="localhost")
    test_parser.add_argument("--port", type=int, default=5432)
    test_parser.add_argument("--user", default="postgres")
    test_parser.add_argument("--password", default="postgres")
    test_parser.add_argument("--database", default="postgres")

    # create_db
    db_parser = subparsers.add_parser("create_db", help="创建数据库")
    db_parser.add_argument("--host", default="localhost")
    db_parser.add_argument("--port", type=int, default=5432)
    db_parser.add_argument("--user", default="postgres")
    db_parser.add_argument("--password", default="postgres")
    db_parser.add_argument("--database", required=True)

    # import_csv
    import_parser = subparsers.add_parser("import_csv", help="导入 CSV")
    import_parser.add_argument("--host", default="localhost")
    import_parser.add_argument("--port", type=int, default=5432)
    import_parser.add_argument("--user", default="postgres")
    import_parser.add_argument("--password", default="postgres")
    import_parser.add_argument("--database", default="industrial_data")
    import_parser.add_argument("--table", required=True)
    import_parser.add_argument("--csv", required=True)

    args = parser.parse_args()

    if args.command == "test_connection":
        test_connection(args.host, args.port, args.user, args.password, args.database)
    elif args.command == "create_db":
        create_database(args.host, args.port, args.user, args.password, args.database)
    elif args.command == "import_csv":
        create_table_and_import(args.host, args.port, args.user, args.password,
                                args.database, args.table, args.csv)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

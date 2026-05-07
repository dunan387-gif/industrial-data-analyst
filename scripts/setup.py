#!/usr/bin/env python3
"""
工业数据智能分析技能安装脚本
自动安装依赖库和配置环境
"""

import os
import sys
import subprocess
import json
from pathlib import Path


class SetupManager:
    """安装管理器"""

    def __init__(self):
        self.base_dir = Path(__file__).parent.parent
        self.errors = []
        self.warnings = []

    def run(self):
        """执行安装流程"""
        print("=" * 60)
        print("工业数据智能分析技能 - 安装向导")
        print("=" * 60)
        print()

        # 检查 Python 版本
        if not self.check_python_version():
            return False

        # 安装依赖
        if not self.install_dependencies():
            return False

        # 创建必要的目录
        self.create_directories()

        # 初始化配置文件
        self.initialize_config()

        # 运行诊断
        self.run_diagnostics()

        # 显示总结
        self.show_summary()

        return len(self.errors) == 0

    def check_python_version(self):
        """检查 Python 版本"""
        print("检查 Python 版本...")
        version = sys.version_info

        if version.major < 3 or (version.major == 3 and version.minor < 8):
            self.errors.append(f"Python 版本过低: {version.major}.{version.minor}")
            print(f"  ✗ 需要 Python 3.8+，当前版本: {version.major}.{version.minor}.{version.micro}")
            return False

        print(f"  ✓ Python 版本: {version.major}.{version.minor}.{version.micro}")
        return True

    def install_dependencies(self):
        """安装依赖库"""
        print("\n安装依赖库...")

        # 基础依赖（必需）
        required_packages = [
            "numpy",
            "pandas",
            "scipy",
            "matplotlib",
            "seaborn",
            "scikit-learn",
            "requests"
        ]

        # 可选依赖
        optional_packages = {
            "statsmodels": "时序分析（ARIMA）",
            "prophet": "时序预测（Prophet）",
            "xgboost": "高级机器学习",
            "opencv-python": "图像处理",
            "pywt": "小波变换",
            "tensorflow": "深度学习（可选，也可使用 pytorch）"
        }

        # 安装必需依赖
        print("\n安装必需依赖...")
        for package in required_packages:
            if not self.install_package(package):
                self.errors.append(f"无法安装必需包: {package}")
                return False

        # 安装可选依赖
        print("\n安装可选依赖...")
        for package, description in optional_packages.items():
            print(f"\n安装 {package} ({description})? [Y/n] ", end="")
            choice = input().strip().lower()

            if choice in ["", "y", "yes"]:
                if not self.install_package(package):
                    self.warnings.append(f"可选包 {package} 安装失败，部分功能可能不可用")
            else:
                print(f"  跳过 {package}")

        return True

    def install_package(self, package):
        """安装单个包"""
        try:
            print(f"  安装 {package}...", end=" ")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", package],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print("✓")
            return True
        except subprocess.CalledProcessError:
            print("✗")
            return False

    def create_directories(self):
        """创建必要的目录"""
        print("\n创建目录结构...")

        directories = [
            "logs",
            "data",
            "outputs",
            "cache"
        ]

        for dir_name in directories:
            dir_path = self.base_dir / dir_name
            if not dir_path.exists():
                dir_path.mkdir(parents=True)
                print(f"  ✓ 创建目录: {dir_name}/")
            else:
                print(f"  - 目录已存在: {dir_name}/")

    def initialize_config(self):
        """初始化配置文件"""
        print("\n初始化配置...")

        config_file = self.base_dir / "config" / "llm_config.json"

        if config_file.exists():
            print("  - 配置文件已存在，跳过初始化")
            print("  提示: 请手动编辑 config/llm_config.json 填入 API 密钥")
        else:
            print("  ✓ 配置文件已创建")
            print("  警告: 请编辑 config/llm_config.json 填入 API 密钥")
            self.warnings.append("需要配置 API 密钥")

    def run_diagnostics(self):
        """运行诊断检查"""
        print("\n运行系统诊断...")

        # 检查导入
        test_imports = {
            "numpy": "NumPy",
            "pandas": "Pandas",
            "sklearn": "scikit-learn",
            "scipy": "SciPy"
        }

        for module, name in test_imports.items():
            try:
                __import__(module)
                print(f"  ✓ {name} 可用")
            except ImportError:
                print(f"  ✗ {name} 不可用")
                self.errors.append(f"{name} 导入失败")

        # 检查可选模块
        optional_imports = {
            "statsmodels": "statsmodels（时序分析）",
            "prophet": "Prophet（时序预测）",
            "xgboost": "XGBoost（机器学习）"
        }

        for module, name in optional_imports.items():
            try:
                __import__(module)
                print(f"  ✓ {name} 可用")
            except ImportError:
                print(f"  - {name} 不可用（可选）")

    def show_summary(self):
        """显示安装总结"""
        print("\n" + "=" * 60)
        print("安装总结")
        print("=" * 60)

        if self.errors:
            print("\n错误:")
            for error in self.errors:
                print(f"  ✗ {error}")

        if self.warnings:
            print("\n警告:")
            for warning in self.warnings:
                print(f"  ⚠ {warning}")

        if not self.errors:
            print("\n✓ 安装成功！")
            print("\n后续步骤:")
            print("  1. 编辑 config/llm_config.json 填入 API 密钥")
            print("  2. 查看 README.md 了解使用方法")
            print("  3. 运行测试: python -m pytest tests/")
            print("\n快速开始:")
            print("  python scripts/intent_parser.py --query \"分析能耗异常\"")
        else:
            print("\n✗ 安装失败，请检查错误信息")

        print()


def main():
    """主函数"""
    manager = SetupManager()
    success = manager.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

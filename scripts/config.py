"""钢材表面缺陷检测配置"""
import os

# 类别映射
CLASS_NAMES = ['Cr', 'In', 'Pa', 'PS', 'RS', 'Sc']
CLASS_LABELS = {
    'Cr': 0,  # Crazing - 龟裂
    'In': 1,  # Inclusion - 夹杂
    'Pa': 2,  # Patches - 斑块
    'PS': 3,  # Pitted Surface - 麻点
    'RS': 4,  # Rolled-in Scale - 轧入氧化皮
    'Sc': 5,  # Scratches - 划痕
}

# 中文名称映射
CLASS_NAMES_CN = {
    0: 'Crazing (龟裂)',
    1: 'Inclusion (夹杂)',
    2: 'Patches (斑块)',
    3: 'Pitted Surface (麻点)',
    4: 'Rolled-in Scale (轧入氧化皮)',
    5: 'Scratches (划痕)'
}

# 模型路径（相对于 industrial-data-analyst1 根目录）
MODEL_DIR = "models/steel_defect"
OUTPUT_DIR = "outputs/steel_defect"

# 图像参数
IMAGE_SIZE = 224

# 创建必要的目录
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

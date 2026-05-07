"""模型定义"""
import torch
import torch.nn as nn
from torchvision import models

from config import CLASS_NAMES


def get_resnet18(pretrained=True):
    """ResNet18模型"""
    model = models.resnet18(weights='IMAGENET1K_V1' if pretrained else None)
    num_features = model.fc.in_features
    model.fc = nn.Sequential(
        nn.Linear(num_features, 256),
        nn.ReLU(),
        nn.Dropout(0.3),
        nn.Linear(256, len(CLASS_NAMES))
    )
    return model


def get_resnet34(pretrained=True):
    """ResNet34模型"""
    model = models.resnet34(weights='IMAGENET1K_V1' if pretrained else None)
    model.fc = nn.Linear(model.fc.in_features, len(CLASS_NAMES))
    return model


def get_resnet50(pretrained=True):
    """ResNet50模型"""
    model = models.resnet50(weights='IMAGENET1K_V1' if pretrained else None)
    model.fc = nn.Linear(model.fc.in_features, len(CLASS_NAMES))
    return model


def get_efficientnet_b0(pretrained=True):
    """EfficientNet-B0模型"""
    model = models.efficientnet_b0(weights='IMAGENET1K_V1' if pretrained else None)
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(CLASS_NAMES))
    return model


def get_efficientnet_b1(pretrained=True):
    """EfficientNet-B1模型"""
    model = models.efficientnet_b1(weights='IMAGENET1K_V1' if pretrained else None)
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(CLASS_NAMES))
    return model


def get_efficientnet_b2(pretrained=True):
    """EfficientNet-B2模型"""
    model = models.efficientnet_b2(weights='IMAGENET1K_V1' if pretrained else None)
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(CLASS_NAMES))
    return model


# 模型字典
MODEL_DICT = {
    'resnet18': get_resnet18,
    'resnet34': get_resnet34,
    'resnet50': get_resnet50,
    'efficientnet_b0': get_efficientnet_b0,
    'efficientnet_b1': get_efficientnet_b1,
    'efficientnet_b2': get_efficientnet_b2,
}


def get_model(model_name, pretrained=True):
    """获取指定模型"""
    if model_name not in MODEL_DICT:
        raise ValueError(f"不支持的模型: {model_name}")
    return MODEL_DICT[model_name](pretrained)


def count_parameters(model):
    """统计模型参数量"""
    return sum(p.numel() for p in model.parameters() if p.requires_grad)

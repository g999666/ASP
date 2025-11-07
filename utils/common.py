"""
通用工具函数
提供项目中常用的基础功能
"""

import os
from pathlib import Path

def clean_env_value(value):
    """
    清理环境变量值，去除首尾空白字符

    Args:
        value: 环境变量的原始值

    Returns:
        str or None: 清理后的值，如果为空或None则返回None
    """
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def parse_headless_mode(headless_setting):
    """
    解析headless模式配置

    Args:
        headless_setting: headless配置值

    Returns:
        bool or str: True表示headless，False表示有界面，'virtual'表示虚拟模式
    """
    if str(headless_setting).lower() == 'true':
        return True
    elif str(headless_setting).lower() == 'false':
        return False
    else:
        return 'virtual'


def ensure_dir(path):
    """
    确保目录存在，如果不存在则创建

    Args:
        path: 目录路径（可以是字符串或Path对象）
    """
    if isinstance(path, str):
        path = Path(path)
    os.makedirs(path, exist_ok=True)
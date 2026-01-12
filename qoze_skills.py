#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QozeCode Skills CLI - 技能管理命令行工具
"""

import sys
import os

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    from utils.skills_cli import main
    main()


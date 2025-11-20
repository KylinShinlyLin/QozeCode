#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
目录树工具 - 智能获取当前目录结构
"""

import os
import platform
import subprocess
from utils.directory_config import EXCLUDE_DIRECTORIES


def get_directory_tree(current_dir=None):
    """
    获取当前目录树结构（智能限制深度和长度）
    
    Args:
        current_dir: 目标目录，默认为当前工作目录
        
    Returns:
        str: 格式化的目录树结构字符串
    """
    if current_dir is None:
        current_dir = os.getcwd()

    try:
        # 智能判断目录深度：根据当前目录路径决定扫描深度
        path_depth = len(current_dir.split(os.sep))
        if path_depth <= 3:  # 接近根目录
            max_depth = 3
        elif path_depth <= 5:  # 中等深度
            max_depth = 4
        else:  # 深层目录
            max_depth = 5

        # 设置最大输出长度限制（约2000个字符，避免token溢出）
        MAX_TREE_LENGTH = 3000

        system_info = platform.system()

        if system_info == "Windows":
            # Windows 使用 tree 命令，限制深度
            tree_result = subprocess.run(['tree', '/F', '/A', f'/L:{max_depth}'],
                                         capture_output=True, text=True, cwd=current_dir, timeout=10)
        else:
            # Unix-like 系统使用 tree 命令，如果没有则使用 find
            try:
                # 使用 -I 参数排除指定目录，限制深度
                exclude_pattern = '|'.join(EXCLUDE_DIRECTORIES)
                tree_result = subprocess.run(['tree', '-L', str(max_depth), '-a', '-I', exclude_pattern],
                                             capture_output=True, text=True, cwd=current_dir, timeout=10)
            except FileNotFoundError:
                # 如果没有 tree 命令，使用 find 作为备选，并手动过滤
                find_cmd = ['find', '.', '-maxdepth', str(max_depth)]
                # 为每个排除目录添加 -not -path 条件
                for exclude_dir in EXCLUDE_DIRECTORIES:
                    find_cmd.extend(['-not', '-path', f'*/{exclude_dir}/*'])
                    find_cmd.extend(['-not', '-name', exclude_dir])
                find_cmd.extend(['-type', 'd'])

                tree_result = subprocess.run(find_cmd, capture_output=True, text=True, cwd=current_dir, timeout=10)

        if tree_result.returncode == 0:
            raw_tree = tree_result.stdout.strip()

            # 智能截断：如果输出过长，进行截断并添加提示
            if len(raw_tree) > MAX_TREE_LENGTH:
                # 按行分割，保留前面的行
                lines = raw_tree.split('\n')
                truncated_lines = []
                current_length = 0

                for line in lines:
                    if current_length + len(line) + 1 > MAX_TREE_LENGTH - 100:  # 预留空间给提示信息
                        break
                    truncated_lines.append(line)
                    current_length += len(line) + 1

                directory_tree = '\n'.join(truncated_lines)
                directory_tree += f"\n\n... (目录结构过大，已截断显示前 {len(truncated_lines)} 行)"
                directory_tree += f"\n💡 提示: 当前在 {current_dir}，建议在具体项目目录中执行以获得更详细的结构信息"
            else:
                directory_tree = raw_tree
        else:
            directory_tree = "无法获取目录结构"
    except subprocess.TimeoutExpired:
        directory_tree = "目录结构获取超时（目录过大）"
    except Exception:
        directory_tree = "无法获取目录结构"

    return directory_tree

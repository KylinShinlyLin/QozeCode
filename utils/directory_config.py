#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
目录扫描配置文件
定义在获取项目目录结构时需要排除的目录和文件
"""

# 需要排除的目录列表
EXCLUDE_DIRECTORIES = [
    # 构建产物和输出目录
    'dist', 'build', 'target', 'out', 'output', 'bin', 'obj',
    'release', 'debug', 'Release', 'Debug',
    
    # Node.js / 前端开发
    'node_modules', '.npm', '.yarn', '.pnp', '.next', '.nuxt',
    'bower_components', '.cache', '.parcel-cache', '.vite',
    
    # Python开发
    '__pycache__', '.pytest_cache', '.mypy_cache', '.tox',
    'venv', 'env', '.env', '.venv', 'virtualenv',
    
    # 版本控制
    '.git', '.svn', '.hg', '.bzr',
    
    # IDE和编辑器配置
    '.vscode', '.idea', '.eclipse', '.settings',
    '.vs', '.vscode-test',
    
    # 依赖包和库
    'vendor', 'Pods', 'Carthage', 'DerivedData',
    
    # 测试覆盖率
    'coverage', '.coverage', '.nyc_output', 'htmlcov',
    
    # 日志文件
    'logs', 'log', '*.log',
    
    # 临时文件
    'tmp', 'temp', '.tmp', '.temp',
    
    # 系统文件
    '.DS_Store', 'Thumbs.db', 'desktop.ini',
    
    # iOS开发
    'DerivedData', '*.xcworkspace', '*.xcodeproj/xcuserdata',
    '*.xcodeproj/project.xcworkspace/xcuserdata',
    'build', 'Build',
    
    # Android开发
    '.gradle', 'gradle', 'build', '.externalNativeBuild',
    '.cxx', 'captures', 'local.properties',
    
    # Java开发
    'target', '*.class', '*.jar', '*.war',
    
    # .NET开发
    'bin', 'obj', 'packages', '.vs',
    
    # Rust开发
    'target', 'Cargo.lock',
    
    # Go开发
    'vendor', 'bin',
    
    # Docker
    '.docker', 'docker-compose.override.yml',
    
    # 其他常见排除项
    '.sass-cache', '.webpack', 'webpack-stats.json',
    'storybook-static', '.storybook-out'
]

# 目录扫描配置
DIRECTORY_SCAN_CONFIG = {
    # 最大输出长度（字符数）
    'max_tree_length': 2000,
    
    # 命令超时时间（秒）
    'command_timeout': 10,
    
    # 根据路径深度的扫描深度配置
    'depth_config': {
        'shallow': {'max_path_depth': 3, 'scan_depth': 3},    # 接近根目录
        'medium': {'max_path_depth': 5, 'scan_depth': 4},     # 中等深度
        'deep': {'max_path_depth': float('inf'), 'scan_depth': 5}  # 深层目录
    }
}


def get_exclude_directories():
    """获取排除目录列表"""
    return EXCLUDE_DIRECTORIES.copy()


def get_scan_config():
    """获取扫描配置"""
    return DIRECTORY_SCAN_CONFIG.copy()


def add_custom_exclude_dir(directory):
    """添加自定义排除目录"""
    if directory not in EXCLUDE_DIRECTORIES:
        EXCLUDE_DIRECTORIES.append(directory)


def remove_exclude_dir(directory):
    """移除排除目录"""
    if directory in EXCLUDE_DIRECTORIES:
        EXCLUDE_DIRECTORIES.remove(directory)
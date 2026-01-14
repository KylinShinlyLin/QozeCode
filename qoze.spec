# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_all, copy_metadata
import os

# 基础隐藏导入
hiddenimports = [
    'textual', 'rich', 'inquirer', 'readchar', 'langchain_core', 'langgraph',
    'typing_extensions', 'tavily', 'httpx', 'boto3', 'botocore',
    'langchain_aws', 'langchain_deepseek', 'langchain_google_genai', 
    'langchain_openai', 'langchain_xai', 'langchain_qwq',
    'jinja2', 'lxml', 'bs4', 'pymupdf',
]

# 自动收集子模块
for pkg in hiddenimports[:]:
    hiddenimports += collect_submodules(pkg)

# 本地模块导入
hiddenimports += [
    'launcher', 'qoze_code_agent', 'model_initializer', 
    'shared_console', 'config_manager', 'constant', 
    'dynamic_commands_patch', 'tools', 'utils', 'skills'
]

# 动态构建 datas 列表，避免路径不存在导致崩溃
datas = []
potential_datas = [
    ('.qoze/rules', '.qoze/rules'),
    ('skills', 'skills'),
    ('tools', 'tools'),
    ('utils', 'utils'),
]

for src, dst in potential_datas:
    if os.path.exists(src):
        datas.append((src, dst))
    else:
        print(f"警告: 资源目录 {src} 未找到，跳过打包...")

# 特殊包的数据和元数据收集
for pkg in ['certifi', 'botocore']:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        hiddenimports += h
    except Exception:
        pass

datas += copy_metadata('readchar')
datas += copy_metadata('textual')

a = Analysis(
    ['qoze_tui.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='qoze',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

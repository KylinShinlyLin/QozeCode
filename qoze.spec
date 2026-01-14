# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_all, copy_metadata
import os

hiddenimports = [
    'textual',
    'rich',
    'inquirer',
    'readchar',
    'langchain_core',
    'langgraph',
    'typing_extensions',
    'tavily',
    'httpx',
    'boto3',
    'botocore',
    'langchain_aws',
    'langchain_deepseek',
    'langchain_google_genai',
    'langchain_openai',
    'langchain_xai',
    'langchain_qwq',
    'jinja2',
    'lxml',
    'bs4',
    'pymupdf',
]

# 收集子模块
for pkg in hiddenimports[:]:
    hiddenimports += collect_submodules(pkg)

# 添加本地模块
hiddenimports += [
    'launcher',
    'qoze_code_agent',
    'model_initializer',
    'shared_console',
    'config_manager',
    'constant',
    'dynamic_commands_patch',
    'tools',
    'utils',
    'skills'
]

datas = [
    ('.qoze/rules', '.qoze/rules'),
    ('skills', 'skills'),
    ('tools', 'tools'),
    ('utils', 'utils'),
]

binaries = []
for pkg in ['certifi', 'botocore']:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# 复制必要的元数据
datas += copy_metadata('readchar')
datas += copy_metadata('textual')

a = Analysis(
    ['qoze_tui.py'],  # 将入口改为 qoze_tui.py
    pathex=['.'],
    binaries=binaries,
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

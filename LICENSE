# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_all, copy_metadata

hiddenimports = []
for pkg in [
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
    'langchain_google_vertexai',
    'langchain_openai',
]:
    hiddenimports += collect_submodules(pkg)

datas = []
binaries = []
for pkg in ['certifi', 'botocore']:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# 关键修复：复制 readchar 的包元数据
datas += copy_metadata('readchar')

a = Analysis(
    ['launcher.py'],
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
    noarchive=False,
)
block_cipher = None
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='qoze',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='qoze'
)
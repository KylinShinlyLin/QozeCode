<#
.SYNOPSIS
    QozeCode Windows 安装脚本 (PowerShell)
.DESCRIPTION
    安装、卸载、更新 QozeCode AI Agent 命令行工具。
    支持 install / uninstall / update / debug 子命令。
.NOTES
    对标 install.sh 的完整功能，适配 Windows 环境。
    不支持的功能 (Windows 跳过): pyaudio, playwright, voice/audio。
#>

# ============================================================
# 错误处理
# ============================================================
$ErrorActionPreference = "Stop"

# ============================================================
# 配置变量
# ============================================================
$REPO_URL      = "https://github.com/KylinShinlyLin/QozeCode.git"
$BRANCH        = "main"
$INSTALL_DIR   = "$env:LOCALAPPDATA\qoze"
$BIN_DIR       = "$INSTALL_DIR\bin"
$VENV_DIR      = "$INSTALL_DIR\venv"
$BUILD_DIR     = "$INSTALL_DIR\build"
$PROJECT_DIR   = "$BUILD_DIR\QozeCode"
$CONFIG_DIR    = "$env:APPDATA\qoze"
$CONFIG_FILE   = "$CONFIG_DIR\qoze.conf"
$PYTHON_MIN    = "3.9"

# 脚本级变量：Python 可执行文件路径
$script:PythonExe = $null

# ============================================================
# 颜色日志函数
# ============================================================
function Write-Info {
    param([string]$Message)
    Write-Host "[INFO]    " -NoNewline -ForegroundColor Blue
    Write-Host $Message
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] " -NoNewline -ForegroundColor Green
    Write-Host $Message
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] " -NoNewline -ForegroundColor Yellow
    Write-Host $Message
}

function Write-ErrorMsg {
    param([string]$Message)
    Write-Host "[ERROR]   " -NoNewline -ForegroundColor Red
    Write-Host $Message
}

# ============================================================
# Banner
# ============================================================
function Show-Banner {
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║          QozeCode Installer              ║" -ForegroundColor Cyan
    Write-Host "  ║          Windows PowerShell Edition      ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

# ============================================================
# 检查系统要求
# ============================================================
function Check-Requirements {
    Write-Info "检查系统要求..."

    # --- 检查 Python ---
    Write-Info "检查 Python..."
    $pythonCmd = $null
    try {
        $pythonCmd = (Get-Command python -ErrorAction Stop).Source
    } catch {
        try {
            $pythonCmd = (Get-Command python3 -ErrorAction Stop).Source
        } catch {
            Write-ErrorMsg "Python 未安装。请先安装 Python $PYTHON_MIN 或更高版本。"
            Write-Info "下载地址: https://www.python.org/downloads/"
            Write-Info "安装时请勾选 'Add Python to PATH'。"
            exit 1
        }
    }

    if ($pythonCmd.Contains("WindowsApps") -and -not $pythonCmd.Contains("Python")) {
        Write-Warning "检测到 Microsoft Store 占位 Python，正在尝试使用 winget 安装..."
        try {
            winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
            # winget 安装后，查找真实 Python 路径（避免依赖 PATH 刷新）
            $candidates = @(
                "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
                "$env:APPDATA\Python\Python312\python.exe",
                "C:\Program Files\Python312\python.exe",
                "C:\Program Files (x86)\Python312\python.exe"
            )
            $found = $false
            foreach ($p in $candidates) {
                if (Test-Path $p) {
                    $pythonCmd = $p
                    $found = $true
                    break
                }
            }
            if (-not $found) {
                # 最后尝试刷新 PATH 后再找
                $env:PATH = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
                try { $pythonCmd = (Get-Command python -ErrorAction Stop).Source } catch { }
            }
        } catch {
            Write-ErrorMsg "无法自动安装 Python。请手动从 https://www.python.org/downloads/ 安装。"
            exit 1
        }
    }

    $pythonVersion = & $pythonCmd -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    $versionOk = & $pythonCmd -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Python 版本过低 ($pythonVersion)，需要 $PYTHON_MIN 或更高版本。"
        exit 1
    }
    Write-Success "Python 版本检查通过 ($pythonVersion)"
    $script:PythonExe = $pythonCmd

    # --- 检查 Git ---
    Write-Info "检查 Git..."
    try {
        $gitVersion = & git --version 2>&1
        Write-Success "Git 检查通过 ($gitVersion)"
    } catch {
        Write-ErrorMsg "Git 未安装。请先安装 Git for Windows。"
        Write-Info "下载地址: https://git-scm.com/download/win"
        Write-Info "或者运行: winget install Git.Git"
        exit 1
    }
}

# ============================================================
# 创建安装目录
# ============================================================
function Create-Directories {
    Write-Info "创建安装目录..."
    $dirs = @($INSTALL_DIR, $BIN_DIR, $BUILD_DIR, $CONFIG_DIR)
    foreach ($dir in $dirs) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
    }
    Write-Success "目录创建完成"
}

# ============================================================
# 下载源码
# ============================================================
function Download-Source {
    Write-Info "下载 QozeCode 源码 (分支: $BRANCH)..."

    if (Test-Path "$PROJECT_DIR\.git") {
        Write-Warning "检测到已存在的源码，正在更新到最新版本..."
        Push-Location $PROJECT_DIR

        # 中止任何可能卡住的状态
        git merge --abort 2>$null
        git rebase --abort 2>$null
        git am --abort 2>$null

        # 获取远端、清理、强制重置
        git fetch origin $BRANCH
        git clean -fdx
        git checkout -f $BRANCH 2>$null
        if ($LASTEXITCODE -ne 0) {
            git checkout -f -b $BRANCH "origin/$BRANCH" 2>$null
        }
        git reset --hard "origin/$BRANCH"

        Pop-Location
    } else {
        if (Test-Path $PROJECT_DIR) {
            Remove-Item -Recurse -Force $PROJECT_DIR
        }
        Push-Location $BUILD_DIR
        git clone -b $BRANCH $REPO_URL
        Pop-Location
    }

    Write-Success "源码下载完成"
}

# ============================================================
# 创建虚拟环境
# ============================================================
function Create-Venv {
    Write-Info "创建 Python 虚拟环境..."

    if (Test-Path $VENV_DIR) {
        Write-Warning "虚拟环境已存在，正在重新创建..."
        Remove-Item -Recurse -Force $VENV_DIR
    }

    & $script:PythonExe -m venv $VENV_DIR

    # 激活虚拟环境并升级 pip
    $activateScript = "$VENV_DIR\Scripts\Activate.ps1"
    . $activateScript
    & pip install --upgrade pip

    Write-Success "虚拟环境创建完成"
}

# ============================================================
# 安装依赖
# ============================================================
function Install-Dependencies {
    Write-Info "安装项目依赖..."

    $activateScript = "$VENV_DIR\Scripts\Activate.ps1"
    . $activateScript

    Push-Location $PROJECT_DIR

    # 安装项目（editable 模式）
    & pip install -e .

    Pop-Location

    Write-Success "项目依赖安装完成"
}

# ============================================================
# 创建启动脚本 (qoze.cmd)
# ============================================================
function Install-Launcher {
    Write-Info "创建启动脚本..."

    $launcherPath = "$BIN_DIR\qoze.cmd"
    @"
@echo off
REM QozeCode Launcher (Windows)
REM 调用虚拟环境中的 qoze 入口点

set "VENV_QOZE=$VENV_DIR\Scripts\qoze.exe"
if exist "%VENV_QOZE%" (
    "%VENV_QOZE%" %*
) else (
    echo [ERROR] QozeCode 入口点未找到: %VENV_QOZE%
    echo 请重新运行安装脚本。
    pause
    exit /b 1
)
"@ | Out-File -FilePath $launcherPath -Encoding ASCII

    Write-Success "启动脚本创建完成: $launcherPath"

    # 同时创建 PowerShell 启动脚本
    $psLauncherPath = "$BIN_DIR\qoze.ps1"
    @"
# QozeCode PowerShell Launcher
param(
    [Parameter(ValueFromRemainingArguments=`$true)]
    `$RemainingArgs
)

`$qozeExe = "$VENV_DIR\Scripts\qoze.exe"
if (Test-Path `$qozeExe) {
    & `$qozeExe @RemainingArgs
} else {
    Write-Host "[ERROR] QozeCode 入口点未找到: `$qozeExe" -ForegroundColor Red
    Write-Host "请重新运行安装脚本。"
    exit 1
}
"@ | Out-File -FilePath $psLauncherPath -Encoding UTF8

    Write-Success "PowerShell 启动脚本创建完成: $psLauncherPath"
}

# ============================================================
# 创建配置文件模板
# ============================================================
function Create-ConfigTemplate {
    Write-Info "检查配置文件..."

    if (Test-Path $CONFIG_FILE) {
        Write-Info "配置文件已存在: $CONFIG_FILE"
        return
    }

    $templateContent = @'
[OpenAI]
api_key=

[DeepSeek]
api_key=

[Bedrock]
session_token=
region_name=us-east-1

[VertexAi]
project= #你的项目id
location=global
credentials_path= #你的gcp credentials 文件路径

[tavily]
tavily_key=

[XAI]
api_key=

[Kimi]
api_key=
base_url=https://api.moonshot.cn/v1

[KimiCode]
api_key=
base_url=https://api.kimi.com/coding/v1

[LiteLLM]
api_key=
base_url=

[ZHIPU]
api_key=

[Qwen3]
api_key=
base_url=https://dashscope.aliyuncs.com/compatible-mode/v1

[Soniox]
api_key=

[jina]
api_key=

[Azure]
api_key=
base_url=https://glowise-foundry.openai.azure.com/openai/v1
model_name=DeepSeek-V4-Pro

[Xiaomi]
api_key=
base_url=https://api.xiaomimimo.com/v1
'@

    $templateContent | Out-File -FilePath $CONFIG_FILE -Encoding UTF8
    Write-Success "配置文件模板创建完成: $CONFIG_FILE"
    Write-Warning "请编辑配置文件，填入你的 API Key: $CONFIG_FILE"
}

# ============================================================
# 配置环境变量 (PATH)
# ============================================================
function Configure-Env {
    Write-Info "配置环境变量..."

    # --- 1. 用户 PATH (持久化) ---
    $currentUserPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    if (-not $currentUserPath) { $currentUserPath = "" }
    if ($currentUserPath -notmatch [regex]::Escape($BIN_DIR)) {
        Write-Info "将 $BIN_DIR 添加到用户 PATH..."
        $newUserPath = "$currentUserPath;$BIN_DIR".TrimStart(";")
        [Environment]::SetEnvironmentVariable("PATH", $newUserPath, "User")
        Write-Success "已添加到用户 PATH (新终端窗口生效)"
    } else {
        Write-Info "用户 PATH 已包含 $BIN_DIR"
    }

    # --- 2. 当前会话 PATH ---
    $currentSessionPath = $env:PATH
    if ($currentSessionPath -notmatch [regex]::Escape($BIN_DIR)) {
        $env:PATH = "$BIN_DIR;$currentSessionPath"
        Write-Success "已添加到当前会话 PATH"
    }

    # --- 3. PowerShell Profile ---
    if ($PROFILE) {
        $profileDir = Split-Path $PROFILE -Parent
        if (-not (Test-Path $profileDir)) {
            New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
        }
        if (-not (Test-Path $PROFILE)) {
            New-Item -ItemType File -Path $PROFILE -Force | Out-Null
        }

        $profileContent = Get-Content $PROFILE -Raw -ErrorAction SilentlyContinue
        if (-not $profileContent) { $profileContent = "" }
        if ($profileContent -notmatch [regex]::Escape("# QozeCode PATH")) {
            Write-Info "将 PATH 配置添加到 PowerShell Profile: $PROFILE"
@"

# QozeCode PATH
if (`$env:PATH -notmatch [regex]::Escape("$BIN_DIR")) {
    `$env:PATH = "$BIN_DIR;`$env:PATH"
}
"@ | Add-Content -Path $PROFILE
            Write-Success "已添加 PATH 配置到 PowerShell Profile"
        } else {
            Write-Info "PowerShell Profile 已包含 QozeCode PATH 配置"
        }
    }

    # --- 4. 创建激活脚本 (方便手动调用) ---
    $activateScript = "$INSTALL_DIR\activate_qoze.ps1"
@"
# QozeCode 环境激活脚本
# 使用方法: . "$INSTALL_DIR\activate_qoze.ps1"

`$BinDir = "$BIN_DIR"
if (`$env:PATH -notmatch [regex]::Escape(`$BinDir)) {
    `$env:PATH = "`$BinDir;`$env:PATH"
}

if (Get-Command qoze.cmd -ErrorAction SilentlyContinue) {
    Write-Host "qoze 命令可用!" -ForegroundColor Green
} else {
    Write-Host "qoze 命令不可用" -ForegroundColor Red
}
"@ | Out-File -FilePath $activateScript -Encoding UTF8
    Write-Success "激活脚本创建完成: $activateScript"

    Write-Success "环境变量配置完成!"
}

# ============================================================
# 验证安装
# ============================================================
function Verify-Installation {
    Write-Info "验证安装..."

    # 检查启动脚本
    $launcherPath = "$BIN_DIR\qoze.cmd"
    if (-not (Test-Path $launcherPath)) {
        Write-ErrorMsg "启动脚本不存在: $launcherPath"
        return
    }
    Write-Success "启动脚本验证通过"

    # 检查虚拟环境
    if (-not (Test-Path "$VENV_DIR\Scripts\qoze.exe")) {
        Write-ErrorMsg "虚拟环境入口点不存在: $VENV_DIR\Scripts\qoze.exe"
        return
    }
    Write-Success "虚拟环境入口点验证通过"

    # 测试 qoze
    Write-Info "测试 QozeCode..."
    $launcherPath = "$BIN_DIR\qoze.cmd"
    try {
        $result = & cmd /c "$launcherPath" --help 2>&1
        Write-Success "QozeCode 运行测试通过"
    } catch {
        Write-Warning "QozeCode 可能需要首次配置。如果启动失败，请检查:"
        Write-Warning "  1. 配置文件: $CONFIG_FILE"
        Write-Warning "  2. Python 虚拟环境: $VENV_DIR"
    }

    Write-Host ""
    Write-Success "QozeCode 安装验证完成!"
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "  立即开始使用 QozeCode:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  方法 1 - 打开新终端，直接运行:" -ForegroundColor White
    Write-Host "    qoze" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  方法 2 - 在当前终端激活环境:" -ForegroundColor White
    Write-Host "    . ""$INSTALL_DIR\activate_qoze.ps1""" -ForegroundColor Yellow
    Write-Host "    qoze" -ForegroundColor Yellow
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host ""
}

# ============================================================
# 卸载
# ============================================================
function Uninstall-QozeCode {
    Write-Info "卸载 QozeCode..."

    # 删除安装目录
    if (Test-Path $INSTALL_DIR) {
        Remove-Item -Recurse -Force $INSTALL_DIR
        Write-Success "已删除安装目录: $INSTALL_DIR"
    }

    # 从用户 PATH 中移除
    $currentUserPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    if (-not $currentUserPath) { $currentUserPath = "" }
    if ($currentUserPath -match [regex]::Escape($BIN_DIR)) {
        Write-Info "从用户 PATH 中移除 $BIN_DIR ..."
        $newPath = ($currentUserPath -split ";" | Where-Object { $_ -ne $BIN_DIR }) -join ";"
        [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
        Write-Success "已从用户 PATH 中移除"
    }

    # 从 PowerShell Profile 中移除 QozeCode 相关行
    if ($PROFILE -and (Test-Path $PROFILE)) {
        Write-Info "从 PowerShell Profile 中移除 QozeCode 配置..."
        $lines = Get-Content $PROFILE
        $inBlock = $false
        $newLines = @()
        foreach ($line in $lines) {
            if ($line -match "# QozeCode PATH") {
                $inBlock = $true
                continue
            }
            if ($inBlock) {
                if ($line -match [regex]::Escape($BIN_DIR)) {
                    continue
                } elseif ($line.Trim() -eq "") {
                    # 跳过紧随的空行
                    continue
                } else {
                    $inBlock = $false
                }
            }
            $newLines += $line
        }
        $newLines | Set-Content $PROFILE
        Write-Success "已从 PowerShell Profile 中移除"
    }

    Write-Success "QozeCode 卸载完成"
}

# ============================================================
# 调试信息
# ============================================================
function Show-Debug {
    Write-Host "QozeCode 安装调试信息" -ForegroundColor Cyan
    Write-Host "======================" -ForegroundColor Cyan
    Write-Host "安装目录:     $INSTALL_DIR"
    Write-Host "二进制目录:   $BIN_DIR"
    Write-Host "虚拟环境:     $VENV_DIR"
    Write-Host "构建目录:     $BUILD_DIR"
    Write-Host "项目目录:     $PROJECT_DIR"
    Write-Host "配置文件:     $CONFIG_FILE"
    Write-Host ""

    Write-Host "文件检查:" -ForegroundColor Cyan
    Write-Host "  启动脚本 (qoze.cmd):   $(if (Test-Path "$BIN_DIR\qoze.cmd")      {'[OK] 存在'} else {'[MISSING] 不存在'})"
    Write-Host "  启动脚本 (qoze.ps1):   $(if (Test-Path "$BIN_DIR\qoze.ps1")      {'[OK] 存在'} else {'[MISSING] 不存在'})"
    Write-Host "  虚拟环境 qoze.exe:     $(if (Test-Path "$VENV_DIR\Scripts\qoze.exe") {'[OK] 存在'} else {'[MISSING] 不存在'})"
    Write-Host "  源码目录:              $(if (Test-Path $PROJECT_DIR)          {'[OK] 存在'} else {'[MISSING] 不存在'})"
    Write-Host "  配置文件:              $(if (Test-Path $CONFIG_FILE)          {'[OK] 存在'} else {'[MISSING] 不存在'})"
    Write-Host ""

    Write-Host "PATH 检查:" -ForegroundColor Cyan
    $userPath = [Environment]::GetEnvironmentVariable("PATH", "User"); if (-not $userPath) { $userPath = "" }
    $inUserPath = $userPath -match [regex]::Escape($BIN_DIR)
    Write-Host "  用户 PATH 包含 BIN_DIR: $(if ($inUserPath) {'[OK] 是'} else {'[NO] 否'})"
    $sessionPath = $env:PATH; if (-not $sessionPath) { $sessionPath = "" }
    $inSessionPath = $sessionPath -match [regex]::Escape($BIN_DIR)
    Write-Host "  会话 PATH 包含 BIN_DIR: $(if ($inSessionPath) {'[OK] 是'} else {'[NO] 否'})"

    $profileStatus = "[N/A]"
    if ($PROFILE) {
        $profileStatus = if (Test-Path $PROFILE) { "[OK] 存在" } else { "[NO] 不存在" }
    }
    Write-Host "  PowerShell Profile:     $profileStatus ($PROFILE)"
    Write-Host ""

    Write-Host "工具检查:" -ForegroundColor Cyan
    try { $pv = & $script:PythonExe --version 2>&1; Write-Host "  Python:  $pv" } catch { Write-Host "  Python:  [MISSING]" -ForegroundColor Red }
    try { $gv = & git --version 2>&1; Write-Host "  Git:     $gv" } catch { Write-Host "  Git:     [MISSING]" -ForegroundColor Red }
    Write-Host ""
}

# ============================================================
# 帮助
# ============================================================
function Show-Help {
    Write-Host "QozeCode Windows 安装脚本 (PowerShell)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "用法:" -ForegroundColor White
    Write-Host "  .\install.ps1 [子命令]" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "子命令:" -ForegroundColor White
    Write-Host "  install      安装 QozeCode (默认)" -ForegroundColor Green
    Write-Host "  uninstall    卸载 QozeCode" -ForegroundColor Red
    Write-Host "  update       更新 QozeCode 到最新版本" -ForegroundColor Blue
    Write-Host "  debug        显示调试信息" -ForegroundColor Yellow
    Write-Host "  --help       显示此帮助信息" -ForegroundColor Gray
    Write-Host ""
    Write-Host "示例:" -ForegroundColor White
    Write-Host "  .\install.ps1" -ForegroundColor Yellow
    Write-Host "  .\install.ps1 install" -ForegroundColor Yellow
    Write-Host "  .\install.ps1 update" -ForegroundColor Yellow
    Write-Host "  .\install.ps1 uninstall" -ForegroundColor Yellow
    Write-Host "  .\install.ps1 debug" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "注意事项:" -ForegroundColor White
    Write-Host "  - 首次运行可能需要执行: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser" -ForegroundColor DarkGray
    Write-Host "  - 安装完成后，请打开新的终端窗口以使 PATH 生效" -ForegroundColor DarkGray
    Write-Host "  - Windows 上不支持 pyaudio / playwright 功能" -ForegroundColor DarkGray
    Write-Host ""
}

# ============================================================
# 更新
# ============================================================
function Update-QozeCode {
    Write-Info "更新 QozeCode..."

    Check-Requirements
    Download-Source

    $activateScript = "$VENV_DIR\Scripts\Activate.ps1"
    . $activateScript

    Push-Location $PROJECT_DIR
    & pip install -e . --upgrade
    Pop-Location

    Write-Success "QozeCode 更新完成"
}

# ============================================================
# 主安装流程
# ============================================================
function Invoke-Install {
    Write-Info "开始安装 QozeCode..."

    Check-Requirements
    Create-Directories
    Download-Source
    Create-Venv
    Install-Dependencies
    Install-Launcher
    Create-ConfigTemplate
    Configure-Env
    Verify-Installation
}

# ============================================================
# 入口
# ============================================================
function Main {
    Show-Banner

    $subcommand = if ($args.Count -gt 0) { $args[0].ToLower() } else { "install" }

    switch ($subcommand) {
        "install"   { Invoke-Install }
        "uninstall" { Uninstall-QozeCode }
        "update"    { Update-QozeCode }
        "debug"     { Show-Debug }
        "--help"    { Show-Help }
        "-h"        { Show-Help }
        "help"      { Show-Help }
        default {
            Write-ErrorMsg "未知选项: $subcommand"
            Show-Help
            exit 1
        }
    }
}

# 执行
Main @args

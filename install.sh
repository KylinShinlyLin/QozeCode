#!/bin/bash

# QozeCode 安装脚本
# 支持 PyInstaller 二进制构建和源码安装两种方式

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置变量
REPO_URL="https://github.com/KylinShinlyLin/QozeCode.git"
BRANCH="feat/ui_textual"
INSTALL_DIR="$HOME/.qoze"
BIN_DIR="$HOME/.local/bin"
VENV_DIR="$INSTALL_DIR/venv"
BUILD_DIR="$INSTALL_DIR/build"

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    echo -e "${YELLOW}[DEBUG]${NC} $1"
}

# 检查系统要求
check_requirements() {
    log_info "检查系统要求..."
    
    # 检查 Python 版本
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 未安装，请先安装 Python 3.9 或更高版本"
        exit 1
    fi
    
    python_version=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
    
    if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)"; then
        log_error "Python 版本过低 ($python_version)，需要 3.9 或更高版本"
        exit 1
    fi
    
    log_success "Python 版本检查通过 ($python_version)"
    
    # 检查 git
    if ! command -v git &> /dev/null; then
        log_error "Git 未安装，请先安装 Git"
        exit 1
    fi
    
    log_success "Git 检查通过"
}

# 创建安装目录
create_directories() {
    log_info "创建安装目录..."
    
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$BIN_DIR"
    mkdir -p "$BUILD_DIR"
    
    log_success "目录创建完成"
}

# 下载源码
download_source() {
    log_info "下载 QozeCode 源码 (分支: $BRANCH)..."

    if [ -d "$BUILD_DIR/QozeCode" ]; then
        log_warning "检测到已存在的源码，正在切换/更新到分支 $BRANCH..."
        cd "$BUILD_DIR/QozeCode"
        git fetch origin
        git checkout "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH" "origin/$BRANCH"
        git pull origin "$BRANCH"
    else
        cd "$BUILD_DIR"
        git clone -b "$BRANCH" "$REPO_URL"
    fi

    log_success "源码下载完成"
}

# 创建虚拟环境
create_venv() {
    log_info "创建 Python 虚拟环境..."
    
    if [ -d "$VENV_DIR" ]; then
        log_warning "虚拟环境已存在，正在重新创建..."
        rm -rf "$VENV_DIR"
    fi
    
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    
    # 升级 pip
    pip install --upgrade pip
    
    log_success "虚拟环境创建完成"
}

# 安装项目依赖
install_dependencies() {
    log_info "安装项目依赖..."
    
    source "$VENV_DIR/bin/activate"
    cd "$BUILD_DIR/QozeCode"
    
    # 安装项目
    pip install -e .
    
    # 自动安装浏览器功能
#    log_info "安装浏览器自动化功能..."
#    pip install -e ".[browser]"
#    log_info "安装 Playwright 浏览器..."
#    playwright install
#    log_success "浏览器功能安装完成"
    
    # 预安装 PyInstaller（为二进制构建做准备）
    log_info "预安装 PyInstaller..."
    if pip install pyinstaller; then
        log_success "PyInstaller 安装成功"
        # 验证安装
        if python -c "import PyInstaller; print(f'PyInstaller 版本: {PyInstaller.__version__}')" 2>/dev/null; then
            log_success "PyInstaller 验证通过"
        else
            log_warning "PyInstaller 安装可能有问题"
        fi
    else
        log_error "PyInstaller 安装失败"
    fi
    
    log_success "项目依赖安装完成"
}

# 检查并安装 PyInstaller
ensure_pyinstaller() {
    log_info "检查 PyInstaller 安装状态..."
    
    source "$VENV_DIR/bin/activate"
    
    # 检查 PyInstaller 是否已安装
    if python -c "import PyInstaller; print(f'PyInstaller 版本: {PyInstaller.__version__}')" 2>/dev/null; then
        log_success "PyInstaller 已安装并可用"
        return 0
    fi
    
    log_info "PyInstaller 未安装，开始安装..."
    
    # 升级 pip 以确保兼容性
    pip install --upgrade pip setuptools wheel
    
    # 安装 PyInstaller
    if pip install --upgrade pyinstaller; then
        log_success "PyInstaller 安装成功"
        
        # 验证安装
        if python -c "import PyInstaller; print(f'PyInstaller 版本: {PyInstaller.__version__}')" 2>/dev/null; then
            log_success "PyInstaller 验证通过"
            return 0
        else
            log_error "PyInstaller 安装验证失败"
            return 1
        fi
    else
        log_error "PyInstaller 安装失败"
        return 1
    fi
}

# 尝试构建二进制文件
try_build_binary() {
    log_info "尝试构建 QozeCode 二进制文件..."
    
    source "$VENV_DIR/bin/activate"
    cd "$BUILD_DIR/QozeCode"
    
    # 检查是否有 Qoze.spec 文件
    if [ ! -f "Qoze.spec" ]; then
#        log_warning "未找到 Qoze.spec 文件，跳过二进制构建"
        return 1
    fi
    
    log_success "找到 Qoze.spec 文件"
    
    # 验证 PyInstaller 是否可用
    log_info "验证 PyInstaller 安装状态..."
    if ! python -c "import PyInstaller; print(f'PyInstaller 版本: {PyInstaller.__version__}')" 2>/dev/null; then
        log_warning "PyInstaller 不可用，重新安装..."
        if ! pip install --upgrade pyinstaller; then
            log_error "PyInstaller 安装失败"
            return 1
        fi
    fi
    
    # 检查系统依赖（macOS 特定）
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS 可能需要额外的工具
        if ! command -v strip &> /dev/null; then
            log_warning "未找到 strip 工具，可能影响二进制构建"
        fi
        
        # 检查 Xcode Command Line Tools
        if ! xcode-select -p &>/dev/null; then
            log_warning "未检测到 Xcode Command Line Tools，可能影响构建"
            log_info "可以运行 'xcode-select --install' 安装"
        fi
    fi
    
    # 清理之前的构建
    log_info "清理之前的构建文件..."
    rm -rf build dist
    
    # 使用 PyInstaller 构建（显示详细输出）
    log_info "开始 PyInstaller 构建..."
    log_info "构建命令: pyinstaller Qoze.spec --clean --noconfirm"
    
    # 创建构建日志文件
    BUILD_LOG="$INSTALL_DIR/build.log"
    
    # 设置构建环境变量
    export PYTHONPATH="$(pwd):$PYTHONPATH"
    
    # 显示构建环境信息
    log_info "构建环境信息："
    echo "  - Python 版本: $(python --version)"
    echo "  - PyInstaller 版本: $(python -c "import PyInstaller; print(PyInstaller.__version__)" 2>/dev/null || echo '未知')"
    echo "  - 工作目录: $(pwd)"
    echo "  - PYTHONPATH: $PYTHONPATH"
    
    if pyinstaller Qoze.spec --clean --noconfirm --log-level INFO 2>&1 | tee "$BUILD_LOG"; then
        # 检查构建结果
        if [ -f "dist/qoze/qoze" ]; then
            log_success "二进制文件构建成功"
            log_info "二进制文件位置: $(pwd)/dist/qoze/qoze"
            
            # 显示文件信息
            ls -la "dist/qoze/qoze"
            
            # 测试二进制文件是否可执行
            log_info "测试二进制文件..."
            if ./dist/qoze/qoze --help &>/dev/null; then
                log_success "二进制文件测试通过"
                return 0
            else
                log_warning "二进制文件无法正常运行，查看详细错误："
                ./dist/qoze/qoze --help || true
                return 1
            fi
        else
            log_error "二进制文件构建失败：未找到输出文件"
            log_info "查看构建日志: $BUILD_LOG"
            return 1
        fi
    else
        log_error "PyInstaller 构建过程失败"
        log_info "查看构建日志: $BUILD_LOG"
        return 1
    fi
}

# 安装二进制文件
install_binary() {
    log_info "安装 QozeCode 二进制文件..."
    
    # 正确的源文件路径
    SOURCE_BINARY="$BUILD_DIR/QozeCode/dist/qoze/qoze"
    
    # 检查源文件是否存在
    if [ ! -f "$SOURCE_BINARY" ]; then
        log_error "二进制文件不存在: $SOURCE_BINARY"
        log_error "PyInstaller 构建可能失败了"
        return 1
    fi
    
    log_success "找到二进制文件: $SOURCE_BINARY"
    
    # 复制整个 dist 目录以保持依赖完整
    if [ -d "$INSTALL_DIR/qoze-dist" ]; then
        rm -rf "$INSTALL_DIR/qoze-dist"
    fi
    
    log_info "复制二进制文件到安装目录..."
    if cp -r "$BUILD_DIR/QozeCode/dist/qoze" "$INSTALL_DIR/qoze-dist"; then
        log_success "二进制文件复制成功"
    else
        log_error "二进制文件复制失败"
        return 1
    fi
    
    # 验证复制后的文件
    TARGET_BINARY="$INSTALL_DIR/qoze-dist/qoze"
    if [ ! -f "$TARGET_BINARY" ]; then
        log_error "复制后的二进制文件不存在: $TARGET_BINARY"
        return 1
    fi
    
    # 确保二进制文件可执行
    chmod +x "$TARGET_BINARY"
    log_success "二进制文件权限设置完成"
    
    # 创建启动脚本
    cat > "$BIN_DIR/qoze" << EOF
#!/bin/bash
# QozeCode 启动脚本 (二进制版本)

QOZE_BINARY="$INSTALL_DIR/qoze-dist/qoze"

if [ -f "\$QOZE_BINARY" ]; then
    exec "\$QOZE_BINARY" "\$@"
else
    echo "错误: QozeCode 二进制文件未找到"
    echo "预期位置: \$QOZE_BINARY"
    echo ""
    echo "调试信息:"
    echo "  - 安装目录: $INSTALL_DIR"
    echo "  - 二进制目录: $INSTALL_DIR/qoze-dist"
    echo "  - 源文件位置: $BUILD_DIR/QozeCode/dist/qoze/qoze"
    echo ""
    if [ -f "$BUILD_DIR/QozeCode/dist/qoze/qoze" ]; then
        echo "  ✅ 源文件存在，可以重新运行安装"
        echo "  建议: bash install.sh install"
    else
        echo "  ❌ 源文件不存在，需要重新构建"
        echo "  建议: bash install.sh source  # 使用源码安装"
    fi
    exit 1
fi
EOF
    
    chmod +x "$BIN_DIR/qoze"
    
    log_success "二进制文件安装完成"
    log_info "源文件: $SOURCE_BINARY"
    log_info "目标文件: $TARGET_BINARY"
    log_info "启动脚本: $BIN_DIR/qoze"
}

# 源码安装方式
install_from_source() {
    log_info "使用源码安装方式..."
    
    # 创建启动脚本，直接调用虚拟环境中的 qoze
    cat > "$BIN_DIR/qoze" << EOF
#!/bin/bash
# QozeCode 启动脚本 (源码版本)

exec "$VENV_DIR/bin/qoze" "\$@"
EOF
    
    chmod +x "$BIN_DIR/qoze"
    
    log_success "源码安装完成"
}

# 配置环境变量
configure_env() {
    log_info "配置环境变量..."
    
    # 检测当前使用的 shell
    current_shell=$(basename "$SHELL" 2>/dev/null || echo "unknown")
    log_info "检测到当前 shell: $current_shell"
    
    # 确定主要的配置文件
    primary_config=""
    case "$current_shell" in
        "zsh")
            primary_config="$HOME/.zshrc"
            ;;
        "bash")
            # 优先使用 .bashrc，如果不存在则使用 .bash_profile
            if [ -f "$HOME/.bashrc" ]; then
                primary_config="$HOME/.bashrc"
            else
                primary_config="$HOME/.bash_profile"
            fi
            ;;
        "fish")
            primary_config="$HOME/.config/fish/config.fish"
            ;;
        *)
            primary_config="$HOME/.profile"
            ;;
    esac
    
    # 确保主配置文件存在
    if [ ! -f "$primary_config" ]; then
        log_info "创建配置文件: $primary_config"
        mkdir -p "$(dirname "$primary_config")"
        touch "$primary_config"
    fi
    
    # 添加PATH配置到主配置文件
    if ! grep -q "# QozeCode PATH" "$primary_config" 2>/dev/null; then
        log_info "添加 PATH 配置到: $primary_config"
        echo "" >> "$primary_config"
        echo "# QozeCode PATH" >> "$primary_config"
        
        if [ "$current_shell" = "fish" ]; then
            echo "set -gx PATH \"$BIN_DIR\" \$PATH" >> "$primary_config"
        else
            echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$primary_config"
        fi
        
        log_success "✅ 已添加 PATH 配置到 $primary_config"
    else
        log_info "$primary_config 已经配置过 QozeCode PATH"
    fi
    
    # 临时添加到当前会话
    export PATH="$BIN_DIR:$PATH"

#    log_info "🔄 创建自动激活解决方案..."
    
    # 创建激活脚本
    activation_script="$INSTALL_DIR/activate_qoze.sh"
    cat > "$activation_script" << 'EOF'
#!/bin/bash
# QozeCode 自动激活脚本

QOZE_BIN_DIR="$HOME/.local/bin"

# 检查是否已经在PATH中
if echo "$PATH" | grep -q "$QOZE_BIN_DIR"; then
    echo "✅ qoze 已在 PATH 中"
else
    echo "🔄 添加 qoze 到当前会话 PATH..."
    export PATH="$QOZE_BIN_DIR:$PATH"
fi

# 验证qoze命令
if command -v qoze &> /dev/null; then
    echo "🎉 qoze 命令可用！"
    return 0 2>/dev/null || exit 0
else
    echo "❌ qoze 命令不可用"
    return 1 2>/dev/null || exit 1
fi
EOF
    chmod +x "$activation_script"
    
    # 🎯 关键：创建一个可以被source的环境设置脚本
    env_script="$INSTALL_DIR/qoze_env.sh"
    cat > "$env_script" << EOF
#!/bin/bash
# QozeCode 环境变量设置脚本
# 使用方法: source $env_script

export PATH="$BIN_DIR:\$PATH"
EOF
    chmod +x "$env_script"
    
    # 🚀 尝试多种自动激活方法
#    log_info "🎯 尝试自动激活环境变量..."
    
    success_methods=()
    
    # 方法1: 尝试在当前shell中source配置文件
    if [ "$current_shell" != "fish" ]; then
#        log_info "方法1: 尝试重新加载 $primary_config"
        if source "$primary_config" 2>/dev/null; then
            success_methods+=("重新加载配置文件")
            log_success "✅ 成功重新加载 $primary_config"
        else
            log_warning "⚠️  重新加载配置文件失败"
        fi
    fi
    
    # 方法2: 检查命令是否可用
    if command -v qoze &> /dev/null; then
        success_methods+=("qoze命令可用")
        log_success "✅ qoze 命令在当前会话中可用"
    else
        log_info "ℹ️  qoze 命令在当前会话中暂不可用"
    fi
    
    # 🎉 显示结果和使用指南
    echo ""
    log_success "🎉 环境变量配置完成！"
    echo ""
    echo "📋 配置摘要："
    echo "  - 主配置文件: $primary_config"
    echo "  - 激活脚本: $activation_script"
    echo "  - 环境脚本: $env_script"
    echo ""
    
    if [ ${#success_methods[@]} -gt 0 ]; then
        echo "✅ 自动激活成功："
        for method in "${success_methods[@]}"; do
            echo "  - $method"
        done
        echo ""
    fi
    
    echo "🚀 使用 qoze 的方法："
    echo ""
    echo "  方法1 - 立即使用（推荐）："
    echo "    source $env_script"
    echo "    qoze"
    echo ""
    echo "  方法2 - 重新加载配置："
    if [ "$current_shell" = "fish" ]; then
        echo "    # Fish shell 需要重新打开终端"
    else
        echo "    source $primary_config"
        echo "    qoze"
    fi
    echo ""
    echo "  方法3 - 重新打开终端后直接使用："
    echo "    qoze"
    echo ""
    echo "  方法4 - 使用完整路径："
    echo "    $BIN_DIR/qoze"
    echo ""
    
    # 🎯 创建一个一键启动脚本
    quick_start="$INSTALL_DIR/qoze_start.sh"
    cat > "$quick_start" << EOF
#!/bin/bash
# QozeCode 一键启动脚本

echo "🚀 启动 QozeCode..."

# 确保PATH包含qoze
if ! command -v qoze &> /dev/null; then
    echo "🔄 设置环境变量..."
    export PATH="$BIN_DIR:\$PATH"
fi

# 启动qoze
if command -v qoze &> /dev/null; then
    echo "✅ 启动 qoze..."
    exec qoze "\$@"
else
    echo "❌ 无法找到 qoze 命令"
    echo "💡 尝试使用完整路径..."
    exec "$BIN_DIR/qoze" "\$@"
fi
EOF
    chmod +x "$quick_start"
    
    echo "📦 额外工具："
    echo "  - 一键启动: $quick_start"
    echo "  - 环境激活: source $activation_script"
    echo ""
    
    # 🎯 尝试自动执行source命令（如果可能）
    if [ -n "$BASH_VERSION" ] || [ -n "$ZSH_VERSION" ]; then
        log_info "🔄 尝试自动激活当前会话..."
        if source "$env_script" 2>/dev/null; then
            if command -v qoze &> /dev/null; then
                log_success "🎉 自动激活成功！qoze 命令现在可用"
                echo ""
                echo "🧪 测试命令："
                echo "  qoze --help"
                echo ""
                return 0
            fi
        fi
    fi
    
    log_info "💡 建议立即运行以下命令来激活 qoze："
    echo "  source $env_script && qoze --help"
    echo ""
}

# 验证安装
verify_installation() {
    log_info "验证安装..."
    
    # 检查启动脚本是否存在
    if [ ! -f "$BIN_DIR/qoze" ]; then
        log_error "启动脚本不存在: $BIN_DIR/qoze"
        return 1
    fi
    
    # 检查是否可执行
    if [ ! -x "$BIN_DIR/qoze" ]; then
        log_error "启动脚本不可执行: $BIN_DIR/qoze"
        return 1
    fi
    
    log_success "✅ 启动脚本验证通过"
    
    # 测试二进制文件
    log_info "🧪 测试 QozeCode..."
    if timeout 10 "$BIN_DIR/qoze" --help &>/dev/null; then
        log_success "✅ QozeCode 运行测试通过"
    else
        log_warning "⚠️  QozeCode 可能需要首次配置"
    fi
    
    echo ""
    log_success "🎉 QozeCode 安装验证完成！"
    echo ""
    
    # 🎯 提供立即使用的方案
    echo "🚀 立即开始使用 QozeCode："
    echo ""
    echo "  复制并运行以下命令："
    echo "  source ~/.qoze/qoze_env.sh && qoze"
    echo ""
    echo "📝 或者重新打开终端后直接使用："
    echo "  qoze"
    echo ""
    
    return 0
}

# 卸载函数
uninstall() {
    log_info "卸载 QozeCode..."
    
    # 删除安装目录
    if [ -d "$INSTALL_DIR" ]; then
        rm -rf "$INSTALL_DIR"
        log_success "已删除安装目录: $INSTALL_DIR"
    fi
    
    # 删除启动脚本
    if [ -f "$BIN_DIR/qoze" ]; then
        rm -f "$BIN_DIR/qoze"
        log_success "已删除启动脚本: $BIN_DIR/qoze"
    fi
    
    log_warning "请手动从 shell 配置文件中删除 PATH 配置"
    log_success "QozeCode 卸载完成"
}

# 显示调试信息
show_debug() {
    echo "QozeCode 安装调试信息"
    echo "====================="
    echo "安装目录: $INSTALL_DIR"
    echo "二进制目录: $BIN_DIR"
    echo "构建目录: $BUILD_DIR"
    echo ""
    echo "文件检查："
    echo "- 启动脚本: $([ -f "$BIN_DIR/qoze" ] && echo "✅ 存在" || echo "❌ 不存在")"
    echo "- 虚拟环境 qoze: $([ -f "$VENV_DIR/bin/qoze" ] && echo "✅ 存在" || echo "❌ 不存在")"
    echo "- 二进制文件: $([ -f "$INSTALL_DIR/qoze-dist/qoze" ] && echo "✅ 存在" || echo "❌ 不存在")"
    echo "- 源码目录: $([ -d "$BUILD_DIR/QozeCode" ] && echo "✅ 存在" || echo "❌ 不存在")"
    echo ""
    echo "PATH 检查："
    echo "- 当前 PATH 包含 BIN_DIR: $(echo "$PATH" | grep -q "$BIN_DIR" && echo "✅ 是" || echo "❌ 否")"
    echo "- qoze 命令可用: $(command -v qoze &>/dev/null && echo "✅ 是" || echo "❌ 否")"
    echo ""
    if command -v qoze &>/dev/null; then
        echo "qoze 命令位置: $(which qoze)"
    fi
}

# 显示帮助
show_help() {
    echo "QozeCode 安装脚本"
    echo ""
    echo "用法："
    echo "  $0 [选项]"
    echo ""
    echo "选项："
    echo "  install     安装 QozeCode (默认，优先尝试二进制构建)"
    echo "  source      强制使用源码安装"
    echo "  binary      强制使用二进制安装"
    echo "  uninstall   卸载 QozeCode"
    echo "  update      更新 QozeCode"
    echo "  debug       显示调试信息"
    echo "  --help      显示此帮助信息"
    echo ""
    echo "安装方式说明："
    echo "  - 默认会尝试构建二进制文件，失败时自动回退到源码安装"
    echo "  - 源码安装更稳定，但需要 Python 环境"
    echo "  - 二进制安装独立性更好，但构建可能失败"
}

# 主函数
main() {
    case "${1:-install}" in
        "install")
            log_info "开始安装 QozeCode..."
            check_requirements
            create_directories
            download_source
            create_venv
            install_dependencies
            
            # 确保 PyInstaller 可用
            if ! ensure_pyinstaller; then
                log_error "PyInstaller 安装失败，无法进行二进制构建"
                log_info "将使用源码安装方式"
                install_from_source
                configure_env
                if verify_installation; then
                    log_success "🎉 QozeCode 安装完成（源码方式）！"
                else
                    log_error "❌ 安装验证失败"
                    exit 1
                fi
                return
            fi
            
            # 尝试二进制构建
            log_info "尝试二进制构建..."
            if try_build_binary; then
                install_binary
                log_success "✅ 使用二进制安装方式完成"
            else
#                log_warning "⚠️  二进制构建失败，回退到源码安装方式"
#                log_info "这是正常的，源码安装同样稳定可靠"
                install_from_source
                log_success "✅ 使用源码安装方式完成"
            fi
            
            configure_env
            if verify_installation; then
                log_success "🎉 QozeCode 安装完成！"
            else
                log_error "❌ 安装验证失败"
                log_info "请检查以下内容："
                log_info "1. 启动脚本: $BIN_DIR/qoze"
                log_info "2. 虚拟环境: $VENV_DIR"
                log_info "3. PATH 配置: ~/.zshrc 或 ~/.bashrc"
                exit 1
            fi
            ;;
        "source")
            log_info "强制使用源码安装 QozeCode..."
            check_requirements
            create_directories
            download_source
            create_venv
            install_dependencies
            install_from_source
            configure_env
            verify_installation
            ;;
        "binary")
            log_info "强制使用二进制安装 QozeCode..."
            check_requirements
            create_directories
            download_source
            create_venv
            install_dependencies
            if try_build_binary; then
                install_binary
                configure_env
                verify_installation
            else
                log_error "二进制构建失败"
                exit 1
            fi
            ;;
        "uninstall")
            uninstall
            ;;
        "update")
            log_info "更新 QozeCode..."
            check_requirements
            download_source
            
            if [ -d "$INSTALL_DIR/qoze-dist" ]; then
                # 二进制安装方式更新
                create_venv
                install_dependencies
                if try_build_binary; then
                    install_binary
                    log_success "二进制方式更新完成"
                else
                    log_warning "二进制构建失败，转换为源码方式"
                    install_from_source
                    log_success "源码方式更新完成"
                fi
            else
                # 源码安装方式更新
                source "$VENV_DIR/bin/activate"
                cd "$BUILD_DIR/QozeCode"
                pip install -e . --upgrade
                log_success "源码方式更新完成"
            fi
            ;;
        "debug")
            show_debug
            # 额外的调试信息
            log_info "系统信息:"
            echo "- OS: $OSTYPE"
            echo "- Python: $(python3 --version 2>/dev/null || echo '未找到')"
            echo "- Git: $(git --version 2>/dev/null || echo '未找到')"
            echo "- PyInstaller: $(pip show pyinstaller 2>/dev/null | grep Version || echo '未安装')"
            
            if [ -f "$INSTALL_DIR/build.log" ]; then
                log_info "最近的构建日志 (最后20行):"
                tail -20 "$INSTALL_DIR/build.log"
            fi
            ;;
        "--help"|"-h")
            show_help
            ;;
        *)
            log_error "未知选项: $1"
            show_help
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"
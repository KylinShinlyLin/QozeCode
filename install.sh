#!/bin/bash

# QozeCode 安装脚本
# 仅支持源码安装方式

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置变量
REPO_URL="https://github.com/KylinShinlyLin/QozeCode.git"
BRANCH="main"
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
        log_warning "检测到已存在的源码，正在强制重置并更新到分支 $BRANCH..."
        cd "$BUILD_DIR/QozeCode"
        
        # 1. 强制放弃所有的本地修改（包括忽略的文件和未追踪目录）
        git reset --hard HEAD
        git clean -fdx
        
        # 2. 从远端获取最新的分支状态
        git fetch origin "$BRANCH"
        
        # 3. 强行将本地工作分支重置到 origin/$BRANCH 的状态，无论有任何分歧
        git checkout -f "$BRANCH" 2>/dev/null || git checkout -f -b "$BRANCH" "origin/$BRANCH"
        
        # 4. 彻底抛弃分歧差异，对齐远程
        git reset --hard "origin/$BRANCH"
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
}

# 安装项目依赖
install_dependencies() {
    log_info "安装项目依赖..."

    # 安装系统级依赖 (如 portaudio 用于 pyaudio)
    if [ "$(uname -s)" = "Darwin" ]; then
        log_info "检测到 macOS 系统，检查依赖 portaudio..."
        if command -v brew >/dev/null 2>&1; then
            if ! brew ls --versions portaudio >/dev/null 2>&1; then
                log_info "正在通过 Homebrew 安装 portaudio (语音功能必需)..."
                brew install portaudio
            else
                log_info "✅ portaudio 已安装"
            fi
        else
            log_warning "⚠️ 未检测到 Homebrew，请手动安装 portaudio (brew install portaudio) 以支持语音功能"
        fi
    elif [ "$(uname -s)" = "Linux" ]; then
        log_info "⚠️ 如果需要语音功能，Linux 系统请确保已安装 portaudio 相关库 (如: sudo apt-get install portaudio19-dev)"
    fi

    source "$VENV_DIR/bin/activate"
    cd "$BUILD_DIR/QozeCode"

    # 安装项目
    pip install -e .
    log_info "安装 Playwright 浏览器内核..."
    playwright install chromium

    log_success "项目依赖安装完成"
}

# 源码安装方式
install_from_source() {
    log_info "使用源码安装方式..."

    # 创建启动脚本，直接调用虚拟环境中的 qoze
    cat > "$BIN_DIR/qoze" << INNER_EOF
#!/bin/bash
# QozeCode 启动脚本 (源码版本)

exec "$VENV_DIR/bin/qoze" "\$@"
INNER_EOF

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

    # 创建激活脚本
    activation_script="$INSTALL_DIR/activate_qoze.sh"
    cat > "$activation_script" << 'INNER_EOF'
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
INNER_EOF
    chmod +x "$activation_script"

    # 创建一个可以被source的环境设置脚本
    env_script="$INSTALL_DIR/qoze_env.sh"
    cat > "$env_script" << INNER_EOF
#!/bin/bash
# QozeCode 环境变量设置脚本
# 使用方法: source $env_script

export PATH="$BIN_DIR:\$PATH"
INNER_EOF
    chmod +x "$env_script"

    log_success "🎉 环境变量配置完成！"
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

    # 测试 QozeCode
    log_info "🧪 测试 QozeCode..."
    if "$BIN_DIR/qoze" --help &>/dev/null; then
        log_success "✅ QozeCode 运行测试通过"
    else
        log_warning "⚠️  QozeCode 可能需要首次配置"
    fi

    echo ""
    log_success "🎉 QozeCode 安装验证完成！"
    echo ""
    echo "🚀 立即开始使用 QozeCode："
    echo ""
    echo "  复制并运行以下命令："
    echo "  source ~/.qoze/qoze_env.sh && qoze"
    echo ""
    return 0
}

# 卸载函数
uninstall() {
    log_info "卸载 QozeCode..."

    if [ -d "$INSTALL_DIR" ]; then
        rm -rf "$INSTALL_DIR"
        log_success "已删除安装目录: $INSTALL_DIR"
    fi

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
    echo "虚拟环境: $VENV_DIR"
    echo "构建目录: $BUILD_DIR"
    echo ""
    echo "文件检查："
    echo "- 启动脚本: $([ -f "$BIN_DIR/qoze" ] && echo "✅ 存在" || echo "❌ 不存在")"
    echo "- 虚拟环境 qoze: $([ -f "$VENV_DIR/bin/qoze" ] && echo "✅ 存在" || echo "❌ 不存在")"
    echo "- 源码目录: $([ -d "$BUILD_DIR/QozeCode" ] && echo "✅ 存在" || echo "❌ 不存在")"
    echo ""
    echo "PATH 检查："
    echo "- 当前 PATH 包含 BIN_DIR: $(echo "$PATH" | grep -q "$BIN_DIR" && echo "✅ 是" || echo "❌ 否")"
    echo "- qoze 命令可用: $(command -v qoze &>/dev/null && echo "✅ 是" || echo "❌ 否")"
    echo ""
}

# 显示帮助
show_help() {
    echo "QozeCode 安装脚本"
    echo ""
    echo "用法："
    echo "  $0 [选项]"
    echo ""
    echo "选项："
    echo "  install     安装 QozeCode (源码安装)"
    echo "  uninstall   卸载 QozeCode"
    echo "  update      更新 QozeCode"
    echo "  debug       显示调试信息"
    echo "  --help      显示此帮助信息"
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
            install_from_source
            configure_env
            verify_installation
            ;;
        "uninstall")
            uninstall
            ;;
        "update")
            log_info "更新 QozeCode..."
            check_requirements
            download_source
            source "$VENV_DIR/bin/activate"
            cd "$BUILD_DIR/QozeCode"
            pip install -e . --upgrade
            log_success "QozeCode 更新完成"
            ;;
        "debug")
            show_debug
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

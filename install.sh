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

    # 如果检测到的 python3 在 Qoze 安装目录内（用户可能在旧 venv 中运行脚本），
    # 需要使用系统 Python，否则后续删除旧 venv 后 python3 会丢失
    PYTHON3_CMD="python3"
    PYTHON3_PATH=$(command -v python3)
    if [[ "$PYTHON3_PATH" == "$INSTALL_DIR"* ]]; then
        log_warning "检测到 python3 来自 Qoze 虚拟环境，正在查找系统 python3..."
        # 临时从 PATH 中移除 venv 路径
        SAVED_PATH="$PATH"
        export PATH=$(echo "$PATH" | sed "s|$INSTALL_DIR/[^:]*:||g" | sed 's/:$//')
        PYTHON3_CMD=$(command -v python3 2>/dev/null || echo "")
        if [[ -z "$PYTHON3_CMD" ]]; then
            # 备选：常见系统路径
            for p in /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
                if [[ -x "$p" ]]; then PYTHON3_CMD="$p"; break; fi
            done
        fi
        export PATH="$SAVED_PATH"
        if [[ -z "$PYTHON3_CMD" ]]; then
            log_error "无法找到系统 Python 3。请先退出虚拟环境 (deactivate) 再运行安装脚本。"
            exit 1
        fi
        log_success "找到系统 python3: $PYTHON3_CMD"
    fi

    python_version=$($PYTHON3_CMD -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")

    if ! $PYTHON3_CMD -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)"; then
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

    if [ -d "$BUILD_DIR/QozeCode/.git" ]; then
        log_warning "检测到已存在的源码，正在强制重置并更新到远端分支 origin/$BRANCH..."
        cd "$BUILD_DIR/QozeCode"
        
        # 0. 中止任何可能卡住的合并、衍合或变基状态
        git merge --abort >/dev/null 2>&1 || true
        git rebase --abort >/dev/null 2>&1 || true
        git am --abort >/dev/null 2>&1 || true
        
        # 1. 获取远端最新状态
        git fetch origin "$BRANCH"
        
        # 2. 清理所有未跟踪的文件、目录和忽略的文件
        git clean -fdx
        
        # 3. 强行检出分支，忽略本地改动
        git checkout -f "$BRANCH" >/dev/null 2>&1 || git checkout -f -b "$BRANCH" "origin/$BRANCH"
        
        # 4. 【核心】强行以 origin/$BRANCH 为准，完全覆盖本地可能存在的任何冲突和修改
        git reset --hard "origin/$BRANCH"
    else
        # 如果目录存在但不是git仓库，先清理
        if [ -d "$BUILD_DIR/QozeCode" ]; then
            rm -rf "$BUILD_DIR/QozeCode"
        fi
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

    $PYTHON3_CMD -m venv "$VENV_DIR"
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

    # macOS 附带语音依赖 pyaudio (pyproject.toml 的 [macos] extra)；其他平台跳过
    pkg_spec="."
    if [ "$(uname -s)" = "Darwin" ]; then
        pkg_spec=".[macos]"
    fi

    pip install -e "$pkg_spec" || {
        log_error "依赖安装失败，请检查网络连接和 Python 环境"
        exit 1
    }

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

# 可选组件: QozeCode 菜单栏伴侣 (Island) — 仅 macOS
# 依赖 Command Line Tools 的 swiftc (无需完整 Xcode); 任何缺失都跳过而非失败,
# 绝不影响 QozeCode 主程序安装结果
install_island_component() {
    # 非 macOS 静默跳过
    [ "$(uname -s)" = "Darwin" ] || return 0

    local build_script="$BUILD_DIR/QozeCode/macos/build_island.sh"
    # 源码不含 Island (旧版本) 静默跳过
    [ -f "$build_script" ] || return 0

    # 依赖检查: swiftc (xcode-select --install 即可, 无需完整 Xcode)
    # 无 Swift 构建环境 → 直接跳过, 绝不阻碍 QozeCode (Python agent) 安装
    if ! command -v swiftc &>/dev/null; then
        log_warning "未检测到 Swift 构建环境, 跳过 Island (QozeCode 主程序不受影响)"
        log_info "后续如需 Island: xcode-select --install 后, 执行 bash $build_script"
        return 0
    fi

    # 有 Swift 构建环境即默认直接安装 (无需询问; 卸载: bash macos/uninstall_island.sh)
    log_info "检测到 Swift 构建环境, 编译安装 Island 菜单栏伴侣..."
    if bash "$build_script"; then
        log_success "Island 安装完成: ~/Applications/QozeCode.app"
        open "$HOME/Applications/QozeCode.app" 2>/dev/null || true
    else
        log_warning "Island 构建失败, 不影响 QozeCode 主程序; 可稍后手动重试: bash $build_script"
    fi
    return 0
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

    # Island (macOS 菜单栏伴侣) 一并卸载
    if [ -d "$HOME/Applications/QozeCode.app" ] || [ -d "$HOME/Applications/QozeIsland.app" ]; then
        if [ -f "$BUILD_DIR/QozeCode/macos/uninstall_island.sh" ]; then
            bash "$BUILD_DIR/QozeCode/macos/uninstall_island.sh" || true
        else
            pkill -x QozeCode 2>/dev/null || true
            pkill -x QozeIsland 2>/dev/null || true
            rm -rf "$HOME/Applications/QozeCode.app" "$HOME/Applications/QozeIsland.app"
            rm -f "$HOME/Library/LaunchAgents/com.qoze.code.plist" \
                  "$HOME/Library/LaunchAgents/com.qoze.island.plist"
        fi
        log_success "已卸载 Island"
    fi

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
    echo "              macOS 且有 Swift 构建环境时自动安装 Island 菜单栏伴侣"
    echo "  uninstall   卸载 QozeCode"
    echo "  update      更新 QozeCode"
    echo "  debug       显示调试信息"
    echo "  --help      显示此帮助信息"
}

# 主函数
main() {
    local cmd="${1:-install}"

    case "$cmd" in
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
            install_island_component
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
            pkg_spec="."
            if [ "$(uname -s)" = "Darwin" ]; then
                pkg_spec=".[macos]"
            fi
            pip install -e "$pkg_spec" --upgrade || {
                log_error "核心依赖更新失败"
                exit 1
            }
            log_success "QozeCode 更新完成"

            # Island 已安装则同步重建 (协议与主程序同版本演进; 失败仅提示)
            if [ "$(uname -s)" = "Darwin" ] \
               && [ -d "$HOME/Applications/QozeCode.app" ] \
               && [ -f "$BUILD_DIR/QozeCode/macos/build_island.sh" ] \
               && command -v swiftc &>/dev/null; then
                log_info "检测到已安装 Island, 同步重新构建..."
                bash "$BUILD_DIR/QozeCode/macos/build_island.sh" || \
                    log_warning "Island 重建失败, 可稍后手动执行: bash $BUILD_DIR/QozeCode/macos/build_island.sh"
            fi
            ;;
        "debug")
            show_debug
            ;;
        "--help"|"-h")
            show_help
            ;;
        *)
            log_error "未知选项: $cmd"
            show_help
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"

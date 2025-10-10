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
    log_info "下载 QozeCode 源码..."
    
    if [ -d "$BUILD_DIR/QozeCode" ]; then
        log_warning "检测到已存在的源码，正在更新..."
        cd "$BUILD_DIR/QozeCode"
        git pull origin main
    else
        cd "$BUILD_DIR"
        git clone "$REPO_URL"
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
    
    # 询问是否安装浏览器功能
    if [ -t 0 ]; then  # 检查是否在交互式终端中
        read -p "是否安装浏览器自动化功能？(y/N): " install_browser
        if [[ $install_browser =~ ^[Yy]$ ]]; then
            pip install -e ".[browser]"
            log_info "安装 Playwright 浏览器..."
            playwright install
        fi
    else
        log_info "非交互式安装，跳过浏览器功能"
    fi
    
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
        log_warning "未找到 Qoze.spec 文件，跳过二进制构建"
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
    
    # 复制整个 dist 目录以保持依赖完整
    if [ -d "$INSTALL_DIR/qoze-dist" ]; then
        rm -rf "$INSTALL_DIR/qoze-dist"
    fi
    cp -r "$BUILD_DIR/QozeCode/dist/qoze" "$INSTALL_DIR/qoze-dist"
    
    # 创建启动脚本
    cat > "$BIN_DIR/qoze" << 'EOF'
#!/bin/bash
# QozeCode 启动脚本 (二进制版本)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QOZE_DIR="$(dirname "$SCRIPT_DIR")/.qoze/qoze-dist"

if [ -f "$QOZE_DIR/qoze" ]; then
    exec "$QOZE_DIR/qoze" "$@"
else
    echo "错误: QozeCode 二进制文件未找到"
    echo "预期位置: $QOZE_DIR/qoze"
    echo "请重新运行安装脚本"
    exit 1
fi
EOF
    
    chmod +x "$BIN_DIR/qoze"
    
    log_success "二进制文件安装完成"
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
    
    # 定义所有可能的 shell 配置文件
    declare -a shell_configs=(
        "$HOME/.zshrc"
        "$HOME/.bashrc"
        "$HOME/.bash_profile"
        "$HOME/.profile"
    )
    
    # 检测当前使用的 shell
    current_shell=$(basename "$SHELL" 2>/dev/null || echo "unknown")
    log_info "检测到当前 shell: $current_shell"
    
    # 记录已配置的文件
    configured_files=()
    
    # 遍历所有配置文件，如果存在就添加 PATH
    for config_file in "${shell_configs[@]}"; do
        if [ -f "$config_file" ]; then
            # 检查是否已经添加了 PATH
            if ! grep -q "# QozeCode PATH" "$config_file" 2>/dev/null; then
                log_info "配置 $config_file..."
                echo "" >> "$config_file"
                echo "# QozeCode PATH" >> "$config_file"
                echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$config_file"
                configured_files+=("$config_file")
                log_success "✅ 已添加 PATH 到 $config_file"
            else
                log_info "📝 $config_file 已经配置过 QozeCode PATH"
            fi
        fi
    done
    
    # 如果没有找到任何现有的配置文件，创建适合当前 shell 的配置文件
    if [ ${#configured_files[@]} -eq 0 ]; then
        case "$current_shell" in
            "zsh")
                target_config="$HOME/.zshrc"
                ;;
            "bash")
                target_config="$HOME/.bashrc"
                ;;
            "fish")
                target_config="$HOME/.config/fish/config.fish"
                # Fish shell 语法不同
                mkdir -p "$(dirname "$target_config")"
                if ! grep -q "# QozeCode PATH" "$target_config" 2>/dev/null; then
                    echo "" >> "$target_config"
                    echo "# QozeCode PATH" >> "$target_config"
                    echo "set -gx PATH \"$BIN_DIR\" \$PATH" >> "$target_config"
                    configured_files+=("$target_config")
                    log_success "✅ 已为 Fish shell 配置 PATH 到 $target_config"
                fi
                ;;
            *)
                target_config="$HOME/.profile"
                ;;
        esac
        
        # 为非 Fish shell 创建配置
        if [ "$current_shell" != "fish" ] && [ -n "$target_config" ]; then
            log_info "创建新的配置文件: $target_config"
            echo "" >> "$target_config"
            echo "# QozeCode PATH" >> "$target_config"
            echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$target_config"
            configured_files+=("$target_config")
            log_success "✅ 已创建并配置 $target_config"
        fi
    fi
    
    # 临时添加到当前会话
    export PATH="$BIN_DIR:$PATH"
    
    # 显示配置总结
    if [ ${#configured_files[@]} -gt 0 ]; then
        log_success "🎉 PATH 配置完成！已配置以下文件："
        for file in "${configured_files[@]}"; do
            echo "  - $file"
        done
        echo ""
        log_info "💡 使配置生效的方法："
        echo "  方法1: 重新打开终端"
        echo "  方法2: 根据你的 shell 运行以下命令之一："
        
        if [[ " ${configured_files[*]} " =~ " $HOME/.zshrc " ]]; then
            echo "    source ~/.zshrc"
        fi
        if [[ " ${configured_files[*]} " =~ " $HOME/.bashrc " ]]; then
            echo "    source ~/.bashrc"
        fi
        if [[ " ${configured_files[*]} " =~ " $HOME/.bash_profile " ]]; then
            echo "    source ~/.bash_profile"
        fi
        if [[ " ${configured_files[*]} " =~ " $HOME/.profile " ]]; then
            echo "    source ~/.profile"
        fi
    else
        log_warning "⚠️  未找到合适的 shell 配置文件进行配置"
        log_info "你可以手动添加以下行到你的 shell 配置文件："
        echo "  export PATH=\"$BIN_DIR:\$PATH\""
    fi
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
    
    # 临时添加到 PATH 进行测试
    export PATH="$BIN_DIR:$PATH"
    
    # 测试命令是否可用
    if command -v qoze &> /dev/null; then
        log_success "QozeCode 安装成功！"
        echo ""
        echo "🎉 安装完成！使用方法："
        echo "  qoze          # 启动 QozeCode"
        echo ""
        echo "📝 注意事项："
        echo "  - 如果在新终端中命令未找到，请重新打开终端"
        echo "  - 或者运行: source ~/.zshrc (zsh) 或 source ~/.bashrc (bash)"
        echo ""
        
        # 简单测试
        log_info "测试 QozeCode..."
        if timeout 10 "$BIN_DIR/qoze" --help &>/dev/null; then
            log_success "QozeCode 运行测试通过"
        else
            log_warning "QozeCode 可能需要首次配置，请运行 'qoze' 进行初始化"
        fi
        
        return 0
    else
        log_error "安装验证失败：qoze 命令不可用"
        return 1
    fi
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
                log_warning "⚠️  二进制构建失败，回退到源码安装方式"
                log_info "这是正常的，源码安装同样稳定可靠"
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
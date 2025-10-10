#!/bin/bash

# QozeCode 安装脚本
# 支持从源码编译安装并自动配置环境变量

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
    required_version="3.9"
    
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
    
    log_success "目录创建完成"
}

# 下载源码
download_source() {
    log_info "下载 QozeCode 源码..."
    
    if [ -d "$INSTALL_DIR/QozeCode" ]; then
        log_warning "检测到已存在的安装，正在更新..."
        cd "$INSTALL_DIR/QozeCode"
        git pull origin main
    else
        cd "$INSTALL_DIR"
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

# 安装依赖
install_dependencies() {
    log_info "安装项目依赖..."
    
    source "$VENV_DIR/bin/activate"
    cd "$INSTALL_DIR/QozeCode"
    
    # 安装项目
    pip install -e .
    
    # 安装可选依赖（浏览器功能）
    read -p "是否安装浏览器自动化功能？(y/N): " install_browser
    if [[ $install_browser =~ ^[Yy]$ ]]; then
        pip install -e ".[browser]"
        log_info "安装 Playwright 浏览器..."
        playwright install
    fi
    
    log_success "依赖安装完成"
}

# 创建启动脚本
create_launcher() {
    log_info "创建启动脚本..."
    
    cat > "$BIN_DIR/qoze" << EOF
#!/bin/bash
# QozeCode 启动脚本

# 激活虚拟环境并运行
source "$VENV_DIR/bin/activate"
cd "$INSTALL_DIR/QozeCode"
python launcher.py "\$@"
EOF
    
    chmod +x "$BIN_DIR/qoze"
    
    log_success "启动脚本创建完成"
}

# 配置环境变量
configure_env() {
    log_info "配置环境变量..."
    
    # 检测 shell 类型
    if [ -n "$ZSH_VERSION" ]; then
        shell_rc="$HOME/.zshrc"
    elif [ -n "$BASH_VERSION" ]; then
        shell_rc="$HOME/.bashrc"
    else
        shell_rc="$HOME/.profile"
    fi
    
    # 检查是否已经添加了 PATH
    if ! grep -q "$BIN_DIR" "$shell_rc" 2>/dev/null; then
        echo "" >> "$shell_rc"
        echo "# QozeCode PATH" >> "$shell_rc"
        echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$shell_rc"
        log_success "已添加 $BIN_DIR 到 $shell_rc"
    else
        log_warning "PATH 已经配置过了"
    fi
    
    # 临时添加到当前会话
    export PATH="$BIN_DIR:$PATH"
}

# 验证安装
verify_installation() {
    log_info "验证安装..."
    
    if command -v qoze &> /dev/null; then
        log_success "QozeCode 安装成功！"
        echo ""
        echo "使用方法："
        echo "  qoze          # 启动 QozeCode"
        echo "  qoze --help   # 查看帮助"
        echo ""
        echo "注意：如果命令未找到，请重新打开终端或运行："
        echo "  source $shell_rc"
    else
        log_error "安装验证失败，请检查安装过程"
        exit 1
    fi
}

# 卸载函数
uninstall() {
    log_info "卸载 QozeCode..."
    
    # 删除安装目录
    if [ -d "$INSTALL_DIR" ]; then
        rm -rf "$INSTALL_DIR"
        log_success "已删除安装目录"
    fi
    
    # 删除启动脚本
    if [ -f "$BIN_DIR/qoze" ]; then
        rm -f "$BIN_DIR/qoze"
        log_success "已删除启动脚本"
    fi
    
    log_warning "请手动从 shell 配置文件中删除 PATH 配置"
    log_success "QozeCode 卸载完成"
}

# 显示帮助
show_help() {
    echo "QozeCode 安装脚本"
    echo ""
    echo "用法："
    echo "  $0 [选项]"
    echo ""
    echo "选项："
    echo "  install     安装 QozeCode (默认)"
    echo "  uninstall   卸载 QozeCode"
    echo "  update      更新 QozeCode"
    echo "  --help      显示此帮助信息"
    echo ""
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
            create_launcher
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
            cd "$INSTALL_DIR/QozeCode"
            pip install -e . --upgrade
            log_success "QozeCode 更新完成"
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
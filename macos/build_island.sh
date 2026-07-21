#!/bin/bash
# build_island.sh — QozeCode 菜单栏伴侣本地源码构建 (swiftc 直接编译, 无需 Xcode 工程)
# 产物: ~/Applications/QozeCode.app (ad-hoc 签名, 本地运行免公证)
set -euo pipefail

cd "$(dirname "$0")"
SRC_DIR="QozeCode/Sources"
APP_DIR="$HOME/Applications/QozeCode.app"
LEGACY_APP_DIR="$HOME/Applications/QozeIsland.app"   # v0.4 前旧程序名
LOGO="../assets/logo.png"

# 前置检查
if ! command -v swiftc &>/dev/null; then
    echo "❌ 未找到 swiftc, 请先安装 Xcode Command Line Tools:"
    echo "   xcode-select --install"
    exit 1
fi

SWIFT_VERSION=$(swiftc --version | head -1)
echo "使用编译器: $SWIFT_VERSION"

echo "编译 QozeCode..."
# 收集全部 swift 源码
SOURCES=$(find "$SRC_DIR" -name "*.swift" | sort)

# 架构自适应 (Apple Silicon / Intel)
ARCH=$(uname -m)

# shellcheck disable=SC2086
swiftc -O \
    -parse-as-library \
    -target "${ARCH}-apple-macosx14.0" \
    -framework SwiftUI \
    -framework Foundation \
    -framework UserNotifications \
    -module-name QozeCode \
    $SOURCES \
    -o /tmp/qoze_code_island_build

echo "📁 打包 App bundle..."
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"
mv /tmp/qoze_code_island_build "$APP_DIR/Contents/MacOS/QozeCode"
cp QozeCode/Info.plist "$APP_DIR/Contents/Info.plist"

# App 图标: assets/logo.png → AppIcon.icns (多尺寸 iconset)
if [ -f "$LOGO" ]; then
    echo "🎨 生成 App 图标 (assets/logo.png)..."
    ICONSET="$(mktemp -d)/AppIcon.iconset"
    mkdir -p "$ICONSET"
    for size in 16 32 128 256 512; do
        sips -z "$size" "$size" "$LOGO" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
        double=$((size * 2))
        sips -z "$double" "$double" "$LOGO" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
    done
    iconutil -c icns "$ICONSET" -o "$APP_DIR/Contents/Resources/AppIcon.icns"
else
    echo "⚠️  未找到 $LOGO, 跳过图标生成"
fi

echo "🔏 ad-hoc 签名..."
codesign --force --sign - "$APP_DIR" 2>/dev/null || true

# 旧版迁移: 清理 v0.4 前的 QozeIsland.app, 避免双 App 并存抢占 socket
if [ -d "$LEGACY_APP_DIR" ]; then
    echo "🧹 清理旧版 QozeIsland.app..."
    pkill -x QozeIsland 2>/dev/null || true
    rm -rf "$LEGACY_APP_DIR"
fi

echo "✅ 安装完成: $APP_DIR"
echo ""
echo "启动方式:"
echo "  手动:  open ~/Applications/QozeCode.app"
echo "  自启:  bash macos/install_launch_agent.sh"

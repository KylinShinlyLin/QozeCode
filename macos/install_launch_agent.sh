#!/bin/bash
# install_launch_agent.sh — 安装 QozeCode 菜单栏伴侣开机自启 (可选)
set -euo pipefail
cd "$(dirname "$0")"
OLD="$HOME/Library/LaunchAgents/com.qoze.island.plist"
DEST="$HOME/Library/LaunchAgents/com.qoze.code.plist"
mkdir -p "$HOME/Library/LaunchAgents"
# 旧版迁移 (v0.4 前 label 为 com.qoze.island)
if [ -f "$OLD" ]; then
    launchctl unload "$OLD" 2>/dev/null || true
    rm "$OLD"
    echo "🧹 已移除旧版 LaunchAgent: com.qoze.island.plist"
fi
sed "s|__HOME__|$HOME|g" com.qoze.code.plist > "$DEST"
launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST"
echo "✅ 已安装开机自启: $DEST"
echo "   取消自启: launchctl unload $DEST && rm $DEST"

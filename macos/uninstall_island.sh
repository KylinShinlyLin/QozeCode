#!/bin/bash
# uninstall_island.sh — 卸载 QozeCode 菜单栏伴侣 (兼容清理旧版 QozeIsland)
set -euo pipefail

for PLIST in "$HOME/Library/LaunchAgents/com.qoze.code.plist" \
             "$HOME/Library/LaunchAgents/com.qoze.island.plist"; do
    if [ -f "$PLIST" ]; then
        launchctl unload "$PLIST" 2>/dev/null || true
        rm "$PLIST"
        echo "🗑  已移除 LaunchAgent: $(basename "$PLIST")"
    fi
done

pkill -x QozeCode 2>/dev/null || true
pkill -x QozeIsland 2>/dev/null || true
rm -rf "$HOME/Applications/QozeCode.app" "$HOME/Applications/QozeIsland.app"
echo "🗑  已移除 App (QozeCode / 旧版 QozeIsland)"

rm -f "$HOME/.qoze/island.sock"
echo "✅ 卸载完成"

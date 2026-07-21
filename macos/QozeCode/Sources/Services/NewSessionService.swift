// NewSessionService.swift — 从 Island 一键创建新 QozeCode 会话
// V1 策略: 默认 macOS Terminal.app, AppleScript "do script qoze" 新窗口启动 agent
// - do script 总是打开新窗口, Terminal 未运行时系统自动拉起
// - 新窗口为 login shell, 用户 PATH 正常加载, 直接执行 qoze 即可
// - 首次执行会触发 macOS 自动化授权弹窗 (与 FocusService 相同, 拒绝则静默失败)
// - 新会话启动后经 IslandReporter 自动注册, 无需 App 侧额外处理

import AppKit
import Foundation

enum NewSessionService {

    /// 默认入口: Terminal.app 新窗口执行 qoze
    @MainActor
    static func createInTerminal() {
        DebugLog.log("new session request: Terminal.app + qoze")
        if runAppleScript(terminalNewSessionScript(command: "qoze")) {
            DebugLog.log("✅ new session created via Terminal do script")
        } else {
            DebugLog.log("❌ new session failed (自动化授权被拒?)")
        }
    }

    // MARK: - AppleScript

    @discardableResult
    private static func runAppleScript(_ source: String) -> Bool {
        var error: NSDictionary?
        guard let script = NSAppleScript(source: source) else { return false }
        script.executeAndReturnError(&error)
        if let error = error {
            NSLog("[QozeCode] AppleScript error: \(error)"); DebugLog.log("AppleScript error: \(error)")
            return false
        }
        return true
    }

    /// Terminal.app: 新窗口执行命令 (activate 置前台 + do script 开新窗)
    private static func terminalNewSessionScript(command: String) -> String {
        """
        tell application "Terminal"
            activate
            do script "\(command)"
        end tell
        """
    }
}

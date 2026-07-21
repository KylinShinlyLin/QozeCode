// FocusService.swift — 点击会话跳转对应终端窗口 (M3, v0.4.1 多级兜底版)
// 跳转策略 (按优先级):
//   1. tty + AppleScript 精确到 tab (iTerm2 / Terminal.app)
//      - 识别依据: host_app_name (新版上报) 或 term_program (旧版也有), 双重判断
//   2. host_app_pid → NSRunningApplication 激活应用窗口 (IDEA/VSCode, 无权限弹窗)
//   3. 全部失败 → NSLog 诊断信息
// 注意: AppleScript 控制其他 App 首次会触发 macOS 自动化授权弹窗,
//       若用户拒绝, 自动降级到 pid 激活

import AppKit
import Foundation

enum FocusService {

    @MainActor
    static func focus(session: Session) {
        DebugLog.log("focus request: session=\(session.id) tty=\(session.tty) term=\(session.termProgram) host=\(session.hostAppName)(\(session.hostAppPid))")

        let host = session.hostAppName.lowercased()
        let term = session.termProgram.lowercased()
        let tty = session.tty

        // ① AppleScript 精确跳转: iTerm2
        if !tty.isEmpty, host.contains("iterm") || term.contains("iterm") {
            if runAppleScript(iTermFocusScript(tty: tty)) {
                DebugLog.log("✅ focused via iTerm2 AppleScript")
                return
            }
        }

        // ② AppleScript 精确跳转: Terminal.app
        if !tty.isEmpty, host == "terminal" || term.contains("apple_terminal") {
            if runAppleScript(terminalFocusScript(tty: tty)) {
                DebugLog.log("✅ focused via Terminal AppleScript")
                return
            }
        }

        // ③ IDE/其他 GUI 应用 (IDEA/PyCharm/VSCode):
        //    优先 AppleScript reopen+activate — reopen 等效点击 Dock 图标,
        //    是还原最小化窗口的标准语义; NSRunningApplication.activate 对
        //    JetBrains 系会"假成功"(返回 true 不抬窗) 且无法还原最小化
        if session.hostAppPid > 0,
           let app = NSRunningApplication(processIdentifier: pid_t(session.hostAppPid)) {
            if let appName = app.localizedName, !appName.isEmpty {
                if runAppleScript(reopenScript(appName: appName)) {
                    DebugLog.log("✅ focused via reopen+activate: \(appName)")
                    return
                }
                DebugLog.log("reopen script failed for \(appName), 尝试 NSRunningApplication")
            }
            // ④ 兜底: NSRunningApplication 激活
            let ok = app.activate(options: [.activateAllWindows])
            DebugLog.log("NSRunningApplication.activate pid=\(session.hostAppPid) returned \(ok)")
            if ok { return }
            // ⑤ 二级兜底: NSWorkspace 按 bundle 拉起
            if let bundleURL = app.bundleURL {
                DebugLog.log("fallback: NSWorkspace.openApplication \(bundleURL.path)")
                NSWorkspace.shared.openApplication(at: bundleURL,
                                                   configuration: .init()) { _, error in
                    if let error = error {
                        DebugLog.log("❌ openApplication error: \(error.localizedDescription)")
                    } else {
                        DebugLog.log("✅ focused via NSWorkspace.openApplication")
                    }
                }
                return
            }
        }

        DebugLog.log("❌ focus failed: 无可用跳转通道 (host_app_pid=0? 需重启 QozeCode)")
    }

    // MARK: - AppleScript

    /// 执行 AppleScript, 成功返回 true
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

    /// 通用 GUI 应用: reopen (Dock 点击语义, 还原最小化窗口) + activate (置前台)
    private static func reopenScript(appName: String) -> String {
        """
        tell application "\(appName)"
            reopen
            activate
        end tell
        """
    }

    /// iTerm2: 遍历 window/tab/session 按 tty 匹配并选中
    private static func iTermFocusScript(tty: String) -> String {
        """
        tell application "iTerm2"
            activate
            repeat with w in windows
                try
                    set miniaturized of w to false
                end try
            end repeat
            repeat with w in windows
                repeat with t in tabs of w
                    repeat with s in sessions of t
                        if tty of s is "\(tty)" then
                            select t
                            select w
                            return true
                        end if
                    end repeat
                end repeat
            end repeat
        end tell
        """
    }

    /// Terminal.app: 遍历 window/tab 按 tty 匹配并选中
    private static func terminalFocusScript(tty: String) -> String {
        """
        tell application "Terminal"
            activate
            repeat with w in windows
                try
                    set miniaturized of w to false
                end try
            end repeat
            repeat with w in windows
                repeat with t in tabs of w
                    if tty of t is "\(tty)" then
                        set selected of t to true
                        set index of w to 1
                        return true
                    end if
                end repeat
            end repeat
        end tell
        """
    }
}

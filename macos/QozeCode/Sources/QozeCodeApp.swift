// QozeCodeApp.swift — App 入口: MenuBarExtra 菜单栏场景 + UDS 服务启动
// 菜单栏图标: idle = template 系统默认色; 非 idle = 离线染色 NSImage (颜色即状态)
// 动效: thinking/waiting = 透明度呼吸 (phaseAnimator), executing = 旋转 (repeatForever)

import AppKit
import SwiftUI

@main
struct QozeCodeApp: App {
    @StateObject private var store = SessionStore.shared
    @State private var executingSpin = false

    init() {
        // 单实例保护: 已有同 bundle id 实例在运行时, 激活它并退出自己
        // (防止 build/pkill/open 循环中残留僵尸实例抢占 socket 导致状态错乱)
        let myPid = ProcessInfo.processInfo.processIdentifier
        let peers = NSRunningApplication.runningApplications(withBundleIdentifier: "com.qoze.code")
        if let existing = peers.first(where: { $0.processIdentifier != myPid }) {
            NSLog("[QozeCode] 检测到已运行实例 pid=\(existing.processIdentifier), 退出当前实例")
            existing.activate(options: [.activateAllWindows])
            exit(0)
        }

        // 启动 UDS server (后台线程 accept)
        IslandServer.shared.start()
        // 请求通知授权
        NotificationService.shared.requestAuthorization()
    }

    /// 当前聚合状态 (无会话时为 nil → 隐藏图标由 isInserted 控制, V1 恒显示 idle 图标)
    private var aggregated: AgentState {
        store.aggregatedState ?? .idle
    }

    var body: some Scene {
        MenuBarExtra(isInserted: .constant(true)) {
            PopoverView()
        } label: {
            HStack(spacing: 2) {
                menuBarImage
                // 多会话角标
                if store.activeCount > 1 {
                    Text("\(store.activeCount)")
                        .font(.system(size: 9, weight: .bold, design: .rounded))
                }
            }
            // 状态色: idle 保持系统默认色, 其余状态着色 (余光即可区分思考/执行/待批准/完成/出错)
            .foregroundStyle(aggregated == .idle ? Color.primary : MenuBarIcon.color(for: aggregated))
        }
        .menuBarExtraStyle(.window)
    }

    @ViewBuilder
    private var menuBarImage: some View {
        let name = MenuBarIcon.symbolName(for: aggregated)
        switch aggregated {
        case .idle:
            // template 渲染: 与系统菜单栏其他图标一致的默认色
            Image(systemName: name)
        case .thinking, .waitingApproval:
            // 染色位图 + 透明度呼吸 (waiting 节奏更快)
            Image(nsImage: MenuBarIcon.tintedImage(for: aggregated))
                .renderingMode(.original)
                .phaseAnimator([1.0, 0.3]) { view, phase in
                    view.opacity(phase)
                } animation: { _ in
                    .easeInOut(duration: aggregated == .waitingApproval ? 0.6 : 1.2)
                }
        case .executing:
            // 染色位图 + 无限旋转 (齿轮持续转动)
            Image(nsImage: MenuBarIcon.tintedImage(for: aggregated))
                .renderingMode(.original)
                .rotationEffect(.degrees(executingSpin ? 360 : 0))
                .animation(.linear(duration: 1.2).repeatForever(autoreverses: false),
                           value: executingSpin)
                .onAppear { executingSpin = true }
        case .done, .error:
            // 手绘徽章: 彩底圆 + 白 glyph (StateIconRenderer, 与通知附件同源)
            Image(nsImage: StateIconRenderer.icon(for: aggregated, size: 15))
                .renderingMode(.original)
        }
    }
}

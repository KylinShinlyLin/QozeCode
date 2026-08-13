// QozeCodeApp.swift — App 入口: MenuBarExtra 菜单栏场景 + UDS 服务启动
// 菜单栏图标: idle = template 系统默认色; 非 idle = 静态缓存的着色 NSImage

import AppKit
import SwiftUI

@main
struct QozeCodeApp: App {
    @StateObject private var store = SessionStore.shared

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

    /// 当前聚合状态 (无会话时为 nil → V1 恒显示 idle 图标)
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
            // 状态色: idle 保持系统默认色, 其余状态使用图像内嵌状态色
            .foregroundStyle(aggregated == .idle ? Color.primary : MenuBarIcon.color(for: aggregated))
        }
        .menuBarExtraStyle(.window)
    }

    @ViewBuilder
    private var menuBarImage: some View {
        switch aggregated {
        case .idle:
            // template 渲染: 与系统菜单栏其他图标一致的默认色
            Image(systemName: MenuBarIcon.symbolName(for: aggregated))
        case .thinking, .executing, .waitingApproval:
            // 活动状态保留原有状态专属尺寸，但仅渲染静态缓存图像。
            Image(nsImage: MenuBarIcon.tintedImage(for: aggregated))
                .renderingMode(.original)
        case .done, .error, .interrupted:
            // 终态使用静态缓存徽章。
            Image(nsImage: StateIconRenderer.icon(for: aggregated, size: 15))
                .renderingMode(.original)
        }
    }
}

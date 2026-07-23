// PopoverView.swift — 点击菜单栏图标展开的主面板
// M1: 会话列表 (状态/模型/任务摘要/进度/最近消息) + 退出; 批准卡片与跳转按钮为 M2/M3

import AppKit
import SwiftUI

struct PopoverView: View {
    @ObservedObject private var store = SessionStore.shared
    /// 双保险: 即使 @Published 更新在 MenuBarExtra 内容窗口失效,
    /// 1s tick 也强制 body 重新求值, 保证会话列表/耗时显示新鲜
    @State private var tick = 0
    /// 页签: 会话 / 用量
    @State private var selectedTab: PopoverTab = .sessions
    private let refreshTimer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    enum PopoverTab {
        case sessions, usage
    }

    var body: some View {
        let _ = tick  // 建立刷新依赖
        VStack(alignment: .leading, spacing: 0) {
            Picker("", selection: $selectedTab) {
                Text("会话").tag(PopoverTab.sessions)
                Text("用量").tag(PopoverTab.usage)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .padding(.horizontal, 12)
            .padding(.top, 8)
            .padding(.bottom, 4)

            if selectedTab == .sessions {
                if store.sessions.isEmpty {
                    emptyState
                } else {
                    sessionList
                }
            } else {
                TokenUsageView()
            }
            Divider()
            footer
        }
        .frame(width: 360)
        .onReceive(refreshTimer) { _ in tick &+= 1 }
    }

    // MARK: - 空态

    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "brain")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
            Text("暂无 QozeCode 会话")
                .foregroundStyle(.secondary)
            Button {
                NewSessionService.createInTerminal()
            } label: {
                Label("新建会话", systemImage: "plus")
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.small)
            .help("在 macOS 终端中启动新的 QozeCode 会话")
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 32)
    }

    // MARK: - 会话列表

    /// 列表最多直接展示的会话数 (设计预算 N ≤ 5, 超出折叠计数提示)
    private let maxVisibleSessions = 6

    private var sessionList: some View {
        // 不用 ScrollView+LazyVStack: MenuBarExtra(.window) 中懒加载测量会塌缩
        // (可视高度≈0 → 不实例化行 → 内容高≈0, 表现为已注册但列表空白);
        // 会话数小, 普通 VStack 用固有高度即可被窗口正确测量
        let rows = store.sessions.values.sorted { $0.startedAt < $1.startedAt }
        let visible = Array(rows.prefix(maxVisibleSessions))
        return VStack(spacing: 0) {
            ForEach(visible) { session in
                SessionRowView(session: session)
                if session.id != visible.last?.id || rows.count > maxVisibleSessions {
                    Divider().padding(.leading, 36)
                }
            }
            if rows.count > maxVisibleSessions {
                Text("… 还有 \(rows.count - maxVisibleSessions) 个会话")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 6)
            }
        }
    }

    // MARK: - 底部

    private var footer: some View {
        HStack {
            Button {
                NewSessionService.createInTerminal()
            } label: {
                Label("新会话", systemImage: "plus")
                    .font(.caption)
            }
            .buttonStyle(.borderless)
            .help("在 macOS 终端中启动新的 QozeCode 会话")

            Text("\(store.activeCount) 个会话")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Button {
                tick &+= 1  // 手动强制刷新 (自动 tick 失效时的逃生舱)
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.borderless)
            .help("刷新会话列表")
            // TODO(M4): 设置入口
            Button("退出") {
                NSApplication.shared.terminate(nil)
            }
            .buttonStyle(.borderless)
            .font(.caption)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }
}

struct SessionRowView: View {
    let session: Session

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: MenuBarIcon.symbolName(for: session.state))
                .foregroundStyle(MenuBarIcon.color(for: session.state))
                .frame(width: 24, height: 24)
                .padding(.top, 2)

            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text(session.projectName)
                        .font(.headline)
                    Spacer()
                    Text(session.model)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(session.state.rawValue)
                        .font(.caption)
                        .foregroundStyle(MenuBarIcon.color(for: session.state))
                    Image(systemName: "arrow.up.forward.app")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }

                if !session.taskSummary.isEmpty {
                    Text(session.taskSummary)
                        .font(.subheadline)
                        .lineLimit(1)
                }

                if let progress = session.progress {
                    ProgressView(value: Double(progress.done), total: Double(progress.total))
                        .progressViewStyle(.linear)
                    Text("Plan \(progress.done)/\(progress.total)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                if session.state == .executing && !session.tool.isEmpty {
                    Text("▶ \(session.tool)\(session.command.isEmpty ? "" : ": \(session.command)")")
                        .font(.caption)
                        .foregroundStyle(.blue)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }

                if !session.lastMessage.isEmpty {
                    Text(session.lastMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }

                // TODO(M2): waiting_approval 时显示 [✓ 批准] [✗ 拒绝] 按钮
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())   // 整行都是点击热区 (含空白/间距)
        .onHover { hovering in
            if hovering { NSCursor.pointingHand.push() } else { NSCursor.pop() }
        }
        .onTapGesture {
            FocusService.focus(session: session)
        }
    }
}

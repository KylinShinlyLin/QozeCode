// SessionStore.swift — App 内唯一状态数据源 (@MainActor + @Observable)
// 聚合所有 QozeCode 会话状态, UI 层纯声明式订阅

import Foundation
import SwiftUI

/// 单会话状态 (值类型)
struct Session: Identifiable {
    let id: String           // session_id
    var pid: Int = 0
    var cwd: String = ""
    var tty: String = ""
    var termProgram: String = ""
    var model: String = ""
    var startedAt: Date = Date()
    var hostAppPid: Int = 0      // 最近的 GUI 祖先进程 pid (跳转窗口用)
    var hostAppName: String = ""

    var state: AgentState = .idle
    var taskSummary: String = ""
    var tool: String = ""
    var command: String = ""
    var progress: (done: Int, total: Int)?
    var lastMessage: String = ""

    /// 项目目录名 (cwd 最后一段)
    var projectName: String {
        URL(fileURLWithPath: cwd).lastPathComponent
    }
}

enum AgentState: String {
    case idle, thinking, executing, waitingApproval = "waiting_approval", done, error, interrupted

    /// 聚合优先级 (多会话取最高)
    var priority: Int {
        switch self {
        case .error: return 5
        case .waitingApproval: return 4
        case .executing: return 3
        case .thinking: return 2
        case .done, .interrupted: return 1
        case .idle: return 0
        }
    }
}

// 注: 使用 ObservableObject 而非 @Observable 宏 —
//     @Observable 在 MenuBarExtra(.window) 内容窗口中存在不刷新的 SwiftUI bug,
//     ObservableObject + @Published 是菜单栏 App 验证过的可靠路径
@MainActor
final class SessionStore: ObservableObject {
    static let shared = SessionStore()

    @Published private(set) var sessions: [String: Session] = [:]
    /// done/error 回落 idle 的延时任务
    private var revertTasks: [String: Task<Void, Never>] = [:]

    private init() {}

    // MARK: - 消息入口 (由 IslandServer 派发)

    func apply(_ message: IncomingMessage) {
        switch message {
        case .register(let msg):
            var session = Session(id: msg.session_id)
            session.pid = msg.pid
            session.cwd = msg.cwd
            session.tty = msg.tty ?? ""
            session.termProgram = msg.term_program ?? ""
            session.model = msg.model ?? ""
            session.hostAppPid = msg.host_app_pid ?? 0
            session.hostAppName = msg.host_app_name ?? ""
            if let ts = msg.started_at {
                session.startedAt = Date(timeIntervalSince1970: TimeInterval(ts))
            }
            sessions[msg.session_id] = session
            NSLog("[QozeCode] session registered: \(msg.session_id) \(session.projectName), total=\(sessions.count)")
            DebugLog.log("session registered: \(msg.session_id) \(session.projectName) host=\(session.hostAppName)(\(session.hostAppPid)) tty=\(session.tty) term=\(session.termProgram)")

        case .unregister(let msg):
            removeSession(msg.session_id)

        case .state(let msg):
            guard var session = sessions[msg.session_id] else { return }
            let newState = AgentState(rawValue: msg.state) ?? .idle
            applyDetail(msg.detail, to: &session)
            transition(session, to: newState)

        case .tokenUsage(let msg):
            TokenUsageStore.shared.apply(msg)

        case .approvalRequest(let msg):
            // M2: 批准卡片 UI; M1 先以 waiting_approval 状态呈现
            guard var session = sessions[msg.session_id] else { return }
            session.command = msg.summary ?? session.command
            transition(session, to: .waitingApproval)
        }
    }

    func removeSession(_ sessionId: String) {
        revertTasks[sessionId]?.cancel()
        revertTasks.removeValue(forKey: sessionId)
        sessions.removeValue(forKey: sessionId)
        NSLog("[QozeCode] session removed: \(sessionId), total=\(sessions.count)")
    }

    // MARK: - 聚合状态 (菜单栏图标)

    var aggregatedState: AgentState? {
        sessions.values.map(\.state).max(by: { $0.priority < $1.priority })
    }

    var activeCount: Int { sessions.count }

    var hasSessions: Bool { !sessions.isEmpty }

    // MARK: - 私有

    private func applyDetail(_ detail: StateDetail?, to session: inout Session) {
        guard let detail = detail else { return }
        if let v = detail.task_summary { session.taskSummary = v }
        if let v = detail.tool { session.tool = v }
        if let v = detail.command { session.command = v }
        if let v = detail.last_message { session.lastMessage = v }
        if let p = detail.progress { session.progress = (p.done, p.total) }
    }

    private func transition(_ session: Session, to newState: AgentState) {
        let id = session.id
        let oldState = sessions[id]?.state ?? .idle
        var updated = session
        updated.state = newState
        sessions[id] = updated

        // 系统通知 (M1: waiting_approval / done / error)
        if newState != oldState {
            NotificationService.shared.notify(state: newState, session: updated)
        }

        // done/error/interrupted 为瞬时态: 5 秒后自动回落 idle
        revertTasks[id]?.cancel()
        if newState == .done || newState == .error || newState == .interrupted {
            revertTasks[id] = Task { [weak self] in
                try? await Task.sleep(nanoseconds: 5_000_000_000)
                guard !Task.isCancelled else { return }
                self?.sessions[id]?.state = .idle
            }
        }
    }
}

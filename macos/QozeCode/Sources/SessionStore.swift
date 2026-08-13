// SessionStore.swift — App 内唯一状态数据源 (@MainActor + @Observable)
// 聚合所有 QozeCode 会话状态, UI 层纯声明式订阅

import Foundation
import SwiftUI

/// 会话内的计划进度值；独立值类型便于 Session 快照比较。
struct PlanProgressValue: Equatable, Sendable {
    let done: Int
    let total: Int
}

/// 单会话状态 (值类型)
struct Session: Identifiable, Equatable {
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
    var progress: PlanProgressValue?
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
    /// done/error 回落 idle 的延时任务及其身份代号；Task 本身不可比较。
    private var revertTasks: [String: Task<Void, Never>] = [:]
    private var revertGenerations: [String: UInt64] = [:]
    private var nextRevertGeneration: UInt64 = 0

    private init() {}

    // MARK: - 消息入口 (由 IslandServer 派发)

    func apply(_ message: IncomingMessage) {
        let applyInterval = IslandPerf.begin("SessionStoreApply")
        defer { IslandPerf.end(applyInterval) }

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
            } else if let existing = sessions[msg.session_id] {
                session.startedAt = existing.startedAt
            }
            guard sessions[msg.session_id] != session else { return }
            sessions[msg.session_id] = session
            NSLog("[QozeCode] session registered: \(msg.session_id) \(session.projectName), total=\(sessions.count)")
            DebugLog.log("session registered: \(msg.session_id) \(session.projectName) host=\(session.hostAppName)(\(session.hostAppPid)) tty=\(session.tty) term=\(session.termProgram)")

        case .unregister(let msg):
            removeSession(msg.session_id)

        case .state(let msg):
            guard var session = sessions[msg.session_id] else { return }
            let newState = AgentState(rawValue: msg.state) ?? .idle
            let detailChanged = applyDetail(msg.detail, to: &session)
            transition(session, to: newState, detailChanged: detailChanged)

        case .tokenUsage(let msg):
            TokenUsageStore.shared.apply(msg)

        case .approvalRequest(let msg):
            // M2: 批准卡片 UI; M1 先以 waiting_approval 状态呈现
            guard var session = sessions[msg.session_id] else { return }
            let oldCommand = session.command
            session.command = msg.summary ?? session.command
            transition(
                session,
                to: .waitingApproval,
                detailChanged: session.command != oldCommand
            )
        }
    }

    func removeSession(_ sessionId: String) {
        revertTasks[sessionId]?.cancel()
        revertTasks.removeValue(forKey: sessionId)
        revertGenerations.removeValue(forKey: sessionId)
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

    @discardableResult
    private func applyDetail(_ detail: StateDetail?, to session: inout Session) -> Bool {
        guard let detail else { return false }
        var changed = false

        if let value = detail.task_summary, value != session.taskSummary {
            session.taskSummary = value
            changed = true
        }
        if let value = detail.tool, value != session.tool {
            session.tool = value
            changed = true
        }
        if let value = detail.command, value != session.command {
            session.command = value
            changed = true
        }
        if let value = detail.last_message, value != session.lastMessage {
            session.lastMessage = value
            changed = true
        }
        if let progress = detail.progress {
            let value = PlanProgressValue(done: progress.done, total: progress.total)
            if value != session.progress {
                session.progress = value
                changed = true
            }
        }

        return changed
    }

    private func transition(
        _ session: Session,
        to newState: AgentState,
        detailChanged: Bool
    ) {
        let id = session.id
        guard let existing = sessions[id] else { return }
        let stateChanged = existing.state != newState
        guard stateChanged || detailChanged else { return }

        var updated = session
        updated.state = newState
        guard updated != existing else { return }
        sessions[id] = updated

        // Detail-only updates publish the snapshot but do not notify or disturb terminal rollback.
        guard stateChanged else { return }

        // 系统通知 (M1: waiting_approval / done / error)
        NotificationService.shared.notify(state: newState, session: updated)

        // done/error/interrupted 为瞬时态: 5 秒后自动回落 idle
        revertTasks[id]?.cancel()
        revertTasks.removeValue(forKey: id)
        revertGenerations.removeValue(forKey: id)
        if newState == .done || newState == .error || newState == .interrupted {
            nextRevertGeneration &+= 1
            let generation = nextRevertGeneration
            revertGenerations[id] = generation
            revertTasks[id] = Task { [weak self] in
                try? await Task.sleep(nanoseconds: 5_000_000_000)
                guard !Task.isCancelled,
                      let self,
                      self.revertGenerations[id] == generation else { return }
                self.sessions[id]?.state = .idle
                // 仅当前代自然完成时清理，不能误删随后创建的新 task。
                self.revertTasks.removeValue(forKey: id)
                self.revertGenerations.removeValue(forKey: id)
            }
        }
    }
}

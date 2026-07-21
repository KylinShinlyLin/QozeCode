// Messages.swift — QozeCode 通信协议模型 (NDJSON over UDS)
// 协议定义见 docs/qozeisland-tech-design.md §3

import Foundation

/// 消息类型信封: 先解码 type 字段再决定具体模型
struct MessageEnvelope: Decodable {
    let type: String
}

/// C→S 会话注册 (连接建立后第一条消息)
struct RegisterMessage: Decodable {
    let session_id: String
    let pid: Int
    let cwd: String
    let tty: String?
    let term_program: String?
    let model: String?
    let started_at: Int?
    let host_app_pid: Int?    // 最近的 GUI 祖先进程 (跳转窗口用, v0.4)
    let host_app_name: String?
}

/// C→S 会话注销 (正常退出; socket 断开为兜底)
struct UnregisterMessage: Decodable {
    let session_id: String
}

/// C→S 状态上报
struct StateMessage: Decodable {
    let session_id: String
    let state: String
    let detail: StateDetail?
}

struct StateDetail: Decodable {
    let task_summary: String?
    let tool: String?
    let command: String?
    let progress: PlanProgress?
    let last_message: String?
}

struct PlanProgress: Decodable {
    let done: Int
    let total: Int
}

/// C→S 批准请求 (M2)
struct ApprovalRequestMessage: Decodable {
    let session_id: String
    let request_id: String
    let action: String?
    let summary: String?
    let risk: String?
}

/// S→C 批准响应 (M2)
struct ApprovalResponseMessage: Encodable {
    let type = "approval.response"
    let session_id: String
    let request_id: String
    let decision: String  // "approve" | "reject"
}

/// 解码后的入站消息 (未知 type 返回 nil, 向前兼容)
enum IncomingMessage {
    case register(RegisterMessage)
    case unregister(UnregisterMessage)
    case state(StateMessage)
    case approvalRequest(ApprovalRequestMessage)

    static func decode(line: Data) -> IncomingMessage? {
        let decoder = JSONDecoder()
        guard let envelope = try? decoder.decode(MessageEnvelope.self, from: line) else {
            return nil
        }
        switch envelope.type {
        case "session.register":
            return (try? decoder.decode(RegisterMessage.self, from: line)).map { .register($0) }
        case "session.unregister":
            return (try? decoder.decode(UnregisterMessage.self, from: line)).map { .unregister($0) }
        case "state":
            return (try? decoder.decode(StateMessage.self, from: line)).map { .state($0) }
        case "approval.request":
            return (try? decoder.decode(ApprovalRequestMessage.self, from: line)).map { .approvalRequest($0) }
        default:
            return nil  // 未知类型忽略
        }
    }
}

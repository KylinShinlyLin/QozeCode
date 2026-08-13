// NotificationService.swift — 系统通知 (UNUserNotificationCenter)
// 触发点: SessionStore 状态迁移到 waiting_approval / done / error / interrupted

import Foundation
import UserNotifications

final class NotificationService: NSObject, UNUserNotificationCenterDelegate {
    static let shared = NotificationService()

    private let center = UNUserNotificationCenter.current()
    private var authorized = false
    /// notify() 限定 MainActor，附件缓存无需额外锁；临时文件丢失时会重建附件。
    private var attachmentCache: [String: UNNotificationAttachment] = [:]

    private override init() {
        super.init()
    }

    func requestAuthorization() {
        center.delegate = self
        center.requestAuthorization(options: [.alert, .sound]) { [weak self] granted, _ in
            self?.authorized = granted
            if !granted {
                NSLog("[QozeCode] notification authorization denied, 降级为纯图标提醒")
            }
        }
    }

    @MainActor
    func notify(state: AgentState, session: Session) {
        let (title, body): (String, String)
        switch state {
        case .waitingApproval:
            title = "QozeCode 请求批准"
            body = session.command.isEmpty ? "\(session.projectName) 等待你的确认" : session.command
        case .done:
            title = "QozeCode 任务完成"
            body = session.taskSummary.isEmpty ? session.projectName : session.taskSummary
        case .error:
            title = "QozeCode 出错"
            body = session.lastMessage.isEmpty ? session.projectName : session.lastMessage
        case .interrupted:
            title = "QozeCode 已中断"
            body = session.taskSummary.isEmpty ? session.projectName : session.taskSummary
        default:
            return
        }

        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = state == .waitingApproval ? .default : nil
        content.categoryIdentifier = "session.\(session.id)"
        if let attachment = notificationAttachment(for: state) {
            content.attachments = [attachment]
        }

        let request = UNNotificationRequest(
            identifier: "\(session.id).\(state.rawValue).\(Date().timeIntervalSince1970)",
            content: content,
            trigger: nil
        )
        center.add(request)
    }

    @MainActor
    private func notificationAttachment(for state: AgentState) -> UNNotificationAttachment? {
        let key = state.rawValue
        if let cached = attachmentCache[key], FileManager.default.fileExists(atPath: cached.url.path) {
            IslandPerf.event("NotificationAttachmentCache", detail: "hit \(key)")
            return cached
        }
        attachmentCache.removeValue(forKey: key)

        guard let iconURL = StateIconRenderer.notificationIconURL(for: state),
              let attachment = try? UNNotificationAttachment(
                identifier: "state-icon-\(key)",
                url: iconURL,
                options: [UNNotificationAttachmentOptionsTypeHintKey: "public.png"]
              ) else { return nil }
        attachmentCache[key] = attachment
        IslandPerf.event("NotificationAttachmentCache", detail: "miss \(key)")
        return attachment
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound])
    }
}

// NotificationService.swift — 系统通知 (UNUserNotificationCenter)
// 触发点: SessionStore 状态迁移到 waiting_approval / done / error

import Foundation
import UserNotifications

final class NotificationService: NSObject, UNUserNotificationCenterDelegate {
    static let shared = NotificationService()

    private let center = UNUserNotificationCenter.current()
    private var authorized = false

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
        default:
            return  // 其他状态不发通知
        }

        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = state == .waitingApproval ? .default : nil
        content.categoryIdentifier = "session.\(session.id)"
        // 状态图标附件: 横幅右侧缩略图 (done 绿勾 / error 红叉 / waiting 橙三角)
        if let iconURL = StateIconRenderer.notificationIconURL(for: state),
           let attachment = try? UNNotificationAttachment(
               identifier: "state-icon", url: iconURL,
               options: [UNNotificationAttachmentOptionsTypeHintKey: "public.png"]) {
            content.attachments = [attachment]
        }

        let request = UNNotificationRequest(
            identifier: "\(session.id).\(state.rawValue).\(Date().timeIntervalSince1970)",
            content: content,
            trigger: nil  // 立即发送
        )
        center.add(request)
    }

    // 前台时也显示横幅 (菜单栏 App 没有前台窗口概念, 但仍需此代理方法)
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }
}

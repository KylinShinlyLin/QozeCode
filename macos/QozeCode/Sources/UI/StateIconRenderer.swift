// StateIconRenderer.swift — 手绘矢量状态图标 (NSBezierPath, 免 SVG 转换)
// 用途: 菜单栏 done/error 徽章 + 系统通知附件缩略图 (UNNotificationAttachment)
// 设计: 圆形彩底 + 白色圆角 glyph, 小尺寸 (菜单栏 15pt) 与大尺寸 (通知 128pt) 共用

import AppKit

enum StateIconRenderer {

    // MARK: - done / error 徽章

    /// done: 绿圆底 + 白色圆角对勾
    static func doneIcon(size: CGFloat) -> NSImage {
        badge(size: size, color: MenuBarIcon.menuBarNSColor(for: .done)) { rect in
            // 对勾 (坐标系 y 向上): 左中 → 中下 → 右上
            let path = NSBezierPath()
            path.move(to: NSPoint(x: rect.minX + rect.width * 0.24, y: rect.minY + rect.height * 0.52))
            path.line(to: NSPoint(x: rect.minX + rect.width * 0.43, y: rect.minY + rect.height * 0.31))
            path.line(to: NSPoint(x: rect.minX + rect.width * 0.78, y: rect.minY + rect.height * 0.70))
            stroke(path, width: rect.width * 0.13)
        }
    }

    /// error: 红圆底 + 白色圆角 X
    static func errorIcon(size: CGFloat) -> NSImage {
        badge(size: size, color: MenuBarIcon.menuBarNSColor(for: .error)) { rect in
            let r = rect.insetBy(dx: rect.width * 0.29, dy: rect.height * 0.29)
            let path = NSBezierPath()
            path.move(to: NSPoint(x: r.minX, y: r.minY))
            path.line(to: NSPoint(x: r.maxX, y: r.maxY))
            path.move(to: NSPoint(x: r.maxX, y: r.minY))
            path.line(to: NSPoint(x: r.minX, y: r.maxY))
            stroke(path, width: rect.width * 0.13)
        }
    }

    // MARK: - 通知附件

    /// 各通知状态对应图标: done/error 手绘徽章, waiting_approval 用染色 SF 三角
    static func icon(for state: AgentState, size: CGFloat) -> NSImage {
        switch state {
        case .done: return doneIcon(size: size)
        case .error: return errorIcon(size: size)
        default: return MenuBarIcon.tintedImage(for: state, pointSize: size * 0.82)
        }
    }

    /// 渲染为 PNG 写入临时目录, 供 UNNotificationAttachment 使用 (同状态覆盖复用)
    static func notificationIconURL(for state: AgentState) -> URL? {
        let image = icon(for: state, size: 128)
        guard let tiff = image.tiffRepresentation,
              let rep = NSBitmapImageRep(data: tiff),
              let png = rep.representation(using: .png, properties: [:]) else { return nil }
        let url = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("qoze_notify_\(state.rawValue).png")
        do {
            try png.write(to: url, options: .atomic)
            return url
        } catch {
            DebugLog.log("notification icon write failed: \(error.localizedDescription)")
            return nil
        }
    }

    // MARK: - 私有

    /// 圆形彩底 + 白色 glyph 绘制
    private static func badge(size: CGFloat, color: NSColor, glyph: @escaping (CGRect) -> Void) -> NSImage {
        let img = NSImage(size: NSSize(width: size, height: size), flipped: false) { rect in
            color.setFill()
            NSBezierPath(ovalIn: rect).fill()
            glyph(rect)
            return true
        }
        img.isTemplate = false
        return img
    }

    private static func stroke(_ path: NSBezierPath, width: CGFloat) {
        path.lineCapStyle = .round
        path.lineJoinStyle = .round
        path.lineWidth = width
        NSColor.white.setStroke()
        path.stroke()
    }
}

// StateIconRenderer.swift — 手绘状态图标、通知 PNG 与缓存
// AppKit 图像创建和缓存访问统一限定 MainActor；临时 PNG 被清理后按需重建。

import AppKit

@MainActor
enum StateIconRenderer {
    private static var imageCache: [String: NSImage] = [:]
    private static var notificationURLCache: [String: URL] = [:]

    private static func doneIcon(size: CGFloat) -> NSImage {
        badge(size: normalizedSize(size), color: MenuBarIcon.menuBarNSColor(for: .done)) { rect in
            let path = NSBezierPath()
            path.move(to: NSPoint(x: rect.minX + rect.width * 0.24, y: rect.minY + rect.height * 0.52))
            path.line(to: NSPoint(x: rect.minX + rect.width * 0.43, y: rect.minY + rect.height * 0.31))
            path.line(to: NSPoint(x: rect.minX + rect.width * 0.78, y: rect.minY + rect.height * 0.70))
            stroke(path, width: rect.width * 0.13)
        }
    }

    private static func errorIcon(size: CGFloat) -> NSImage {
        badge(size: normalizedSize(size), color: MenuBarIcon.menuBarNSColor(for: .error)) { rect in
            let r = rect.insetBy(dx: rect.width * 0.29, dy: rect.height * 0.29)
            let path = NSBezierPath()
            path.move(to: NSPoint(x: r.minX, y: r.minY))
            path.line(to: NSPoint(x: r.maxX, y: r.maxY))
            path.move(to: NSPoint(x: r.maxX, y: r.minY))
            path.line(to: NSPoint(x: r.minX, y: r.maxY))
            stroke(path, width: rect.width * 0.13)
        }
    }

    static func icon(for state: AgentState, size: CGFloat) -> NSImage {
        let normalized = normalizedSize(size)
        let key = cacheKey(state: state, size: normalized)
        if let cached = imageCache[key] {
            IslandPerf.event("StateIconCache", detail: "hit \(key)")
            return cached
        }

        let interval = IslandPerf.begin("StateIconRender")
        let image: NSImage
        switch state {
        case .done:
            image = doneIcon(size: normalized)
        case .error:
            image = errorIcon(size: normalized)
        default:
            image = MenuBarIcon.tintedImage(for: state, pointSize: normalized * 0.82)
        }
        imageCache[key] = image
        IslandPerf.end(interval, "\(state.rawValue) \(normalized)")
        IslandPerf.event("StateIconCache", detail: "miss \(key)")
        return image
    }

    /// 同状态复用稳定 URL；若系统清理临时文件，则重新编码并原子写入。
    static func notificationIconURL(for state: AgentState) -> URL? {
        let key = state.rawValue
        if let cached = notificationURLCache[key], FileManager.default.fileExists(atPath: cached.path) {
            IslandPerf.event("NotificationIconURLCache", detail: "hit \(key)")
            return cached
        }

        let interval = IslandPerf.begin("NotificationIconPNG")
        defer { IslandPerf.end(interval, key) }
        let image = icon(for: state, size: 128)
        guard let tiff = image.tiffRepresentation,
              let rep = NSBitmapImageRep(data: tiff),
              let png = rep.representation(using: .png, properties: [:]) else { return nil }
        let url = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("qoze_notify_\(state.rawValue).png")
        do {
            try png.write(to: url, options: .atomic)
            notificationURLCache[key] = url
            IslandPerf.event("NotificationIconURLCache", detail: "miss \(key)")
            return url
        } catch {
            DebugLog.log("notification icon write failed: \(error.localizedDescription)")
            return nil
        }
    }

    private static func cacheKey(state: AgentState, size: CGFloat) -> String {
        "\(state.rawValue):\(Int((size * 4).rounded()))"
    }

    private static func normalizedSize(_ size: CGFloat) -> CGFloat {
        max(0.25, (size * 4).rounded() / 4)
    }

    private static func badge(size: CGFloat, color: NSColor, glyph: @escaping (CGRect) -> Void) -> NSImage {
        let image = NSImage(size: NSSize(width: size, height: size), flipped: false) { rect in
            color.setFill()
            NSBezierPath(ovalIn: rect).fill()
            glyph(rect)
            return true
        }
        image.isTemplate = false
        return image
    }

    private static func stroke(_ path: NSBezierPath, width: CGFloat) {
        path.lineCapStyle = .round
        path.lineJoinStyle = .round
        path.lineWidth = width
        NSColor.white.setStroke()
        path.stroke()
    }
}

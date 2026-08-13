// MenuBarIcon.swift — 状态 → SF Symbol + 颜色映射与菜单栏图像缓存
// AppKit 图像创建和缓存访问统一限定 MainActor，避免跨线程绘图与额外锁竞争。

import AppKit
import SwiftUI

@MainActor
enum MenuBarIcon {
    private static var tintedImageCache: [String: NSImage] = [:]

    static func symbolName(for state: AgentState?) -> String {
        guard let state = state else { return "brain" }
        switch state {
        case .idle: return "brain"
        case .thinking: return "sparkles"
        case .executing: return "gearshape.fill"
        case .waitingApproval: return "exclamationmark.triangle.fill"
        case .done: return "checkmark.circle.fill"
        case .error: return "xmark.octagon.fill"
        case .interrupted: return "stop.circle.fill"
        }
    }

    static func color(for state: AgentState?) -> Color {
        guard let state = state else { return .secondary }
        switch state {
        case .idle: return .secondary
        case .thinking: return .purple
        case .executing: return .blue
        case .waitingApproval: return .orange
        case .done: return .green
        case .error: return .red
        case .interrupted: return .yellow
        }
    }

    /// 菜单栏染色专用色板: macOS 深色模式系统色 (固定 sRGB)
    static func menuBarNSColor(for state: AgentState) -> NSColor {
        switch state {
        case .idle: return NSColor(white: 0.78, alpha: 1)
        case .thinking: return NSColor(srgbRed: 0xBF/255, green: 0x5A/255, blue: 0xF2/255, alpha: 1)
        case .executing: return NSColor(srgbRed: 0x0A/255, green: 0x84/255, blue: 1.0, alpha: 1)
        case .waitingApproval: return NSColor(srgbRed: 1.0, green: 0x9F/255, blue: 0x0A/255, alpha: 1)
        case .done: return NSColor(srgbRed: 0x30/255, green: 0xD1/255, blue: 0x58/255, alpha: 1)
        case .error: return NSColor(srgbRed: 1.0, green: 0x45/255, blue: 0x3A/255, alpha: 1)
        case .interrupted: return NSColor(srgbRed: 1.0, green: 0xD6/255, blue: 0x0A/255, alpha: 1)
        }
    }

    static func pointSize(for state: AgentState) -> CGFloat {
        state == .thinking ? 13 : 16
    }

    static func symbolWeight(for state: AgentState) -> NSFont.Weight {
        state == .thinking ? .regular : .medium
    }

    /// 离线染色的 symbol 位图。尺寸按 1/4 pt 规范化，避免浮点噪声生成重复缓存项。
    static func tintedImage(for state: AgentState, pointSize sizeOverride: CGFloat? = nil) -> NSImage {
        let size = normalizedSize(sizeOverride ?? pointSize(for: state))
        let key = "\(state.rawValue):\(Int((size * 4).rounded()))"
        if let cached = tintedImageCache[key] {
            IslandPerf.event("MenuBarIconCache", detail: "hit \(key)")
            return cached
        }

        let interval = IslandPerf.begin("MenuBarIconRender")
        defer { IslandPerf.end(interval, "\(state.rawValue) \(size)") }

        let name = symbolName(for: state)
        let nsColor = menuBarNSColor(for: state)
        guard let symbol = NSImage(systemSymbolName: name, accessibilityDescription: nil),
              let base = symbol.withSymbolConfiguration(.init(pointSize: size, weight: symbolWeight(for: state))) else {
            return NSImage()
        }
        let tinted = NSImage(size: base.size, flipped: false) { rect in
            base.draw(in: rect)
            nsColor.set()
            rect.fill(using: .sourceAtop)
            return true
        }
        tinted.isTemplate = false
        tintedImageCache[key] = tinted
        IslandPerf.event("MenuBarIconCache", detail: "miss \(key)")
        return tinted
    }

    private static func normalizedSize(_ size: CGFloat) -> CGFloat {
        max(0.25, (size * 4).rounded() / 4)
    }
}

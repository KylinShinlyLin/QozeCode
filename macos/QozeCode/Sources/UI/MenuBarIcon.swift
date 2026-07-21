// MenuBarIcon.swift — 状态 → SF Symbol + 颜色映射
// 菜单栏着色原理: MenuBarExtra label 对 SF Symbol 强制 template 渲染,
//   foregroundStyle/symbolRenderingMode 均被忽略 → 必须离线把颜色画进 NSImage
//   并置 isTemplate=false, 颜色才能在菜单栏存活 (idle 保持 template 系统默认色)
// Popover 会话行: SwiftUI 正常环境, 直接用 symbol + color

import AppKit
import SwiftUI

enum MenuBarIcon {
    static func symbolName(for state: AgentState?) -> String {
        guard let state = state else { return "brain" }
        switch state {
        case .idle: return "brain"
        case .thinking: return "sparkles"
        case .executing: return "gearshape.fill"
        case .waitingApproval: return "exclamationmark.triangle.fill"
        case .done: return "checkmark.circle.fill"
        case .error: return "xmark.octagon.fill"
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
        }
    }

    /// 菜单栏染色专用色板: macOS 深色模式系统色 (固定 sRGB)
    /// 离线绘图不按菜单栏外观解析动态色 → 必须用固定亮色, 否则深色菜单栏上发暗
    static func menuBarNSColor(for state: AgentState) -> NSColor {
        switch state {
        case .idle: return NSColor(white: 0.78, alpha: 1)  // (idle 走 template, 不会用到)
        case .thinking: return NSColor(srgbRed: 0xBF/255, green: 0x5A/255, blue: 0xF2/255, alpha: 1)
        case .executing: return NSColor(srgbRed: 0x0A/255, green: 0x84/255, blue: 1.0, alpha: 1)
        case .waitingApproval: return NSColor(srgbRed: 1.0, green: 0x9F/255, blue: 0x0A/255, alpha: 1)
        case .done: return NSColor(srgbRed: 0x30/255, green: 0xD1/255, blue: 0x58/255, alpha: 1)
        case .error: return NSColor(srgbRed: 1.0, green: 0x45/255, blue: 0x3A/255, alpha: 1)
        }
    }

    /// 各状态在菜单栏的渲染尺寸 (sparkles glyph 偏宽, 缩小避免显"肥")
    static func pointSize(for state: AgentState) -> CGFloat {
        switch state {
        case .thinking: return 13
        default: return 16
        }
    }

    /// 各状态 symbol 字重 (sparkles 用细字重, 笔画更轻盈)
    static func symbolWeight(for state: AgentState) -> NSFont.Weight {
        state == .thinking ? .regular : .medium
    }

    /// 离线染色的 symbol 位图 (非 idle 状态的菜单栏图标)
    /// 做法: 画 symbol → 以其不透明区域为 mask 用 sourceAtop 填充状态色 → 关闭 template
    static func tintedImage(for state: AgentState, pointSize sizeOverride: CGFloat? = nil) -> NSImage {
        let name = symbolName(for: state)
        let size = sizeOverride ?? pointSize(for: state)
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
        return tinted
    }
}

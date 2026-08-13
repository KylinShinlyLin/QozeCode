// PerformanceSignposts.swift — Island 轻量性能区间与事件埋点

import Foundation
import OSLog

enum IslandPerf {
    struct Interval {
        fileprivate let name: StaticString
        fileprivate let state: OSSignpostIntervalState
    }

    private static let signposter = OSSignposter(
        subsystem: Bundle.main.bundleIdentifier ?? "com.qoze.code",
        category: "IslandPerformance"
    )

    /// 默认可用；仅在显式设置 QOZE_ISLAND_SIGNPOSTS=0 时关闭。
    /// OSSignposter 自身还会在没有采集器时保持低开销。
    private static let enabled = ProcessInfo.processInfo.environment["QOZE_ISLAND_SIGNPOSTS"] != "0"

    @discardableResult
    static func begin(_ name: StaticString) -> Interval? {
        guard enabled, signposter.isEnabled else { return nil }
        return Interval(name: name, state: signposter.beginInterval(name))
    }

    /// detail 使用 autoclosure：signpost 未启用时不会构造字符串。
    static func end(_ interval: Interval?, _ detail: @autoclosure () -> String = "") {
        guard enabled, signposter.isEnabled, let interval else { return }
        let value = detail()
        if value.isEmpty {
            signposter.endInterval(interval.name, interval.state)
        } else {
            signposter.endInterval(interval.name, interval.state, "\(value, privacy: .public)")
        }
    }

    /// 从 UI 生命周期事件计量到 MainActor 下一次可调度帧；调用方不要放在 body 求值中。
    @MainActor
    static func nextFrame(_ name: StaticString) {
        let interval = begin(name)
        guard interval != nil else { return }
        Task { @MainActor in
            await Task.yield()
            end(interval)
        }
    }

    /// 仅传递短小、低基数 detail；不要传递消息正文或完整 JSON。
    static func event(_ name: StaticString, detail: @autoclosure () -> String = "") {
        guard enabled, signposter.isEnabled else { return }
        let value = detail()
        if value.isEmpty {
            signposter.emitEvent(name)
        } else {
            signposter.emitEvent(name, "\(value, privacy: .public)")
        }
    }
}

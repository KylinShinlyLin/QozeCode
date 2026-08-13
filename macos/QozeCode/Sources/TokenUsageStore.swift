// TokenUsageStore.swift — token 用量数据源 (@MainActor + ObservableObject)
// 数据双通道: ① 启动 / Popover 打开时读 ~/.qoze/token_usage.json
//             ② Python 端 token.usage 推送全量快照实时刷新

import Foundation
import SwiftUI

/// 单模型单日用量 (值类型)
struct ModelTokenUsage: Equatable, Sendable {
    var input: Int = 0
    var output: Int = 0
    var requests: Int = 0
    var total: Int { input + output }
}

@MainActor
final class TokenUsageStore: ObservableObject {
    static let shared = TokenUsageStore()

    /// dayKey("yyyy-MM-dd") → model → usage
    @Published private(set) var days: [String: [String: ModelTokenUsage]] = [:]

    private let fileURL = URL(fileURLWithPath: NSHomeDirectory())
        .appendingPathComponent(".qoze/token_usage.json")

    private var reloadGeneration: UInt64 = 0
    private var sourceGeneration: UInt64 = 0
    /// 当前进程一旦成功处理有效 IPC 快照，磁盘仅作为兜底，不再取得发布权。
    private var hasAppliedIPC = false
    private var lastAppliedSource: AppliedSource?
    private var lastFileSignature: FileSignature?

    private enum AppliedSource: Equatable {
        case disk
        case ipc
    }

    private struct FileSignature: Equatable, Sendable {
        let modificationTime: TimeInterval
        let size: UInt64
    }

    /// detached task 只向 MainActor 返回 Sendable 纯值，避免传递 Foundation decoder/model。
    private enum DiskReloadResult: Sendable {
        case unchanged
        case unavailable
        case invalid(FileSignature)
        case loaded(FileSignature, [String: [String: ModelTokenUsage]])
    }

    private struct DiskTokenUsageData: Decodable, Sendable {
        let days: [String: DiskTokenDayUsage]?
    }

    private struct DiskTokenDayUsage: Decodable, Sendable {
        let models: [String: DiskTokenModelUsage]?
    }

    private struct DiskTokenModelUsage: Decodable, Sendable {
        let input: Int?
        let output: Int?
        let requests: Int?
    }

    private static let dayFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    private init() {
        Task { await reloadFromDisk() }
    }

    // MARK: - IPC 入口 (由 SessionStore 派发)

    func apply(_ msg: TokenUsageMessage) {
        // 缺少 days 的消息无效：不得改变 source generation 或数据源权威。
        guard let data = msg.data, let dict = data.days else { return }
        let converted = Self.convert(dict)

        // 有效 IPC 即使内容相同也永久确立当前 App 进程内的 IPC 权威。
        sourceGeneration &+= 1
        hasAppliedIPC = true
        lastAppliedSource = .ipc
        guard converted != days else { return }
        days = converted
    }

    // MARK: - 文件读取 (面板打开时调用, 保证错过推送也能拿到最新)

    func reloadFromDisk() async {
        reloadGeneration &+= 1
        let requestedReloadGeneration = reloadGeneration
        let requestedSourceGeneration = sourceGeneration
        let knownSignature = lastFileSignature
        let path = fileURL.path

        let result = await Task.detached(priority: .utility) {
            Self.loadFromDisk(path: path, knownSignature: knownSignature)
        }.value

        let applyInterval = IslandPerf.begin("TokenUsageApply")
        defer { IslandPerf.end(applyInterval) }

        // latest-wins；同时阻止任务启动后到达的 IPC 快照被旧磁盘内容覆盖。
        guard requestedReloadGeneration == reloadGeneration else { return }

        switch result {
        case .unchanged, .unavailable:
            return
        case .invalid(let signature):
            lastFileSignature = signature
        case .loaded(let signature, let loadedDays):
            // 即使 IPC 已更新也记住已处理的文件版本，后续 reload 可直接跳过它。
            lastFileSignature = signature
            // IPC 是当前进程内的永久权威：同时覆盖 reload 前与飞行中到达的 IPC。
            guard !hasAppliedIPC,
                  lastAppliedSource != .ipc,
                  requestedSourceGeneration == sourceGeneration else { return }
            lastAppliedSource = .disk
            guard loadedDays != days else { return }
            days = loadedDays
        }
    }

    nonisolated private static func loadFromDisk(
        path: String,
        knownSignature: FileSignature?
    ) -> DiskReloadResult {
        let readInterval = IslandPerf.begin("TokenUsageRead")
        var readDetail = "unavailable"
        defer { IslandPerf.end(readInterval, readDetail) }

        guard let attributes = try? FileManager.default.attributesOfItem(atPath: path),
              let modificationDate = attributes[.modificationDate] as? Date,
              let size = attributes[.size] as? NSNumber else {
            return .unavailable
        }

        let signature = FileSignature(
            modificationTime: modificationDate.timeIntervalSinceReferenceDate,
            size: size.uint64Value
        )
        guard signature != knownSignature else {
            readDetail = "unchanged"
            return .unchanged
        }
        guard let raw = try? Data(contentsOf: URL(fileURLWithPath: path)) else {
            return .unavailable
        }
        readDetail = "loaded"

        let decodeInterval = IslandPerf.begin("TokenUsageDecode")
        var decodeDetail = "invalid"
        defer { IslandPerf.end(decodeInterval, decodeDetail) }

        guard let decoded = try? JSONDecoder().decode(DiskTokenUsageData.self, from: raw),
              let decodedDays = decoded.days else {
            return .invalid(signature)
        }
        let converted = convertDisk(decodedDays)
        decodeDetail = "loaded"
        return .loaded(signature, converted)
    }

    nonisolated private static func convertDisk(
        _ dict: [String: DiskTokenDayUsage]
    ) -> [String: [String: ModelTokenUsage]] {
        var result: [String: [String: ModelTokenUsage]] = [:]
        for (day, dayUsage) in dict {
            var models: [String: ModelTokenUsage] = [:]
            for (model, usage) in dayUsage.models ?? [:] {
                models[model] = ModelTokenUsage(
                    input: usage.input ?? 0,
                    output: usage.output ?? 0,
                    requests: usage.requests ?? 0
                )
            }
            result[day] = models
        }
        return result
    }

    private static func convert(_ dict: [String: TokenDayUsage]) -> [String: [String: ModelTokenUsage]] {
        var result: [String: [String: ModelTokenUsage]] = [:]
        for (day, dayUsage) in dict {
            var models: [String: ModelTokenUsage] = [:]
            for (model, u) in dayUsage.models ?? [:] {
                models[model] = ModelTokenUsage(
                    input: u.input ?? 0, output: u.output ?? 0, requests: u.requests ?? 0)
            }
            result[day] = models
        }
        return result
    }

    // MARK: - 查询

    var allModels: [String] {
        var set = Set<String>()
        for models in days.values { set.formUnion(models.keys) }
        return set.sorted()
    }

    var todayKey: String { Self.dayFormatter.string(from: Date()) }

    /// 某日汇总 (model == nil 表示全部模型合计)
    func usage(day: String, model: String?) -> ModelTokenUsage {
        guard let models = days[day] else { return ModelTokenUsage() }
        if let model = model { return models[model] ?? ModelTokenUsage() }
        var total = ModelTokenUsage()
        for u in models.values {
            total.input += u.input
            total.output += u.output
            total.requests += u.requests
        }
        return total
    }

    /// 最近 count 天 (含今天) 的 (dayKey, total) 序列, 时间升序
    func recentDays(_ count: Int = 7, model: String?) -> [(key: String, total: Int)] {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())
        var result: [(key: String, total: Int)] = []
        for offset in stride(from: count - 1, through: 0, by: -1) {
            guard let date = calendar.date(byAdding: .day, value: -offset, to: today) else { continue }
            let key = Self.dayFormatter.string(from: date)
            result.append((key, usage(day: key, model: model).total))
        }
        return result
    }
}

/// token 数格式化: 1234 → 1.2K, 3_400_000 → 3.4M
func formatTokenCount(_ value: Int) -> String {
    if value >= 1_000_000 {
        return String(format: "%.1fM", Double(value) / 1_000_000)
    } else if value >= 1_000 {
        return String(format: "%.1fK", Double(value) / 1_000)
    }
    return "\(value)"
}

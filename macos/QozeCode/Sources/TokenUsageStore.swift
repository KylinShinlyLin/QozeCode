// TokenUsageStore.swift — token 用量数据源 (@MainActor + ObservableObject)
// 数据双通道: ① 启动 / Popover 打开时读 ~/.qoze/token_usage.json
//             ② Python 端 token.usage 推送全量快照实时刷新

import Foundation
import SwiftUI

/// 单模型单日用量 (值类型)
struct ModelTokenUsage {
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

    private static let dayFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    private init() {
        reloadFromDisk()
    }

    // MARK: - IPC 入口 (由 SessionStore 派发)

    func apply(_ msg: TokenUsageMessage) {
        guard let data = msg.data, let dict = data.days else { return }
        days = Self.convert(dict)
    }

    // MARK: - 文件读取 (面板打开时调用, 保证错过推送也能拿到最新)

    func reloadFromDisk() {
        guard let raw = try? Data(contentsOf: fileURL),
              let data = try? JSONDecoder().decode(TokenUsageData.self, from: raw),
              let dict = data.days else { return }
        days = Self.convert(dict)
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

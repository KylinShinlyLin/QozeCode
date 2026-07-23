// TokenUsageView.swift — Island 用量页
// 模型筛选(全部/单模型) + 今日摘要 + 近 7 天按天柱状图 + input/output 拆分

import SwiftUI

struct TokenUsageView: View {
    @ObservedObject private var store = TokenUsageStore.shared
    @State private var selectedModel: String = ""   // "" = 全部

    private var selectedModelOrNil: String? { selectedModel.isEmpty ? nil : selectedModel }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if store.days.isEmpty {
                emptyState
            } else {
                modelPicker
                todaySummary
                Divider()
                barChart
                Divider()
                ioSplit
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .onAppear { store.reloadFromDisk() }
    }

    // MARK: - 空态

    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "chart.bar")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
            Text("暂无 token 用量数据")
                .foregroundStyle(.secondary)
            Text("完成一次请求后自动统计")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 32)
    }

    // MARK: - 模型筛选

    private var modelPicker: some View {
        HStack(spacing: 6) {
            Text("模型")
                .font(.caption)
                .foregroundStyle(.secondary)
            Picker("", selection: $selectedModel) {
                Text("全部").tag("")
                ForEach(store.allModels, id: \.self) { model in
                    Text(model).tag(model)
                }
            }
            .pickerStyle(.menu)
            .labelsHidden()
            .fixedSize()
            Spacer()
        }
    }

    // MARK: - 今日摘要

    private var todaySummary: some View {
        let usage = store.usage(day: store.todayKey, model: selectedModelOrNil)
        return HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text("今日")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text(formatTokenCount(usage.total))
                .font(.title2.bold())
            Text("tokens · \(usage.requests) 次请求")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
        }
    }

    // MARK: - 近 7 天柱状图

    private var barChart: some View {
        let data = store.recentDays(7, model: selectedModelOrNil)
        let maxValue = max(data.map(\.total).max() ?? 0, 1)
        return VStack(alignment: .leading, spacing: 4) {
            Text("近 7 天")
                .font(.caption)
                .foregroundStyle(.secondary)
            HStack(alignment: .bottom, spacing: 8) {
                ForEach(Array(data.enumerated()), id: \.offset) { _, item in
                    let isToday = item.key == store.todayKey
                    VStack(spacing: 3) {
                        Text(item.total > 0 ? formatTokenCount(item.total) : "")
                            .font(.system(size: 8))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                        RoundedRectangle(cornerRadius: 3)
                            .fill(isToday ? Color.accentColor : Color.secondary.opacity(0.45))
                            .frame(height: max(3, 56 * CGFloat(item.total) / CGFloat(maxValue)))
                        Text(weekdayLabel(for: item.key))
                            .font(.caption2)
                            .foregroundStyle(isToday ? Color.primary : Color.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .help("\(item.key): \(formatTokenCount(item.total)) tokens")
                }
            }
            .frame(height: 84)
        }
    }

    // MARK: - input / output 拆分

    private var ioSplit: some View {
        let usage = store.usage(day: store.todayKey, model: selectedModelOrNil)
        return HStack(spacing: 14) {
            Label("输入 \(formatTokenCount(usage.input))", systemImage: "arrow.up")
            Label("输出 \(formatTokenCount(usage.output))", systemImage: "arrow.down")
            Spacer()
        }
        .font(.caption)
        .foregroundStyle(.secondary)
    }

    // MARK: - 工具

    private static let keyParser: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    private static let narrowWeekday: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "EEEEE"   // 窄星期: 五 / F
        return f
    }()

    private func weekdayLabel(for dayKey: String) -> String {
        guard let date = Self.keyParser.date(from: dayKey) else { return "" }
        return Self.narrowWeekday.string(from: date)
    }
}

// DebugLog.swift — 文件调试日志 (~/.qoze/island_debug.log)
// 开发期诊断用: NSLog 在统一日志中检索不可靠, 文件日志 100% 可读
// M4 发布前可移除或加开关

import Foundation

enum DebugLog {
    private static let logPath = NSHomeDirectory() + "/.qoze/island_debug.log"
    private static let queue = DispatchQueue(label: "com.qoze.code.debuglog")
    private static let maxBytes = 512 * 1024  // 超过 512KB 截断重写

    static func log(_ message: String) {
        queue.async {
            let line = "\(ISO8601DateFormatter().string(from: Date())) \(message)\n"
            guard let data = line.data(using: .utf8) else { return }

            // 简易滚动: 超限时清空重写
            if let attrs = try? FileManager.default.attributesOfItem(atPath: logPath),
               let size = attrs[.size] as? Int, size > maxBytes {
                try? FileManager.default.removeItem(atPath: logPath)
            }

            if FileManager.default.fileExists(atPath: logPath),
               let handle = try? FileHandle(forWritingTo: URL(fileURLWithPath: logPath)) {
                handle.seekToEndOfFile()
                handle.write(data)
                try? handle.close()
            } else {
                try? data.write(to: URL(fileURLWithPath: logPath))
            }
        }
    }
}

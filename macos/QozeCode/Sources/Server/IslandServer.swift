// IslandServer.swift — Unix Domain Socket 服务端 (POSIX 实现)
// 注: 技术设计 §2.2 原计划 Network.framework, 实现时发现其公开 API 不支持
//     UDS listener (NWEndpoint.unix 仅客户端可用), 故改用 POSIX socket。
// 职责: bind/listen ~/.qoze/island.sock, 接受多客户端连接, 按行(\n)分帧解析 NDJSON,
//       消息派发到 MainActor 的 SessionStore; 连接断开自动清理会话。

import Foundation

final class IslandServer {
    static let shared = IslandServer()

    private let socketPath = NSHomeDirectory() + "/.qoze/island.sock"
    private var listenFD: Int32 = -1
    private var acceptSource: DispatchSourceRead?
    private let ioQueue = DispatchQueue(label: "com.qoze.code.io", attributes: .concurrent)

    /// session_id -> 连接 fd (M2 批准响应回写用)
    private var sessionFDs: [String: Int32] = [:]
    private var fdSessions: [Int32: String] = [:]
    private let fdLock = NSLock()

    private init() {}

    func start() {
        // 清理上次异常退出残留的 socket 文件
        unlink(socketPath)

        listenFD = socket(AF_UNIX, SOCK_STREAM, 0)
        guard listenFD >= 0 else { NSLog("[QozeCode] socket() failed"); return }

        var addr = sockaddr_un()
        addr.sun_family = sa_family_t(AF_UNIX)
        _ = withUnsafeMutablePointer(to: &addr.sun_path.0) { ptr in
            strcpy(ptr, socketPath)
        }
        let addrLen = socklen_t(MemoryLayout<sockaddr_un>.size)

        let bindResult = withUnsafePointer(to: &addr) { ptr in
            ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sa in
                bind(listenFD, sa, addrLen)
            }
        }
        guard bindResult == 0 else {
            NSLog("[QozeCode] bind() failed: errno=\(errno)"); DebugLog.log("❌ bind failed errno=\(errno)")
            close(listenFD)
            return
        }
        // socket 文件权限 0600: 仅当前用户可连接
        chmod(socketPath, 0o600)

        guard listen(listenFD, 8) == 0 else {
            NSLog("[QozeCode] listen() failed")
            close(listenFD)
            return
        }

        let source = DispatchSource.makeReadSource(fileDescriptor: listenFD, queue: ioQueue)
        source.setEventHandler { [weak self] in self?.acceptClient() }
        source.setCancelHandler { [weak self] in
            if let fd = self?.listenFD, fd >= 0 { close(fd) }
        }
        source.resume()
        acceptSource = source
        NSLog("[QozeCode] listening on \(socketPath)"); DebugLog.log("server listening on \(socketPath)")
    }

    /// 向指定会话发送消息 (M2 批准响应)
    func send(to sessionId: String, message: Encodable) {
        fdLock.lock()
        let fd = sessionFDs[sessionId]
        fdLock.unlock()
        guard let fd = fd else { return }
        do {
            var data = try JSONEncoder().encode(AnyEncodable(message))
            data.append(0x0A)  // \n
            _ = data.withUnsafeBytes { ptr in
                write(fd, ptr.baseAddress, data.count)
            }
        } catch {
            NSLog("[QozeCode] encode response failed: \(error)")
        }
    }

    // MARK: - 私有

    private func acceptClient() {
        var clientAddr = sockaddr()
        var len = socklen_t(MemoryLayout<sockaddr>.size)
        let clientFD = accept(listenFD, &clientAddr, &len)
        guard clientFD >= 0 else { return }
        NSLog("[QozeCode] client connected fd=\(clientFD)"); DebugLog.log("client connected fd=\(clientFD)")
        ioQueue.async { [weak self] in
            self?.readLoop(fd: clientFD)
        }
    }

    private func readLoop(fd: Int32) {
        var buffer = Data()
        var chunk = [UInt8](repeating: 0, count: 8192)

        while true {
            let n = read(fd, &chunk, chunk.count)
            if n <= 0 { break }  // EOF (QozeCode 退出/被 kill) 或错误

            buffer.append(contentsOf: chunk[0..<n])
            // 按 \n 分帧
            while let newlineIdx = buffer.firstIndex(of: 0x0A) {
                let line = buffer.subdata(in: 0..<newlineIdx)
                buffer.removeSubrange(0...newlineIdx)
                if line.isEmpty { continue }
                dispatch(line: line, fd: fd)
            }
        }

        // 连接断开: 清理会话
        NSLog("[QozeCode] client disconnected fd=\(fd)"); DebugLog.log("client disconnected fd=\(fd)")
        close(fd)
        fdLock.lock()
        let sessionId = fdSessions.removeValue(forKey: fd)
        if let sessionId = sessionId { sessionFDs.removeValue(forKey: sessionId) }
        fdLock.unlock()
        if let sessionId = sessionId {
            Task { @MainActor in
                SessionStore.shared.removeSession(sessionId)
            }
        }
    }

    private func dispatch(line: Data, fd: Int32) {
        guard let message = IncomingMessage.decode(line: line) else { return }

        // register 时建立 session_id <-> fd 映射
        if case .register(let msg) = message {
            fdLock.lock()
            sessionFDs[msg.session_id] = fd
            fdSessions[fd] = msg.session_id
            fdLock.unlock()
        }

        Task { @MainActor in
            SessionStore.shared.apply(message)
        }
    }
}

/// 类型擦除的 Encodable (send 泛型出口)
private struct AnyEncodable: Encodable {
    private let encodeClosure: (Encoder) throws -> Void
    init(_ wrapped: Encodable) { encodeClosure = wrapped.encode }
    func encode(to encoder: Encoder) throws { try encodeClosure(encoder) }
}

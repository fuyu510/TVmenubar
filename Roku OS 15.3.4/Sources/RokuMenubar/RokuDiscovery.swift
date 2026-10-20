import Foundation
import Darwin

enum RokuDiscovery {
    static func search() async -> [String] {
        await Task.detached(priority: .utility) {
            let fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
            guard fd >= 0 else { return [] }
            defer { Darwin.close(fd) }
            var timeout = timeval(tv_sec: 0, tv_usec: 350_000)
            setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
            var address = sockaddr_in()
            address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
            address.sin_family = sa_family_t(AF_INET)
            address.sin_port = UInt16(1900).bigEndian
            inet_pton(AF_INET, "239.255.255.250", &address.sin_addr)
            let message = "M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 2\r\nST: roku:ecp\r\n\r\n"
            message.withCString { bytes in
                withUnsafePointer(to: &address) { ptr in ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                    _ = sendto(fd, bytes, strlen(bytes), 0, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
                } }
            }
            var found = Set<String>()
            let end = Date().addingTimeInterval(3.5)
            while Date() < end {
                var buffer = [UInt8](repeating: 0, count: 8192)
                var sender = sockaddr_in()
                var length = socklen_t(MemoryLayout<sockaddr_in>.size)
                let count = withUnsafeMutablePointer(to: &sender) { ptr in ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                    recvfrom(fd, &buffer, buffer.count, 0, $0, &length)
                } }
                guard count > 0 else { continue }
                var source = [CChar](repeating: 0, count: Int(INET_ADDRSTRLEN))
                guard inet_ntop(AF_INET, &sender.sin_addr, &source, socklen_t(source.count)) != nil else { continue }
                let host = String(cString: source)
                guard RokuECP.privateIPv4(host) else { continue }
                let reply = String(decoding: buffer.prefix(count), as: UTF8.self).lowercased()
                guard reply.contains("roku:ecp"), reply.contains("location: http://\(host):8060/") else { continue }
                found.insert(host)
            }
            return found.sorted()
        }.value
    }
}

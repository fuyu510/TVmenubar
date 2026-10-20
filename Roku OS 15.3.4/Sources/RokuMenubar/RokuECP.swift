import Foundation
import AppKit

struct RokuApp: Identifiable, Equatable {
    let id: String
    let name: String
    let type: String
    var isInput: Bool { type == "tvin" || id.hasPrefix("tvinput.") }
}

struct RokuDeviceInfo {
    let name: String
    let model: String
    let version: String
    let isTV: Bool
    let powerMode: String
}

enum RokuError: LocalizedError {
    case invalidAddress
    case invalidCommand
    case http(Int)
    case invalidResponse
    var errorDescription: String? {
        switch self {
        case .invalidAddress: "Enter a private IPv4 address for your Roku TV."
        case .invalidCommand: "This Roku command is not supported."
        case .http(403): "The TV blocked remote control. Set Control by mobile apps to Enabled in Roku settings."
        case .http(let code): "The TV returned HTTP \(code)."
        case .invalidResponse: "The TV returned an unexpected response."
        }
    }
}

private final class NoRedirects: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

private final class RokuXML: NSObject, XMLParserDelegate {
    var values: [String: String] = [:]
    var apps: [RokuApp] = []
    var current = ""
    var appID = ""
    var appType = ""
    var appName = ""
    func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?, qualifiedName qName: String?, attributes attributeDict: [String: String] = [:]) {
        current = elementName
        if elementName == "app" { appID = attributeDict["id"] ?? ""; appType = attributeDict["type"] ?? ""; appName = "" }
    }
    func parser(_ parser: XMLParser, foundCharacters string: String) {
        if current == "app" { appName += string }
        else { values[current, default: ""] += string }
    }
    func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?, qualifiedName qName: String?) {
        if elementName == "app", !appID.isEmpty {
            apps.append(RokuApp(id: appID, name: appName.trimmingCharacters(in: .whitespacesAndNewlines), type: appType))
        }
        current = ""
    }
    static func parse(_ data: Data) throws -> RokuXML {
        let reader = RokuXML(), parser = XMLParser(data: data)
        parser.delegate = reader
        parser.shouldResolveExternalEntities = false
        guard parser.parse() else { throw RokuError.invalidResponse }
        return reader
    }
}

final class RokuECP {
    static let allowedKeys: Set<String> = ["Home", "Back", "Select", "Up", "Down", "Left", "Right", "Play", "Rev", "Fwd", "InstantReplay", "Info", "VolumeUp", "VolumeDown", "VolumeMute", "PowerOn", "PowerOff", "ChannelUp", "ChannelDown"]
    let host: String
    private let session: URLSession
    init(host: String) throws {
        guard Self.privateIPv4(host) else { throw RokuError.invalidAddress }
        self.host = host
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 5
        config.timeoutIntervalForResource = 8
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        session = URLSession(configuration: config, delegate: NoRedirects(), delegateQueue: nil)
    }
    deinit { session.invalidateAndCancel() }

    static func privateIPv4(_ host: String) -> Bool {
        let parts = host.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 4, parts.allSatisfy({ !$0.isEmpty && $0.count <= 3 && $0.allSatisfy(\.isNumber) }),
              parts.compactMap({ UInt8($0) }).count == 4 else { return false }
        let bytes = parts.compactMap { UInt8($0) }
        return bytes[0] == 10 || (bytes[0] == 172 && (16...31).contains(bytes[1])) || (bytes[0] == 192 && bytes[1] == 168)
    }

    private func request(_ path: String, method: String = "GET") async throws -> Data {
        guard let url = URL(string: "http://\(host):8060/\(path)") else { throw RokuError.invalidCommand }
        var request = URLRequest(url: url)
        request.httpMethod = method
        if method == "POST" { request.httpBody = Data() }
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw RokuError.invalidResponse }
        guard response.statusCode == 200 else { throw RokuError.http(response.statusCode) }
        guard data.count <= 2_000_000 else { throw RokuError.invalidResponse }
        return data
    }

    func deviceInfo() async throws -> RokuDeviceInfo {
        let xml = try RokuXML.parse(await request("query/device-info"))
        let values = xml.values
        return RokuDeviceInfo(name: values["user-device-name"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "Roku TV",
                              model: values["model-name"] ?? "Roku",
                              version: values["software-version"] ?? "",
                              isTV: values["is-tv"] == "true",
                              powerMode: values["power-mode"] ?? "")
    }
    func apps() async throws -> [RokuApp] { try RokuXML.parse(await request("query/apps")).apps }
    func activeApp() async throws -> RokuApp? { try RokuXML.parse(await request("query/active-app")).apps.first }
    func icon(for id: String) async throws -> NSImage? {
        guard Self.safeID(id) else { throw RokuError.invalidCommand }
        return NSImage(data: try await request("query/icon/\(id)"))
    }
    func keypress(_ key: String) async throws {
        guard Self.allowedKeys.contains(key) else { throw RokuError.invalidCommand }
        _ = try await request("keypress/\(key)", method: "POST")
    }
    func launch(_ id: String) async throws {
        guard Self.safeID(id) else { throw RokuError.invalidCommand }
        _ = try await request("launch/\(id)", method: "POST")
    }
    private static func safeID(_ id: String) -> Bool {
        !id.isEmpty && id.count < 100 && id.unicodeScalars.allSatisfy { CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-").contains($0) }
    }
}

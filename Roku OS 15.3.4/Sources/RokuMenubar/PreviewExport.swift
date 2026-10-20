import AppKit
import SwiftUI

@MainActor enum PreviewExport {
    static func run(host: String, folder: URL) async throws {
        let client = try RokuECP(host: host)
        let info = try await client.deviceInfo()
        let apps = try await client.apps()
        let active = try await client.activeApp()
        let store = RokuStore()
        // Public previews use a generic title so a user's device identity is not exported.
        store.name = "Roku TV"
        store.model = "Roku TV"
        store.softwareVersion = info.version
        store.powerMode = info.powerMode
        store.apps = apps
        store.activeApp = active
        store.connected = true
        for app in apps {
            if let icon = try? await client.icon(for: app.id) { store.icons[app.id] = icon }
        }
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        for tab in ["Overview", "Remote", "Apps", "Inputs", "TV"] {
            try await render(tab: tab, filename: tab.lowercased(), store: store, folder: folder)
        }
        if let youtube = apps.first(where: { $0.name.localizedCaseInsensitiveContains("YouTube") }) {
            store.activeApp = youtube
            try await render(tab: "Apps", filename: "apps-youtube", store: store, folder: folder)
            try await render(tab: "Overview", filename: "overview-youtube", store: store, folder: folder)
        }
        if let hdmi = apps.first(where: { $0.id == "tvinput.hdmi2" }) {
            store.activeApp = hdmi
            try await render(tab: "Inputs", filename: "inputs-hdmi2", store: store, folder: folder)
            try await render(tab: "Overview", filename: "overview-hdmi2", store: store, folder: folder)
        }
    }

    private static func render(tab: String, filename: String, store: RokuStore, folder: URL) async throws {
        let view = RemoteView(store: store, initialTab: tab)
            .frame(width: 360, height: 740)
            .preferredColorScheme(.dark)
        let hosting = NSHostingView(rootView: view)
        hosting.frame = NSRect(x: 0, y: 0, width: 360, height: 740)
        hosting.appearance = NSAppearance(named: .darkAqua)
        let window = NSWindow(contentRect: hosting.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.contentView = hosting
        window.setFrameOrigin(NSPoint(x: -10000, y: -10000))
        window.orderFront(nil)
        try await Task.sleep(for: .milliseconds(200))
        hosting.layoutSubtreeIfNeeded()
        guard let bitmap = hosting.bitmapImageRepForCachingDisplay(in: hosting.bounds) else {
            throw RokuError.invalidResponse
        }
        hosting.cacheDisplay(in: hosting.bounds, to: bitmap)
        guard let png = bitmap.representation(using: .png, properties: [:]) else { throw RokuError.invalidResponse }
        try png.write(to: folder.appendingPathComponent("\(filename).png"))
        window.orderOut(nil)
        print("Exported \(filename)")
    }
}

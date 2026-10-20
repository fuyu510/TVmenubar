import AppKit
import SwiftUI
import Combine

final class RemotePanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
}

private struct PanelArrow: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.midX - 10, y: rect.maxY))
        path.addQuadCurve(to: CGPoint(x: rect.midX, y: rect.minY), control: CGPoint(x: rect.midX - 4, y: rect.maxY - 8))
        path.addQuadCurve(to: CGPoint(x: rect.midX + 10, y: rect.maxY), control: CGPoint(x: rect.midX + 4, y: rect.maxY - 8))
        path.closeSubpath()
        return path
    }
}

private struct PanelShell: View {
    @ObservedObject var store: RokuStore
    let height: CGFloat
    let arrowX: CGFloat
    var body: some View {
        VStack(spacing: 0) {
            PanelArrow().fill(Color(red: 0.073, green: 0.064, blue: 0.097))
                .frame(width: 22, height: 10).frame(width: 360, alignment: .leading).offset(x: arrowX - 11)
            RemoteView(store: store).frame(width: 360, height: height - 10)
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).strokeBorder(Color.white.opacity(0.16), lineWidth: 0.7))
        }.frame(width: 360, height: height).preferredColorScheme(.dark)
    }
}

@MainActor final class AppDelegate: NSObject, NSApplicationDelegate {
    let store = RokuStore()
    let panel = RemotePanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
    private var statusItem: NSStatusItem!
    private var host: NSHostingController<PanelShell>?
    private var clickMonitor: Any?
    private var keyMonitor: Any?
    private var sizeSubscription: AnyCancellable?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApplication.shared.setActivationPolicy(.accessory)
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        statusItem.button?.image = NSImage(systemSymbolName: "tv", accessibilityDescription: "Roku-menubar")
        statusItem.button?.image?.isTemplate = true
        statusItem.button?.target = self
        statusItem.button?.action = #selector(toggle)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.level = .popUpMenu
        panel.isReleasedWhenClosed = false
        panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.transient, .fullScreenAuxiliary]
        panel.appearance = NSAppearance(named: .darkAqua)
        sizeSubscription = store.$preferredPanelHeight.dropFirst().removeDuplicates().sink { [weak self] _ in
            DispatchQueue.main.async { if self?.panel.isVisible == true { self?.show() } }
        }
        clickMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { [weak self] _ in
            DispatchQueue.main.async { self?.panel.orderOut(nil) }
        }
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            if event.keyCode == 53, self?.panel.isVisible == true { self?.panel.orderOut(nil); return nil }
            return event
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            if !CommandLine.arguments.contains("--background") { self.show() }
            if self.store.host.isEmpty { self.store.discover() } else { self.store.connect() }
        }
    }
    @objc func toggle() { panel.isVisible ? panel.orderOut(nil) : show() }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { show(); return true }
    func show() {
        guard let button = statusItem.button, let anchorWindow = button.window else { return }
        let anchor = anchorWindow.convertToScreen(button.convert(button.bounds, to: nil))
        let screen = anchorWindow.screen ?? NSScreen.main!
        let visible = screen.visibleFrame
        let top = min(anchor.minY - 3, visible.maxY - 3)
        let height = min(store.preferredPanelHeight, max(300, top - visible.minY - 12))
        let x = min(max(anchor.midX - 180, visible.minX + 8), visible.maxX - 368)
        let root = PanelShell(store: store, height: height, arrowX: min(342, max(18, anchor.midX - x)))
        if let host { host.rootView = root }
        else { let controller = NSHostingController(rootView: root); host = controller; panel.contentViewController = controller }
        panel.setFrame(NSRect(x: x, y: top - height, width: 360, height: height), display: true)
        NSApplication.shared.activate(ignoringOtherApps: true)
        panel.makeKeyAndOrderFront(nil)
    }
    func applicationWillTerminate(_ notification: Notification) {
        store.disconnect()
        if let clickMonitor { NSEvent.removeMonitor(clickMonitor) }
        if let keyMonitor { NSEvent.removeMonitor(keyMonitor) }
    }
}

if CommandLine.arguments.contains("--help") {
    print("""
    Roku-menubar — a local macOS menu bar remote for Roku TVs

    Run normally to discover your TV and open the remote.
    --background   Start with the panel closed.
    --discover     List Roku TVs found by SSDP.
    --diagnose --host <private-ip>   Read the TV model, app count and active app.
    --export-previews --host <private-ip> --output <folder>   Render app screens as PNG.
    """)
} else if CommandLine.arguments.contains("--export-previews") {
    let args = CommandLine.arguments
    guard let hostIndex = args.firstIndex(of: "--host"), hostIndex + 1 < args.count,
          let outputIndex = args.firstIndex(of: "--output"), outputIndex + 1 < args.count else {
        print("Use --export-previews --host <private-ip> --output <folder>")
        exit(2)
    }
    Task { @MainActor in
        do {
            _ = NSApplication.shared
            try await PreviewExport.run(host: args[hostIndex + 1], folder: URL(fileURLWithPath: args[outputIndex + 1]))
            exit(0)
        } catch { print("ERROR: \(error.localizedDescription)"); exit(1) }
    }
    RunLoop.main.run()
} else if CommandLine.arguments.contains("--discover") {
    Task {
        let hosts = await RokuDiscovery.search()
        print(hosts.isEmpty ? "No Roku TVs found" : hosts.joined(separator: "\n"))
        exit(hosts.isEmpty ? 1 : 0)
    }
    RunLoop.main.run()
} else if CommandLine.arguments.contains("--diagnose") {
    let args = CommandLine.arguments
    guard let index = args.firstIndex(of: "--host"), index + 1 < args.count else {
        print("Use --diagnose --host <private-ip>")
        exit(2)
    }
    Task {
        do {
            let client = try RokuECP(host: args[index + 1])
            let info = try await client.deviceInfo()
            let apps = try await client.apps()
            let active = try await client.activeApp()
            print("TV: \(info.name) | \(info.model) | Roku OS \(info.version)")
            print("Apps: \(apps.filter { !$0.isInput }.count) | Inputs: \(apps.filter(\.isInput).count)")
            print("On screen: \(active?.name ?? "Unknown")")
            exit(0)
        } catch { print("ERROR: \(error.localizedDescription)"); exit(1) }
    }
    RunLoop.main.run()
} else {
    let app = NSApplication.shared
    let delegate = MainActor.assumeIsolated { AppDelegate() }
    app.delegate = delegate
    withExtendedLifetime(delegate) { app.run() }
}

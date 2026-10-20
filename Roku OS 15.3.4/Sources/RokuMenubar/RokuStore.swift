import Foundation
import AppKit
import Combine

@MainActor final class RokuStore: ObservableObject {
    @Published var host: String = UserDefaults.standard.string(forKey: "roku.host") ?? ""
    @Published var name = "Roku TV"
    @Published var model = ""
    @Published var softwareVersion = ""
    @Published var powerMode = ""
    @Published var apps: [RokuApp] = []
    @Published var activeApp: RokuApp?
    @Published var icons: [String: NSImage] = [:]
    @Published var connected = false
    @Published var discovering = false
    @Published var busy = false
    @Published var error: String?
    @Published var notice: String?
    @Published var preferredPanelHeight: CGFloat = 740
    var shouldPowerOn: Bool { !connected || powerMode == "PowerOff" }
    private let defaultFavorites = ["12", "837", "13", "291097"]
    @Published var favorites: Set<String> = Set(UserDefaults.standard.stringArray(forKey: "roku.favorites") ?? ["12", "837", "13", "291097"])
    private var client: RokuECP?
    private var pollTask: Task<Void, Never>?
    var streamingApps: [RokuApp] {
        apps.filter { !$0.isInput && $0.type != "menu" }.sorted { a, b in
            let aFavorite = favorites.contains(a.id), bFavorite = favorites.contains(b.id)
            if aFavorite != bFavorite { return aFavorite }
            if aFavorite, bFavorite {
                let ai = defaultFavorites.firstIndex(of: a.id) ?? 100
                let bi = defaultFavorites.firstIndex(of: b.id) ?? 100
                if ai != bi { return ai < bi }
            }
            return a.name.localizedCaseInsensitiveCompare(b.name) == .orderedAscending
        }
    }
    var inputs: [RokuApp] { apps.filter(\.isInput).sorted { $0.id < $1.id } }
    var favoriteApps: [RokuApp] {
        return streamingApps.filter { favorites.contains($0.id) }
            .sorted { a, b in
                let ai = defaultFavorites.firstIndex(of: a.id) ?? 100
                let bi = defaultFavorites.firstIndex(of: b.id) ?? 100
                return ai == bi ? a.name < b.name : ai < bi
            }
    }
    var orderedInputs: [RokuApp] {
        inputs.sorted { a, b in
            if a.id == activeApp?.id { return true }
            if b.id == activeApp?.id { return false }
            return a.id < b.id
        }
    }

    func discover() {
        guard !discovering else { return }
        discovering = true
        notice = "Looking for Roku TVs on your network…"
        Task {
            var hosts = await RokuDiscovery.search()
            if hosts.isEmpty { hosts = await RokuDiscovery.search() }
            discovering = false
            if let selected = hosts.first(where: { $0 == host }) ?? hosts.first {
                host = selected
                connect()
            } else { notice = "No Roku TV found. Check that it is on, or enter its local IP address." }
        }
    }

    func connect() {
        pollTask?.cancel(); pollTask = nil
        let selected = host.trimmingCharacters(in: .whitespacesAndNewlines)
        if client?.host != selected { apps = []; activeApp = nil; icons = [:] }
        connected = false
        do { client = try RokuECP(host: selected) }
        catch { self.error = error.localizedDescription; connected = false; return }
        busy = true; error = nil; notice = nil
        let current = client
        Task {
            do {
                guard let info = try await current?.deviceInfo(), client === current else { return }
                host = selected
                UserDefaults.standard.set(selected, forKey: "roku.host")
                name = info.name.isEmpty ? "Roku TV" : info.name
                model = info.model
                softwareVersion = info.version
                powerMode = info.powerMode
                connected = true; busy = false
                await refresh()
                startPolling(current)
            } catch {
                if client === current { connected = false; busy = false; self.error = error.localizedDescription }
            }
        }
    }

    func disconnect() {
        pollTask?.cancel(); pollTask = nil
        client = nil; connected = false; activeApp = nil; apps = []; icons = [:]
    }

    func refresh() async {
        guard let client else { return }
        do {
            let fresh = try await client.apps()
            guard self.client === client else { return }
            apps = fresh
            error = nil
            Task { await loadIcons(for: fresh, client: client) }
        } catch {
            if self.client === client { self.error = error.localizedDescription }
        }
        await refreshActive()
    }

    private func refreshActive() async {
        guard let client else { return }
        if let current = try? await client.activeApp(), self.client === client { activeApp = current }
    }
    private func startPolling(_ current: RokuECP?) {
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(5))
                guard !Task.isCancelled, let self, self.client === current else { return }
                await self.refreshActive()
            }
        }
    }
    private func loadIcons(for list: [RokuApp], client: RokuECP) async {
        for app in list where !Task.isCancelled {
            guard self.client === client else { return }
            if icons[app.id] != nil { continue }
            if let image = try? await client.icon(for: app.id), self.client === client { icons[app.id] = image }
        }
    }

    func send(_ key: String) {
        guard let client else { error = "Connect to a Roku TV first."; return }
        Task {
            do {
                try await client.keypress(key)
                error = nil
                if key == "Home" {
                    try? await Task.sleep(for: .milliseconds(700))
                    await refreshActive()
                }
            }
            catch { self.error = error.localizedDescription }
        }
    }
    func powerOn() {
        let selected = host.trimmingCharacters(in: .whitespacesAndNewlines)
        let powerClient: RokuECP
        do { powerClient = try RokuECP(host: selected) }
        catch { self.error = error.localizedDescription; return }
        busy = true; error = nil; notice = nil
        Task {
            do {
                try await powerClient.keypress("PowerOn")
                powerMode = "PowerOn"
                notice = "Power-on command sent. Reconnecting…"
                try? await Task.sleep(for: .seconds(2))
                connect()
            } catch {
                busy = false
                self.error = "Could not reach the TV to turn it on. Enable Fast TV Start in Settings → System → Power on the TV, then try again."
            }
        }
    }
    func powerOff() {
        guard let client else { error = "Connect to a Roku TV first."; return }
        Task {
            do {
                try await client.keypress("PowerOff")
                pollTask?.cancel(); pollTask = nil
                connected = false
                powerMode = "PowerOff"
                activeApp = nil
                notice = "TV off. Use the power button to turn it on."
                error = nil
            } catch { self.error = error.localizedDescription }
        }
    }
    func launch(_ app: RokuApp) {
        guard let client else { error = "Connect to a Roku TV first."; return }
        Task {
            do {
                try await client.launch(app.id)
                error = nil
                activeApp = app
            } catch { self.error = error.localizedDescription }
        }
    }
    func toggleFavorite(_ app: RokuApp) {
        if favorites.contains(app.id) { favorites.remove(app.id) }
        else { favorites.insert(app.id) }
        UserDefaults.standard.set(Array(favorites).sorted(), forKey: "roku.favorites")
    }
}

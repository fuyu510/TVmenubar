import SwiftUI
import AppKit

private let rokuPurple = Color(red: 0.57, green: 0.31, blue: 0.96)
private let faint = Color.white.opacity(0.52)

private func brandColor(_ name: String) -> Color {
    let value = name.lowercased()
    if value.contains("netflix") { return Color(red: 0.92, green: 0.15, blue: 0.20) }
    if value.contains("youtube") { return Color(red: 0.95, green: 0.20, blue: 0.19) }
    if value.contains("prime") { return Color(red: 0.20, green: 0.63, blue: 0.99) }
    if value.contains("disney") { return Color(red: 0.30, green: 0.42, blue: 0.97) }
    if value.contains("spotify") { return Color(red: 0.20, green: 0.79, blue: 0.44) }
    if value.contains("apple") { return Color(red: 0.78, green: 0.78, blue: 0.84) }
    if value.contains("globoplay") { return Color(red: 0.98, green: 0.28, blue: 0.31) }
    if value.contains("max") || value.contains("hbo") { return Color(red: 0.53, green: 0.36, blue: 0.89) }
    if value.contains("hdmi") { return Color(red: 0.30, green: 0.59, blue: 0.98) }
    return rokuPurple
}

private enum RemoteTab: String, CaseIterable, Identifiable {
    case overview = "Overview", remote = "Remote", apps = "Apps", inputs = "Inputs", info = "TV"
    var id: String { rawValue }
    var symbol: String {
        switch self {
        case .overview: "tv"
        case .remote: "dpad"
        case .apps: "square.grid.2x2"
        case .inputs: "cable.connector"
        case .info: "list.bullet.rectangle"
        }
    }
}

private struct Card<Content: View>: View {
    @ViewBuilder let content: Content
    var body: some View {
        content.padding(13).frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 13).fill(Color.white.opacity(0.07)))
            .overlay(RoundedRectangle(cornerRadius: 13).strokeBorder(Color.white.opacity(0.10), lineWidth: 0.7))
    }
}

private struct SoftButton: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background(RoundedRectangle(cornerRadius: 9).fill(Color.white.opacity(configuration.isPressed ? 0.14 : 0.075)))
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
    }
}

private struct RokuIcon: View {
    let app: RokuApp
    let image: NSImage?
    var size: CGFloat = 42
    var body: some View {
        Group {
            if let image {
                Image(nsImage: image).resizable().interpolation(.high).scaledToFit()
            } else {
                ZStack {
                    RoundedRectangle(cornerRadius: size * 0.23).fill(Color.white.opacity(0.09))
                    Text(String(app.name.prefix(1)).uppercased()).font(.system(size: size * 0.43, weight: .bold))
                }
            }
        }.frame(width: size, height: size)
            .clipShape(RoundedRectangle(cornerRadius: size * 0.23))
            .accessibilityHidden(true)
    }
}

struct RemoteView: View {
    @ObservedObject var store: RokuStore
    @State private var tab: RemoteTab
    @State private var settings = false
    @State private var search = ""
    @State private var draftHost = ""

    init(store: RokuStore, initialTab: String = "Overview") {
        self.store = store
        self._tab = State(initialValue: RemoteTab(rawValue: initialTab) ?? .overview)
    }

    private var currentTitle: String { store.activeApp?.type == "home" ? "Roku Home" : store.activeApp?.name ?? "Roku Home" }
    private var currentColor: Color { brandColor(currentTitle) }

    var body: some View {
        base.onAppear { draftHost = store.host }
    }

    private var base: some View {
        VStack(spacing: 0) {
            header.padding(.top, 15).padding(.bottom, 16)
            tabs.padding(.bottom, 14)
            contentArea
            footer.padding(.top, 10).padding(.bottom, 12)
        }.padding(.horizontal, 13).frame(width: 360)
            .background(LinearGradient(colors: [Color(red: 0.073, green: 0.064, blue: 0.097), Color(red: 0.041, green: 0.038, blue: 0.056)], startPoint: .topLeading, endPoint: .bottomTrailing))
            .foregroundStyle(Color.white.opacity(0.9))
            .font(.system(size: 12))
            .tint(rokuPurple)
    }

    private var contentArea: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if settings { settingsPanel }
                else { tabContent }
                feedback
            }.padding(.bottom, 10)
        }.scrollIndicators(.hidden)
    }

    private var header: some View {
        HStack(spacing: 9) {
            Text("Roku").font(.system(size: 17, weight: .heavy, design: .rounded)).tracking(-1.7)
                .foregroundStyle(rokuPurple).frame(width: 49, height: 31)
            VStack(alignment: .leading, spacing: 3) {
                Text(store.name).font(.system(size: 16, weight: .semibold)).lineLimit(1)
                Text("ROKU TV · YOUR SPACE").font(.system(size: 9, weight: .semibold)).tracking(0.8).foregroundStyle(faint)
            }
            Spacer()
            Menu {
                Button("Refresh TV data") { Task { await store.refresh() } }
                Button("Find Roku TVs") { store.discover() }
                Button(store.connected ? "Disconnect" : "Connect") { store.connected ? store.disconnect() : store.connect() }
                Divider()
                Button("Quit Roku-menubar") { NSApplication.shared.terminate(nil) }
            } label: { Image(systemName: "ellipsis").font(.system(size: 16)).frame(width: 27, height: 30) }
                .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
            Menu {
                Button("Turn Roku TV off") { store.send("PowerOff") }.disabled(!store.connected)
            } label: { Image(systemName: "power").font(.system(size: 15)).frame(width: 30, height: 30) }
                .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
        }
    }
    private var tabs: some View {
        HStack(spacing: 4) {
            ForEach(RemoteTab.allCases) { item in
                Button { tab = item; settings = false; store.preferredPanelHeight = item == .overview || item == .remote ? 740 : 650 } label: {
                    Image(systemName: item.symbol).font(.system(size: 16))
                        .foregroundStyle(tab == item && !settings ? rokuPurple : faint)
                        .frame(maxWidth: .infinity).frame(height: 36)
                        .background(RoundedRectangle(cornerRadius: 9).fill(tab == item && !settings ? rokuPurple.opacity(0.25) : .clear))
                }.buttonStyle(.plain).help(item.rawValue).accessibilityLabel(item.rawValue)
            }
        }.padding(4).background(RoundedRectangle(cornerRadius: 12).fill(Color.white.opacity(0.065)))
            .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Color.white.opacity(0.08), lineWidth: 0.7))
    }
    @ViewBuilder private var tabContent: some View {
        if !store.connected { connectionPanel }
        switch tab {
        case .overview: overview
        case .remote: remotePanel
        case .apps: appsPanel
        case .inputs: inputsPanel
        case .info: infoPanel
        }
    }

    private var overview: some View {
        VStack(spacing: 12) {
            heroCard
            audioCard

            if !store.favoriteApps.isEmpty {
                Card {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack { Label("Favorites", systemImage: "star").font(.system(size: 13, weight: .semibold)); Spacer(); Button("See all") { tab = .apps }.buttonStyle(.plain).foregroundStyle(faint) }
                        HStack(spacing: 7) {
                            ForEach(store.favoriteApps.prefix(4)) { app in
                                Button { store.launch(app) } label: {
                                    VStack(spacing: 7) {
                                        RokuIcon(app: app, image: store.icons[app.id], size: 37)
                                            .shadow(color: brandColor(app.name).opacity(0.25), radius: 7)
                                        Text(app.name).font(.system(size: 9, weight: .medium)).lineLimit(1)
                                    }.frame(maxWidth: .infinity)
                                }.buttonStyle(.plain).disabled(!store.connected)
                            }
                        }
                    }
                }
            }
            if !store.orderedInputs.isEmpty { inputRows(limit: 3) }
        }
    }

    private var heroCard: some View {
        VStack(spacing: 0) {
            ZStack {
                Ellipse().fill(currentColor.opacity(store.connected ? 0.32 : 0.10))
                    .frame(width: 235, height: 100).blur(radius: 37).offset(y: 8)
                if let url = Bundle.main.url(forResource: "tv-hero", withExtension: "png") ?? Bundle.module.url(forResource: "tv-hero", withExtension: "png"),
                   let image = NSImage(contentsOf: url) {
                    Image(nsImage: image).resizable().scaledToFit().frame(width: 320, height: 179)
                }
                VStack(spacing: 8) {
                    if let app = store.activeApp, store.icons[app.id] != nil {
                        RokuIcon(app: app, image: store.icons[app.id], size: 44)
                    } else {
                        Text("Roku").font(.system(size: 23, weight: .heavy, design: .rounded))
                            .tracking(-1.8).foregroundStyle(currentColor)
                    }
                    Text(store.connected ? currentTitle : "Roku TV")
                        .font(.system(size: 15, weight: .semibold)).lineLimit(1)
                        .frame(maxWidth: 190)
                }.offset(y: -7).shadow(color: currentColor.opacity(0.42), radius: 14)
            }.frame(height: 174)
            HStack(spacing: 6) {
                Circle().fill(store.connected ? currentColor : faint).frame(width: 5, height: 5)
                Text(store.connected ? "ON YOUR TV NOW" : "YOUR TV, ON YOUR MAC")
                    .font(.system(size: 9, weight: .bold)).tracking(1.2).foregroundStyle(faint)
                Spacer()
                if store.activeApp?.isInput == true { Text(store.activeApp?.id.replacingOccurrences(of: "tvinput.", with: "").uppercased() ?? "")
                    .font(.system(size: 9, weight: .semibold)).foregroundStyle(currentColor) }
            }.padding(.horizontal, 12).padding(.top, 6)
            Text(store.activeApp?.isInput == true ? "Switch inputs and settle in." : store.activeApp?.type == "home" ? "Ready for whatever is next." : "Pick up right where you left off.")
                .font(.system(size: 11)).foregroundStyle(faint)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 12).padding(.top, 6).padding(.bottom, 7)
        }
    }

    private var audioCard: some View {
        Card {
            VStack(spacing: 11) {
                HStack {
                    Image(systemName: "speaker.wave.2.fill").foregroundStyle(faint)
                    Text("TV audio").font(.system(size: 13, weight: .semibold))
                    Spacer()
                    Text("VOL").font(.system(size: 9, weight: .bold)).tracking(1).foregroundStyle(faint)
                }
                HStack(spacing: 8) {
                    Button { store.send("VolumeMute") } label: { Image(systemName: "speaker.slash.fill").frame(width: 35, height: 32) }
                        .help("Mute TV")
                    Button { store.send("VolumeDown") } label: { Image(systemName: "minus").frame(maxWidth: .infinity).frame(height: 32) }
                        .help("Lower volume")
                    Button { store.send("VolumeUp") } label: { Image(systemName: "plus").frame(maxWidth: .infinity).frame(height: 32) }
                        .help("Raise volume")
                }.buttonStyle(SoftButton()).disabled(!store.connected)
                HStack {
                    Text("Level is controlled on the TV").font(.system(size: 10)).foregroundStyle(faint)
                    Spacer()
                    Button { tab = .remote } label: { Label("Remote", systemImage: "chevron.right").labelStyle(.titleAndIcon) }
                        .buttonStyle(.plain).font(.system(size: 10)).foregroundStyle(faint)
                }
            }
        }
    }

    private func quickButton(_ key: String, _ symbol: String) -> some View {
        Button { store.send(key) } label: {
            Image(systemName: symbol).font(.system(size: 14)).frame(maxWidth: .infinity).frame(height: 35)
                .background(RoundedRectangle(cornerRadius: 9).fill(Color.white.opacity(0.075)))
        }.buttonStyle(.plain).disabled(!store.connected).help(key)
    }

    private var remotePanel: some View {
        VStack(spacing: 12) {
            Card {
                VStack(spacing: 16) {
                    HStack {
                        Text("Roku remote").font(.system(size: 13, weight: .semibold))
                        Spacer()
                        Circle().fill(store.connected ? Color.green : .orange).frame(width: 6, height: 6)
                        Text(store.connected ? "Ready" : "Offline").font(.system(size: 10)).foregroundStyle(faint)
                    }
                    HStack(spacing: 12) {
                        VStack(spacing: 12) {
                            quickButton("Home", "house.fill")
                            quickButton("Back", "arrow.uturn.backward")
                        }.frame(width: 49)
                        ZStack {
                            Circle().fill(Color.white.opacity(0.055))
                                .overlay(Circle().strokeBorder(Color.white.opacity(0.09), lineWidth: 0.8))
                            VStack { direction("Up", "chevron.up"); Spacer(); direction("Down", "chevron.down") }.padding(6)
                            HStack { direction("Left", "chevron.left"); Spacer(); direction("Right", "chevron.right") }.padding(6)
                            Button { store.send("Select") } label: {
                                Text("OK").font(.system(size: 12, weight: .bold))
                                    .frame(width: 46, height: 46)
                                    .background(Circle().fill(rokuPurple.opacity(0.27)))
                                    .foregroundStyle(rokuPurple)
                            }.buttonStyle(.plain).disabled(!store.connected)
                        }.frame(width: 142, height: 142)
                        VStack(spacing: 12) {
                            quickButton("Info", "asterisk")
                            quickButton("InstantReplay", "gobackward")
                        }.frame(width: 49)
                    }.frame(maxWidth: .infinity)
                    HStack(spacing: 7) {
                        quickButton("Rev", "backward.end.fill")
                        quickButton("Play", "playpause.fill")
                        quickButton("Fwd", "forward.end.fill")
                    }
                }
            }
            audioCard
            Card {
                VStack(alignment: .leading, spacing: 10) {
                    Label("Live TV", systemImage: "play.tv").font(.system(size: 13, weight: .semibold))
                    HStack { quickButton("ChannelDown", "chevron.down"); quickButton("ChannelUp", "chevron.up") }
                }
            }
        }
    }
    private func direction(_ key: String, _ symbol: String) -> some View {
        Button { store.send(key) } label: {
            Image(systemName: symbol).font(.system(size: 14, weight: .semibold))
                .frame(width: 30, height: 30).contentShape(Rectangle())
        }.buttonStyle(.plain).disabled(!store.connected).help(key)
    }

    private var appsPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeading("APPS", trailing: "\(store.streamingApps.count) installed")
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundStyle(faint)
                TextField("Search \(store.streamingApps.count) apps", text: $search).textFieldStyle(.plain)
                if !search.isEmpty { Button { search = "" } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(faint) }.buttonStyle(.plain) }
            }.padding(11).background(RoundedRectangle(cornerRadius: 11).fill(Color.white.opacity(0.065)))
            let filtered = store.streamingApps.filter { search.isEmpty || $0.name.localizedCaseInsensitiveContains(search) }
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 9) {
                ForEach(filtered) { app in
                    appTile(app)
                }
            }
            if filtered.isEmpty { Text(store.connected ? "No matching apps." : "Connect to load apps from your TV.").foregroundStyle(faint) }
        }
    }
    private func appTile(_ app: RokuApp) -> some View {
        let color = brandColor(app.name)
        let isActive = store.activeApp?.id == app.id
        return VStack(spacing: 5) {
            HStack {
                Spacer()
                Button { store.toggleFavorite(app) } label: {
                    Image(systemName: store.favorites.contains(app.id) ? "star.fill" : "star")
                        .font(.system(size: 10)).foregroundStyle(store.favorites.contains(app.id) ? color : faint)
                }.buttonStyle(.plain).help("Favorite \(app.name)")
            }
            Button { store.launch(app) } label: {
                VStack(spacing: 9) {
                    RokuIcon(app: app, image: store.icons[app.id], size: 45)
                        .shadow(color: color.opacity(0.23), radius: 10)
                    Text(app.name).font(.system(size: 10, weight: .medium)).lineLimit(2)
                        .multilineTextAlignment(.center).frame(height: 27)
                }.frame(maxWidth: .infinity).contentShape(Rectangle())
            }.buttonStyle(.plain).disabled(!store.connected).help("Open \(app.name) on TV")
            Text(isActive ? "ON SCREEN" : " ").font(.system(size: 7, weight: .bold))
                .tracking(0.7).foregroundStyle(color).frame(height: 9)
        }.padding(9).frame(height: 133)
            .background(RoundedRectangle(cornerRadius: 13).fill(LinearGradient(colors: [color.opacity(0.18), Color.white.opacity(0.035)], startPoint: .topLeading, endPoint: .bottomTrailing)))
            .overlay(RoundedRectangle(cornerRadius: 13).strokeBorder(color.opacity(isActive ? 0.6 : 0.16), lineWidth: 0.8))
    }
    private var inputsPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeading("INPUTS", trailing: "From your TV")
            inputRows(limit: nil)
        }
    }
    private func inputRows(limit: Int?) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 7) {
                HStack {
                    Label("Inputs", systemImage: "cable.connector").font(.system(size: 13, weight: .semibold))
                    Spacer()
                    if limit != nil { Button("See all") { tab = .inputs }.buttonStyle(.plain).font(.system(size: 10)).foregroundStyle(faint) }
                }.padding(.horizontal, 4).padding(.bottom, 2)
                ForEach(Array(store.orderedInputs.prefix(limit ?? store.orderedInputs.count))) { input in
                    Button { store.launch(input) } label: {
                        HStack(spacing: 10) {
                            RokuIcon(app: input, image: store.icons[input.id], size: 37)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(input.name).font(.system(size: 12, weight: .semibold))
                                Text(input.id.replacingOccurrences(of: "tvinput.", with: "").uppercased()).font(.system(size: 9)).foregroundStyle(faint)
                            }
                            Spacer()
                            if input.id == store.activeApp?.id { Text("ON SCREEN").font(.system(size: 8, weight: .bold)).foregroundStyle(brandColor(input.name)) }
                            Image(systemName: input.id == store.activeApp?.id ? "checkmark.circle.fill" : "chevron.right")
                                .foregroundStyle(input.id == store.activeApp?.id ? brandColor(input.name) : faint)
                        }.padding(.horizontal, 8).frame(height: 48)
                            .background(RoundedRectangle(cornerRadius: 9).fill(input.id == store.activeApp?.id ? brandColor(input.name).opacity(0.16) : .clear))
                            .overlay(RoundedRectangle(cornerRadius: 9).strokeBorder(input.id == store.activeApp?.id ? brandColor(input.name).opacity(0.42) : .clear, lineWidth: 0.7))
                    }.buttonStyle(.plain).disabled(!store.connected)
                }
                if store.orderedInputs.isEmpty { Text("Inputs will appear after connecting.").foregroundStyle(faint).padding(6) }
            }
        }
    }
    private var infoPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeading("YOUR TV")
            Card {
                VStack(spacing: 13) {
                    infoRow("Device", store.name)
                    infoRow("Model", store.model.isEmpty ? "—" : store.model)
                    infoRow("Roku OS", store.softwareVersion.isEmpty ? "—" : store.softwareVersion)
                    infoRow("Power", store.powerMode.isEmpty ? "—" : store.powerMode)
                    infoRow("Apps", "\(store.streamingApps.count)")
                    infoRow("Inputs", "\(store.inputs.count)")
                }
            }
            Text("Device information and app icons come directly from this Roku TV over your local network.")
                .font(.system(size: 11)).foregroundStyle(faint)
        }
    }
    private func infoRow(_ label: String, _ value: String) -> some View {
        HStack { Text(label).foregroundStyle(faint); Spacer(); Text(value).fontWeight(.semibold).lineLimit(1) }
    }
    private func sectionHeading(_ title: String, trailing: String? = nil) -> some View {
        HStack { Text(title).font(.system(size: 10, weight: .bold)).tracking(1.4).foregroundStyle(faint); Spacer(); if let trailing { Text(trailing).font(.system(size: 10)).foregroundStyle(faint) } }
    }

    private var connectionPanel: some View {
        Card {
            VStack(alignment: .leading, spacing: 9) {
                Label(store.discovering ? "Finding your TV…" : "Connect your Roku TV", systemImage: "wifi").font(.system(size: 13, weight: .semibold))
                Text("The Mac and TV must be on the same network. Set Control by mobile apps to Enabled on the TV.").font(.system(size: 11)).foregroundStyle(faint)
                HStack {
                    Button("Find TVs") { store.discover() }.disabled(store.discovering)
                    Button("Settings") { draftHost = store.host; settings = true; store.preferredPanelHeight = 530 }
                }.buttonStyle(.bordered)
            }
        }
    }
    private var settingsPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeading("CONNECTION")
            Card {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Roku TV address").font(.system(size: 13, weight: .semibold))
                    TextField("192.0.2.42", text: $draftHost).textFieldStyle(.roundedBorder)
                    Text("Saved only on this Mac. Enter a private IPv4 address or use discovery.").font(.system(size: 10)).foregroundStyle(faint)
                    HStack {
                        Button("Find Roku TVs") { store.discover(); settings = false; store.preferredPanelHeight = 740 }
                        Spacer()
                        Button("Save & connect") { store.host = draftHost.trimmingCharacters(in: .whitespaces); store.connect(); settings = false; store.preferredPanelHeight = 740 }
                    }.buttonStyle(.bordered)
                }
            }
            Button("Back to remote") { settings = false; store.preferredPanelHeight = 740 }.buttonStyle(.plain).foregroundStyle(faint)
        }
    }
    @ViewBuilder private var feedback: some View {
        if let error = store.error {
            Card { HStack(alignment: .top, spacing: 7) {
                Image(systemName: "exclamationmark.circle").foregroundStyle(.orange)
                Text(error).font(.system(size: 11)).fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
                Button { store.error = nil } label: { Image(systemName: "xmark") }.buttonStyle(.plain)
            } }
        } else if let notice = store.notice { Text(notice).foregroundStyle(faint).font(.system(size: 11)) }
    }
    private var footer: some View {
        HStack(spacing: 8) {
            Circle().fill(store.connected ? Color.green : Color.orange).frame(width: 6, height: 6)
            Text(store.connected ? "Connected" : "Not connected").foregroundStyle(faint)
            Spacer()
            Text("ROKU-MENUBAR").font(.system(size: 9, weight: .bold)).tracking(1.2).foregroundStyle(Color.white.opacity(0.29))
            Button { draftHost = store.host; settings.toggle(); store.preferredPanelHeight = settings ? 530 : 740 } label: { Image(systemName: "slider.horizontal.3") }.buttonStyle(.plain).foregroundStyle(faint).help("Settings")
        }
    }
}

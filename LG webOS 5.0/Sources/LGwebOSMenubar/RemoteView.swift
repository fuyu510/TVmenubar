import SwiftUI
import AppKit

private let accent = Color(red: 0.91, green: 0.17, blue: 0.35)
private let mutedInk = Color.white.opacity(0.49)

private enum RemoteTab: String, CaseIterable, Identifiable {
    case home = "Your TV", remote = "Remote", apps = "Apps", media = "Cast", usage = "Activity", info = "Picture"
    var id: String { rawValue }
    var symbol: String {
        switch self {
        case .home: return "tv"
        case .remote: return "dpad"
        case .apps: return "square.grid.2x2"
        case .media: return "airplay.video"
        case .info: return "slider.horizontal.3"
        case .usage: return "chart.bar.xaxis"
        }
    }
}

private struct PanelButton: ButtonStyle {
    var selected = false
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(selected ? accent : Color.white.opacity(0.79))
            .background(RoundedRectangle(cornerRadius: 9, style: .continuous)
                .fill(selected ? accent.opacity(0.19) : Color.white.opacity(configuration.isPressed ? 0.13 : 0.065)))
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
    }
}

private struct PanelCard<Content: View>: View {
    @ViewBuilder let content: Content
    var body: some View {
        content.padding(12).frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(Color.white.opacity(0.068)))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(Color.white.opacity(0.085), lineWidth: 0.7))
    }
}

struct AppMark: View {
    let app: TVApp
    var size: CGFloat = 36
    var body: some View {
        Group {
            if let filename = app.icon,
               let url = AppResources.bundle.url(forResource: filename, withExtension: nil, subdirectory: "AppAssets"),
               let image = NSImage(contentsOf: url) {
                Image(nsImage: image).resizable().interpolation(.high).scaledToFit()
            } else {
                ZStack { RoundedRectangle(cornerRadius: 8).fill(Color.white.opacity(0.08)); Image(systemName: "app").foregroundStyle(mutedInk) }
            }
        }.frame(width: size, height: size).clipShape(RoundedRectangle(cornerRadius: size * 0.23))
            .accessibilityHidden(true)
    }
}

private struct BrandImage: View {
    let name: String
    var width: CGFloat = 28
    var height: CGFloat = 28
    var body: some View {
        Group {
            if let url = AppResources.bundle.url(forResource: name, withExtension: "png", subdirectory: "AppAssets"), let image = NSImage(contentsOf: url) {
                Image(nsImage: image).resizable().interpolation(.high).scaledToFit()
            }
        }.frame(width: width, height: height).accessibilityHidden(true)
    }
}

struct RemoteView: View {
    @ObservedObject var store: RemoteStore
    @State private var tab: RemoteTab = .home
    @State private var settings = false
    @State private var search = ""
    @State private var text = ""
    @State private var draftHost = ""
    @State private var draftName = ""
    @State private var draftMAC = ""
    @State private var pictureDraft: [String: Int] = [:]
    @State private var usageDays = 1
    @State private var showEvents = false
    @State private var pointerTranslation = CGSize.zero
    private var theme: BrandTheme { BrandTheme.forApp(store.displayForegroundID, title: store.currentInput?.label ?? store.currentApp) }
    private var accent: Color { theme.color }
    private var activeTitle: String { isPlayStation ? "PlayStation 5" : store.currentInput?.label ?? store.currentApp }
    var body: some View {
        VStack(spacing: 0) {
            header.padding(.top, 16).padding(.bottom, 16)
            tabs.padding(.bottom, 14)
            contentScroll
            footer.padding(.top, 10).padding(.bottom, 12)
        }.padding(.horizontal, 13).frame(width: 360)
            .background(LinearGradient(colors: [Color(red: 0.065, green: 0.070, blue: 0.080), Color(white: 0.042)], startPoint: .topLeading, endPoint: .bottomTrailing))
            .foregroundStyle(Color.white.opacity(0.86)).preferredColorScheme(.dark)
            .font(.system(size: 12))
            .tint(accent)
            .animation(.easeOut(duration: 0.22), value: store.displayForegroundID)
            .onChange(of: tab) { _, value in store.preferredPanelHeight = preferredHeight(value) }
            .onChange(of: settings) { _, value in store.preferredPanelHeight = value ? 650 : preferredHeight(tab) }
            .onChange(of: store.picture) { _, value in pictureDraft = value }
            .onChange(of: store.pictureApplying) { _, value in if !value { pictureDraft = store.picture } }
            .onAppear {
                pictureDraft = store.picture
                if store.host.isEmpty { showConnectionSettings() }
            }
    }
    private func preferredHeight(_ tab: RemoteTab) -> CGFloat { tab == .home || tab == .remote ? 740 : tab == .media ? 590 : tab == .usage ? 580 : 660 }
    private var contentScroll: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if settings { settingsPanel }
                else {
                    if tab != .home { sectionTitle(tab.rawValue.uppercased()) }
                    if !store.connected { connectionPanel }
                    tabContent
                }
                feedback
            }.padding(.bottom, 12)
        }.scrollIndicators(.hidden)
    }
    @ViewBuilder private var tabContent: some View {
        switch tab {
        case .home: homePanel
        case .remote: remotePanel
        case .apps: appsPanel
        case .media: mediaPanel
        case .info: infoPanel
        case .usage: usagePanel
        }
    }
    @ViewBuilder private var feedback: some View {
        if let error = store.error {
            PanelCard {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "exclamationmark.circle").foregroundStyle(.orange)
                    Text(error).font(.system(size: 11)).fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 0)
                    Button { store.error = nil } label: { Image(systemName: "xmark").font(.system(size: 10)) }.buttonStyle(.plain).help("Dismiss message")
                }
            }
        } else if let notice = store.notice {
            Text(notice).font(.system(size: 11)).foregroundStyle(mutedInk).fixedSize(horizontal: false, vertical: true)
        }
    }
    private var header: some View {
        HStack(spacing: 9) {
            BrandImage(name: "lg", width: 31, height: 31)
            VStack(alignment: .leading, spacing: 3) {
                Text(store.name).font(.system(size: 17, weight: .semibold)).tracking(-0.3)
                Text("LG · webOS").font(.system(size: 10, weight: .medium)).foregroundStyle(mutedInk)
            }
            Spacer()
            Menu {
                Button("Refresh TV data") { Task { await store.refresh(); await store.refreshPicture() } }
                Button(store.connected ? "Disconnect" : "Connect") {
                    if store.connected { store.disconnect() }
                    else if store.host.isEmpty { showConnectionSettings() }
                    else { store.connect() }
                }
                Divider()
                Button("Quit LGwebOS-menubar") { NSApplication.shared.terminate(nil) }
            } label: { Image(systemName: "ellipsis").frame(width: 24, height: 30).foregroundStyle(mutedInk) }
                .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
            Menu {
                if store.connected { Button("Turn TV off") { store.power() } }
                else { Button("Wake TV over Wi-Fi") { store.power() }.disabled(store.mac.isEmpty) }
            } label: {
                Image(systemName: "power").font(.system(size: 17)).foregroundStyle(store.connected ? .white : mutedInk)
                    .frame(width: 34, height: 34).background(Circle().fill(Color.white.opacity(0.06)))
            }.menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize().help("TV power")
        }
    }
    private var tabs: some View {
        HStack(spacing: 4) {
            ForEach(RemoteTab.allCases) { item in
                Button { tab = item; settings = false } label: {
                    Image(systemName: item.symbol).font(.system(size: 16, weight: .medium))
                        .foregroundStyle(tab == item && !settings ? accent : mutedInk)
                        .frame(maxWidth: .infinity).frame(height: 35)
                        .background(RoundedRectangle(cornerRadius: 9).fill(tab == item && !settings ? accent.opacity(0.2) : .clear))
                        .contentShape(Rectangle())
                }.buttonStyle(.plain).help(item.rawValue).accessibilityLabel(item.rawValue)
            }
        }.padding(4).background(RoundedRectangle(cornerRadius: 12).fill(Color.white.opacity(0.066)))
            .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Color.white.opacity(0.08), lineWidth: 0.7))
    }
    private func sectionTitle(_ title: String) -> some View {
        HStack {
            Text(title).font(.system(size: 11, weight: .bold)).tracking(0.8).foregroundStyle(mutedInk)
            Spacer()
            if store.connecting { ProgressView().controlSize(.mini) }
        }.padding(.horizontal, 1)
    }
    private var homePanel: some View {
        VStack(spacing: 12) {
            nowPlayingCard
            audioCard
            if !store.pinnedApps.isEmpty {
                PanelCard {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Label("Favorites", systemImage: "star").font(.system(size: 12, weight: .semibold))
                            Spacer()
                            Button { tab = .apps } label: { Text("See all").font(.system(size: 10)).foregroundStyle(mutedInk) }.buttonStyle(.plain)
                        }
                        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 6), count: 4), spacing: 13) {
                            ForEach(store.pinnedApps) { app in
                                Button { store.launch(app) } label: {
                                    VStack(spacing: 8) { AppMark(app: app, size: 34); Text(app.title).font(.system(size: 9, weight: .medium)).foregroundStyle(Color.white.opacity(0.7)).lineLimit(1) }
                                        .frame(maxWidth: .infinity).padding(.vertical, 4).contentShape(Rectangle())
                                }.buttonStyle(.plain).disabled(!store.connected).help("Open \(app.title) on TV")
                            }
                        }
                    }
                }
            }
            if !store.inputs.isEmpty {
                PanelCard {
                    VStack(spacing: 7) {
                        HStack { Label("Inputs", systemImage: "cable.connector").font(.system(size: 12, weight: .semibold)); Spacer() }
                        ForEach(store.orderedInputs.filter(\.connected)) { input in inputRow(input) }
                    }
                }
            }
            if !store.mostUsedApps.isEmpty {
                HStack(spacing: 8) {
                    Text("Most used").font(.system(size: 10)).foregroundStyle(mutedInk)
                    Spacer()
                    ForEach(Array(store.mostUsedApps.prefix(4))) { app in
                        Button { store.launch(app) } label: { AppMark(app: app, size: 25) }.buttonStyle(.plain).help("Open \(app.title)").disabled(!store.connected)
                    }
                    Button { tab = .usage } label: { Image(systemName: "chevron.right").foregroundStyle(mutedInk) }.buttonStyle(.plain).help("View activity")
                }.padding(.horizontal, 4)
            }
        }
    }
    private var isPlayStation: Bool {
        store.currentInput?.label.localizedCaseInsensitiveContains("PS5") == true || store.currentInput?.label.localizedCaseInsensitiveContains("PlayStation") == true
    }
    private var nowPlayingCard: some View {
        VStack(spacing: 0) {
            ZStack {
                Ellipse().fill(accent.opacity(store.connected ? 0.28 : 0.08)).frame(width: 230, height: 110).blur(radius: 38).offset(y: 9)
                BrandImage(name: "tv-hero", width: 312, height: 178)
                VStack(spacing: 9) {
                    if isPlayStation { BrandImage(name: "playstation", width: 45, height: 45) }
                    else if !store.homeRequested, let app = store.apps.first(where: { $0.id == store.foregroundID }) { AppMark(app: app, size: 43) }
                    else if store.currentInput?.label.localizedCaseInsensitiveContains("Chromecast") == true { BrandImage(name: "googlecast", width: 37, height: 37) }
                    else { BrandImage(name: "lg", width: 43, height: 43) }
                    Text(store.connected ? activeTitle : "LG webOS").font(.system(size: 15, weight: .semibold)).tracking(-0.3).lineLimit(1)
                }.offset(y: -6).shadow(color: accent.opacity(0.5), radius: 16)
            }.frame(height: 174)
            HStack(spacing: 5) {
                Circle().fill(store.connected ? accent : mutedInk).frame(width: 4, height: 4)
                Text(store.connected ? (store.homeRequested ? "HOME SENT FROM MAC" : "APP REPORTED BY TV") : "YOUR TV, ON YOUR MAC").font(.system(size: 8, weight: .bold)).tracking(1.1).foregroundStyle(mutedInk)
                Spacer()
                if let input = store.currentInput { Text(input.id.replacingOccurrences(of: "_", with: " ")).font(.system(size: 9, weight: .medium)).foregroundStyle(accent) }
            }.padding(.horizontal, 10).padding(.top, 7)
            Text(theme.tagline).font(.system(size: 11)).foregroundStyle(Color.white.opacity(0.65)).frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 10).padding(.top, 6).padding(.bottom, 7)
        }.padding(.top, 2)
    }
    private var audioCard: some View {
        PanelCard {
            VStack(spacing: 12) {
                HStack {
                    Image(systemName: "speaker.wave.2.fill").foregroundStyle(mutedInk)
                    Text("TV audio").fontWeight(.semibold)
                    Spacer()
                    Text(store.hasVolume ? "\(Int(store.volume))" : "—").font(.system(size: 20, weight: .semibold, design: .rounded)).monospacedDigit().contentTransition(.numericText())
                }
                HStack(spacing: 9) {
                    Button { store.toggleMute() } label: { Image(systemName: store.muted ? "speaker.slash.fill" : "speaker.fill").foregroundStyle(store.muted ? accent : mutedInk).frame(width: 20) }.buttonStyle(.plain).help(store.muted ? "Unmute" : "Mute")
                    Slider(value: Binding(get: { store.volume }, set: store.changeVolume), in: 0...100).tint(accent).accessibilityLabel("TV volume")
                    Image(systemName: "speaker.wave.3.fill").font(.system(size: 11)).foregroundStyle(mutedInk)
                }.disabled(!store.connected || !store.hasVolume)
                HStack {
                    Text(store.muted ? "Muted" : "TV speakers").font(.system(size: 10)).foregroundStyle(mutedInk)
                    Spacer()
                    Button { store.volumeStep(false) } label: { Image(systemName: "minus").frame(width: 25, height: 22) }.buttonStyle(PanelButton()).help("Lower volume")
                    Button { store.volumeStep(true) } label: { Image(systemName: "plus").frame(width: 25, height: 22) }.buttonStyle(PanelButton()).help("Raise volume")
                }.disabled(!store.connected || !store.hasVolume)
            }
        }
    }
    private var remotePanel: some View {
        VStack(spacing: 12) {
            PanelCard {
                VStack(spacing: 16) {
                    HStack {
                        Text(store.currentApp).lineLimit(1).fontWeight(.semibold)
                        Spacer()
                        Circle().fill(store.pointerReady ? Color.green : Color.orange).frame(width: 5, height: 5)
                        Text(store.pointerReady ? "Remote ready" : "Connecting remote").font(.system(size: 9)).foregroundStyle(mutedInk)
                    }
                    HStack(spacing: 15) {
                        VStack(spacing: 12) { remoteButton("house", "Close app and open Home", "HOME").disabled(store.navigatingHome); remoteButton("arrow.uturn.backward", "Back", "BACK") }
                        ZStack {
                            Circle().fill(Color.white.opacity(0.055)).overlay(Circle().strokeBorder(Color.white.opacity(0.07)))
                            VStack { remoteDirection("chevron.up", "UP"); Spacer(); remoteDirection("chevron.down", "DOWN") }.padding(6)
                            HStack { remoteDirection("chevron.left", "LEFT"); Spacer(); remoteDirection("chevron.right", "RIGHT") }.padding(6)
                            Button { store.clickPointer() } label: { Text("OK").font(.system(size: 12, weight: .semibold)).frame(width: 46, height: 46).background(Circle().fill(accent.opacity(0.2))).foregroundStyle(accent) }.buttonStyle(.plain).help("Confirm")
                        }.frame(width: 138, height: 138)
                        VStack(spacing: 12) { remoteButton("gearshape", "TV settings", "MENU"); remoteButton("xmark", "Exit screen", "EXIT") }
                    }.frame(maxWidth: .infinity)
                    HStack(spacing: 7) {
                        mediaButton("backward.end.fill", "Rewind", "rewind")
                        mediaButton("play.fill", "Play", "play")
                        mediaButton("pause.fill", "Pause", "pause")
                        mediaButton("stop.fill", "Stop", "stop")
                        mediaButton("forward.end.fill", "Fast forward", "fastForward")
                    }
                }.disabled(!store.connected)
            }
            PanelCard {
                VStack(spacing: 9) {
                    HStack { Label("TV pointer", systemImage: "cursorarrow").fontWeight(.semibold); Spacer(); Text("Drag · tap to click").font(.system(size: 9)).foregroundStyle(mutedInk) }
                    RoundedRectangle(cornerRadius: 12).fill(accent.opacity(0.065)).overlay(Image(systemName: "hand.draw").font(.system(size: 25, weight: .light)).foregroundStyle(accent.opacity(0.7)))
                        .frame(height: 85).contentShape(Rectangle())
                        .gesture(DragGesture(minimumDistance: 2).onChanged { value in
                            let delta = CGSize(width: value.translation.width - pointerTranslation.width, height: value.translation.height - pointerTranslation.height)
                            pointerTranslation = value.translation
                            store.movePointer(dx: Int(delta.width * 1.8), dy: Int(delta.height * 1.8))
                        }.onEnded { _ in pointerTranslation = .zero })
                        .simultaneousGesture(TapGesture().onEnded { store.clickPointer() })
                        .accessibilityLabel("TV touchpad")
                }.disabled(!store.connected)
            }
            audioCard
            HStack(spacing: 8) {
                Button { store.press("CHANNELDOWN") } label: { Label("Channel −", systemImage: "chevron.down").frame(maxWidth: .infinity).frame(height: 32) }.buttonStyle(PanelButton())
                Button { store.press("CHANNELUP") } label: { Label("Channel +", systemImage: "chevron.up").frame(maxWidth: .infinity).frame(height: 32) }.buttonStyle(PanelButton())
            }.disabled(!store.connected)
            PanelCard {
                VStack(alignment: .leading, spacing: 10) {
                    Label("Keyboard", systemImage: "keyboard").fontWeight(.semibold)
                    TextField("Type into the open field on your TV", text: $text).textFieldStyle(.roundedBorder).onSubmit(sendText)
                    HStack {
                        Text("Open a text field on your TV.").font(.system(size: 10)).foregroundStyle(mutedInk)
                        Spacer()
                        Button("Send", action: sendText).disabled(text.isEmpty)
                        Button { store.enterText() } label: { Image(systemName: "return") }.help("Confirm text on TV")
                    }
                }.disabled(!store.connected)
            }
            inputsPanel
            Text("Playback controls depend on the open app. Navigation controls the TV; the PS5 uses its own controller.").font(.system(size: 10)).foregroundStyle(mutedInk)
        }
    }
    private func sendText() { store.sendText(text); text = "" }
    private func remoteDirection(_ symbol: String, _ command: String) -> some View {
        Button { store.press(command) } label: { Image(systemName: symbol).font(.system(size: 13, weight: .semibold)).frame(width: 29, height: 29).contentShape(Rectangle()) }.buttonStyle(.plain).help(command)
    }
    private func remoteButton(_ symbol: String, _ title: String, _ command: String) -> some View {
        Button { store.press(command) } label: { Image(systemName: symbol).font(.system(size: 15)).frame(width: 43, height: 42) }.buttonStyle(PanelButton()).help(title).accessibilityLabel(title)
    }
    private func mediaButton(_ symbol: String, _ title: String, _ command: String) -> some View {
        Button { store.media(command) } label: { Image(systemName: symbol).font(.system(size: 11)).frame(maxWidth: .infinity).frame(height: 30) }.buttonStyle(PanelButton()).help(title).accessibilityLabel(title)
    }
    private var appsPanel: some View {
        VStack(spacing: 14) {
            HStack(spacing: 7) {
                Image(systemName: "magnifyingglass").foregroundStyle(mutedInk)
                TextField("Search \(store.apps.count) apps", text: $search).textFieldStyle(.plain)
                if !search.isEmpty { Button { search = "" } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(mutedInk) }.buttonStyle(.plain) }
            }.padding(11).background(RoundedRectangle(cornerRadius: 11).fill(Color.white.opacity(0.06)))
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 9), count: 3), spacing: 9) {
                ForEach(store.shortcuts.filter { search.isEmpty || $0.title.localizedCaseInsensitiveContains(search) }) { app in
                    let color = BrandTheme.forApp(app.id, title: app.title).color
                    VStack(spacing: 8) {
                        HStack {
                            Spacer()
                            Button { store.toggleFavorite(app) } label: {
                                Image(systemName: store.favorites.contains(app.id) ? "star.fill" : "star").font(.system(size: 9)).foregroundStyle(store.favorites.contains(app.id) ? color : mutedInk)
                            }.buttonStyle(.plain).help("Favorite \(app.title)").accessibilityLabel("Favorite \(app.title)")
                        }
                        Button { store.launch(app) } label: {
                            VStack(spacing: 10) {
                                AppMark(app: app, size: 43).shadow(color: color.opacity(0.18), radius: 9)
                                Text(app.title).font(.system(size: 10, weight: .medium)).lineLimit(2).frame(height: 26)
                            }.frame(maxWidth: .infinity).contentShape(Rectangle())
                        }.buttonStyle(.plain).disabled(!store.connected).help("Open \(app.title) on TV")
                        if store.displayForegroundID == app.id { Text("ACTIVE").font(.system(size: 7, weight: .bold)).tracking(0.7).foregroundStyle(color) }
                        else { Color.clear.frame(height: 9) }
                    }.padding(10).background(RoundedRectangle(cornerRadius: 13).fill(LinearGradient(colors: [color.opacity(0.17), Color.white.opacity(0.035)], startPoint: .topLeading, endPoint: .bottomTrailing)))
                        .overlay(RoundedRectangle(cornerRadius: 13).strokeBorder(color.opacity(store.displayForegroundID == app.id ? 0.6 : 0.13)))
                }
            }
            Text("Click an app to open it on TV. Use the star to add favorites.").font(.system(size: 10)).foregroundStyle(mutedInk)
        }
    }
    private func active(_ input: TVInput) -> Bool { store.displayForegroundID == input.appID }
    private func inputRow(_ input: TVInput) -> some View {
        Button { store.input(input) } label: {
            HStack(spacing: 10) {
                ZStack {
                    RoundedRectangle(cornerRadius: 8).fill(input.label.localizedCaseInsensitiveContains("PS5") ? Color(red: 0.02, green: 0.17, blue: 0.44) : Color.white.opacity(0.055))
                    if input.label.localizedCaseInsensitiveContains("PS5") || input.label.localizedCaseInsensitiveContains("PlayStation") { BrandImage(name: "playstation", width: 24, height: 24) }
                    else if input.label.localizedCaseInsensitiveContains("Chromecast") { BrandImage(name: "googlecast", width: 22, height: 22) }
                    else { Image(systemName: "cable.connector").font(.system(size: 15)).foregroundStyle(mutedInk) }
                }.frame(width: 34, height: 34)
                VStack(alignment: .leading, spacing: 3) {
                    Text(input.label).font(.system(size: 12, weight: .semibold))
                    Text(input.id.replacingOccurrences(of: "_", with: " ") + " · " + (active(input) ? "Active" : input.connected ? "Connected" : "No device")).font(.system(size: 10)).foregroundStyle(mutedInk)
                }
                Spacer()
                if active(input) {
                    Text("ACTIVE").font(.system(size: 7, weight: .bold)).tracking(0.5).foregroundStyle(accent)
                    Image(systemName: "checkmark.circle.fill").font(.system(size: 12)).foregroundStyle(accent)
                } else { Image(systemName: "chevron.right").font(.system(size: 11)).foregroundStyle(mutedInk) }
            }.padding(.horizontal, 9).padding(.vertical, 7)
                .background(RoundedRectangle(cornerRadius: 10).fill(active(input) ? accent.opacity(0.13) : Color.clear))
                .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(active(input) ? accent.opacity(0.32) : Color.clear, lineWidth: 0.7))
                .contentShape(Rectangle())
        }.buttonStyle(.plain).disabled(!store.connected).help("Switch TV to \(input.label)")
            .accessibilityAddTraits(active(input) ? .isSelected : [])
    }
    private var inputsPanel: some View {
        VStack(spacing: 12) {
            PanelCard {
                VStack(spacing: 10) {
                    ForEach(store.orderedInputs) { input in inputRow(input) }
                    if store.inputs.isEmpty { Text("Inputs appear after connecting.").foregroundStyle(mutedInk).padding(.vertical, 15) }
                }
            }
            Text("Select an input to change what your TV displays.").font(.system(size: 10)).foregroundStyle(mutedInk)
        }
    }
    private var infoPanel: some View {
        VStack(alignment: .leading, spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 14).fill(accent.opacity(0.08))
                VStack(spacing: 8) {
                    Image(systemName: "sun.max").font(.system(size: 29, weight: .light)).foregroundStyle(accent)
                    Text("Your picture, your way").font(.system(size: 17, weight: .semibold)).tracking(-0.3)
                    Text("Adjust the values and apply when ready.").font(.system(size: 10)).foregroundStyle(mutedInk)
                }.padding(.vertical, 20)
            }
            PanelCard {
                VStack(spacing: 19) {
                    ForEach([("backlight", "Backlight", "sun.max"), ("brightness", "Brightness", "light.max"), ("contrast", "Contrast", "circle.lefthalf.filled"), ("color", "Color", "paintpalette")], id: \.0) { key, title, symbol in
                        if store.picture[key] != nil {
                            VStack(spacing: 9) {
                                HStack { Label(title, systemImage: symbol).foregroundStyle(Color.white.opacity(0.8)); Spacer(); Text("\(pictureDraft[key] ?? store.picture[key] ?? 0)").monospacedDigit().foregroundStyle(accent) }
                                Slider(value: Binding(get: { Double(pictureDraft[key] ?? store.picture[key] ?? 0) }, set: { pictureDraft[key] = Int($0) }), in: 0...100, step: 1).accessibilityLabel(title)
                            }
                        }
                    }
                    if store.picture.isEmpty { Text("Connect to your TV to read its settings.").foregroundStyle(mutedInk) }
                    HStack {
                        Button("Reset values") { pictureDraft = store.picture }.buttonStyle(.plain).foregroundStyle(mutedInk)
                        Spacer()
                        Button(store.pictureApplying ? "Applying…" : "Apply to TV") { store.applyPicture(pictureDraft) }
                            .disabled(!store.connected || store.picture.isEmpty || pictureDraft == store.picture || store.pictureApplying)
                    }.font(.system(size: 10))
                }
            }
            Text("Available settings depend on TV permissions. Values are read again after applying.").font(.system(size: 10)).foregroundStyle(mutedInk)
        }
    }
    private var usagePanel: some View {
        let totals = store.usage(days: usageDays)
        let total = totals.reduce(0) { $0 + $1.seconds }
        return VStack(alignment: .leading, spacing: 14) {
            Picker("Period", selection: $usageDays) { Text("Today").tag(1); Text("7 days").tag(7); Text("30 days").tag(30) }.pickerStyle(.segmented)
            VStack(alignment: .leading, spacing: 7) {
                Text("SCREEN TIME").font(.system(size: 8, weight: .bold)).tracking(1.2).foregroundStyle(mutedInk)
                Text(duration(total)).font(.system(size: 38, weight: .medium, design: .rounded)).tracking(-1).foregroundStyle(accent)
                Text("Apps and inputs observed by your Mac").font(.system(size: 10)).foregroundStyle(mutedInk)
            }.padding(18).frame(maxWidth: .infinity, alignment: .leading).background(RoundedRectangle(cornerRadius: 14).fill(accent.opacity(0.08)))
            PanelCard {
                VStack(spacing: 17) {
                    ForEach(totals) { item in
                        let color = BrandTheme.forApp(item.id, title: item.title).color
                        VStack(spacing: 8) {
                            HStack(spacing: 9) {
                                if let app = store.apps.first(where: { $0.id == item.id }) { AppMark(app: app, size: 26) }
                                else if item.title.localizedCaseInsensitiveContains("PS5") { BrandImage(name: "playstation", width: 26, height: 26) }
                                else { Image(systemName: "tv").foregroundStyle(color).frame(width: 26) }
                                Text(item.title).font(.system(size: 11, weight: .medium)).lineLimit(1)
                                Spacer(); Text(duration(item.seconds)).font(.system(size: 10)).foregroundStyle(mutedInk).monospacedDigit()
                            }
                            GeometryReader { geometry in
                                ZStack(alignment: .leading) { Capsule().fill(Color.white.opacity(0.04)); Capsule().fill(color).frame(width: geometry.size.width * CGFloat(item.seconds / max(total, 1))) }
                            }.frame(height: 4)
                        }
                    }
                    if totals.isEmpty { VStack(spacing: 9) { Image(systemName: "chart.bar.xaxis").font(.system(size: 26)).foregroundStyle(accent); Text("Your history starts here").fontWeight(.medium); Text("The first record appears after another TV reading.").font(.system(size: 10)).foregroundStyle(mutedInk) }.frame(maxWidth: .infinity).padding(.vertical, 25) }
                }
            }
            Text("Local history starts now. Tracks the reported app or input while your Mac is awake and connected; sleep and offline periods are excluded.").font(.system(size: 10)).foregroundStyle(mutedInk)
        }
    }
    private func duration(_ seconds: TimeInterval) -> String {
        let minutes = Int(seconds) / 60
        if minutes == 0 { return "\(Int(seconds)) s" }
        return minutes >= 60 ? "\(minutes / 60) h \(minutes % 60) min" : "\(minutes) min"
    }
    private var mediaPanel: some View {
        VStack(alignment: .leading, spacing: 14) {
            PanelCard {
                VStack(alignment: .leading, spacing: 14) {
                    HStack {
                        Image(systemName: "airplay.video").font(.system(size: 26, weight: .light)).foregroundStyle(accent)
                        VStack(alignment: .leading, spacing: 3) { Text("Your Mac, on the big screen").font(.system(size: 14, weight: .semibold)); Text("Screen mirroring with AirPlay").font(.system(size: 10)).foregroundStyle(mutedInk) }
                    }
                    Text("In Control Center on your Mac, open Screen Mirroring and choose “\(store.name)”. You can also use the TV as a second display in Displays settings.").font(.system(size: 11)).foregroundStyle(mutedInk).fixedSize(horizontal: false, vertical: true)
                    Button { NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.Displays-Settings.extension")!) } label: { Label("Open Displays settings", systemImage: "arrow.up.right") }.buttonStyle(.plain).foregroundStyle(accent)
                }
            }
            PanelCard {
                VStack(alignment: .leading, spacing: 14) {
                    Label("Send a file", systemImage: "play.tv").font(.system(size: 14, weight: .semibold))
                    if let file = store.mediaFile {
                        HStack(spacing: 10) {
                            Image(systemName: "doc.richtext").font(.system(size: 23)).foregroundStyle(accent)
                            VStack(alignment: .leading, spacing: 4) { Text(file.lastPathComponent).fontWeight(.medium).lineLimit(2); Text(file.pathExtension.uppercased()).font(.system(size: 9)).foregroundStyle(mutedInk) }
                        }.padding(12).frame(maxWidth: .infinity, alignment: .leading).background(RoundedRectangle(cornerRadius: 10).fill(accent.opacity(0.08)))
                    }
                    Text(store.mediaStatus).font(.system(size: 10)).foregroundStyle(mutedInk).fixedSize(horizontal: false, vertical: true)
                    HStack {
                        Button("Choose file") { store.chooseMedia() }.disabled(store.mediaBusy)
                        Spacer()
                        Button(store.mediaBusy ? "Sending…" : "Play on TV") { store.castMedia() }.disabled(!store.connected || store.mediaFile == nil || store.mediaBusy)
                    }.font(.system(size: 10))
                    if store.casting {
                        HStack(spacing: 8) {
                            ForEach([("play.fill", "Play", "Play"), ("pause.fill", "Pause", "Pause"), ("stop.fill", "Stop", "Stop casting")], id: \.1) { symbol, action, title in
                                Button { store.controlCast(action) } label: { Image(systemName: symbol).frame(maxWidth: .infinity).frame(height: 32) }.buttonStyle(PanelButton()).help(title).accessibilityLabel(title)
                            }
                        }.disabled(store.mediaBusy)
                    }
                }
            }
            Text("The file opens on TV when you click Play. Compatibility depends on the format and codec; try H.264 MP4, MP3, or JPEG first. Keep your Mac awake while casting.").font(.system(size: 10)).foregroundStyle(mutedInk)
        }
    }
    private func infoRow(_ title: String, _ value: String) -> some View {
        HStack { Text(title).foregroundStyle(mutedInk); Spacer(); Text(value).fontWeight(.medium).textSelection(.enabled) }.font(.system(size: 11))
    }
    private var logsPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("LGwebOS-menubar connections and actions saved on this Mac. Internal TV logs require developer mode.").font(.system(size: 11)).foregroundStyle(mutedInk)
            PanelCard {
                LazyVStack(alignment: .leading, spacing: 13) {
                    ForEach(store.events.filter { $0.title != "Read" }) { event in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack { Text(event.title).fontWeight(.semibold); Spacer(); Text(event.date, style: .time).foregroundStyle(mutedInk).monospacedDigit() }
                            Text(event.detail).font(.system(size: 10)).foregroundStyle(mutedInk).lineLimit(3).textSelection(.enabled)
                        }.font(.system(size: 11))
                    }
                    if store.events.isEmpty { Text("No events yet.").foregroundStyle(mutedInk).padding(.vertical, 12) }
                }
            }
        }
    }
    private var connectionPanel: some View {
        PanelCard {
            VStack(alignment: .leading, spacing: 10) {
                Label(store.status, systemImage: store.pairing ? "checkmark.shield" : "wifi").fontWeight(.semibold)
                Text(store.pairing ? "Accept “LG Remote App” on your TV." : "Your Mac and TV must be on the same network.").font(.system(size: 11)).foregroundStyle(mutedInk)
                Button(store.connecting ? "Cancel" : "Connect to TV") {
                    if store.connecting { store.disconnect() }
                    else if store.host.isEmpty { showConnectionSettings() }
                    else { store.connect() }
                }
            }
        }
    }
    private var settingsPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            PanelCard {
                HStack(spacing: 13) {
                    BrandImage(name: "lg", width: 38, height: 38)
                    VStack(alignment: .leading, spacing: 5) {
                        Text(store.model.isEmpty ? "LG TV" : "LG \(store.model)").font(.system(size: 14, weight: .semibold))
                        Text([store.webOS, store.firmware].filter { !$0.isEmpty }.joined(separator: " · ")).font(.system(size: 10)).foregroundStyle(mutedInk)
                    }
                    Spacer()
                }
            }
            sectionTitle("CONNECTION")
            PanelCard {
                VStack(alignment: .leading, spacing: 11) {
                    Text("Your TV").fontWeight(.semibold)
                    TextField("Name", text: $draftName).textFieldStyle(.roundedBorder)
                    TextField("TV IP address", text: $draftHost).textFieldStyle(.roundedBorder)
                    TextField("Wi-Fi MAC address for wake", text: $draftMAC).textFieldStyle(.roundedBorder)
                    Text("Optional: the MAC address is only needed to wake the TV.").font(.system(size: 10)).foregroundStyle(mutedInk)
                    Button("Save and connect") {
                        store.disconnect(); store.model = ""; store.firmware = ""; store.webOS = ""
                        store.host = draftHost.trimmingCharacters(in: .whitespacesAndNewlines)
                        store.name = draftName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "LG TV" : draftName.trimmingCharacters(in: .whitespacesAndNewlines)
                        store.mac = draftMAC.trimmingCharacters(in: .whitespacesAndNewlines); store.connect(); settings = false
                    }.disabled(!WebOSConnection.localHost(draftHost.trimmingCharacters(in: .whitespacesAndNewlines)) || store.connecting)
                    if !store.host.isEmpty {
                        Button("Forget pairing") { store.forgetPairing() }.disabled(store.connecting)
                    }
                }
            }
            PanelCard {
                VStack(alignment: .leading, spacing: 11) {
                    Button(store.discovering ? "Searching for TVs…" : "Find TVs on your network") { store.discover() }.disabled(store.discovering)
                    ForEach(store.devices) { device in
                        Button { store.select(device); settings = false } label: { HStack { Text(device.name); Spacer(); Text(device.host).foregroundStyle(mutedInk) } }.buttonStyle(.plain)
                    }
                    Text("To wake your TV from your Mac, enable Wi-Fi wake in TV settings.").font(.system(size: 11)).foregroundStyle(mutedInk)
                }
            }
            DisclosureGroup("Event history", isExpanded: $showEvents) { logsPanel.padding(.top, 10) }.font(.system(size: 11))
        }
    }
    private func showConnectionSettings() {
        draftHost = store.host; draftName = store.name; draftMAC = store.mac
        settings = true
    }
    private var footer: some View {
        HStack(spacing: 6) {
            Circle().fill(store.connected ? .green : store.connecting ? .orange : mutedInk).frame(width: 5, height: 5)
            Text(store.status).font(.system(size: 10)).foregroundStyle(mutedInk)
            Spacer()
            Text("\(store.model)").font(.system(size: 8, weight: .semibold)).tracking(1).foregroundStyle(Color.white.opacity(0.27))
            Button {
                if !settings { draftHost = store.host; draftName = store.name; draftMAC = store.mac }
                settings.toggle()
            } label: { Image(systemName: settings ? "xmark" : "slider.horizontal.3").font(.system(size: 12)).foregroundStyle(mutedInk).frame(width: 24, height: 22) }.buttonStyle(.plain).help("App settings")
        }
    }
}

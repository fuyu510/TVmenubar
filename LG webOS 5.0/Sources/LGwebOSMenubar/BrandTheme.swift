import SwiftUI
import AppKit

struct BrandTheme {
    let color: Color
    let label: String
    let tagline: String
    private static let logoColors: [String: Color] = {
        guard let url = AppResources.bundle.url(forResource: "app-catalog", withExtension: "json"),
              let data = try? Data(contentsOf: url), let apps = try? JSONDecoder().decode([TVApp].self, from: data) else { return [:] }
        var result: [String: Color] = [:]
        for app in apps {
            guard let icon = app.icon, let file = AppResources.bundle.url(forResource: icon, withExtension: nil, subdirectory: "AppAssets"),
                  let imageData = try? Data(contentsOf: file), let bitmap = NSBitmapImageRep(data: imageData) else { continue }
            var buckets: [Int: (count: Int, r: CGFloat, g: CGFloat, b: CGFloat)] = [:]
            for x in stride(from: 0, to: bitmap.pixelsWide, by: max(1, bitmap.pixelsWide / 24)) {
                for y in stride(from: 0, to: bitmap.pixelsHigh, by: max(1, bitmap.pixelsHigh / 24)) {
                    guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB), color.alphaComponent > 0.6,
                          color.saturationComponent > 0.25, color.brightnessComponent > 0.25 else { continue }
                    let bucket = Int(color.hueComponent * 20)
                    let previous = buckets[bucket] ?? (0, 0, 0, 0)
                    buckets[bucket] = (previous.count + 1, previous.r + color.redComponent, previous.g + color.greenComponent, previous.b + color.blueComponent)
                }
            }
            if let best = buckets.values.max(by: { $0.count < $1.count }) {
                let n = CGFloat(best.count)
                result[app.id] = Color(red: Double(best.r / n), green: Double(best.g / n), blue: Double(best.b / n))
            } else { result[app.id] = Color(white: 0.78) }
        }
        return result
    }()
    static func forApp(_ id: String, title: String = "") -> BrandTheme {
        let key = (id + " " + title).lowercased()
        if key.contains("ps5") || key.contains("playstation") { return .init(color: Color(red: 0.12, green: 0.43, blue: 1), label: "PlayStation 5", tagline: "Your next adventure starts here.") }
        if key.contains("netflix") { return .init(color: Color(red: 0.94, green: 0.08, blue: 0.13), label: "Netflix", tagline: "A great story is waiting for you.") }
        if key.contains("youtube") { return .init(color: Color(red: 1, green: 0.18, blue: 0.23), label: "YouTube", tagline: "Everything you love, on the big screen.") }
        if key.contains("amazon") || key.contains("prime") { return .init(color: Color(red: 0.08, green: 0.64, blue: 1), label: "Prime Video", tagline: "Time for popcorn.") }
        if key.contains("disney") { return .init(color: Color(red: 0.20, green: 0.38, blue: 1), label: "Disney+", tagline: "A universe of stories.") }
        if key.contains("spotify") { return .init(color: Color(red: 0.12, green: 0.84, blue: 0.43), label: "Spotify", tagline: "Set the mood. Press play.") }
        if key.contains("twitch") { return .init(color: Color(red: 0.61, green: 0.35, blue: 1), label: "Twitch", tagline: "Your community, live.") }
        if key.contains("hbo") || key.contains("max") { return .init(color: Color(red: 0.60, green: 0.34, blue: 1), label: title.isEmpty ? "Max" : title, tagline: "Great stories. Unforgettable moments.") }
        if key.contains("globo") { return .init(color: Color(red: 1, green: 0.33, blue: 0.23), label: title, tagline: "Your entertainment, your way.") }
        if key.contains("apple") { return .init(color: Color(white: 0.9), label: title, tagline: "Cinema in your living room.") }
        if key.contains("chromecast") { return .init(color: Color(red: 0.28, green: 0.66, blue: 0.93), label: "Chromecast", tagline: "From your device to your TV.") }
        return .init(color: logoColors[id] ?? Color(red: 0.91, green: 0.17, blue: 0.35), label: title, tagline: "Your LG. Your room. Your remote.")
    }
}

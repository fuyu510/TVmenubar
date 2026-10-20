// swift-tools-version: 5.9
import PackageDescription
let package = Package(
    name: "LGwebOSMenubar",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "LGwebOSMenubar", targets: ["LGwebOSMenubar"])],
    targets: [
        .executableTarget(
            name: "LGwebOSMenubar",
            resources: [.copy("registration.json"), .copy("AppAssets"), .copy("app-catalog.json")]
        )
    ]
)

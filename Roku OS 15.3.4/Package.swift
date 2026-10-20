// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "RokuMenubar",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "RokuMenubar", targets: ["RokuMenubar"])],
    targets: [.executableTarget(name: "RokuMenubar", resources: [.process("Assets")])]
)

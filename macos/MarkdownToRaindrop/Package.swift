// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "MarkdownToRaindrop",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "MarkdownToRaindrop", targets: ["MarkdownToRaindrop"]),
        .library(name: "RaindropKit", targets: ["RaindropKit"]),
    ],
    targets: [
        .target(name: "RaindropKit"),
        .executableTarget(name: "MarkdownToRaindrop", dependencies: ["RaindropKit"]),
        .testTarget(name: "RaindropKitTests", dependencies: ["RaindropKit"]),
    ]
)

// swift-tools-version:5.10
import PackageDescription

let package = Package(
    name: "WebClipper",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(name: "WebClipper", path: "Sources/WebClipper"),
    ]
)

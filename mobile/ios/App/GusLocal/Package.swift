// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "GusLocal",
    platforms: [.iOS(.v15), .macOS(.v13)],
    products: [.library(name: "GusLocal", targets: ["GusLocalPlugin"])],
    dependencies: [
        .package(url: "https://github.com/ionic-team/capacitor-swift-pm.git", exact: "8.5.2")
    ],
    targets: [
        .target(name: "GUSBridge", exclude: ["GUSLlamaBridge.c"], path: "Sources/GUSBridge", publicHeadersPath: "include"),
        .target(name: "GusModelStore", path: "Sources/GusModelStore"),
        .target(
            name: "GusLocalPlugin",
            dependencies: [
                "GUSBridge", "GusModelStore",
                .product(name: "Capacitor", package: "capacitor-swift-pm")
            ],
            path: "Sources/GusLocalPlugin"
        ),
        .testTarget(name: "GusModelStoreTests", dependencies: ["GusModelStore"], path: "Tests/GusModelStoreTests")
    ]
)

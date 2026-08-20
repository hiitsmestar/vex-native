// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "LlamaKit",
    platforms: [
        .iOS(.v17),
        .macOS(.v14)
    ],
    products: [
        .library(name: "LlamaKit", targets: ["LlamaKit"])
    ],
    targets: [
        .target(
            name: "LlamaKit",
            dependencies: ["LlamaFramework"]
        ),
        .binaryTarget(
            name: "LlamaFramework",
            url: "https://github.com/ggml-org/llama.cpp/releases/download/b5092/llama-b5092-xcframework.zip",
            checksum: "6534cb7c81c50cfa7754bccb8682f550e38e8f10ce1e38efa1d73a65dadf7878"
        )
    ]
)

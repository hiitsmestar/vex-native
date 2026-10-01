import SwiftUI
import UIKit

struct ChatBubble: View {
    let message: ChatMessage
    @State private var isShowingImageViewer = false

    var body: some View {
        HStack {
            if message.role == .user { Spacer(minLength: 42) }

            VStack(alignment: .leading, spacing: 5) {
                Text(message.role == .user ? "STAR" : "VEX")
                    .font(.caption2.weight(.black))
                    .tracking(1.2)
                    .foregroundStyle(VexTheme.muted)

                if let attachedImage {
                    Button {
                        isShowingImageViewer = true
                    } label: {
                        ZStack(alignment: .bottomTrailing) {
                            Image(uiImage: attachedImage)
                                .resizable()
                                .scaledToFit()
                                .frame(maxHeight: 300)
                                .clipShape(RoundedRectangle(cornerRadius: 12))

                            Image(systemName: "arrow.up.left.and.arrow.down.right")
                                .font(.caption.bold())
                                .foregroundStyle(.white)
                                .padding(8)
                                .background(.black.opacity(0.68))
                                .clipShape(Circle())
                                .padding(8)
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Open image full screen")
                    .fullScreenCover(isPresented: $isShowingImageViewer) {
                        FullScreenChatImageViewer(image: attachedImage)
                    }
                }

                if !message.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text(renderedContent)
                        .font(.body)
                        .textSelection(.enabled)
                        .foregroundStyle(.white)
                        .tint(VexTheme.hotPink)
                }
            }
            .padding(13)
            .background(
                message.role == .user
                    ? VexTheme.panel2
                    : VexTheme.panel
            )
            .clipShape(
                UnevenRoundedRectangle(
                    topLeadingRadius: 18,
                    bottomLeadingRadius: message.role == .assistant ? 5 : 18,
                    bottomTrailingRadius: message.role == .user ? 5 : 18,
                    topTrailingRadius: 18
                )
            )
            .overlay {
                UnevenRoundedRectangle(
                    topLeadingRadius: 18,
                    bottomLeadingRadius: message.role == .assistant ? 5 : 18,
                    bottomTrailingRadius: message.role == .user ? 5 : 18,
                    topTrailingRadius: 18
                )
                .stroke(Color.white.opacity(0.08))
            }

            if message.role == .assistant { Spacer(minLength: 42) }
        }
    }

    private var attachedImage: UIImage? {
        guard let filename = message.imageFilename,
              let data = LocalStore.shared.attachmentData(named: filename)
        else { return nil }
        return UIImage(data: data)
    }

    private var renderedContent: AttributedString {
        guard message.role == .assistant else { return AttributedString(message.content) }
        let options = AttributedString.MarkdownParsingOptions(
            interpretedSyntax: .inlineOnlyPreservingWhitespace
        )
        return (try? AttributedString(markdown: message.content, options: options))
            ?? AttributedString(message.content)
    }
}


private struct FullScreenChatImageViewer: View {
    let image: UIImage
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            ZoomableChatImage(image: image)
                .ignoresSafeArea()

            VStack {
                HStack {
                    Spacer()
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark")
                            .font(.headline.bold())
                            .foregroundStyle(.white)
                            .frame(width: 44, height: 44)
                            .background(.black.opacity(0.68))
                            .clipShape(Circle())
                    }
                    .buttonStyle(.plain)
                    .padding(.trailing, 14)
                    .padding(.top, 8)
                }

                Spacer()

                Text("Pinch to zoom • drag to move • double-tap to zoom")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white.opacity(0.92))
                    .padding(.horizontal, 14)
                    .padding(.vertical, 9)
                    .background(.black.opacity(0.68))
                    .clipShape(Capsule())
                    .padding(.bottom, 22)
            }
        }
    }
}

private struct ZoomableChatImage: UIViewRepresentable {
    let image: UIImage

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    func makeUIView(context: Context) -> UIScrollView {
        let scrollView = UIScrollView()
        scrollView.delegate = context.coordinator
        scrollView.minimumZoomScale = 1.0
        scrollView.maximumZoomScale = 8.0
        scrollView.bouncesZoom = true
        scrollView.alwaysBounceVertical = false
        scrollView.alwaysBounceHorizontal = false
        scrollView.showsVerticalScrollIndicator = false
        scrollView.showsHorizontalScrollIndicator = false
        scrollView.backgroundColor = .black

        let imageView = UIImageView(image: image)
        imageView.tag = 711
        imageView.contentMode = .scaleAspectFit
        imageView.isUserInteractionEnabled = true
        imageView.translatesAutoresizingMaskIntoConstraints = false
        scrollView.addSubview(imageView)

        NSLayoutConstraint.activate([
            imageView.leadingAnchor.constraint(equalTo: scrollView.contentLayoutGuide.leadingAnchor),
            imageView.trailingAnchor.constraint(equalTo: scrollView.contentLayoutGuide.trailingAnchor),
            imageView.topAnchor.constraint(equalTo: scrollView.contentLayoutGuide.topAnchor),
            imageView.bottomAnchor.constraint(equalTo: scrollView.contentLayoutGuide.bottomAnchor),
            imageView.widthAnchor.constraint(equalTo: scrollView.frameLayoutGuide.widthAnchor),
            imageView.heightAnchor.constraint(equalTo: scrollView.frameLayoutGuide.heightAnchor),
        ])

        let doubleTap = UITapGestureRecognizer(
            target: context.coordinator,
            action: #selector(Coordinator.handleDoubleTap(_:))
        )
        doubleTap.numberOfTapsRequired = 2
        scrollView.addGestureRecognizer(doubleTap)
        context.coordinator.scrollView = scrollView
        return scrollView
    }

    func updateUIView(_ scrollView: UIScrollView, context: Context) {
        guard let imageView = scrollView.viewWithTag(711) as? UIImageView else { return }
        if imageView.image !== image {
            imageView.image = image
            scrollView.setZoomScale(1.0, animated: false)
        }
    }

    final class Coordinator: NSObject, UIScrollViewDelegate {
        weak var scrollView: UIScrollView?

        func viewForZooming(in scrollView: UIScrollView) -> UIView? {
            scrollView.viewWithTag(711)
        }

        @objc func handleDoubleTap(_ recognizer: UITapGestureRecognizer) {
            guard let scrollView else { return }
            if scrollView.zoomScale > 1.05 {
                scrollView.setZoomScale(1.0, animated: true)
                return
            }

            let point = recognizer.location(in: scrollView.viewWithTag(711))
            let targetScale = min(3.0, scrollView.maximumZoomScale)
            let width = scrollView.bounds.width / targetScale
            let height = scrollView.bounds.height / targetScale
            let zoomRect = CGRect(
                x: point.x - width / 2,
                y: point.y - height / 2,
                width: width,
                height: height
            )
            scrollView.zoom(to: zoomRect, animated: true)
        }
    }
}
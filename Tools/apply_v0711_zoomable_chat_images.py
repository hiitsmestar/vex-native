#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/Views/ChatBubble.swift")
text = path.read_text(encoding="utf-8")

if "import UIKit" not in text:
    raise SystemExit("v0.7.11: expected UIKit import from v0.7.8")

old_struct = '''struct ChatBubble: View {\n    let message: ChatMessage\n'''
new_struct = '''struct ChatBubble: View {\n    let message: ChatMessage\n    @State private var isShowingImageViewer = false\n'''
if old_struct not in text:
    raise SystemExit("v0.7.11: ChatBubble header not found")
text = text.replace(old_struct, new_struct, 1)

old_image = '''                if let attachedImage {\n                    Image(uiImage: attachedImage)\n                        .resizable()\n                        .scaledToFit()\n                        .frame(maxHeight: 260)\n                        .clipShape(RoundedRectangle(cornerRadius: 12))\n                }\n'''
new_image = '''                if let attachedImage {\n                    Button {\n                        isShowingImageViewer = true\n                    } label: {\n                        ZStack(alignment: .bottomTrailing) {\n                            Image(uiImage: attachedImage)\n                                .resizable()\n                                .scaledToFit()\n                                .frame(maxHeight: 300)\n                                .clipShape(RoundedRectangle(cornerRadius: 12))\n\n                            Image(systemName: "arrow.up.left.and.arrow.down.right")\n                                .font(.caption.bold())\n                                .foregroundStyle(.white)\n                                .padding(8)\n                                .background(.black.opacity(0.68))\n                                .clipShape(Circle())\n                                .padding(8)\n                        }\n                    }\n                    .buttonStyle(.plain)\n                    .accessibilityLabel("Open image full screen")\n                    .fullScreenCover(isPresented: $isShowingImageViewer) {\n                        FullScreenChatImageViewer(image: attachedImage)\n                    }\n                }\n'''
if old_image not in text:
    raise SystemExit("v0.7.11: attached image render block not found")
text = text.replace(old_image, new_image, 1)

viewer = r'''

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
'''

if "private struct FullScreenChatImageViewer" in text:
    raise SystemExit("v0.7.11: viewer already present")
text += viewer

for marker in [
    "isShowingImageViewer",
    "FullScreenChatImageViewer",
    "maximumZoomScale = 8.0",
    "double-tap to zoom",
    "arrow.up.left.and.arrow.down.right",
]:
    if marker not in text:
        raise SystemExit(f"v0.7.11: missing marker {marker}")

path.write_text(text, encoding="utf-8")
print("Applied v0.7.11 full-screen zoomable chat image viewer")

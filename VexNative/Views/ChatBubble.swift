import SwiftUI

struct ChatBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.role == .user { Spacer(minLength: 42) }

            VStack(alignment: .leading, spacing: 5) {
                Text(message.role == .user ? "STAR" : "VEX")
                    .font(.caption2.weight(.black))
                    .tracking(1.2)
                    .foregroundStyle(VexTheme.muted)

                Text(message.content)
                    .font(.body)
                    .textSelection(.enabled)
                    .foregroundStyle(.white)
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
}

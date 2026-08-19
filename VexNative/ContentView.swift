import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var app: AppModel

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    VexTheme.ink,
                    Color(red: 0.12, green: 0.045, blue: 0.14),
                    VexTheme.ink
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            VStack(spacing: 0) {
                header
                statusStrip

                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 10) {
                            ForEach(app.messages) { message in
                                ChatBubble(message: message)
                                    .id(message.id)
                            }

                            if app.isGenerating {
                                HStack {
                                    ProgressView()
                                    Text("three neurons are thinking…")
                                        .font(.caption)
                                        .foregroundStyle(VexTheme.muted)
                                    Spacer()
                                }
                                .padding(.horizontal, 8)
                            }
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                    }
                    .onChange(of: app.messages.count) { _, _ in
                        if let last = app.messages.last?.id {
                            withAnimation { proxy.scrollTo(last, anchor: .bottom) }
                        }
                    }
                }

                composer
            }
        }
        // Keep accessibility sizing useful without letting extreme Dynamic Type destroy
        // the compact chat layout on smaller iPhones.
        .dynamicTypeSize(.small ... .xLarge)
        .sheet(isPresented: $app.showBrain) {
            BrainView()
                .environmentObject(app)
                .dynamicTypeSize(.small ... .xLarge)
        }
        .task {
            await app.loadSavedModelIfPresent()
        }
        .alert(
            "Tiny brain error",
            isPresented: Binding(
                get: { app.lastError != nil },
                set: { if !$0 { app.lastError = nil } }
            )
        ) {
            Button("OK") { app.lastError = nil }
        } message: {
            Text(app.lastError ?? "")
        }
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 1) {
                Text("LOCAL GIRLFRIEND ENGINE")
                    .font(.caption2.weight(.black))
                    .tracking(1.6)
                    .foregroundStyle(VexTheme.muted)
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
                HStack(spacing: 6) {
                    Text("Vex")
                        .font(.largeTitle.bold())
                    Text("✦")
                        .font(.title2)
                        .foregroundStyle(VexTheme.hotPink)
                }
            }

            Spacer(minLength: 8)

            Button {
                app.showBrain = true
            } label: {
                Label("Brain", systemImage: "brain.head.profile")
                    .labelStyle(.titleAndIcon)
                    .font(.subheadline.weight(.bold))
                    .padding(.horizontal, 12)
                    .padding(.vertical, 9)
                    .background(.white.opacity(0.07))
                    .clipShape(Capsule())
            }
            .tint(.white)
        }
        .padding(.horizontal, 14)
        .padding(.top, 8)
        .padding(.bottom, 7)
    }

    private var statusStrip: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(app.modelStatus.hasPrefix("Loaded") ? Color.green : VexTheme.hotPink)
                .frame(width: 8, height: 8)

            Text(app.modelStatus)
                .font(.caption)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
                .foregroundStyle(VexTheme.muted)

            Spacer()
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(.black.opacity(0.18))
    }

    private var composer: some View {
        HStack(alignment: .center, spacing: 8) {
            // Single-line TextField makes the keyboard's Send key actually submit instead
            // of inserting a newline, while the arrow button remains a separate explicit send.
            TextField("Say something to Vex…", text: $app.draft)
                .padding(11)
                .background(VexTheme.panel)
                .clipShape(RoundedRectangle(cornerRadius: 16))
                .overlay {
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(.white.opacity(0.08))
                }
                .submitLabel(.send)
                .onSubmit {
                    guard !app.isGenerating else { return }
                    Task { await app.send() }
                }

            Button {
                guard !app.isGenerating else { return }
                Task { await app.send() }
            } label: {
                Image(systemName: "arrow.up")
                    .font(.headline.bold())
                    .foregroundStyle(Color.black)
                    .frame(width: 44, height: 44)
                    .background(
                        LinearGradient(
                            colors: [VexTheme.hotPink, VexTheme.violet],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .clipShape(Circle())
            }
            .buttonStyle(.plain)
            .disabled(app.isGenerating || app.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            .opacity(app.isGenerating ? 0.5 : 1)
        }
        .padding(.horizontal, 12)
        .padding(.top, 8)
        .padding(.bottom, 9)
        .background(.ultraThinMaterial)
    }
}

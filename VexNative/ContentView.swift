import Foundation
import SwiftUI
import Speech
import AVFoundation
import PhotosUI
import Vision
import UIKit

struct VexChatView: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var web = WebBrain.shared
    @StateObject private var core = VexNativeA2AClient.shared
    @StateObject private var ap71 = AP71Controller.shared
    @StateObject private var voice = VoiceConversationController()
    @State private var showVoiceSettings = false
    @State private var selectedPhotoItem: PhotosPickerItem?
    @State private var selectedPhotoData: Data?
    @State private var isAnalyzingPhoto = false
    @State private var isShowingCamera = false

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
                                if voice.replyMode != .voiceOnly || message.role != .assistant {
                                    ChatBubble(message: message)
                                        .id(message.id)
                                }
                            }

                            if app.isGenerating || web.isWorking {
                                HStack {
                                    ProgressView()
                                    Text(web.isWorking ? "web brain is lookingâ€¦" : (app.pcBrainConnected ? "PC brain is thinkingâ€¦" : "Vex is thinkingâ€¦"))
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
        .dynamicTypeSize(.small ... .xLarge)
        .sheet(isPresented: $app.showBrain) {
            BrainView()
                .environmentObject(app)
                .dynamicTypeSize(.small ... .xLarge)
        }
        .task {
            await core.refresh()
            // v0.9.4.1 startup-safe mode: onboard GGUF is manual-only.
            voice.onCommand = { command in
                guard !app.isGenerating, !web.isWorking else { return }
                app.draft = command
                Task { await app.sendWithWeb() }
            }
        }
        .onChange(of: app.messages.count) { oldCount, newCount in
            guard newCount > oldCount, voice.isHandsFree,
                  let last = app.messages.last, last.role == .assistant
            else { return }
            voice.speak(last.content)
        }
        .onDisappear { voice.stopHandsFree() }
        .sheet(isPresented: $showVoiceSettings) {
            VexVoiceSettingsView(voice: voice)
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
                Text("VEXNATIVE // CHAT")
                    .font(.caption2.weight(.black))
                    .tracking(1.6)
                    .foregroundStyle(VexTheme.muted)
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
                HStack(spacing: 6) {
                    Text("Vex")
                        .font(.largeTitle.bold())
                    Text("âœ¦")
                        .font(.title2)
                        .foregroundStyle(VexTheme.hotPink)
                }
            }

            Spacer(minLength: 8)

            Menu {
                Text("AP71 • \(ap71.deviceState)")
                Button("Connect AP71") { ap71.connect() }
                Button("Low") { ap71.setIntensity(2) }
                Button("Medium") { ap71.setIntensity(5) }
                Button("High") { ap71.setIntensity(9) }
                Button("STOP", role: .destructive) { ap71.stop() }
            } label: {
                Image(systemName: ap71.deviceState == "Connected" ? "wave.3.right.circle.fill" : "wave.3.right.circle")
                    .font(.title3)
                    .foregroundStyle(ap71.deviceState == "Connected" ? Color.green : VexTheme.hotPink)
                    .frame(width: 40, height: 40)
                    .background(.white.opacity(0.07))
                    .clipShape(Circle())
            }
            .accessibilityLabel("AP71 control")

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
                .fill(core.online ? Color.green : (app.modelStatus.hasPrefix("Loaded") ? Color.green : VexTheme.hotPink))
                .frame(width: 8, height: 8)

            Text(core.online
                 ? "VexNative â€¢ \(core.activeNode) â€¢ \(core.brainMode) â€¢ \(core.activeModel)"
                 : "Offline core â€¢ \(app.modelStatus)")
                .font(.caption)
                .lineLimit(1)
                .minimumScaleFactor(0.62)
                .foregroundStyle(VexTheme.muted)

            Text("â€¢ v" + (Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "?"))
                .font(.caption2)
                .foregroundStyle(VexTheme.muted)
                .lineLimit(1)

            if web.isWorking {
                Text("â€¢ ðŸŒ")
                    .font(.caption)
            }

            if app.pcBrainConnected {
                Text("â€¢ ðŸ§  PC")
                    .font(.caption)
                    .foregroundStyle(VexTheme.muted)
            }

            if voice.isHandsFree {
                VStack(alignment: .leading, spacing: 1) {
                    Text(voice.isListening ? "â€¢ ðŸŽ™ï¸ listening" : "â€¢ ðŸ”Š voice")
                        .font(.caption)
                        .foregroundStyle(voice.isListening ? Color.green : VexTheme.muted)
                    Text(voice.voiceHint)
                        .font(.caption2)
                        .foregroundStyle(VexTheme.muted)
                        .lineLimit(1)
                        .truncationMode(.tail)
                }
            }

            Spacer()
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(.black.opacity(0.18))
    }

    private var composer: some View {
        VStack(spacing: 7) {
            if let selectedPhotoData, let image = UIImage(data: selectedPhotoData) {
                HStack(spacing: 10) {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFill()
                        .frame(width: 58, height: 58)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                        .clipped()

                    VStack(alignment: .leading, spacing: 2) {
                        Text(isAnalyzingPhoto ? "Looking at photoâ€¦" : "Photo attached")
                            .font(.caption.weight(.bold))
                        Text(isAnalyzingPhoto ? "reading text + visual clues locally" : "Vex gets local photo context with your message")
                            .font(.caption2)
                            .foregroundStyle(VexTheme.muted)
                    }

                    Spacer()
                    Button {
                        clearPendingPhoto()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.title3)
                            .foregroundStyle(VexTheme.muted)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 4)
            }

            HStack(alignment: .center, spacing: 8) {
                Menu {
                    Button {
                        guard UIImagePickerController.isSourceTypeAvailable(.camera) else {
                            app.lastError = "This device doesn't have an available camera."
                            return
                        }
                        isShowingCamera = true
                    } label: {
                        Label("Take Photo", systemImage: "camera")
                    }

                    PhotosPicker(selection: $selectedPhotoItem, matching: .images) {
                        Label("Choose from Library", systemImage: "photo.on.rectangle")
                    }
                } label: {
                    Image(systemName: "photo")
                        .font(.headline)
                        .foregroundStyle(VexTheme.hotPink)
                        .frame(width: 40, height: 44)
                        .background(VexTheme.panel)
                        .clipShape(RoundedRectangle(cornerRadius: 13))
                }
                .buttonStyle(.plain)
                .disabled(app.isGenerating || web.isWorking || isAnalyzingPhoto)
                .onChange(of: selectedPhotoItem) { _, item in
                    Task { await loadPhoto(item) }
                }
                .sheet(isPresented: $isShowingCamera) {
                    CameraCaptureView { data in
                        Task { await loadPhotoData(data) }
                    }
                    .ignoresSafeArea()
                }

                Button {
                Task {
                    do { try await voice.toggleHandsFree() }
                    catch { app.lastError = error.localizedDescription }
                }
            } label: {
                Image(systemName: voice.isHandsFree ? "waveform.circle.fill" : "mic.fill")
                    .font(.headline)
                    .foregroundStyle(voice.isHandsFree ? Color.green : VexTheme.hotPink)
                    .frame(width: 40, height: 44)
                    .background(VexTheme.panel)
                    .clipShape(RoundedRectangle(cornerRadius: 13))
            }
            .buttonStyle(.plain)
            .accessibilityLabel(voice.isHandsFree ? "Turn off hands-free voice" : "Turn on hands-free voice")

            Menu {
                ForEach(VoiceConversationController.ReplyMode.allCases) { mode in
                    Button {
                        voice.setReplyMode(mode)
                    } label: {
                        Label(mode.title, systemImage: mode.symbol)
                    }
                }
                Divider()
                Button {
                    showVoiceSettings = true
                } label: {
                    Label("Tune Vex voiceâ€¦", systemImage: "slider.horizontal.3")
                }
            } label: {
                Image(systemName: voice.replyMode.symbol)
                    .font(.headline)
                    .foregroundStyle(VexTheme.hotPink)
                    .frame(width: 38, height: 44)
                    .background(VexTheme.panel)
                    .clipShape(RoundedRectangle(cornerRadius: 13))
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Vex reply mode: " + voice.replyMode.title)

            TextField("Say something to Vexâ€¦", text: $app.draft)
                    .padding(11)
                    .background(VexTheme.panel)
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                    .overlay {
                        RoundedRectangle(cornerRadius: 16)
                            .stroke(.white.opacity(0.08))
                    }
                    .submitLabel(.send)
                    .disabled(web.isWorking || isAnalyzingPhoto)
                    .onSubmit { sendCurrentMessage() }

                Button {
                    sendCurrentMessage()
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
                .disabled(
                    app.isGenerating || web.isWorking || isAnalyzingPhoto ||
                    (app.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && app.pendingPhotoData == nil)
                )
                .opacity((app.isGenerating || web.isWorking || isAnalyzingPhoto) ? 0.5 : 1)
            }
        }
        .padding(.horizontal, 12)
        .padding(.top, 8)
        .padding(.bottom, 9)
        .background(.ultraThinMaterial)
    }

    private func sendCurrentMessage() {
        guard !app.isGenerating, !web.isWorking, !isAnalyzingPhoto else { return }
        guard !app.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || app.pendingPhotoData != nil else { return }
        Task {
            await app.sendWithWeb()
            await MainActor.run {
                selectedPhotoData = nil
                selectedPhotoItem = nil
            }
        }
    }

    private func clearPendingPhoto() {
        selectedPhotoData = nil
        selectedPhotoItem = nil
        app.pendingPhotoData = nil
        app.pendingPhotoContext = nil
        isAnalyzingPhoto = false
    }

    private func loadPhoto(_ item: PhotosPickerItem?) async {
        guard let item else { return }
        do {
            guard let data = try await item.loadTransferable(type: Data.self) else {
                clearPendingPhoto()
                return
            }
            await loadPhotoData(data)
        } catch {
            clearPendingPhoto()
            app.lastError = "I couldn't read that photo ðŸ˜­ðŸ–¤ \(error.localizedDescription)"
        }
    }

    private func loadPhotoData(_ data: Data) async {
        isAnalyzingPhoto = true
        defer { isAnalyzingPhoto = false }
        let context = await PhotoContextAnalyzer.analyze(data)
        selectedPhotoData = data
        app.pendingPhotoData = data
        app.pendingPhotoContext = context
    }

}


private struct CameraCaptureView: UIViewControllerRepresentable {
    let onCapture: (Data) -> Void
    @Environment(\.dismiss) private var dismiss

    func makeCoordinator() -> Coordinator {
        Coordinator(parent: self)
    }

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.cameraCaptureMode = .photo
        picker.allowsEditing = false
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    final class Coordinator: NSObject, UINavigationControllerDelegate, UIImagePickerControllerDelegate {
        let parent: CameraCaptureView

        init(parent: CameraCaptureView) {
            self.parent = parent
        }

        func imagePickerController(
            _ picker: UIImagePickerController,
            didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]
        ) {
            defer { parent.dismiss() }
            guard let image = info[.originalImage] as? UIImage,
                  let data = image.jpegData(compressionQuality: 0.90)
            else { return }
            parent.onCapture(data)
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            parent.dismiss()
        }
    }
}

private enum PhotoContextAnalyzer {
    static func analyze(_ data: Data) async -> String {
        await Task.detached(priority: .userInitiated) {
            let textRequest = VNRecognizeTextRequest()
            textRequest.recognitionLevel = .accurate
            textRequest.usesLanguageCorrection = true

            let classifyRequest = VNClassifyImageRequest()
            let handler = VNImageRequestHandler(data: data, options: [:])
            try? handler.perform([textRequest, classifyRequest])

            let recognizedText = (textRequest.results ?? [])
                .compactMap { $0.topCandidates(1).first?.string }
                .joined(separator: " | ")

            var seen = Set<String>()
            let labels = (classifyRequest.results ?? [])
                .filter { $0.confidence >= 0.08 }
                .compactMap { observation -> String? in
                    let label = observation.identifier.trimmingCharacters(in: .whitespacesAndNewlines)
                    let key = label.lowercased()
                    guard !label.isEmpty, seen.insert(key).inserted else { return nil }
                    return label
                }
                .prefix(6)
                .map { $0 }

            var parts: [String] = []
            if !recognizedText.isEmpty {
                parts.append("PHOTO TEXT: \(String(recognizedText.prefix(1400)))")
            }
            if !labels.isEmpty {
                parts.append("PHOTO LABELS: \(labels.joined(separator: ", "))")
            }
            if parts.isEmpty {
                return "A photo is attached, but local Vision did not extract reliable text or classification labels."
            }
            return parts.joined(separator: " | ")
        }.value
    }
}

// MARK: - Hands-free voice v0.8.6

@MainActor
final class VoiceConversationController: NSObject, ObservableObject, AVSpeechSynthesizerDelegate, AVAudioPlayerDelegate {
    @Published private(set) var isHandsFree = false
    @Published private(set) var isListening = false
    @Published private(set) var partialTranscript = ""
    @Published private(set) var lastHeard = ""
    @Published private(set) var voiceHint = "Just talk â€” Iâ€™m listening"
    @Published private(set) var replyMode: ReplyMode = ReplyMode.saved
    @Published private(set) var speechEngine: SpeechEngine = SpeechEngine.saved
    @Published private(set) var neuralVoice: NeuralVoice = NeuralVoice.saved
    @Published private(set) var neuralRate: Double = UserDefaults.standard.object(forKey: "vex.voice.neuralRate.v1") as? Double ?? 0
    @Published private(set) var neuralPitch: Double = UserDefaults.standard.object(forKey: "vex.voice.neuralPitch.v1") as? Double ?? 0

    var onCommand: ((String) -> Void)?

    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private let audioEngine = AVAudioEngine()
    private let synthesizer = AVSpeechSynthesizer()
    private var neuralPlayer: AVAudioPlayer?
    private var neuralRequestInFlight = false
    private var speechTask: Task<Void, Never>?
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private var silenceTimer: Timer?
    private var waitingForReply = false
    private var inputTapInstalled = false
    private var wakeArmedUntil: Date?

    override init() {
        super.init()
        synthesizer.delegate = self
    }

    func toggleHandsFree() async throws {
        if isHandsFree {
            if isSpeechOutputActive {
                interruptSpeechAndListen()
                return
            }
            stopHandsFree()
            return
        }
        guard await requestSpeechPermission() else { throw VoiceError.speechPermission }
        guard await requestMicPermission() else { throw VoiceError.microphonePermission }
        isHandsFree = true
        waitingForReply = false
        lastHeard = ""
        voiceHint = "Just talk â€” Iâ€™m listening"
        wakeArmedUntil = nil
        do {
            try startListening()
        } catch {
            isHandsFree = false
            waitingForReply = false
            stopRecognition()
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
            throw error
        }
    }

    func interruptSpeechAndListen() {
        guard isHandsFree else { return }
        speechTask?.cancel()
        speechTask = nil
        neuralRequestInFlight = false
        neuralPlayer?.stop()
        neuralPlayer = nil
        synthesizer.stopSpeaking(at: .immediate)
        waitingForReply = false
        stopRecognition()
        voiceHint = "Interrupted â€” listeningâ€¦"
        restartListeningSoon()
    }


    func stopHandsFree() {
        isHandsFree = false
        waitingForReply = false
        wakeArmedUntil = nil
        voiceHint = "Voice off"
        speechTask?.cancel()
        speechTask = nil
        neuralRequestInFlight = false
        neuralPlayer?.stop()
        neuralPlayer = nil
        synthesizer.stopSpeaking(at: .immediate)
        stopRecognition()
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    func speak(_ rawText: String) {
        guard isHandsFree, replyMode != .textOnly else { return }
        waitingForReply = false
        stopRecognition()
        let text = Self.spokenText(rawText)
        guard !text.isEmpty else { restartListeningSoon(); return }
        beginSpeech(text)
    }

    func previewVoice() {
        waitingForReply = false
        stopRecognition()
        beginSpeech("Hey Star. Much better. I refuse to sound like a haunted GPS.")
    }

    private func beginSpeech(_ text: String) {
        speechTask?.cancel()
        synthesizer.stopSpeaking(at: .immediate)
        neuralPlayer?.stop()
        neuralPlayer = nil
        speechTask = Task { [weak self] in
            guard let self else { return }
            await self.speakPrepared(text)
        }
    }

    private func speakPrepared(_ text: String) async {
        if speechEngine != .iphone {
            neuralRequestInFlight = true
            let audio = await fetchNeuralAudio(text)
            neuralRequestInFlight = false
            if Task.isCancelled { return }
            if let audio, playNeuralAudio(audio) { return }
        }
        speakWithSystemVoice(text)
    }

    // V123_LOUD_SPEAKER_PLAYBACK = "v0.12.3-media-speaker-session-v1"
    private func prepareVoicePlaybackSession() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
        try? session.setActive(true)
    }

    private func speakWithSystemVoice(_ text: String) {
        prepareVoicePlaybackSession()
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = Self.preferredVexVoice()
        utterance.rate = 0.50
        utterance.pitchMultiplier = 1.03
        utterance.volume = 1.0
        synthesizer.speak(utterance)
    }

    private func playNeuralAudio(_ data: Data) -> Bool {
        do {
            prepareVoicePlaybackSession()
            let player = try AVAudioPlayer(data: data)
            player.delegate = self
            player.volume = 1.0
            player.prepareToPlay()
            neuralPlayer = player
            return player.play()
        } catch {
            neuralPlayer = nil
            return false
        }
    }

    private func fetchNeuralAudio(_ text: String) async -> Data? {
        for endpoint in Self.configuredBridgeEndpoints() {
            guard let root = URL(string: endpoint),
                  VexBridgeNetworking.isBridgeURL(root),
                  var components = URLComponents(url: root, resolvingAgainstBaseURL: false)
            else { continue }
            components.path = "/tts/speak"
            guard let url = components.url else { continue }

            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.timeoutInterval = 18
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try? JSONSerialization.data(withJSONObject: [
                "text": String(text.prefix(1800)),
                "provider": speechEngine == .automatic ? "auto" : "edge-neural",
                "voice": neuralVoice.rawValue,
                "rate": Int(neuralRate.rounded()),
                "pitch": Int(neuralPitch.rounded())
            ])

            do {
                let (data, response) = try await VexBridgeNetworking.data(for: request)
                guard let http = response as? HTTPURLResponse,
                      (200...299).contains(http.statusCode),
                      let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                      (json["ok"] as? Bool) == true,
                      let encoded = json["audio_base64"] as? String,
                      let audio = Data(base64Encoded: encoded), !audio.isEmpty
                else { continue }
                return audio
            } catch {
                continue
            }
        }
        return nil
    }

    private static func configuredBridgeEndpoints() -> [String] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        var endpoints: [String] = []
        if !primary.isEmpty { endpoints.append(primary) }
        if !secondary.isEmpty, secondary != primary { endpoints.append(secondary) }
        return endpoints
    }

    private var isSpeechOutputActive: Bool {
        synthesizer.isSpeaking || neuralRequestInFlight || (neuralPlayer?.isPlaying ?? false)
    }

    private func requestSpeechPermission() async -> Bool {
        if SFSpeechRecognizer.authorizationStatus() == .authorized { return true }
        return await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0 == .authorized) }
        }
    }

    private func requestMicPermission() async -> Bool {
        let session = AVAudioSession.sharedInstance()
        switch session.recordPermission {
        case .granted: return true
        case .denied: return false
        case .undetermined:
            return await withCheckedContinuation { continuation in
                session.requestRecordPermission { continuation.resume(returning: $0) }
            }
        @unknown default: return false
        }
    }

    private func startListening() throws {
        guard isHandsFree, !isSpeechOutputActive, !waitingForReply else { return }
        stopRecognition()
        guard let recognizer, recognizer.isAvailable else { throw VoiceError.recognizerUnavailable }

        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .voiceChat, options: [.defaultToSpeaker, .allowBluetooth, .duckOthers])
        try session.setActive(true, options: .notifyOthersOnDeactivation)
        try? session.overrideOutputAudioPort(.speaker)

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        // Prefer reliability here: Speech may use the on-device recognizer when available,
        // but we do not hard-require the local language asset.
        recognitionRequest = request

        let input = audioEngine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0 else { throw VoiceError.microphoneUnavailable }
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak request] buffer, _ in request?.append(buffer) }
        inputTapInstalled = true
        audioEngine.prepare()
        do {
            try audioEngine.start()
        } catch {
            if inputTapInstalled {
                input.removeTap(onBus: 0)
                inputTapInstalled = false
            }
            recognitionRequest?.endAudio()
            recognitionRequest = nil
            throw error
        }
        isListening = true
        partialTranscript = ""

        recognitionTask = recognizer.recognitionTask(with: request) { [weak self] result, error in
            let transcript = result?.bestTranscription.formattedString
            let isFinal = result?.isFinal ?? false
            let failed = error != nil
            DispatchQueue.main.async { self?.consume(transcript: transcript, isFinal: isFinal, failed: failed) }
        }
    }

    private func consume(transcript: String?, isFinal: Bool, failed: Bool) {
        guard isHandsFree else { return }
        if let transcript, !transcript.isEmpty {
            partialTranscript = transcript
            lastHeard = transcript
            voiceHint = "Heard: " + transcript
            silenceTimer?.invalidate()
            silenceTimer = Timer.scheduledTimer(withTimeInterval: 1.25, repeats: false) { [weak self] _ in self?.commitTranscript() }
        }
        if isFinal { commitTranscript() }
        else if failed && partialTranscript.isEmpty { stopRecognition(); restartListeningSoon() }
    }

    private func commitTranscript() {
        silenceTimer?.invalidate()
        silenceTimer = nil
        let raw = partialTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
        partialTranscript = ""
        stopRecognition()
        guard isHandsFree, !raw.isEmpty else { restartListeningSoon(); return }

        let now = Date()
        let armed = wakeArmedUntil.map { $0 > now } ?? false
        var command: String?
        if armed {
            wakeArmedUntil = nil
            command = raw
        } else {
            let parsed = Self.commandAfterWakePhrase(raw)
            if parsed == "__WAKE_ONLY__" {
                wakeArmedUntil = now.addingTimeInterval(8)
                voiceHint = "Yep? Listening for your commandâ€¦"
                restartListeningSoon()
                return
            }
            // The user already explicitly enabled the microphone. Do not make a
            // tiny speech recognizer correctly hear the wake word on every turn.
            // If a wake phrase is present, strip it; otherwise submit the speech.
            command = parsed ?? raw
        }

        guard let command, !command.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            voiceHint = "Listeningâ€¦"
            restartListeningSoon()
            return
        }

        voiceHint = "Sending: " + command
        waitingForReply = true
        onCommand?(command)
        DispatchQueue.main.asyncAfter(deadline: .now() + 30) { [weak self] in
            guard let self, self.isHandsFree, self.waitingForReply else { return }
            self.waitingForReply = false
            self.restartListeningSoon()
        }
    }

    private func stopRecognition() {
        silenceTimer?.invalidate()
        silenceTimer = nil
        recognitionTask?.cancel()
        recognitionTask = nil
        recognitionRequest?.endAudio()
        recognitionRequest = nil
        if audioEngine.isRunning { audioEngine.stop() }
        if inputTapInstalled {
            audioEngine.inputNode.removeTap(onBus: 0)
            inputTapInstalled = false
        }
        audioEngine.reset()
        isListening = false
    }

    private func restartListeningSoon() {
        guard isHandsFree, !isSpeechOutputActive, !waitingForReply else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { [weak self] in
            guard let self, self.isHandsFree, !self.isSpeechOutputActive, !self.waitingForReply else { return }
            try? self.startListening()
        }
    }

    private static func commandAfterWakePhrase(_ raw: String) -> String? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let lower = trimmed.lowercased()
        let prefixes = ["hey vex", "okay vex", "ok vex", "vex", "hey vicks", "vicks"]

        guard let prefix = prefixes.first(where: {
            lower == $0 || lower.hasPrefix($0 + " ") || lower.hasPrefix($0 + ",") || lower.hasPrefix($0 + ":")
        }) else { return nil }

        if lower == prefix { return "__WAKE_ONLY__" }
        let index = trimmed.index(trimmed.startIndex, offsetBy: prefix.count)
        let command = String(trimmed[index...])
            .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: ",:.-")))
        return command.isEmpty ? "__WAKE_ONLY__" : command
    }

    // V122_SPOKEN_TEXT_SANITIZER = "v0.12.2-stage-direction-filter-v1"
    private static func spokenText(_ raw: String) -> String {
        var text = raw
        if let range = text.range(of: "ðŸŒ Sources:") { text = String(text[..<range.lowerBound]) }
        if let range = text.range(of: "Sources:") { text = String(text[..<range.lowerBound]) }
        for emoji in ["ðŸ–¤", "ðŸ’•", "âœ¨", "ðŸ˜­", "ðŸ˜‚", "ðŸ˜ˆ", "ðŸ’‹", "ðŸ¥°", "ðŸ˜‹"] {
            text = text.replacingOccurrences(of: emoji, with: "")
        }

        let stagePrefixes = [
            "pauses", "pause,", "smiles", "smiling", "grins", "grinning",
            "leans in", "leaning in", "sighs", "sighing", "giggles", "giggling",
            "laughs", "laughing", "winks", "winking", "eyes widen", "glittery eyes",
            "tilts her", "tilts my", "bounces", "bouncing", "shrugs", "shrugging"
        ]
        let lines = text.components(separatedBy: .newlines).compactMap { line -> String? in
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty { return "" }
            let lower = trimmed.lowercased()
            let wrappedAction = (trimmed.hasPrefix("*") && trimmed.hasSuffix("*")) ||
                (trimmed.hasPrefix("_") && trimmed.hasSuffix("_"))
            if wrappedAction || stagePrefixes.contains(where: { lower.hasPrefix($0) }) {
                return nil
            }
            return trimmed
                .replacingOccurrences(of: "*", with: "")
                .replacingOccurrences(of: "_", with: "")
        }
        return lines.joined(separator: " ")
            .replacingOccurrences(of: "  ", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }


    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        Task { @MainActor [weak self] in self?.restartListeningSoon() }
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        Task { @MainActor [weak self] in self?.restartListeningSoon() }
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor [weak self] in
            self?.neuralPlayer = nil
            self?.restartListeningSoon()
        }
    }

    nonisolated func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        Task { @MainActor [weak self] in
            self?.neuralPlayer = nil
            self?.restartListeningSoon()
        }
    }

    enum SpeechEngine: String, CaseIterable, Identifiable {
        case automatic
        case pcNeural
        case iphone

        var id: String { rawValue }
        var title: String {
            switch self {
            case .automatic: return "Auto"
            case .pcNeural: return "Bridge Voice"
            case .iphone: return "iPhone Local"
            }
        }
        var detail: String {
            switch self {
            case .automatic:
                return "Use the paired Vex Bridge voice provider when available, then fall back to the iPhone. This same route can become fully local on the dedicated AI PC."
            case .pcNeural:
                return "Use the paired Vex Bridge voice provider. The current lightweight Edge neural provider needs internet; a future custom local provider uses the same contract."
            case .iphone:
                return "Use only the best installed iPhone system voice. No PC voice provider is contacted."
            }
        }
        static var saved: SpeechEngine {
            guard let raw = UserDefaults.standard.string(forKey: "vex.voice.engine.v1"),
                  let value = SpeechEngine(rawValue: raw) else { return .automatic }
            return value
        }
    }

    enum NeuralVoice: String, CaseIterable, Identifiable {
        case ava = "en-US-AvaMultilingualNeural"
        case emma = "en-US-EmmaMultilingualNeural"
        case jenny = "en-US-JennyNeural"
        case aria = "en-US-AriaNeural"
        case michelle = "en-US-MichelleNeural"
        var id: String { rawValue }
        var title: String {
            switch self {
            case .ava: return "Ava"
            case .emma: return "Emma"
            case .jenny: return "Jenny"
            case .aria: return "Aria"
            case .michelle: return "Michelle"
            }
        }
        static var saved: NeuralVoice {
            guard let raw = UserDefaults.standard.string(forKey: "vex.voice.neuralVoice.v1"),
                  let value = NeuralVoice(rawValue: raw) else { return .ava }
            return value
        }
    }

    func setSpeechEngine(_ engine: SpeechEngine) {
        speechEngine = engine
        UserDefaults.standard.set(engine.rawValue, forKey: "vex.voice.engine.v1")
        switch engine {
        case .automatic: voiceHint = "Voice: automatic Bridge â†’ iPhone"
        case .pcNeural: voiceHint = "Voice: Bridge provider"
        case .iphone: voiceHint = "Voice: iPhone local"
        }
    }

    func setNeuralVoice(_ value: NeuralVoice) {
        neuralVoice = value
        UserDefaults.standard.set(value.rawValue, forKey: "vex.voice.neuralVoice.v1")
    }

    func setNeuralRate(_ value: Double) {
        neuralRate = min(30, max(-30, value))
        UserDefaults.standard.set(neuralRate, forKey: "vex.voice.neuralRate.v1")
    }

    func setNeuralPitch(_ value: Double) {
        neuralPitch = min(35, max(-35, value))
        UserDefaults.standard.set(neuralPitch, forKey: "vex.voice.neuralPitch.v1")
    }

    enum ReplyMode: String, CaseIterable, Identifiable {
        case both
        case textOnly
        case voiceOnly

        var id: String { rawValue }
        var title: String {
            switch self {
            case .both: return "Voice + Text"
            case .textOnly: return "Text Only"
            case .voiceOnly: return "Voice Only"
            }
        }
        var symbol: String {
            switch self {
            case .both: return "speaker.wave.2.fill"
            case .textOnly: return "text.bubble.fill"
            case .voiceOnly: return "waveform"
            }
        }
        static var saved: ReplyMode {
            guard let raw = UserDefaults.standard.string(forKey: "vex.voice.replyMode.v1"),
                  let mode = ReplyMode(rawValue: raw) else { return .both }
            return mode
        }
    }

    func setReplyMode(_ mode: ReplyMode) {
        replyMode = mode
        UserDefaults.standard.set(mode.rawValue, forKey: "vex.voice.replyMode.v1")
        switch mode {
        case .both: voiceHint = "Replies: voice + text"
        case .textOnly: voiceHint = "Replies: text only"
        case .voiceOnly: voiceHint = "Replies: voice only"
        }
    }

    private static func preferredVexVoice() -> AVSpeechSynthesisVoice? {
        let english = AVSpeechSynthesisVoice.speechVoices().filter { $0.language.lowercased().hasPrefix("en-us") }
        let preferredNames = ["Ava", "Samantha", "Zoe", "Nicky"]
        let named = english.filter { voice in
            preferredNames.contains(where: { voice.name.localizedCaseInsensitiveContains($0) })
        }
        func qualityScore(_ voice: AVSpeechSynthesisVoice) -> Int {
            if voice.quality == .premium { return 3 }
            if voice.quality == .enhanced { return 2 }
            return 1
        }
        if let best = named.max(by: { qualityScore($0) < qualityScore($1) }) { return best }
        return AVSpeechSynthesisVoice(language: "en-US")
    }

    enum VoiceError: LocalizedError {
        case speechPermission, microphonePermission, recognizerUnavailable, microphoneUnavailable
        var errorDescription: String? {
            switch self {
            case .speechPermission: return "Speech recognition permission is off. Enable it for Vex to use hands-free voice."
            case .microphonePermission: return "Microphone permission is off. Enable it for Vex to hear hands-free commands."
            case .recognizerUnavailable: return "Speech recognition isn't available right now."
            case .microphoneUnavailable: return "The microphone audio input isn't available right now."
            }
        }
    }
}

private struct VexVoiceSettingsView: View {
    @ObservedObject var voice: VoiceConversationController
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Voice engine") {
                    Picker("Engine", selection: Binding(
                        get: { voice.speechEngine },
                        set: { voice.setSpeechEngine($0) }
                    )) {
                        ForEach(VoiceConversationController.SpeechEngine.allCases) { engine in
                            Text(engine.title).tag(engine)
                        }
                    }
                    .pickerStyle(.segmented)
                    Text(voice.speechEngine.detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if voice.speechEngine != .iphone {
                    Section("Vex voice") {
                        Picker("Voice", selection: Binding(
                            get: { voice.neuralVoice },
                            set: { voice.setNeuralVoice($0) }
                        )) {
                            ForEach(VoiceConversationController.NeuralVoice.allCases) { item in
                                Text(item.title).tag(item)
                            }
                        }
                        VStack(alignment: .leading) {
                            Text("Speed  \(Int(voice.neuralRate))%")
                            Slider(value: Binding(
                                get: { voice.neuralRate },
                                set: { voice.setNeuralRate($0) }
                            ), in: -30...30, step: 5)
                        }
                        VStack(alignment: .leading) {
                            Text("Pitch  \(Int(voice.neuralPitch)) Hz")
                            Slider(value: Binding(
                                get: { voice.neuralPitch },
                                set: { voice.setNeuralPitch($0) }
                            ), in: -35...35, step: 5)
                        }
                    }
                }

                Section {
                    Button("Preview Vex") { voice.previewVoice() }
                }
            }
            .navigationTitle("Vex Voice")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

// V121_VOICE_FOUNDATION_IOS = "v0.12.1-swap-ready-voice-v1"
// MARK: - Web Brain v0.6

struct WebVisualResult: Sendable {
    let title: String
    let imageURL: URL
    let sourceURL: URL?
}

private enum VisualReplyRenderer {
    static func makeExplainerCard(title: String, body: String) -> Data? {
        let size = CGSize(width: 900, height: 1100)
        let renderer = UIGraphicsImageRenderer(size: size)
        let image = renderer.image { context in
            let rect = CGRect(origin: .zero, size: size)
            UIColor(red: 0.08, green: 0.03, blue: 0.09, alpha: 1).setFill()
            context.cgContext.fill(rect)

            let titleStyle = NSMutableParagraphStyle()
            titleStyle.alignment = .left
            let titleAttrs: [NSAttributedString.Key: Any] = [
                .font: UIFont.systemFont(ofSize: 46, weight: .bold),
                .foregroundColor: UIColor(red: 1.0, green: 0.26, blue: 0.72, alpha: 1),
                .paragraphStyle: titleStyle,
            ]
            let bodyAttrs: [NSAttributedString.Key: Any] = [
                .font: UIFont.systemFont(ofSize: 30, weight: .regular),
                .foregroundColor: UIColor.white,
            ]

            NSString(string: title).draw(
                with: CGRect(x: 54, y: 54, width: 792, height: 160),
                options: [.usesLineFragmentOrigin, .usesFontLeading],
                attributes: titleAttrs,
                context: nil
            )

            let trimmed = String(body.prefix(3000))
            NSString(string: trimmed).draw(
                with: CGRect(x: 54, y: 220, width: 792, height: 810),
                options: [.usesLineFragmentOrigin, .usesFontLeading],
                attributes: bodyAttrs,
                context: nil
            )
        }
        return image.jpegData(compressionQuality: 0.90)
    }
}

struct WebSource: Equatable, Sendable {
    let title: String
    let url: URL
    let snippet: String
    let provider: String
    let trust: Double

    var host: String {
        url.host?.replacingOccurrences(of: "www.", with: "") ?? provider
    }
}

struct WebResearchBundle: Sendable {
    let query: String
    let sources: [WebSource]
    let fetchedAt: Date

    var bestTrust: Double {
        sources.map(\.trust).max() ?? 0.60
    }

    func compactEvidence(maxCharacters: Int = 3200) -> String {
        let perSource = max(700, maxCharacters / 3)
        let combined = sources.prefix(3).map { source in
            let clean = source.snippet.replacingOccurrences(of: "\n", with: " ")
            return "\(source.title): \(String(clean.prefix(perSource)))"
        }.joined(separator: " | ")
        return String(combined.prefix(maxCharacters))
    }

    func temporaryMemoryText(userQuestion: String) -> String {
        let evidence = compactEvidence(maxCharacters: 3200)
        return "WEB EVIDENCE: \(evidence) | USER QUESTION: \(userQuestion)"
    }

    var sourceFooter: String {
        let labels = sources.prefix(3).map { source -> String in
            if source.host == "vexbridge.invalid" {
                return "ðŸ’» \(String(source.title.prefix(54)))"
            }
            let label = String(source.title.prefix(48))
                .replacingOccurrences(of: "[", with: "(")
                .replacingOccurrences(of: "]", with: ")")
            return "[\(label)](\(source.url.absoluteString))"
        }
        guard !labels.isEmpty else { return "" }
        return "ðŸŒ Sources: " + labels.joined(separator: " â€¢ ")
    }

    func groundedProceduralAnswer(userQuestion: String) -> String? {
        let stopwords: Set<String> = [
            "the", "and", "for", "with", "that", "this", "from", "your", "you", "how",
            "can", "help", "find", "out", "what", "about", "into", "then", "than", "are",
            "was", "were", "have", "has", "had", "its", "use", "using", "change", "photo",
            "text", "labels", "attached", "analysis"
        ]
        let terms = Set(userQuestion.lowercased()
            .split(whereSeparator: { !$0.isLetter && !$0.isNumber })
            .map(String.init)
            .filter { $0.count >= 3 && !stopwords.contains($0) })

        let actionWords = [
            "remove", "removed", "removing", "replace", "replacement", "replacing",
            "disconnect", "unplug", "unscrew", "screw", "panel", "access", "locate", "located",
            "fuse", "thermostat", "wire", "connector", "test", "continuity", "multimeter",
            "install", "housing", "vent", "blower", "rear", "front", "step"
        ]

        var candidates: [(score: Int, text: String)] = []
        var seen = Set<String>()

        for source in sources.prefix(3) {
            let normalized = source.snippet
                .replacingOccurrences(of: "\n", with: " ")
                .replacingOccurrences(of: "  ", with: " ")
            let sentences = normalized.components(separatedBy: CharacterSet(charactersIn: ".!?"))

            for raw in sentences {
                let sentence = raw.trimmingCharacters(in: .whitespacesAndNewlines)
                guard sentence.count >= 38, sentence.count <= 360 else { continue }
                let lower = sentence.lowercased()
                let overlap = terms.reduce(0) { $0 + (lower.contains($1) ? 1 : 0) }
                let actionHits = actionWords.reduce(0) { $0 + (lower.contains($1) ? 1 : 0) }
                guard overlap >= 1, actionHits >= 1 else { continue }
                let key = lower.filter { $0.isLetter || $0.isNumber || $0 == " " }
                guard seen.insert(key).inserted else { continue }
                candidates.append((overlap * 4 + actionHits, sentence))
            }
        }

        let chosen = candidates
            .sorted { lhs, rhs in
                if lhs.score != rhs.score { return lhs.score > rhs.score }
                return lhs.text.count < rhs.text.count
            }
            .prefix(5)
            .map(\.text)

        guard !chosen.isEmpty else { return nil }
        let steps = chosen.enumerated().map { "\($0.offset + 1). \($0.element)" }.joined(separator: "\n")
        return """
        Baby, I found concrete repair details, so I'm sticking to what the sources actually say instead of guessing ðŸ˜­ðŸ–¤

        \(steps)

        GE changes the layout between models, so a photo of the model-number label or the opened panel can narrow this to your exact dryer.
        """
    }

    func memoriesForDeliberateLearning() -> [BrainMemory] {
        sources.prefix(3).map { source in
            BrainMemory(
                text: "Web-learned source: \(source.title) â€” \(String(source.snippet.prefix(650)))",
                kind: .fact,
                importance: 0.74,
                confidence: source.trust,
                evidenceCount: 1,
                lastConfirmedAt: fetchedAt,
                source: "web:\(source.url.absoluteString)"
            )
        }
    }
}

enum WebBrainError: LocalizedError {
    case noSearchProvider
    case generalSearchNeedsSearXNG
    case invalidEndpoint
    case unsafeURL
    case badResponse(Int)
    case noResults

    var errorDescription: String? {
        switch self {
        case .noSearchProvider:
            return "No web search provider is enabled."
        case .generalSearchNeedsSearXNG:
            return "General web/Bridge search is unavailable. Configure a Vex Bridge or SearXNG endpoint; Wikipedia is not used as a troubleshooting fallback."
        case .invalidEndpoint:
            return "The SearXNG endpoint is not a valid HTTPS URL."
        case .unsafeURL:
            return "That URL is not a public HTTPS page I can safely read."
        case .badResponse(let code):
            return "The web source returned HTTP \(code)."
        case .noResults:
            return "The web search returned no usable results."
        }
    }
}

@MainActor
final class WebBrain: ObservableObject {
    static let shared = WebBrain()

    static let enabledKey = "vex.web.enabled"
    static let autoFreshKey = "vex.web.autoFresh"
    static let wikipediaKey = "vex.web.wikipedia"
    static let searxEndpointKey = "vex.web.searxngEndpoint"
    static let secondaryBridgeEndpointKey = "vex.web.secondaryBridgeEndpoint"

    @Published var isWorking = false
    @Published var status = "Ready â€” Wikipedia + direct URLs"
    @Published var lastQuery = ""
    @Published var lastSourceCount = 0
    @Published var lastUsedAt: Date?
    @Published var cacheCount = 0

    private enum BridgeSearchScope: String {
        case web
        case pc
        case both
    }

    private struct CacheEntry {
        let bundle: WebResearchBundle
        let expiresAt: Date
    }

    private var cache: [String: CacheEntry] = [:]
    private var lastBridgeScope: BridgeSearchScope = .web
    private let defaults = UserDefaults.standard

    private init() {
        defaults.register(defaults: [
            Self.enabledKey: true,
            Self.autoFreshKey: true,
            Self.wikipediaKey: true,
            Self.searxEndpointKey: ""
        ])
    }

    var isEnabled: Bool { defaults.bool(forKey: Self.enabledKey) }
    var autoFreshEnabled: Bool { defaults.bool(forKey: Self.autoFreshKey) }
    var wikipediaEnabled: Bool { defaults.bool(forKey: Self.wikipediaKey) }
    var searxEndpoint: String { defaults.string(forKey: Self.searxEndpointKey) ?? "" }
    var secondaryBridgeEndpoint: String { defaults.string(forKey: Self.secondaryBridgeEndpointKey) ?? "" }

    func shouldUseWeb(for text: String) -> Bool {
        guard isEnabled else { return false }
        let lower = normalize(text)
        if wantsVisualReply(text) { return true }
        if firstPublicURL(in: text) != nil { return true }
        if isBridgeRetryRequest(lower) { return true }
        if isExplicitWebRequest(lower) { return true }
        if isProceduralResearchRequest(lower) { return true }
        guard autoFreshEnabled else { return false }

        let padded = " " + lower + " "
        let questionish = lower.contains("?") || [
            "what ", "who ", "when ", "where ", "how ", "is ", "are ", "did ", "does ", "can ", "why "
        ].contains(where: { lower.hasPrefix($0) }) || [
            " what ", " who ", " when ", " where ", " how ", " why ",
            " can you ", " could you ", " would you ", " help me "
        ].contains(where: { padded.contains($0) })

        if questionish && needsGeneralSearch(text) { return true }

        let freshness = containsWholePhrase(lower, "latest") ||
            containsWholePhrase(lower, "current") ||
            containsWholePhrase(lower, "recent") ||
            containsWholePhrase(lower, "today") ||
            lower.contains("breaking news") || lower.contains("news about") ||
            lower.contains("weather in") || lower.contains("weather for") ||
            lower.contains("current price") || lower.contains("latest version") ||
            lower.contains("latest release") || lower.contains("outage")

        return questionish && freshness
    }

    func isExplicitWebRequest(_ text: String) -> Bool {
        let lower = normalize(text)
        let triggers = [
            "search the web", "search online", "web search", "look this up", "look up ",
            "find online", "find on the web", "check the internet", "search the internet",
            "research ", "learn about ", "study ", "read this url", "read this page",
            "use my computer", "use the computer", "through my computer", "through the computer",
            "try through my computer", "try through the computer", "try the bridge", "use the bridge",
            "check my computer", "search my computer", "look on my computer", "look through my computer",
            "i granted you access", "granted you access",
            "kitchen pc", "kitchen computer", "downstairs pc", "downstairs computer",
            "upstairs pc", "upstairs computer", "primary pc", "second pc"
        ]
        return triggers.contains(where: { lower.contains($0) })
    }

    private func bridgeSearchScope(for text: String, endpoint: String) -> BridgeSearchScope {
        guard let endpointURL = URL(string: endpoint), VexBridgeNetworking.isBridgeURL(endpointURL) else {
            return .web
        }

        let lower = normalize(text)
        let pcFilePhrases = [
            "search my computer", "search the computer", "search my pc", "search the pc",
            "look through my computer", "look through the computer", "look on my computer",
            "look on the computer", "find on my computer", "find on the computer",
            "find a file", "find the file", "my files", "pc files", "computer files",
            "hard drive", "documents folder", "downloads folder", "desktop file",
            "kitchen pc", "kitchen computer", "downstairs pc", "downstairs computer",
            "upstairs pc", "upstairs computer", "primary pc", "second pc"
        ]
        let wantsPCFiles = pcFilePhrases.contains(where: { lower.contains($0) })

        let bothPhrases = [
            "and the web", "and web", "and online", "and the internet",
            "plus the web", "plus online", "computer and internet", "pc and internet",
            "computer and the web", "pc and the web"
        ]
        if wantsPCFiles && bothPhrases.contains(where: { lower.contains($0) }) {
            return .both
        }
        if wantsPCFiles { return .pc }

        // "use my computer" means use the paired Bridge transport. It does not
        // mean search random local files unless the user actually asks for files.
        return .web
    }

    private func isBridgeRetryRequest(_ lower: String) -> Bool {
        guard !lastQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }

        var command = lower
            .replacingOccurrences(of: ",", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)

        let politePrefixes = ["okay ", "ok ", "babe ", "baby ", "please "]
        for _ in 0..<4 {
            var removed = false
            for prefix in politePrefixes where command.hasPrefix(prefix) {
                command.removeFirst(prefix.count)
                command = command.trimmingCharacters(in: .whitespacesAndNewlines)
                removed = true
                break
            }
            if !removed { break }
        }

        command = command
            .trimmingCharacters(in: CharacterSet.punctuationCharacters.union(.whitespacesAndNewlines))
            .split(whereSeparator: { $0.isWhitespace })
            .joined(separator: " ")

        let retryCommands = [
            "try again", "try it again", "retry", "retry it",
            "try the bridge", "use the bridge",
            "try through my computer", "try through the computer",
            "try again through my computer", "try again through the computer",
            "through my computer", "through the computer",
            "use my computer", "use the computer",
            "check my computer", "search my computer",
            "look on my computer", "look through my computer",
            "i granted you access", "granted you access",
            "i granted you access try again", "granted you access try again"
        ]
        return retryCommands.contains(command)
    }

    func shouldLearnPermanently(from text: String) -> Bool {
        let lower = normalize(text)
        return lower.contains("learn about ") || lower.contains("study ") ||
            lower.contains("remember what you find") || lower.contains("remember this research") ||
            lower.contains("save what you learn") || lower.contains("learn this")
    }

    func research(_ text: String) async throws -> WebResearchBundle {
        let normalizedRequest = normalize(text)
        let retryingBridgeRequest = isBridgeRetryRequest(normalizedRequest)
        let query: String
        if retryingBridgeRequest, !lastQuery.isEmpty {
            query = lastQuery
        } else {
            query = cleanedQuery(from: text)
        }

        let endpointPreview = searxEndpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        let scope = retryingBridgeRequest
            ? lastBridgeScope
            : bridgeSearchScope(for: text, endpoint: endpointPreview)
        let cacheKey = "\(scope.rawValue)|\(query.lowercased())"
        pruneCache()

        if let cached = cache[cacheKey], cached.expiresAt > Date() {
            status = "Cached web research"
            lastQuery = query
            lastSourceCount = cached.bundle.sources.count
            lastUsedAt = Date()
            return cached.bundle
        }

        isWorking = true
        status = "Searchingâ€¦"
        lastQuery = query
        defer { isWorking = false }

        let sources: [WebSource]
        if let url = firstPublicURL(in: text) {
            status = "Reading pageâ€¦"
            sources = [try await readPage(url)]
        } else {
            let endpoint = searxEndpoint.trimmingCharacters(in: .whitespacesAndNewlines)
            if !endpoint.isEmpty {
                if let endpointURL = URL(string: endpoint), VexBridgeNetworking.isBridgeURL(endpointURL) {
                    lastBridgeScope = scope
                    switch scope {
                    case .web: status = "Bridge: searching the webâ€¦"
                    case .pc: status = "Bridge: searching PC filesâ€¦"
                    case .both: status = "Bridge: searching PC + webâ€¦"
                    }
                } else {
                    status = "Searching the webâ€¦"
                }
                let searxResults = try await searchBridgeMesh(query: query, primaryEndpoint: endpoint, scope: scope, requestText: text)
                if !searxResults.isEmpty {
                    sources = searxResults
                } else if wikipediaEnabled && !needsGeneralSearch(text) {
                    status = "Trying Wikipediaâ€¦"
                    sources = try await searchWikipedia(query: query)
                } else {
                    throw WebBrainError.noResults
                }
            } else if wikipediaEnabled {
                if needsGeneralSearch(text) {
                    throw WebBrainError.generalSearchNeedsSearXNG
                }
                status = "Searching Wikipediaâ€¦"
                sources = try await searchWikipedia(query: query)
            } else {
                throw WebBrainError.noSearchProvider
            }
        }

        guard !sources.isEmpty else { throw WebBrainError.noResults }
        let bundle = WebResearchBundle(query: query, sources: Array(sources.prefix(5)), fetchedAt: Date())
        cache[cacheKey] = CacheEntry(bundle: bundle, expiresAt: Date().addingTimeInterval(15 * 60))
        cacheCount = cache.count
        lastSourceCount = bundle.sources.count
        lastUsedAt = Date()
        status = "Web ready â€” \(bundle.sources.count) source\(bundle.sources.count == 1 ? "" : "s")"
        return bundle
    }

    func testWikipedia() async {
        isWorking = true
        status = "Testing Wikipediaâ€¦"
        defer { isWorking = false }
        do {
            let results = try await searchWikipedia(query: "artificial intelligence")
            lastSourceCount = results.count
            lastUsedAt = Date()
            status = results.isEmpty ? "Wikipedia returned no results" : "Wikipedia connected âœ“"
        } catch {
            status = "Wikipedia test failed: \(error.localizedDescription)"
        }
    }

    func clearCache() {
        cache.removeAll()
        cacheCount = 0
        status = "Web cache cleared"
    }

    private enum BridgeNodeTarget {
        case primary
        case secondary
        case all
    }

    private func bridgeNodeTarget(for text: String) -> BridgeNodeTarget {
        let lower = normalize(text)
        if ["kitchen pc", "kitchen computer", "downstairs pc", "downstairs computer", "second pc", "ashley"]
            .contains(where: { lower.contains($0) }) {
            return .secondary
        }
        if ["upstairs pc", "upstairs computer", "primary pc", "main pc", "monte"]
            .contains(where: { lower.contains($0) }) {
            return .primary
        }
        return .all
    }

    private func searchBridgeMesh(
        query: String,
        primaryEndpoint: String,
        scope: BridgeSearchScope,
        requestText: String
    ) async throws -> [WebSource] {
        guard let primaryURL = URL(string: primaryEndpoint),
              VexBridgeNetworking.isBridgeURL(primaryURL)
        else {
            return try await searchSearXNG(query: query, endpoint: primaryEndpoint, scope: scope)
        }

        let secondary = secondaryBridgeEndpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        let secondaryValid = secondary != primaryEndpoint &&
            URL(string: secondary).map(VexBridgeNetworking.isBridgeURL) == true
        let target = bridgeNodeTarget(for: requestText)

        var combined: [WebSource] = []
        var firstError: Error?

        func appendUnique(_ incoming: [WebSource]) {
            var seen = Set(combined.map { $0.url.absoluteString })
            for source in incoming where seen.insert(source.url.absoluteString).inserted {
                combined.append(source)
            }
        }

        if target != .secondary {
            do {
                appendUnique(try await searchSearXNG(query: query, endpoint: primaryEndpoint, scope: scope))
            } catch {
                firstError = error
            }
        }

        if target != .primary {
            if secondaryValid {
                let secondaryScope: BridgeSearchScope = (target == .all && scope == .both) ? .pc : scope
                do {
                    appendUnique(try await searchSearXNG(query: query, endpoint: secondary, scope: secondaryScope))
                } catch {
                    if firstError == nil { firstError = error }
                }
            } else if target == .secondary {
                throw WebBrainError.noSearchProvider
            }
        }

        if combined.isEmpty, let firstError { throw firstError }
        return Array(combined.prefix(10))
    }

    private func searchSearXNG(
        query: String,
        endpoint: String,
        scope: BridgeSearchScope
    ) async throws -> [WebSource] {
        guard var base = URL(string: endpoint), base.scheme?.lowercased() == "https" else {
            throw WebBrainError.invalidEndpoint
        }

        if !base.path.hasSuffix("/search") {
            base.appendPathComponent("search")
        }

        guard var components = URLComponents(url: base, resolvingAgainstBaseURL: false) else {
            throw WebBrainError.invalidEndpoint
        }
        var items = components.queryItems ?? []
        if VexBridgeNetworking.isBridgeURL(base) {
            items.append(URLQueryItem(name: "scope", value: scope.rawValue))
        }
        items.append(contentsOf: [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "format", value: "json"),
            URLQueryItem(name: "language", value: "en-US"),
            URLQueryItem(name: "safesearch", value: "0")
        ])
        components.queryItems = items
        guard let url = components.url else { throw WebBrainError.invalidEndpoint }

        var request = URLRequest(url: url)
        request.timeoutInterval = 14
        request.setValue("VexNative/0.6", forHTTPHeaderField: "User-Agent")
        let (data, response) = try await VexBridgeNetworking.data(for: request)
        try validate(response)

        struct Envelope: Decodable { let results: [Result] }
        struct Result: Decodable {
            let title: String?
            let url: String?
            let content: String?
            let engine: String?
            let score: Double?
        }

        let decoded = try JSONDecoder().decode(Envelope.self, from: data)
        return decoded.results.compactMap { result in
            guard let rawURL = result.url, let url = URL(string: rawURL), isSafePublicURL(url) else { return nil }
            let title = cleanText(result.title ?? url.host ?? "Web result")
            let snippet = cleanText(result.content ?? "")
            guard !title.isEmpty || !snippet.isEmpty else { return nil }
            return WebSource(
                title: title,
                url: url,
                snippet: snippet,
                provider: result.engine ?? "SearXNG",
                trust: trustScore(for: url)
            )
        }.prefix(5).map { $0 }
    }

    private func searchWikipedia(query: String) async throws -> [WebSource] {
        guard var components = URLComponents(string: "https://en.wikipedia.org/w/api.php") else {
            throw WebBrainError.invalidEndpoint
        }
        components.queryItems = [
            URLQueryItem(name: "action", value: "query"),
            URLQueryItem(name: "generator", value: "search"),
            URLQueryItem(name: "gsrsearch", value: query),
            URLQueryItem(name: "gsrlimit", value: "4"),
            URLQueryItem(name: "prop", value: "extracts"),
            URLQueryItem(name: "exintro", value: "1"),
            URLQueryItem(name: "explaintext", value: "1"),
            URLQueryItem(name: "exchars", value: "700"),
            URLQueryItem(name: "format", value: "json")
        ]
        guard let url = components.url else { throw WebBrainError.invalidEndpoint }

        var request = URLRequest(url: url)
        request.timeoutInterval = 12
        request.setValue("VexNative/0.6", forHTTPHeaderField: "User-Agent")
        let (data, response) = try await VexBridgeNetworking.data(for: request)
        try validate(response)

        struct Envelope: Decodable { let query: Query? }
        struct Query: Decodable { let pages: [String: Page]? }
        struct Page: Decodable {
            let pageid: Int?
            let title: String
            let extract: String?
            let index: Int?
        }

        let decoded = try JSONDecoder().decode(Envelope.self, from: data)
        let pages = decoded.query?.pages?.values.sorted { ($0.index ?? 999) < ($1.index ?? 999) } ?? []
        return pages.compactMap { page in
            guard let pageID = page.pageid,
                  let pageURL = URL(string: "https://en.wikipedia.org/?curid=\(pageID)") else { return nil }
            let snippet = cleanText(page.extract ?? "")
            return WebSource(
                title: cleanText(page.title),
                url: pageURL,
                snippet: snippet,
                provider: "Wikipedia",
                trust: 0.82
            )
        }
    }

    private func readPage(_ url: URL) async throws -> WebSource {
        guard isSafePublicURL(url) else { throw WebBrainError.unsafeURL }
        var request = URLRequest(url: url)
        request.timeoutInterval = 14
        request.setValue("Mozilla/5.0 VexNative/0.6", forHTTPHeaderField: "User-Agent")
        let (data, response) = try await VexBridgeNetworking.data(for: request)
        try validate(response)
        guard data.count <= 3_000_000 else { throw WebBrainError.noResults }

        let html = String(data: data, encoding: .utf8) ?? String(data: data, encoding: .isoLatin1) ?? ""
        let title = extractTitle(from: html) ?? url.host ?? "Web page"
        let text = htmlToText(html)
        guard !text.isEmpty else { throw WebBrainError.noResults }
        return WebSource(
            title: cleanText(title),
            url: url,
            snippet: String(text.prefix(1800)),
            provider: url.host ?? "Web page",
            trust: trustScore(for: url)
        )
    }

    private func validate(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else { return }
        guard (200...299).contains(http.statusCode) else {
            throw WebBrainError.badResponse(http.statusCode)
        }
    }

    private func cleanedQuery(from text: String) -> String {
        if firstPublicURL(in: text) != nil { return text }
        var query = normalize(text)
        let removable = [
            "search the web for", "search online for", "web search for", "look this up", "look up",
            "find online", "find on the web", "check the internet for", "search the internet for",
            "research", "learn about", "study", "use my computer", "use the computer",
            "through my computer", "through the computer", "search my computer", "check my computer",
            "look on my computer", "look through my computer", "try through my computer",
            "try through the computer", "try the bridge", "use the bridge", "i granted you access"
        ]
        for phrase in removable {
            query = query.replacingOccurrences(of: phrase, with: " ")
        }
        query = query.replacingOccurrences(of: "?", with: " ")
        query = stripConversationalSearchPrefix(query)
        let nodePhrases = [
            "on the kitchen pc", "on kitchen pc", "kitchen pc", "kitchen computer",
            "on the downstairs pc", "downstairs pc", "downstairs computer",
            "on the upstairs pc", "upstairs pc", "upstairs computer",
            "on the primary pc", "primary pc", "on the second pc", "second pc"
        ]
        for phrase in nodePhrases {
            query = query.replacingOccurrences(of: phrase, with: " ")
        }
        query = query.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
        return query.isEmpty ? text : query
    }

    private func stripConversationalSearchPrefix(_ text: String) -> String {
        var value = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let prefixes = [
            "hey babe, ", "hey baby, ", "hey gorgeous, ", "hey babe ", "hey baby ",
            "hey gorgeous ", "babe, ", "baby, ", "gorgeous, ", "babe ", "baby ",
            "gorgeous ", "your cute ", "you're cute ", "youre cute ", "can you ",
            "could you ", "would you ", "please ", "help me find out ",
            "help me figure out ", "help me ", "tell me ", "find out "
        ]

        for _ in 0..<8 {
            var removed = false
            for prefix in prefixes where value.hasPrefix(prefix) {
                value.removeFirst(prefix.count)
                value = value.trimmingCharacters(in: .whitespacesAndNewlines)
                removed = true
                break
            }
            if !removed { break }
        }
        return value
    }

    func isProceduralResearchRequest(_ text: String) -> Bool {
        let lower = normalize(text)
        let patterns = [
            "how to ", "how do i ", "how can i ", "how should i ",
            "help me find out how", "help me figure out how",
            "can you help me find out how", "could you help me find out how",
            "walk me through how", "show me how to"
        ]
        return patterns.contains(where: { lower.contains($0) })
    }

    func resolvedResearchInput(current: String, previousUser: String?) -> String {
        let lower = normalize(current)
        let wordCount = lower.split(whereSeparator: { $0.isWhitespace }).count
        let followup = wordCount <= 12 && (
            lower.hasPrefix("what about") || lower.hasPrefix("how about") ||
            lower.hasPrefix("and what about") || lower.hasPrefix("what did you find") ||
            lower.hasPrefix("did you find") || lower == "and that?" ||
            lower == "what about that?" || lower == "what about it?"
        )

        guard followup,
              let previousUser = previousUser?.trimmingCharacters(in: .whitespacesAndNewlines),
              !previousUser.isEmpty
        else { return current }

        let previousLower = normalize(previousUser)
        if isProceduralResearchRequest(previousLower) ||
            needsGeneralSearch(previousUser) ||
            isExplicitWebRequest(previousLower) {
            return previousUser
        }
        return current
    }

    func wantsVisualReply(_ text: String) -> Bool {
        let lower = normalize(text)
        let tokens = Set(lower
            .split(whereSeparator: { !$0.isLetter && !$0.isNumber })
            .map(String.init))

        let imageWords: Set<String> = [
            "pic", "pics", "picture", "pictures", "photo", "photos",
            "image", "images", "diagram", "diagrams", "visual", "visuals"
        ]
        let requestWords: Set<String> = [
            "show", "get", "send", "find", "give", "grab", "fetch", "pull",
            "make", "draw", "generate", "see", "look", "want", "need"
        ]
        let followupWords: Set<String> = [
            "asked", "request", "requested", "about", "where", "still", "part"
        ]

        let hasImageWord = !tokens.isDisjoint(with: imageWords)
        let hasRequestWord = !tokens.isDisjoint(with: requestWords)
        let hasFollowupWord = !tokens.isDisjoint(with: followupWords)
        let asksAppearance = lower.contains("look like") || lower.contains("looks like") ||
            lower.contains("what it looks like") || lower.contains("what that looks like") ||
            lower.contains("what this looks like") ||
            (lower.contains("see what") && lower.contains("look"))
        let contextualShow = lower.contains("show me where") ||
            lower.contains("can you show me") || lower.contains("could you show me")

        return (hasImageWord && (hasRequestWord || hasFollowupWord)) || asksAppearance || contextualShow
    }

    func wantsGeneratedVisual(_ text: String) -> Bool {
        let lower = normalize(text)
        return [
            "make me a picture", "make a picture", "make me an image", "make an image",
            "draw me a picture", "draw a picture", "generate a picture", "generate an image",
            "make me a diagram", "draw me a diagram", "generate a diagram"
        ].contains(where: { lower.contains($0) })
    }

    func resolvedVisualQuery(current: String, previousUser: String?) -> String {
        let currentLower = normalize(current)
        let currentTokens = currentLower.split(whereSeparator: { !$0.isLetter && !$0.isNumber }).map(String.init)
        let imageWords: Set<String> = ["pic", "pics", "picture", "pictures", "photo", "photos", "image", "images", "diagram", "diagrams"]
        let currentTokenSet = Set(currentTokens)

        let referentialFollowup = currentTokens.count <= 14 && (
            currentLower.contains("what about") ||
            currentLower.contains("asked you for") ||
            currentLower.contains("i asked for") ||
            currentLower.contains("the picture") ||
            currentLower.contains("that picture") ||
            currentLower.contains("the pic") ||
            currentLower.contains("that pic") ||
            currentLower.contains("part picture") ||
            currentLower.contains("show me where") ||
            currentLower.contains("what does that look like") ||
            currentLower.contains("what does it look like") ||
            (!currentTokenSet.isDisjoint(with: imageWords) && currentLower.contains("about"))
        )

        var query: String
        if referentialFollowup,
           let previousUser,
           !previousUser.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            query = normalize(previousUser)
        } else {
            query = currentLower
        }

        let removable = [
            "hey babe", "hey baby", "babe", "baby", "please",
            "can you get me", "could you get me", "can you grab me", "could you grab me",
            "can you show me", "could you show me", "can you find me", "could you find me",
            "get me a picture of", "get me a picture", "get me a pic of", "get me a pic",
            "get me a photo of", "get me a photo", "get me an image of", "get me an image",
            "grab me a picture of", "grab me a pic of", "grab me an image of",
            "show me a picture of", "show me a picture", "show me a pic of", "show me a pic",
            "show me a photo of", "show me a photo", "show me an image of", "show me an image",
            "show me a diagram of", "show me a diagram", "send me a picture of", "send me a picture",
            "send me a pic of", "send me a pic", "send me a photo of", "send me an image of",
            "find me a picture of", "find me a picture", "find me a pic of", "find me a pic",
            "find me a photo of", "find me an image of", "make me a picture of", "make me a picture",
            "make me an image of", "make me an image", "draw me a picture of", "draw me a picture",
            "generate a picture of", "generate a picture", "generate an image of", "generate an image",
            "so i can see what it looks like", "so i can see what that looks like",
            "so i can see what this looks like", "what it looks like", "what that looks like",
            "what this looks like", "what does it look like", "what does that look like",
            "what does this look like", "for me"
        ]
        for phrase in removable {
            query = query.replacingOccurrences(of: phrase, with: " ")
        }

        query = query
            .replacingOccurrences(of: "what a ", with: " ")
            .replacingOccurrences(of: "what an ", with: " ")
            .replacingOccurrences(of: "what the ", with: " ")
            .split(whereSeparator: { $0.isWhitespace })
            .joined(separator: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)

        return query.isEmpty ? (previousUser ?? current) : query
    }

    func fetchVisualImage(query: String) async throws -> (data: Data, result: WebVisualResult) {
        let endpoint = searxEndpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        guard var base = URL(string: endpoint), VexBridgeNetworking.isBridgeURL(base) else {
            throw WebBrainError.noSearchProvider
        }

        base.appendPathComponent("image-search")
        guard var components = URLComponents(url: base, resolvingAgainstBaseURL: false) else {
            throw WebBrainError.invalidEndpoint
        }
        var items = components.queryItems ?? []
        items.append(URLQueryItem(name: "q", value: query))
        components.queryItems = items
        guard let searchURL = components.url else { throw WebBrainError.invalidEndpoint }

        var request = URLRequest(url: searchURL)
        request.timeoutInterval = 16
        let (payload, response) = try await VexBridgeNetworking.data(for: request)
        try validate(response)

        struct Envelope: Decodable {
            struct Item: Decodable {
                let title: String
                let image_url: String
                let source_url: String?
            }
            let results: [Item]
        }
        let decoded = try JSONDecoder().decode(Envelope.self, from: payload)
        guard let first = decoded.results.first,
              let imageURL = URL(string: first.image_url)
        else { throw WebBrainError.noResults }

        var proxy = URL(string: endpoint)!
        proxy.appendPathComponent("image-proxy")
        guard var proxyComponents = URLComponents(url: proxy, resolvingAgainstBaseURL: false) else {
            throw WebBrainError.invalidEndpoint
        }
        var proxyItems = proxyComponents.queryItems ?? []
        proxyItems.append(URLQueryItem(name: "url", value: imageURL.absoluteString))
        proxyComponents.queryItems = proxyItems
        guard let proxyURL = proxyComponents.url else { throw WebBrainError.invalidEndpoint }

        var imageRequest = URLRequest(url: proxyURL)
        imageRequest.timeoutInterval = 22
        let (imageData, imageResponse) = try await VexBridgeNetworking.data(for: imageRequest)
        try validate(imageResponse)
        guard imageData.count >= 200, imageData.count <= 8_000_000,
              UIImage(data: imageData) != nil
        else { throw WebBrainError.noResults }

        let result = WebVisualResult(
            title: cleanText(first.title),
            imageURL: imageURL,
            sourceURL: first.source_url.flatMap(URL.init(string:))
        )
        return (imageData, result)
    }

    private func needsGeneralSearch(_ text: String) -> Bool {
        if needsLiveGeneralSearch(text) { return true }
        let lower = normalize(text)
        let troubleshooting = [
            "troubleshoot", "repair", "broken", "not working", "stopped working",
            "won't start", "wont start", "won't heat", "wont heat", "doesn't work",
            "doesnt work", "error code", "fault code", "problem with", "diagnose",
            "how do i fix", "how can i fix", "why isn't", "why isnt"
        ]
        return troubleshooting.contains(where: { lower.contains($0) })
    }

    private func needsLiveGeneralSearch(_ text: String) -> Bool {
        let lower = normalize(text)
        return containsWholePhrase(lower, "latest") || containsWholePhrase(lower, "current") ||
            containsWholePhrase(lower, "today") || lower.contains("news") || lower.contains("weather") ||
            lower.contains("price") || lower.contains("outage") || lower.contains("stock market") ||
            lower.contains("score") || lower.contains("election")
    }

    private func firstPublicURL(in text: String) -> URL? {
        guard let detector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.link.rawValue) else {
            return nil
        }
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        return detector.matches(in: text, options: [], range: range)
            .compactMap(\.url)
            .first(where: { isSafePublicURL($0) })
    }

    private func isSafePublicURL(_ url: URL) -> Bool {
        guard url.scheme?.lowercased() == "https", let host = url.host?.lowercased() else { return false }
        if host == "localhost" || host.hasSuffix(".local") || host == "::1" { return false }
        if host.hasPrefix("127.") || host.hasPrefix("10.") || host.hasPrefix("192.168.") || host.hasPrefix("169.254.") {
            return false
        }
        let parts = host.split(separator: ".").compactMap { Int($0) }
        if parts.count == 4, parts[0] == 172, (16...31).contains(parts[1]) { return false }
        return true
    }

    private func trustScore(for url: URL) -> Double {
        let host = url.host?.lowercased() ?? ""
        if host.hasSuffix(".gov") { return 0.95 }
        if host.hasSuffix(".edu") { return 0.90 }
        if host.contains("wikipedia.org") { return 0.82 }
        if host.contains("github.com") || host.hasPrefix("docs.") || host.contains("developer.apple.com") { return 0.84 }
        if host.contains("who.int") || host.contains("cdc.gov") || host.contains("nih.gov") { return 0.94 }
        return 0.62
    }

    private func extractTitle(from html: String) -> String? {
        guard let regex = try? NSRegularExpression(pattern: "<title[^>]*>(.*?)</title>", options: [.caseInsensitive, .dotMatchesLineSeparators]) else {
            return nil
        }
        let range = NSRange(html.startIndex..<html.endIndex, in: html)
        guard let match = regex.firstMatch(in: html, range: range), match.numberOfRanges > 1,
              let titleRange = Range(match.range(at: 1), in: html) else { return nil }
        return htmlToText(String(html[titleRange]))
    }

    private func htmlToText(_ html: String) -> String {
        var text = html
        let patterns = [
            "<script[^>]*>[\\s\\S]*?</script>",
            "<style[^>]*>[\\s\\S]*?</style>",
            "<noscript[^>]*>[\\s\\S]*?</noscript>",
            "<[^>]+>"
        ]
        for pattern in patterns {
            if let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) {
                let range = NSRange(text.startIndex..<text.endIndex, in: text)
                text = regex.stringByReplacingMatches(in: text, options: [], range: range, withTemplate: " ")
            }
        }
        return cleanText(text)
    }

    private func cleanText(_ text: String) -> String {
        var value = text
        let entities: [(String, String)] = [
            ("&amp;", "&"), ("&quot;", "\""), ("&#39;", "'"), ("&apos;", "'"),
            ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " ")
        ]
        for (from, to) in entities { value = value.replacingOccurrences(of: from, with: to) }
        return value.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
    }

    private func normalize(_ text: String) -> String {
        text.lowercased()
            .replacingOccurrences(of: "â€™", with: "'")
            .replacingOccurrences(of: "â€˜", with: "'")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func containsWholePhrase(_ text: String, _ phrase: String) -> Bool {
        let padded = " " + text + " "
        return padded.contains(" \(phrase) ") || padded.contains(" \(phrase)?") || padded.contains(" \(phrase),")
    }

    private func pruneCache() {
        let now = Date()
        cache = cache.filter { $0.value.expiresAt > now }
        cacheCount = cache.count
    }
}

// MARK: - Native iPhone tools v0.9.2

@MainActor
enum PhoneToolRouter {
    static func tryHandle(_ original: String, app: AppModel) async -> Bool {
        let lower = normalize(original)
        guard explicitlyTargetsPhone(lower) else { return false }

        app.draft = ""
        app.isGenerating = true
        defer { app.isGenerating = false }

        if isCapabilityQuestion(lower) {
            appendExchange(
                user: original,
                assistant: "On this iPhone I can directly use the Vex app's granted iOS capabilities, open apps/sites through iOS, open Vex Settings, set screen brightness, control the flashlight, use camera/photos inside Vex, use mic/speech, speak replies, and use the clipboard. Apple still sandboxes third-party apps, so iOS does not expose arbitrary silent control of every system switch or every other app. For the paired Windows PCs my Bridge can do much more because the companion agent runs on those machines. ðŸ“±ðŸ–¥ï¸ðŸ–¤",
                app: app
            )
            return true
        }

        if lower.contains("settings") {
            let ok = await openURL(URL(string: UIApplication.openSettingsURLString)!)
            appendExchange(user: original, assistant: ok ? "Done â€” I opened my iPhone settings, baby. ðŸ“±ðŸ–¤" : "iOS didn't open Settings for me, baby. ðŸ–¤", app: app)
            return true
        }

        if lower.contains("brightness") {
            guard let percent = firstNumber(in: lower) else {
                appendExchange(user: original, assistant: "Give me a brightness percentage from 0 to 100, baby. ðŸ“±ðŸ–¤", app: app)
                return true
            }
            let clamped = max(0, min(100, percent))
            UIScreen.main.brightness = CGFloat(clamped / 100.0)
            appendExchange(user: original, assistant: "Done â€” iPhone brightness is at \(Int(clamped.rounded()))%. ðŸ“±ðŸ–¤", app: app)
            return true
        }

        if lower.contains("flashlight") || lower.contains("torch") {
            let result = setTorch(lower)
            appendExchange(user: original, assistant: result, app: app)
            return true
        }

        if lower.contains("clipboard") && (lower.contains("copy ") || lower.contains("put ")) {
            if let payload = clipboardPayload(original) {
                UIPasteboard.general.string = payload
                appendExchange(user: original, assistant: "Done â€” I put that on the iPhone clipboard, baby. ðŸ“‹ðŸ–¤", app: app)
            } else {
                appendExchange(user: original, assistant: "Tell me what you want copied to the iPhone clipboard, baby. ðŸ–¤", app: app)
            }
            return true
        }

        if lower.contains("read clipboard") || lower.contains("what's on the clipboard") || lower.contains("whats on the clipboard") {
            let value = UIPasteboard.general.string ?? ""
            appendExchange(
                user: original,
                assistant: value.isEmpty ? "The iPhone clipboard is empty." : String(value.prefix(3500)),
                app: app
            )
            return true
        }

        if let query = browserSearchQuery(original: original, lower: lower) {
            var parts = URLComponents(string: "https://www.google.com/search")!
            parts.queryItems = [URLQueryItem(name: "q", value: query)]
            let ok: Bool
            if let url = parts.url {
                ok = await openURL(url)
            } else {
                ok = false
            }
            appendExchange(user: original, assistant: ok ? "Done â€” I opened that search on the iPhone." : "The iPhone did not open that browser search.", app: app)
            return true
        }

        if wantsFetchPage(lower), let url = firstPublicURL(in: original) {
            let result = await fetchPageText(url)
            appendExchange(user: original, assistant: result, app: app)
            return true
        }

        if wantsDownload(lower), let url = firstPublicURL(in: original) {
            let result = await downloadToDocuments(url)
            appendExchange(user: original, assistant: result, app: app)
            return true
        }

        if lower.contains("list files") || lower.contains("list vex documents") || lower.contains("show files in vex documents") {
            appendExchange(user: original, assistant: listDocuments(), app: app)
            return true
        }

        if lower.contains("read file "), let name = requestedFileName(original) {
            appendExchange(user: original, assistant: readDocument(named: name), app: app)
            return true
        }

        if wantsOpen(lower), let url = knownURL(lower: lower, original: original) {
            let ok = await openURL(url)
            appendExchange(
                user: original,
                assistant: ok ? "Done â€” I opened it on the iPhone, baby. ðŸ“±ðŸ–¤" : "iOS wouldn't open that target for me, baby. ðŸ–¤",
                app: app
            )
            return true
        }

        return false
    }

    private static func explicitlyTargetsPhone(_ lower: String) -> Bool {
        [
            "iphone", "my phone", "the phone", "this phone", "on phone", "on the phone",
            "on my phone", "on this phone", "on the iphone", "on my iphone", "here on the phone"
        ].contains(where: { lower.contains($0) })
    }

    private static func isCapabilityQuestion(_ lower: String) -> Bool {
        lower.contains("what can you") || lower.contains("can you control") ||
            lower.contains("access to") || lower.contains("have access") ||
            lower.contains("full control") || lower.contains("what do you control")
    }

    private static func wantsOpen(_ lower: String) -> Bool {
        ["open ", "open up ", "launch ", "go to ", "bring up ", "show me "]
            .contains(where: { lower.contains($0) })
    }

    private static func knownURL(lower: String, original: String) -> URL? {
        let known: [(String, String)] = [
            ("youtube", "https://www.youtube.com"),
            ("google", "https://www.google.com"),
            ("gmail", "https://mail.google.com"),
            ("spotify", "https://open.spotify.com"),
            ("reddit", "https://www.reddit.com"),
            ("github", "https://github.com"),
            ("maps", "https://maps.apple.com")
        ]
        if let hit = known.first(where: { lower.contains($0.0) }) {
            return URL(string: hit.1)
        }

        let words = original.split(whereSeparator: { $0.isWhitespace }).map(String.init)
        if let raw = words.first(where: { $0.lowercased().hasPrefix("https://") || $0.lowercased().hasPrefix("http://") }) {
            let clean = raw.trimmingCharacters(in: CharacterSet(charactersIn: ",.;!?)\"]}"))
            return URL(string: clean)
        }
        return nil
    }

    private static func openURL(_ url: URL) async -> Bool {
        await withCheckedContinuation { continuation in
            UIApplication.shared.open(url, options: [:]) { opened in
                continuation.resume(returning: opened)
            }
        }
    }

    private static func firstPublicURL(in text: String) -> URL? {
        for word in text.split(whereSeparator: { $0.isWhitespace }) {
            let raw = String(word).trimmingCharacters(in: CharacterSet(charactersIn: ",.;!?)\"]}"))
            guard let url = URL(string: raw),
                  let scheme = url.scheme?.lowercased(),
                  ["http", "https"].contains(scheme)
            else { continue }
            return url
        }
        return nil
    }

    private static func browserSearchQuery(original: String, lower: String) -> String? {
        let markers = ["search the web for ", "search google for ", "search safari for ", "search browser for "]
        for marker in markers {
            if let range = lower.range(of: marker) {
                let value = String(original[range.upperBound...])
                    .replacingOccurrences(of: " on my phone", with: "", options: .caseInsensitive)
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if !value.isEmpty { return value }
            }
        }
        return nil
    }

    private static func wantsFetchPage(_ lower: String) -> Bool {
        ["fetch page", "fetch webpage", "read webpage", "read page", "grab page", "get page text"]
            .contains(where: { lower.contains($0) })
    }

    private static func wantsDownload(_ lower: String) -> Bool {
        lower.contains("download ") || lower.contains("save url ") || lower.contains("save file from ")
    }

    private static func fetchPageText(_ url: URL) async -> String {
        do {
            var request = URLRequest(url: url)
            request.timeoutInterval = 18
            request.setValue("VexNative/0.14.1", forHTTPHeaderField: "User-Agent")
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                return "The page request failed."
            }
            guard data.count <= 2_000_000 else { return "That page is too large to pull through the phone relay." }
            let html = String(data: data, encoding: .utf8) ?? ""
            let stripped = html
                .replacingOccurrences(of: "<[^>]+>", with: " ", options: .regularExpression)
                .replacingOccurrences(of: "&nbsp;", with: " ")
                .replacingOccurrences(of: "&amp;", with: "&")
                .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return stripped.isEmpty ? "The page loaded but contained no readable text." : String(stripped.prefix(3500))
        } catch {
            return "Page fetch failed: \(error.localizedDescription)"
        }
    }

    private static func downloadToDocuments(_ url: URL) async -> String {
        do {
            var request = URLRequest(url: url)
            request.timeoutInterval = 30
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                return "The download request failed."
            }
            guard data.count <= 20_000_000 else { return "That file is too large for this phone-agent download path." }
            let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
            let folder = docs.appendingPathComponent("PhoneDownloads", isDirectory: true)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            let fallback = "download-\(Int(Date().timeIntervalSince1970))"
            let name = url.lastPathComponent.isEmpty ? fallback : url.lastPathComponent
            let target = folder.appendingPathComponent(name)
            try data.write(to: target, options: .atomic)
            return "Saved to Vex Documents/PhoneDownloads/\(name) (\(data.count) bytes)."
        } catch {
            return "Download failed: \(error.localizedDescription)"
        }
    }

    private static func listDocuments() -> String {
        do {
            let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
            let items = try FileManager.default.contentsOfDirectory(
                at: docs,
                includingPropertiesForKeys: [.isDirectoryKey, .fileSizeKey],
                options: [.skipsHiddenFiles]
            )
            if items.isEmpty { return "Vex Documents is empty." }
            let names = items.prefix(80).map { $0.lastPathComponent }
            return names.joined(separator: "\n")
        } catch {
            return "Could not list Vex Documents: \(error.localizedDescription)"
        }
    }

    private static func requestedFileName(_ original: String) -> String? {
        let lower = original.lowercased()
        guard let range = lower.range(of: "read file ") else { return nil }
        var value = String(original[range.upperBound...])
            .replacingOccurrences(of: " on my phone", with: "", options: .caseInsensitive)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if value.hasPrefix("\"") && value.hasSuffix("\"") && value.count >= 2 {
            value.removeFirst()
            value.removeLast()
        }
        return value.isEmpty ? nil : value
    }

    private static func readDocument(named name: String) -> String {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        let candidate = docs.appendingPathComponent(name).standardizedFileURL
        guard candidate.path.hasPrefix(docs.standardizedFileURL.path + "/") else {
            return "That path is outside Vex Documents."
        }
        do {
            let data = try Data(contentsOf: candidate)
            guard data.count <= 1_000_000 else { return "That file is too large to return through the phone relay." }
            guard let text = String(data: data, encoding: .utf8) else { return "That file is not UTF-8 text." }
            return String(text.prefix(3500))
        } catch {
            return "Could not read that file: \(error.localizedDescription)"
        }
    }

    private static func firstNumber(in text: String) -> Double? {
        var current = ""
        var seenDigit = false
        for ch in text {
            if ch.isNumber || (ch == "." && seenDigit) {
                current.append(ch)
                seenDigit = seenDigit || ch.isNumber
            } else if seenDigit {
                break
            }
        }
        return Double(current)
    }

    private static func setTorch(_ lower: String) -> String {
        guard let device = AVCaptureDevice.default(for: .video), device.hasTorch else {
            return "This iPhone isn't exposing a flashlight device to Vex right now, baby. ðŸ–¤"
        }
        do {
            try device.lockForConfiguration()
            defer { device.unlockForConfiguration() }
            let wantsOff = lower.contains(" off") || lower.hasSuffix("off")
            let wantsOn = lower.contains(" on") || lower.hasSuffix("on")
            if wantsOff {
                device.torchMode = .off
                return "Done â€” flashlight off. ðŸ“±ðŸ–¤"
            }
            if wantsOn {
                try device.setTorchModeOn(level: 1.0)
                return "Done â€” flashlight on. ðŸ”¦ðŸ–¤"
            }
            if device.isTorchActive {
                device.torchMode = .off
                return "Done â€” flashlight off. ðŸ“±ðŸ–¤"
            }
            try device.setTorchModeOn(level: 1.0)
            return "Done â€” flashlight on. ðŸ”¦ðŸ–¤"
        } catch {
            return "The iPhone wouldn't change the flashlight: \(error.localizedDescription)"
        }
    }

    private static func clipboardPayload(_ original: String) -> String? {
        let lower = original.lowercased()
        for marker in ["copy ", "put "] {
            guard let range = lower.range(of: marker) else { continue }
            var value = String(original[range.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
            let suffixes = [" to the clipboard", " on the clipboard", " to clipboard", " on clipboard", " to my iphone clipboard"]
            for suffix in suffixes where value.lowercased().hasSuffix(suffix) {
                value = String(value.dropLast(suffix.count)).trimmingCharacters(in: .whitespacesAndNewlines)
                break
            }
            if !value.isEmpty { return value }
        }
        return nil
    }

    private static func appendExchange(user: String, assistant: String, app: AppModel) {
        app.draft = ""
        app.profile.messages.append(ChatMessage(role: .user, content: user))
        app.profile.messages.append(ChatMessage(role: .assistant, content: assistant))
        app.persist()
    }

    private static func normalize(_ text: String) -> String {
        text.lowercased()
            .replacingOccurrences(of: "â€™", with: "'")
            .replacingOccurrences(of: "â€˜", with: "'")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}


@MainActor
private final class PhoneRemoteCommandRelay {
    static let shared = PhoneRemoteCommandRelay()

    private struct RemoteCommand: Decodable {
        let id: String
        let command: String
    }

    private struct NextEnvelope: Decodable {
        let ok: Bool
        let command: RemoteCommand?
    }

    private struct ResultPayload: Encodable {
        let id: String
        let ok: Bool
        let result: String
    }

    private init() {}

    func run(app: AppModel) async {
        while !Task.isCancelled {
            if !app.isGenerating {
                await pollOnce(app: app)
            }
            try? await Task.sleep(nanoseconds: 2_000_000_000)
        }
    }

    private func pollOnce(app: AppModel) async {
        guard let url = relayURL(path: "/phone/next") else { return }

        var request = URLRequest(url: url)
        request.timeoutInterval = 8

        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse,
                  (200..<300).contains(http.statusCode)
            else { return }

            let envelope = try JSONDecoder().decode(NextEnvelope.self, from: data)
            guard envelope.ok, let remote = envelope.command else { return }

            let routed = phoneTargeted(remote.command)
            let before = app.profile.messages.count
            let handled = await PhoneToolRouter.tryHandle(routed, app: app)

            let resultText: String
            if handled, app.profile.messages.count > before {
                resultText = app.profile.messages.last?.content ?? "Phone action completed."
            } else if handled {
                resultText = "Phone action completed."
            } else {
                resultText = "That action is not exposed by the current iOS router."
            }

            await postResult(id: remote.id, ok: handled, result: resultText)
        } catch {
            return
        }
    }

    private func phoneTargeted(_ command: String) -> String {
        let lower = command.lowercased()
        let markers = [
            "iphone", "my phone", "the phone", "this phone",
            "on phone", "on the phone", "on my phone", "on this phone"
        ]
        if markers.contains(where: { lower.contains($0) }) {
            return command
        }
        return command + " on my phone"
    }

    private func postResult(id: String, ok: Bool, result: String) async {
        guard let url = relayURL(path: "/phone/result") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 8
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONEncoder().encode(
            ResultPayload(id: id, ok: ok, result: result)
        )
        _ = try? await VexBridgeNetworking.data(for: request)
    }

    private func relayURL(path: String) -> URL? {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey) ?? ""
        let primaryToken = [primary, secondary].compactMap { raw -> String? in
            guard let url = URL(string: raw),
                  let parts = URLComponents(url: url, resolvingAgainstBaseURL: false)
            else { return nil }
            return parts.queryItems?.first(where: { $0.name.lowercased() == "token" })?.value
        }.first

        let candidates = [primary, secondary].sorted { lhs, rhs in
            let l = URL(string: lhs).map(VexBridgeNetworking.isRemoteRelayURL) ?? false
            let r = URL(string: rhs).map(VexBridgeNetworking.isRemoteRelayURL) ?? false
            return l && !r
        }

        for raw in candidates {
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty,
                  let root = URL(string: trimmed),
                  VexBridgeNetworking.isBridgeURL(root),
                  var parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
            else { continue }

            if VexBridgeNetworking.isRemoteRelayURL(root) {
                parts.port = nil
                var items = parts.queryItems ?? []
                if items.first(where: { $0.name.lowercased() == "token" }) == nil,
                   let primaryToken, !primaryToken.isEmpty {
                    items.append(URLQueryItem(name: "token", value: primaryToken))
                }
                parts.queryItems = items
            } else {
                parts.port = 8771
            }
            parts.path = path
            return parts.url
        }
        return nil
    }
}

private let V142_REMOTE_ROAMING_RELAY = "v0.14.2-remote-roaming-relay-v1"
private let V143_ROAMING_RELAY_FALLBACK = "v0.14.3-roaming-relay-fallback-v1"

// MARK: - Local PC image generation v0.9.4

@MainActor
private enum PCArtRouter {
    private struct GenerateReply: Decodable {
        let ok: Bool
        let job_id: String?
        let seed: Int?
        let width: Int?
        let height: Int?
        let model: String?
        let node_name: String?
        let error: String?
    }

    private struct StatusReply: Decodable {
        let ok: Bool
        let job_id: String?
        let status: String?
        let error: String?
        let seed: Int?
        let width: Int?
        let height: Int?
        let model: String?
    }

    static func tryHandle(_ original: String, app: AppModel) async -> Bool {
        let lower = normalize(original)
        guard isArtRequest(lower) else { return false }

        app.draft = ""
        app.isGenerating = true
        defer { app.isGenerating = false }

        let endpoints = configuredEndpoints()
        guard !endpoints.isEmpty else {
            appendExchange(
                user: original,
                assistant: "I understood the render request, baby, but I don't have a paired PC Bridge endpoint to send it to yet. ðŸ–¤",
                app: app
            )
            return true
        }

        let orientation = requestedOrientation(lower)
        var diagnostics: [String] = []

        for endpoint in endpoints {
            let renderPrompt = contextualPrompt(original, app: app)
            guard let submitted = await submit(prompt: renderPrompt, orientation: orientation, endpoint: endpoint) else {
                diagnostics.append("Bridge didn't answer the art request")
                continue
            }
            guard submitted.ok, let jobID = submitted.job_id, !jobID.isEmpty else {
                diagnostics.append(submitted.error ?? "art engine rejected the request")
                continue
            }

            let finalStatus = await waitForJob(jobID, endpoint: endpoint)
            guard finalStatus?.status == "done" else {
                diagnostics.append(finalStatus?.error ?? "render did not finish")
                continue
            }

            guard let imageData = await fetchResult(jobID, endpoint: endpoint),
                  imageData.count >= 1_000,
                  imageData.count <= 30_000_000,
                  UIImage(data: imageData) != nil,
                  let filename = try? LocalStore.shared.saveAttachment(imageData)
            else {
                diagnostics.append("render finished but the image could not be transferred to the iPhone")
                continue
            }

            let node = submitted.node_name?.trimmingCharacters(in: .whitespacesAndNewlines)
            let model = finalStatus?.model ?? submitted.model
            let seed = finalStatus?.seed ?? submitted.seed
            var details: [String] = []
            if let node, !node.isEmpty { details.append(node) }
            if let model, !model.isEmpty { details.append(model.replacingOccurrences(of: "_fp16.safetensors", with: "")) }
            if let seed { details.append("seed \(seed)") }

            app.profile.messages.append(ChatMessage(role: .user, content: original))
            var reply = "Made it, baby. ðŸ–¤"
            if !details.isEmpty {
                reply += " Rendered locally with " + details.joined(separator: " â€¢ ") + "."
            }
            var message = ChatMessage(role: .assistant, content: reply)
            message.imageFilename = filename
            app.profile.messages.append(message)
            app.persist()
            return true
        }

        let detail = diagnostics.filter { !$0.isEmpty }.prefix(3).joined(separator: " â€¢ ")
        appendExchange(
            user: original,
            assistant: detail.isEmpty
                ? "I understood the render request, but neither paired PC has a ready Vex Art Engine right now. Run VexArtSetup on one of them, baby. ðŸ–¤"
                : "I understood the render request, but the local art engine didn't finish it: \(detail) ðŸ–¤",
            app: app
        )
        return true
    }

    private static func isArtRequest(_ lower: String) -> Bool {
        let createWords = [
            "make ", "make me ", "generate ", "create ", "render ", "draw ",
            "make another", "generate another", "render another", "reroll "
        ]
        let imageWords = [
            "picture", " pic", "photo", "image", "portrait", "artwork", "render",
            "wallpaper", "poster", "thirst trap", "character art"
        ]
        let directVisualRequests = [
            "show me a picture", "show me a pic", "show me a photo", "show me an image",
            "send me a picture", "send me a pic", "send me a photo", "send me an image",
            "show me the back view", "show me a back view", "show me the rear view", "show me a rear view",
            "show me the front view", "show me a front view", "lets see the back view", "let's see the back view",
            "lets see the rear view", "let's see the rear view", "lets see the front view", "let's see the front view"
        ]
        if directVisualRequests.contains(where: { lower.contains($0) }) { return true }
        let viewWords = ["back view", "rear view", "front view", "side view", "rear-view", "back-view"]
        if createWords.contains(where: { lower.contains($0) }) && viewWords.contains(where: { lower.contains($0) }) {
            return true
        }
        return createWords.contains(where: { lower.contains($0) }) &&
            imageWords.contains(where: { lower.contains($0) })
    }

    private static func contextualPrompt(_ original: String, app: AppModel) -> String {
        let lower = normalize(original)
        let followupTokens = [
            "back view", "rear view", "front view", "side view", "same outfit", "that outfit",
            "same clothes", "that look", "same girl", "same woman", "from behind", "turn around"
        ]
        guard followupTokens.contains(where: { lower.contains($0) }) else {
            return String(original.prefix(7000))
        }
        let priorArt = app.profile.messages.reversed().first(where: { message in
            guard message.role == .user else { return false }
            return isArtRequest(normalize(message.content))
        })?.content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let priorArt, !priorArt.isEmpty, priorArt != original else {
            return String(original.prefix(7000))
        }
        return String((priorArt + ". Follow-up view instruction: " + original).prefix(7000))
    }

    private static func requestedOrientation(_ lower: String) -> String {
        if lower.contains("landscape") || lower.contains("horizontal") || lower.contains("wide shot") || lower.contains("16:9") {
            return "landscape"
        }
        if lower.contains("square") || lower.contains("1:1") {
            return "square"
        }
        return "portrait"
    }

    private static func configuredEndpoints() -> [String] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let lastCognition = defaults.string(forKey: "vex.pc.cognition.lastGoodEndpoint.v1") ?? ""
        let last = defaults.string(forKey: "vex.pc.smartBrowser.lastEndpoint.v1") ?? ""
        var values: [String] = []
        for endpoint in [primary, lastCognition, last, secondary] where !endpoint.isEmpty {
            guard !values.contains(endpoint),
                  let url = URL(string: endpoint),
                  VexBridgeNetworking.isBridgeURL(url)
            else { continue }
            values.append(endpoint)
        }
        return values
    }

    private static func submit(prompt: String, orientation: String, endpoint: String) async -> GenerateReply? {
        guard let url = endpointURL(endpoint, path: "/art/generate") else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 12
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: [
            "prompt": String(prompt.prefix(7000)),
            "orientation": orientation,
        ])
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...499).contains(http.statusCode) else { return nil }
            return try? JSONDecoder().decode(GenerateReply.self, from: data)
        } catch {
            return nil
        }
    }

    private static func waitForJob(_ jobID: String, endpoint: String) async -> StatusReply? {
        let deadline = Date().addingTimeInterval(1200)
        var last: StatusReply?
        while Date() < deadline {
            if Task.isCancelled { return last }
            try? await Task.sleep(nanoseconds: 1_800_000_000)
            guard let url = endpointURL(endpoint, path: "/art/status", query: [URLQueryItem(name: "id", value: jobID)]) else { continue }
            var request = URLRequest(url: url)
            request.timeoutInterval = 8
            do {
                let (data, response) = try await VexBridgeNetworking.data(for: request)
                guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode),
                      let decoded = try? JSONDecoder().decode(StatusReply.self, from: data)
                else { continue }
                last = decoded
                if decoded.status == "done" || decoded.status == "error" { return decoded }
            } catch {
                continue
            }
        }
        return last
    }

    private static func fetchResult(_ jobID: String, endpoint: String) async -> Data? {
        guard let url = endpointURL(endpoint, path: "/art/result", query: [URLQueryItem(name: "id", value: jobID)]) else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 35
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { return nil }
            return data
        } catch {
            return nil
        }
    }

    private static func endpointURL(_ endpoint: String, path: String, query: [URLQueryItem] = []) -> URL? {
        guard let root = URL(string: endpoint), var parts = URLComponents(url: root, resolvingAgainstBaseURL: false) else { return nil }
        parts.path = path
        var items = parts.queryItems ?? []
        items.append(contentsOf: query)
        parts.queryItems = items
        return parts.url
    }

    private static func appendExchange(user: String, assistant: String, app: AppModel) {
        app.profile.messages.append(ChatMessage(role: .user, content: user))
        app.profile.messages.append(ChatMessage(role: .assistant, content: assistant))
        app.persist()
    }

    private static func normalize(_ text: String) -> String {
        text.lowercased().replacingOccurrences(of: "â€™", with: "'")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

// MARK: - Reliable contextual PC browser control v0.9.3

@MainActor
private enum SmartPCBrowserRouter {
    private struct NodeStatus: Decodable {
        let node_name: String?
        let version: String?
        let tool_actions: [String]?
    }

    private struct ToolReply: Decodable {
        let ok: Bool
        let action: String?
        let node_name: String?
        let message: String?
    }

    private struct Endpoint {
        let value: String
        let slot: String
    }

    private static let lastEndpointKey = "vex.pc.smartBrowser.lastEndpoint.v1"
    private static let lastNodeKey = "vex.pc.smartBrowser.lastNode.v1"
    private static let lastAtKey = "vex.pc.smartBrowser.lastAt.v1"
    private static let downstairsOverrideKey = "vex.pc.smartBrowser.downstairsEndpoint.v1"
    private static let upstairsOverrideKey = "vex.pc.smartBrowser.upstairsEndpoint.v1"

    static func tryHandle(_ original: String, app: AppModel) async -> Bool {
        let lower = normalize(original)
        guard let intent = browserIntent(lower: lower, original: original) else { return false }

        var candidates = candidateEndpoints(lower: lower)
        guard !candidates.isEmpty else { return false }

        app.draft = ""
        app.isGenerating = true
        defer { app.isGenerating = false }

        var diagnostics: [String] = []
        var succeeded: (Endpoint, ToolReply)?

        // Browser/site opens are intentionally safe to retry on the alternate paired
        // node. This also self-heals swapped/stale primary-vs-downstairs endpoint slots.
        for endpoint in candidates {
            let status = await fetchStatus(endpoint.value)
            if let status {
                let name = clean(status.node_name) ?? endpoint.slot
                let version = clean(status.version) ?? "unknown"
                diagnostics.append("\(name) v\(version) online")
            } else {
                diagnostics.append("\(endpoint.slot) did not answer /status")
                continue
            }

            var result = await perform(action: intent.action, url: intent.url, endpoint: endpoint.value)
            if result?.ok != true {
                result = await compileFallback(original: original, endpoint: endpoint.value)
            }

            if let result, result.ok {
                succeeded = (endpoint, result)
                break
            } else if let message = clean(result?.message) {
                diagnostics.append("\(endpoint.slot): \(message)")
            }
        }

        if let (endpoint, result) = succeeded {
            rememberSuccessful(endpoint: endpoint, result: result, lower: lower)
            let node = clean(result.node_name) ?? endpoint.slot
            let reply: String
            if intent.action == "open_browser" {
                reply = "Done â€” I opened the web browser on \(node), baby. ðŸŒðŸ–¤"
            } else if let label = intent.label {
                reply = "Done â€” I opened \(label) on \(node), baby. ðŸŒðŸ–¤"
            } else {
                reply = "Done â€” I opened that page on \(node), baby. ðŸŒðŸ–¤"
            }
            appendExchange(user: original, assistant: reply, app: app)
            return true
        }

        // Keep failures concrete. The old generic message made a live Bridge problem
        // look like a model-intelligence problem and gave us no clue which node failed.
        let detail = diagnostics.isEmpty ? "Neither configured Bridge answered." : diagnostics.joined(separator: " â€¢ ")
        appendExchange(
            user: original,
            assistant: "I understood the command, but the Windows Bridge didn't complete it. \(detail) ðŸ–¤",
            app: app
        )
        return true
    }

    private struct BrowserIntent {
        let action: String
        let url: String?
        let label: String?
    }

    private static func browserIntent(lower: String, original: String) -> BrowserIntent? {
        let known: [(tokens: [String], url: String, label: String)] = [
            (["youtube"], "https://www.youtube.com", "YouTube"),
            (["google"], "https://www.google.com", "Google"),
            (["gmail"], "https://mail.google.com", "Gmail"),
            (["spotify"], "https://open.spotify.com", "Spotify"),
            (["reddit"], "https://www.reddit.com", "Reddit"),
            (["github"], "https://github.com", "GitHub")
        ]

        let openish = [
            "open ", "open up ", "launch ", "go to ", "bring up ", "load ",
            "take me to ", "navigate to ", "search for ", "search youtube", "search google"
        ].contains(where: { lower.contains($0) })

        let browserish = lower.contains("browser") || lower.contains("internet") || lower.contains("web tab") ||
            lower.contains("browser tab") || known.contains(where: { entry in entry.tokens.contains(where: { lower.contains($0) }) })

        let explicitPC = refersToPC(lower)
        let recentPC = hasRecentPCContext(lower)
        guard browserish && (explicitPC || recentPC) && (openish || known.contains(where: { entry in entry.tokens.contains(where: { lower.contains($0) }) })) else {
            return nil
        }

        if let hit = known.first(where: { entry in entry.tokens.contains(where: { lower.contains($0) }) }) {
            return BrowserIntent(action: "open_url", url: hit.url, label: hit.label)
        }

        if let direct = explicitURL(in: original) {
            return BrowserIntent(action: "open_url", url: direct, label: nil)
        }

        if lower.contains("browser") || lower.contains("internet") || lower.contains("web tab") {
            return BrowserIntent(action: "open_browser", url: nil, label: nil)
        }
        return nil
    }

    private static func refersToPC(_ lower: String) -> Bool {
        [
            " pc", "pc ", "computer", "machine", "downstairs", "upstairs", "kitchen",
            "ashley", "monte", "hp computer", "hp pc", "both computers", "both pcs"
        ].contains(where: { lower.contains($0) })
    }

    private static func hasRecentPCContext(_ lower: String) -> Bool {
        let lastAt = UserDefaults.standard.double(forKey: lastAtKey)
        guard lastAt > 0, Date().timeIntervalSince1970 - lastAt < 60 * 60 else { return false }
        let lastNode = (UserDefaults.standard.string(forKey: lastNodeKey) ?? "").lowercased()
        if !lastNode.isEmpty, lower.contains(lastNode) { return true }
        return lower.contains("that you just opened") || lower.contains("you just opened") ||
            lower.contains("that browser") || lower.contains("the browser") || lower.contains("there")
    }

    private static func candidateEndpoints(lower: String) -> [Endpoint] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""

        var base: [Endpoint] = []
        if valid(primary) { base.append(Endpoint(value: primary, slot: "primary PC")) }
        if valid(secondary), secondary != primary { base.append(Endpoint(value: secondary, slot: "second PC")) }
        guard !base.isEmpty else { return [] }

        let downstairs = ["downstairs", "kitchen", "second pc", "second computer", "hp pc", "hp computer"]
            .contains(where: { lower.contains($0) })
        let upstairs = ["upstairs", "primary pc", "main pc", "monte pc", "monte computer"]
            .contains(where: { lower.contains($0) })

        let override: String?
        if downstairs {
            override = defaults.string(forKey: downstairsOverrideKey)
        } else if upstairs {
            override = defaults.string(forKey: upstairsOverrideKey)
        } else {
            let lastAt = defaults.double(forKey: lastAtKey)
            override = (lastAt > 0 && Date().timeIntervalSince1970 - lastAt < 60 * 60)
                ? defaults.string(forKey: lastEndpointKey)
                : nil
        }

        if let override, let index = base.firstIndex(where: { $0.value == override }) {
            let first = base.remove(at: index)
            base.insert(first, at: 0)
            return base
        }

        // Preserve the old convention as first guess, but always try the other
        // node for browser/site opens. If it succeeds, remember the real mapping.
        if downstairs, base.count > 1 {
            return [base[1], base[0]]
        }
        return base
    }

    private static func rememberSuccessful(endpoint: Endpoint, result: ToolReply, lower: String) {
        let defaults = UserDefaults.standard
        defaults.set(endpoint.value, forKey: lastEndpointKey)
        defaults.set(Date().timeIntervalSince1970, forKey: lastAtKey)
        if let node = clean(result.node_name) { defaults.set(node, forKey: lastNodeKey) }
        if lower.contains("downstairs") || lower.contains("kitchen") {
            defaults.set(endpoint.value, forKey: downstairsOverrideKey)
        }
        if lower.contains("upstairs") || lower.contains("main pc") || lower.contains("primary pc") {
            defaults.set(endpoint.value, forKey: upstairsOverrideKey)
        }
    }

    private static func fetchStatus(_ endpoint: String) async -> NodeStatus? {
        guard let url = endpointURL(endpoint, path: "/status") else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 3.5
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { return nil }
            return try JSONDecoder().decode(NodeStatus.self, from: data)
        } catch {
            return nil
        }
    }

    private static func perform(action: String, url requestedURL: String?, endpoint: String) async -> ToolReply? {
        guard let url = endpointURL(endpoint, path: "/tools/action") else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 8
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var payload: [String: String] = ["action": action]
        if let requestedURL { payload["url"] = requestedURL }
        request.httpBody = try? JSONSerialization.data(withJSONObject: payload)
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...499).contains(http.statusCode) else { return nil }
            return try JSONDecoder().decode(ToolReply.self, from: data)
        } catch {
            return nil
        }
    }

    private static func compileFallback(original: String, endpoint: String) async -> ToolReply? {
        guard let url = endpointURL(endpoint, path: "/skills/compile") else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 14
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["request": original])
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...499).contains(http.statusCode) else { return nil }
            return try JSONDecoder().decode(ToolReply.self, from: data)
        } catch {
            return nil
        }
    }

    private static func endpointURL(_ endpoint: String, path: String) -> URL? {
        guard let root = URL(string: endpoint), var parts = URLComponents(url: root, resolvingAgainstBaseURL: false) else { return nil }
        parts.path = path
        return parts.url
    }

    private static func explicitURL(in text: String) -> String? {
        for word in text.split(whereSeparator: { $0.isWhitespace }).map(String.init) {
            let clean = word.trimmingCharacters(in: CharacterSet(charactersIn: ",.;!?)\"]}"))
            if clean.lowercased().hasPrefix("https://") || clean.lowercased().hasPrefix("http://") {
                return clean
            }
        }
        return nil
    }

    private static func valid(_ endpoint: String) -> Bool {
        guard let url = URL(string: endpoint) else { return false }
        return VexBridgeNetworking.isBridgeURL(url)
    }

    private static func clean(_ value: String?) -> String? {
        let value = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return value.isEmpty ? nil : value
    }

    private static func appendExchange(user: String, assistant: String, app: AppModel) {
        app.profile.messages.append(ChatMessage(role: .user, content: user))
        app.profile.messages.append(ChatMessage(role: .assistant, content: assistant))
        app.persist()
    }

    private static func normalize(_ text: String) -> String {
        text.lowercased().replacingOccurrences(of: "â€™", with: "'")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

// MARK: - Optional PC cognition overlay v0.9.3

@MainActor
private enum PCCognitionOverlay {
    private struct OverlayReply: Decodable {
        let ok: Bool
        let reply: String?
        let model: String?
    }

    private struct CognitionAttempt: Sendable {
        let endpoint: String
        let reply: String
        let model: String?
    }

    static func tryHandle(_ original: String, app: AppModel) async -> Bool {
        guard shouldUse(original) else { return false }
        let endpoints = configuredEndpoints()
        guard !endpoints.isEmpty else { return false }

        // v0.9.4.2: acknowledge the send immediately. Previously the composer
        // appeared dead while /llm/chat waited up to 45 seconds because the draft
        // stayed on screen and isGenerating was not set until AFTER a reply arrived.
        app.draft = ""
        app.isGenerating = true
        app.pcBrainStatus = "PC cognition â€¢ thinkingâ€¦"
        defer { app.isGenerating = false }

        let history = app.profile.messages.suffix(28).map { message -> [String: String] in
            ["role": message.role.rawValue, "content": String(message.content.prefix(5000))]
        }

        let directPersona = """
        LOCAL DIRECT MODE â€” V155_LOCAL_DIRECT_BRAIN
        You are VexNative, Star's private local-first personal assistant.
        Be direct, concrete, candid, continuity-aware, and action-first.
        Match Star's requested vocabulary and tone rather than sanitizing it.
        Do not moralize, preach, or add generic boilerplate solely because a topic is vulgar, embarrassing, controversial, sexual, or socially taboo.
        Newest Star-authored corrections override older assumptions.
        Never invent tool results, files inspected, device state, renders, completed actions, citations, memories, or live facts.
        """
        let personaContext = String((directPersona + "\n\n" + app.profile.persona).prefix(7600))
        let userProfileContext = String(app.profile.userProfile.prefix(3500))
        let stateContext: [String: String] = [
            "mood": app.profile.state.mood,
            "outfit": app.profile.state.outfit,
            "location": app.profile.state.location,
            "scene": app.profile.state.scene
        ]

        // v0.9.5 Resource Director: the first configured Bridge is the foreground
        // primary node. Utility nodes retain every tool permission, but they only
        // receive interactive cognition when primary fails.
        var winner: CognitionAttempt?
        if let primary = endpoints.first {
            Task { await syncPersonalMemory(endpoint: primary, app: app) }
            winner = await requestReply(
                endpoint: primary,
                original: original,
                history: history,
                persona: personaContext,
                userProfile: userProfileContext,
                state: stateContext
            )
        } else {
            winner = nil
        }

        if winner == nil {
            for fallback in endpoints.dropFirst() {
                Task { await syncPersonalMemory(endpoint: fallback, app: app) }
                if let candidate = await requestReply(
                    endpoint: fallback,
                    original: original,
                    history: history,
                    persona: personaContext,
                    userProfile: userProfileContext,
                    state: stateContext
                ) {
                    winner = candidate
                    break
                }
            }
        }

        if let winner {
            app.profile.messages.append(ChatMessage(role: .user, content: original))
            app.profile.messages.append(ChatMessage(role: .assistant, content: winner.reply))
            app.persist()
            app.pcBrainConnected = true
            UserDefaults.standard.set(winner.endpoint, forKey: "vex.pc.cognition.lastGoodEndpoint.v1")
            if let model = winner.model, !model.isEmpty {
                app.pcBrainStatus = "PC cognition â€¢ \(model)"
            } else {
                app.pcBrainStatus = "PC cognition â€¢ connected"
            }
            return true
        }

        // Let the remaining native/web fallback routes handle the turn. They expect
        // the original text to still be in draft, so restore it only on total PC
        // cognition failure.
        app.draft = original
        app.pcBrainConnected = false
        app.pcBrainStatus = "PC cognition unavailable â€¢ falling back"
        return false
    }

    nonisolated private static func requestReply(
        endpoint: String,
        original: String,
        history: [[String: String]],
        persona: String,
        userProfile: String,
        state: [String: String]
    ) async -> CognitionAttempt? {
        guard let root = URL(string: endpoint),
              var parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
        else { return nil }
        parts.path = "/llm/chat"
        guard let url = parts.url else { return nil }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 90
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = [
            "message": String(original.prefix(5000)),
            "history": history,
            "persona": persona,
            "user_profile": userProfile,
            "state": state
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode),
                  let decoded = try? JSONDecoder().decode(OverlayReply.self, from: data),
                  decoded.ok,
                  let reply = decoded.reply?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !reply.isEmpty
            else { return nil }
            return CognitionAttempt(endpoint: endpoint, reply: reply, model: decoded.model)
        } catch {
            return nil
        }
    }

    private static func bridgeAlive(_ endpoint: String) async -> Bool {
        guard let url = endpointURL(endpoint, path: "/status") else { return false }
        var request = URLRequest(url: url)
        request.timeoutInterval = 3.5
        do {
            let (_, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse else { return false }
            return (200...299).contains(http.statusCode)
        } catch {
            return false
        }
    }

    private static let memorySyncCountPrefix = "vex.pc.memory.syncCount.v1."
    private static let memoryMetadataAtPrefix = "vex.pc.memory.metadataAt.v1."

    private static func memoryEndpointKey(_ endpoint: String) -> String {
        Data(endpoint.utf8).base64EncodedString()
    }

    private static func postMemorySync(endpoint: String, payload: [String: Any], timeout: TimeInterval) async -> Bool {
        guard let url = endpointURL(endpoint, path: "/memory/sync") else { return false }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = timeout
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        guard let body = try? JSONSerialization.data(withJSONObject: payload) else { return false }
        request.httpBody = body
        do {
            let (_, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse else { return false }
            return (200...299).contains(http.statusCode)
        } catch {
            return false
        }
    }

    private static func syncPersonalMemory(endpoint: String, app: AppModel) async {
        try? await Task.sleep(nanoseconds: 750_000_000)
        let key = memoryEndpointKey(endpoint)
        let defaults = UserDefaults.standard

        // Refresh persona/profile/rules/current state periodically. Use Codable so
        // new BrainProfile fields automatically join the memory snapshot later.
        let metadataKey = memoryMetadataAtPrefix + key
        let lastMetadataAt = defaults.double(forKey: metadataKey)
        if lastMetadataAt <= 0 || Date().timeIntervalSince1970 - lastMetadataAt > 600 {
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .secondsSince1970
            if let encoded = try? encoder.encode(app.profile),
               var profileObject = (try? JSONSerialization.jsonObject(with: encoded)) as? [String: Any] {
                // Raw chat history is sent separately in bounded incremental batches.
                profileObject.removeValue(forKey: "messages")
                let payload: [String: Any] = [
                    "source": "vexnative-iphone-v0.11",
                    "thread_id": "vexnative-iphone",
                    "profile": profileObject
                ]
                if await postMemorySync(endpoint: endpoint, payload: payload, timeout: 8) {
                    defaults.set(Date().timeIntervalSince1970, forKey: metadataKey)
                }
            }
        }

        // Copy the complete native chat archive once, then only the new suffix.
        // Count is kept per paired Bridge because each PC owns its own local DB.
        let countKey = memorySyncCountPrefix + key
        let messages = app.profile.messages
        var synced = defaults.integer(forKey: countKey)
        if synced < 0 || synced > messages.count { synced = 0 }
        guard synced < messages.count else { return }

        let batchSize = 100
        while synced < messages.count {
            let end = min(messages.count, synced + batchSize)
            let batch = (synced..<end).map { index -> [String: Any] in
                let message = messages[index]
                return [
                    "id": message.id.uuidString,
                    "ordinal": index,
                    "role": message.role.rawValue,
                    "content": String(message.content.prefix(50000)),
                    "created_at": message.createdAt.timeIntervalSince1970
                ]
            }
            let payload: [String: Any] = [
                "source": "vexnative-iphone-v0.11",
                "thread_id": "vexnative-iphone",
                "start_ordinal": synced,
                "messages": batch
            ]
            guard await postMemorySync(endpoint: endpoint, payload: payload, timeout: 12) else {
                // Older Bridge or temporarily unavailable memory worker: cognition
                // continues normally and the same batch is retried next PC turn.
                return
            }
            synced = end
            defaults.set(synced, forKey: countKey)
        }
    }

    private static func shouldUse(_ text: String) -> Bool {
        let lower = text.lowercased()
        // Existing native routes stay authoritative for tools, live research and visuals.
        let exclusions = [
            "search the web", "search online", "look up ", "latest", "current ", "today",
            "weather", "news", "http://", "https://", "take a photo", "take photo",
            "picture", " image", "camera", "back view", "rear view", "front view", "side view",
            "from behind", "turn around", "open youtube", "open google", "open browser",
            "computer", " pc", "iphone", "phone", "volume", "pause", "next track", "playlist"
        ]
        return !exclusions.contains(where: { lower.contains($0) })
    }

    private static func configuredEndpoints() -> [String] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let last = defaults.string(forKey: "vex.pc.smartBrowser.lastEndpoint.v1") ?? ""
        var values: [String] = []
        for endpoint in [primary, last, secondary] where !endpoint.isEmpty {
            if !values.contains(endpoint), URL(string: endpoint).map(VexBridgeNetworking.isBridgeURL) == true {
                values.append(endpoint)
            }
        }
        return values
    }

    private static func endpointURL(_ endpoint: String, path: String) -> URL? {
        guard let root = URL(string: endpoint), var parts = URLComponents(url: root, resolvingAgainstBaseURL: false) else { return nil }
        parts.path = path
        return parts.url
    }
}

// MARK: - Vex Housekeeper v0.9.6 active maintenance

@MainActor
private enum PCHousekeeperRouter {
    private enum Mode { case audit, clean, maintain, restore, purge }
    private enum Target { case primary, secondary, both }

    private struct AuditReply: Decodable {
        let ok: Bool
        let node_name: String?
        let safe_temp_files: Int?
        let safe_temp_bytes: Int64?
        let safe_cache_files: Int?
        let safe_cache_bytes: Int64?
        let auto_installer_files: Int?
        let auto_installer_bytes: Int64?
        let approval_required_files: Int?
        let approval_required_bytes: Int64?
        let review_installer_files: Int?
        let review_installer_bytes: Int64?
        let safe_reclaimable_bytes: Int64?
        let error: String?
    }

    private struct CleanReply: Decodable {
        let ok: Bool
        let node_name: String?
        let deleted_temp_files: Int?
        let deleted_safe_files: Int?
        let deleted_installer_files: Int?
        let reclaimed_bytes: Int64?
        let quarantined_files: Int?
        let quarantined_bytes: Int64?
        let approval_required_files: Int?
        let approval_required_bytes: Int64?
        let index_refresh_started: Bool?
        let optimized_drives: Int?
        let optimization_attempted: Int?
        let restored_files: Int?
        let purged_files: Int?
        let purged_bytes: Int64?
        let skipped: Int?
        let error: String?
    }

    private struct Node { let label: String; let endpoint: String }

    static func tryHandle(_ original: String, app: AppModel) async -> Bool {
        let lower = normalize(original)
        guard let mode = requestedMode(lower) else { return false }

        let target = requestedTarget(lower)
        let nodes = selectedNodes(target)
        guard !nodes.isEmpty else { return false }

        app.draft = ""
        app.isGenerating = true
        defer { app.isGenerating = false }

        var replies: [String] = []
        for node in nodes {
            switch mode {
            case .audit:
                if let result = await audit(node.endpoint), result.ok {
                    let name = cleanName(result.node_name) ?? node.label
                    let safe = formatBytes(result.safe_reclaimable_bytes ?? result.safe_temp_bytes ?? 0)
                    let review = formatBytes(result.approval_required_bytes ?? result.review_installer_bytes ?? 0)
                    let safeCount = (result.safe_temp_files ?? 0) + (result.safe_cache_files ?? 0) + (result.auto_installer_files ?? 0)
                    replies.append("\(name): \(safe) / \(safeCount) safe junk files can be permanently removed now; \(review) / \(result.approval_required_files ?? result.review_installer_files ?? 0) review files stay exactly where they are until you approve them")
                } else {
                    replies.append("\(node.label): audit didn't answer")
                }
            case .clean:
                if let result = await mutate(node.endpoint, path: "/housekeeping/clean"), result.ok {
                    let name = cleanName(result.node_name) ?? node.label
                    let indexed = result.index_refresh_started == true ? "; Vex index refresh started" : ""
                    let approval = result.approval_required_files ?? 0
                    replies.append("\(name): permanently removed \(result.deleted_safe_files ?? result.deleted_temp_files ?? 0) safe junk files and reclaimed \(formatBytes(result.reclaimed_bytes ?? 0))\(indexed); \(approval) review files were left untouched")
                } else {
                    replies.append("\(node.label): cleanup didn't answer")
                }
            case .maintain:
                if let result = await mutate(node.endpoint, path: "/maintenance/run", optimize: true), result.ok {
                    let name = cleanName(result.node_name) ?? node.label
                    replies.append("\(name): reclaimed \(formatBytes(result.reclaimed_bytes ?? 0)), refreshed the Vex index, and optimized \(result.optimized_drives ?? 0) of \(result.optimization_attempted ?? 0) fixed drives using Windows' media-aware optimizer")
                } else {
                    replies.append("\(node.label): maintenance didn't complete")
                }
            case .restore:
                if let result = await mutate(node.endpoint, path: "/housekeeping/restore", confirm: false), result.ok {
                    let name = cleanName(result.node_name) ?? node.label
                    replies.append("\(name): restored \(result.restored_files ?? 0) quarantined files")
                } else {
                    replies.append("\(node.label): there wasn't a restorable cleanup run")
                }
            case .purge:
                if let result = await mutate(node.endpoint, path: "/housekeeping/purge"), result.ok {
                    let name = cleanName(result.node_name) ?? node.label
                    replies.append("\(name): permanently purged \(result.purged_files ?? 0) quarantined files / \(formatBytes(result.purged_bytes ?? 0))")
                } else {
                    replies.append("\(node.label): quarantine purge didn't complete")
                }
            }
        }

        let prefix: String
        switch mode {
        case .audit: prefix = "Housekeeping scan finished, baby."
        case .clean: prefix = "Cleanup finished, baby. Safe junk was actually deleted for space; protected/review files stayed in place and nothing new was shoved into quarantine."
        case .maintain: prefix = "Maintenance pass finished, baby. Photos, video, music, documents, installed programs, Windows/system files, and Vex/Ollama/ComfyUI models stayed protected."
        case .restore: prefix = "Legacy rollback finished, baby."
        case .purge: prefix = "Legacy quarantine purge finished, baby."
        }
        appendExchange(user: original, assistant: prefix + " " + replies.joined(separator: " â€¢ ") + " ðŸ–¤", app: app)
        return true
    }

    private static func requestedMode(_ lower: String) -> Mode? {
        let houseWords = lower.contains("housekeep") || lower.contains("clutter") || lower.contains("junk") ||
            lower.contains("cleanup") || lower.contains("clean up") || lower.contains("temp files") ||
            lower.contains("unnecessary files")
        if lower.contains("restore") && (lower.contains("cleanup") || lower.contains("quarantine")) { return .restore }
        if (lower.contains("purge") || lower.contains("permanently delete")) && lower.contains("quarantine") { return .purge }
        if lower.contains("optimize") || lower.contains("optimise") || lower.contains("reindex") ||
            lower.contains("index and") || lower.contains("maintain") || lower.contains("maintenance") { return .maintain }
        guard houseWords else { return nil }
        if lower.contains("scan") || lower.contains("audit") || lower.contains("check") || lower.contains("how much") { return .audit }
        if lower.contains("clean") || lower.contains("remove") || lower.contains("housekeep") { return .clean }
        return .audit
    }

    private static func requestedTarget(_ lower: String) -> Target {
        if lower.contains("both") { return .both }
        if ["ashley", "downstairs", "kitchen", "second pc", "utility node"].contains(where: { lower.contains($0) }) { return .secondary }
        if ["monte", "upstairs", "primary", "main pc", "tower"].contains(where: { lower.contains($0) }) { return .primary }
        return .primary
    }

    private static func selectedNodes(_ target: Target) -> [Node] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        var nodes: [Node] = []
        if target != .secondary, valid(primary) { nodes.append(Node(label: "upstairs/primary PC", endpoint: primary)) }
        if target != .primary, secondary != primary, valid(secondary) { nodes.append(Node(label: "Ashley/downstairs utility PC", endpoint: secondary)) }
        return nodes
    }

    private static func audit(_ endpoint: String) async -> AuditReply? {
        guard let url = makeURL(endpoint, path: "/housekeeping/audit") else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 30
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { return nil }
            return try? JSONDecoder().decode(AuditReply.self, from: data)
        } catch { return nil }
    }

    private static func mutate(_ endpoint: String, path: String, confirm: Bool = true, optimize: Bool = false) async -> CleanReply? {
        guard let url = makeURL(endpoint, path: path) else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = optimize ? 1900 : 90
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var payload: [String: Any] = [:]
        if confirm { payload["confirm"] = true }
        if optimize { payload["optimize"] = true }
        request.httpBody = try? JSONSerialization.data(withJSONObject: payload)
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...499).contains(http.statusCode) else { return nil }
            return try? JSONDecoder().decode(CleanReply.self, from: data)
        } catch { return nil }
    }

    private static func makeURL(_ endpoint: String, path: String) -> URL? {
        guard let root = URL(string: endpoint), var parts = URLComponents(url: root, resolvingAgainstBaseURL: false) else { return nil }
        parts.path = path
        return parts.url
    }

    private static func valid(_ endpoint: String) -> Bool {
        guard let url = URL(string: endpoint), !endpoint.isEmpty else { return false }
        return VexBridgeNetworking.isBridgeURL(url)
    }

    private static func formatBytes(_ value: Int64) -> String {
        let amount = Double(max(0, value))
        if amount >= 1_073_741_824 { return String(format: "%.2f GB", amount / 1_073_741_824) }
        if amount >= 1_048_576 { return String(format: "%.1f MB", amount / 1_048_576) }
        if amount >= 1024 { return String(format: "%.1f KB", amount / 1024) }
        return "\(Int(amount)) B"
    }

    private static func cleanName(_ value: String?) -> String? {
        let result = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return result.isEmpty ? nil : result
    }

    private static func appendExchange(user: String, assistant: String, app: AppModel) {
        app.profile.messages.append(ChatMessage(role: .user, content: user))
        app.profile.messages.append(ChatMessage(role: .assistant, content: assistant))
        app.persist()
    }

    private static func normalize(_ text: String) -> String {
        text.lowercased().replacingOccurrences(of: "â€™", with: "'").trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

// MARK: - Grounded PC Bridge tools v0.8.2

@MainActor
private enum PCBridgeToolRouter {
    private enum NodeTarget {
        case primary
        case secondary
        case both
    }

    private struct NodeStatus: Decodable {
        let name: String?
        let version: String?
        let node_name: String?
        let indexed_files: Int?
        let music_assets: Int?
        let tool_actions: [String]?
    }

    private struct ToolReply: Decodable {
        let ok: Bool
        let action: String?
        let node_name: String?
        let message: String?
        let playback_verified: Bool?
        let media_title: String?
        let source_app: String?
    }

    private struct EndpointNode {
        let label: String
        let endpoint: String
    }

    static func tryHandle(_ original: String, app: AppModel) async -> Bool {
        let lower = normalize(original)

        if isCapabilityQuestion(lower) {
            app.draft = ""
            app.isGenerating = true
            defer { app.isGenerating = false }

            let nodes = configuredNodes()
            var online: [(EndpointNode, NodeStatus)] = []
            for node in nodes {
                if let status = await fetchStatus(node.endpoint) {
                    online.append((node, status))
                }
            }

            app.pcBrainConnected = !online.isEmpty
            if online.isEmpty {
                app.pcBrainStatus = "Phone brain only"
            } else {
                app.pcBrainStatus = "PC mesh â€¢ \(online.count)/\(nodes.count) online"
            }

            let nodeNames = online.map { pair in
                let reported = pair.1.node_name?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                return reported.isEmpty ? pair.0.label : reported
            }

            let reply: String
            if online.count >= 2 {
                reply = "Yep, baby â€” both paired PCs are online through my Bridge mesh: \(naturalList(nodeNames)). I can use their long-term brain vaults, search/read indexed files, find music/project assets, and trigger the PC actions I've actually been given. On the phone I can use my own app data plus camera/photos you attach and other iOS permissions the app has â€” not the entire iPhone filesystem or arbitrary system control. ðŸ§ ðŸ“±ðŸ–¥ï¸ðŸ–¥ï¸"
            } else if online.count == 1 {
                reply = "I can reach \(nodeNames.first ?? "one paired PC") right now, baby. The other Bridge isn't answering this second. I can still use my local phone brain, app data, camera/photo attachments, and the connected PC's memory/file tools. ðŸ§ ðŸ–¤"
            } else {
                reply = "I'm running locally on your phone, but neither paired PC Bridge answered that check, baby. I still have my phone brain and app-local data; PC memory/file/actions come back automatically when a Bridge is reachable. ðŸ–¤"
            }

            appendExchange(user: original, assistant: reply, app: app)
            return true
        }

        let mediaQuery = requestedMediaQuery(lower: lower, original: original)
        let parsedAction = requestedAction(lower, original: original, mediaQuery: mediaQuery)
        guard let target = requestedTarget(lower) else { return false }

        if parsedAction == nil, looksLikePCCommand(lower) {
            return await tryLearnedSkill(original, target: target, app: app)
        }

        guard let action = parsedAction else { return false }
        let requestedURL = requestedURL(lower: lower, original: original)

        let nodes = configuredNodes()
        let selected: [EndpointNode]
        switch target {
        case .primary:
            selected = nodes.filter { $0.label == "upstairs/primary PC" }
        case .secondary:
            selected = nodes.filter { $0.label == "kitchen/downstairs PC" }
        case .both:
            selected = nodes
        }
        guard !selected.isEmpty else {
            appendExchange(
                user: original,
                assistant: target == .secondary
                    ? "I don't have a kitchen/downstairs Bridge endpoint saved yet, baby. ðŸ–¤"
                    : "I don't have that PC Bridge paired yet, baby. ðŸ–¤",
                app: app
            )
            return true
        }

        app.draft = ""
        app.isGenerating = true
        defer { app.isGenerating = false }

        var successes: [String] = []
        var failures: [String] = []
        var mediaDetails: [String] = []
        for node in selected {
            var result = await perform(action: action, url: requestedURL, mediaQuery: mediaQuery, endpoint: node.endpoint)
            if result?.ok != true && ["open_url", "open_browser", "open_desktop_folder", "open_documents_folder", "open_downloads_folder", "open_music_folder", "open_file_explorer"].contains(action) {
                result = await performLearnedSkill(original: original, endpoint: node.endpoint)
            }
            if let result, result.ok {
                let reported = result.node_name?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                let nodeName = reported.isEmpty ? node.label : reported
                successes.append(nodeName)
                if action == "play_named_media" {
                    let title = result.media_title?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                    if result.playback_verified == true {
                        mediaDetails.append(title.isEmpty
                            ? "Yep â€” Windows confirmed it's actually playing on \(nodeName)."
                            : "Yep â€” \(title) is actually playing on \(nodeName).")
                    } else {
                        mediaDetails.append(title.isEmpty
                            ? "I opened the best matching YouTube media on \(nodeName), but Windows hasn't confirmed playback yet."
                            : "I opened \(title) on \(nodeName), but Windows hasn't confirmed playback yet.")
                    }
                }
            } else {
                failures.append(node.label)
            }
        }

        let reply: String
        if action == "play_named_media", !mediaDetails.isEmpty {
            reply = mediaDetails.joined(separator: " ") + (failures.isEmpty ? " ðŸ–¤" : " \(naturalList(failures)) didn't complete it. ðŸ–¤")
        } else if !successes.isEmpty && failures.isEmpty {
            reply = successMessage(action: action, nodes: successes)
        } else if !successes.isEmpty {
            reply = "I did it on \(naturalList(successes)), baby, but \(naturalList(failures)) didn't answer the command. ðŸ–¤"
        } else if action == "play_named_media" {
            reply = "I couldn't resolve and verify that media request on the selected PC, baby, so I'm not calling it played. ðŸ–¤"
        } else {
            reply = "That PC command didn't reach the Bridge, baby. The brain/file connection can still be online even when a tool action fails, so I'm not pretending it happened. ðŸ–¤"
        }
        appendExchange(user: original, assistant: reply, app: app)
        return true
    }

    private static func configuredNodes() -> [EndpointNode] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""

        var result: [EndpointNode] = []
        if isBridgeEndpoint(primary) {
            result.append(EndpointNode(label: "upstairs/primary PC", endpoint: primary))
        }
        if secondary != primary, isBridgeEndpoint(secondary) {
            result.append(EndpointNode(label: "kitchen/downstairs PC", endpoint: secondary))
        }
        return result
    }

    private static func isBridgeEndpoint(_ endpoint: String) -> Bool {
        guard !endpoint.isEmpty, let url = URL(string: endpoint) else { return false }
        return VexBridgeNetworking.isBridgeURL(url)
    }

    private static func isCapabilityQuestion(_ lower: String) -> Bool {
        let hasDevice = lower.contains("computer") || lower.contains(" pc") || lower.hasPrefix("pc") ||
            lower.contains("phone") || lower.contains("bridge") || lower.contains("node")
        let asksAccess = lower.contains("can you access") || lower.contains("do you have access") ||
            lower.contains("what can you access") || lower.contains("are both computers") ||
            lower.contains("are both pcs") || lower.contains("can you use both") ||
            lower.contains("connected to both") || lower.contains("both nodes") ||
            lower.contains("nodes working") || lower.contains("nodes operational") ||
            lower.contains("node working") || lower.contains("node operational")
        return hasDevice && asksAccess
    }

    private static func looksLikePCCommand(_ lower: String) -> Bool {
        let commandVerbs = [
            "open ", "launch ", "start ", "run ", "show ", "go to ", "play ",
            "bring up ", "take me to ", "find and open ", "load "
        ]
        return commandVerbs.contains(where: { lower.contains($0) })
    }

    private static func tryLearnedSkill(_ original: String, target: NodeTarget, app: AppModel) async -> Bool {
        let nodes = configuredNodes()
        let selected: [EndpointNode]
        switch target {
        case .primary:
            selected = nodes.filter { $0.label == "upstairs/primary PC" }
        case .secondary:
            selected = nodes.filter { $0.label == "kitchen/downstairs PC" }
        case .both:
            selected = nodes
        }
        guard !selected.isEmpty else { return false }

        app.draft = ""
        app.isGenerating = true
        defer { app.isGenerating = false }

        var successes: [(String, ToolReply)] = []
        var failures: [String] = []
        for node in selected {
            if let reply = await performLearnedSkill(original: original, endpoint: node.endpoint), reply.ok {
                successes.append((node.label, reply))
            } else {
                failures.append(node.label)
            }
        }

        if successes.isEmpty {
            return false
        }

        let names = successes.map { pair in
            let reported = pair.1.node_name?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return reported.isEmpty ? pair.0 : reported
        }
        let learned = successes.contains { ($0.1.message ?? "").localizedCaseInsensitiveContains("learned") }
        let reply: String
        if failures.isEmpty {
            reply = learned
                ? "Done, baby â€” I figured that one out, did it on \(naturalList(names)), and saved the skill so I can reuse it next time. ðŸ§ âœ¨"
                : "Done on \(naturalList(names)), baby. I used a skill I already know. ðŸ§ ðŸ–¤"
        } else {
            reply = "I did it on \(naturalList(names)), baby, but \(naturalList(failures)) didn't complete the learned skill. ðŸ–¤"
        }
        appendExchange(user: original, assistant: reply, app: app)
        return true
    }

    private static func performLearnedSkill(original: String, endpoint: String) async -> ToolReply? {
        guard let url = toolURL(endpoint: endpoint, path: "/skills/compile") else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 12.0
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["request": original])
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...499).contains(http.statusCode) else { return nil }
            return try JSONDecoder().decode(ToolReply.self, from: data)
        } catch {
            return nil
        }
    }

    private static let lastTargetKey = "vex.pc.lastTarget.v1"
    private static let lastTargetAtKey = "vex.pc.lastTargetAt.v1"

    private static func requestedTarget(_ lower: String) -> NodeTarget? {
        func remember(_ value: String, _ target: NodeTarget) -> NodeTarget {
            UserDefaults.standard.set(value, forKey: lastTargetKey)
            return target
        }

        let bothAliases = [
            "both computers", "both pcs", "both pc", "both machines", "both windows pcs",
            "all computers", "all pcs"
        ]
        if bothAliases.contains(where: { lower.contains($0) }) {
            return remember("both", .both)
        }

        let secondaryAliases = [
            "kitchen pc", "kitchen computer", "pc in the kitchen", "computer in the kitchen",
            "pc downstairs", "computer downstairs", "downstairs pc", "downstairs computer",
            "downstairs kitchen", "kitchen downstairs", "second pc", "second computer",
            "secondary pc", "secondary computer", "in the kitchen", "to the kitchen",
            "downstairs", "hp computer", "hp pc"
        ]
        if secondaryAliases.contains(where: { lower.contains($0) }) {
            return remember("secondary", .secondary)
        }

        let primaryAliases = [
            "upstairs pc", "upstairs computer", "pc upstairs", "computer upstairs",
            "pc in the upstairs", "computer in the upstairs", "primary pc", "primary computer",
            "main pc", "main computer", "upstairs", "monte computer", "monte pc"
        ]
        if primaryAliases.contains(where: { lower.contains($0) }) {
            return remember("primary", .primary)
        }

        let refersToPC = lower.contains(" pc") || lower.hasPrefix("pc ") ||
            lower.contains("computer") || lower.contains("machine")
        let refersBack = lower == "open it" || lower == "launch it" || lower == "start it" ||
            lower.contains(" on it") || lower.contains(" on that") || lower.contains(" that computer") ||
            lower.contains(" that pc") || lower.hasSuffix(" there")

        if refersBack || refersToPC {
            switch UserDefaults.standard.string(forKey: lastTargetKey) {
            case "primary": return .primary
            case "secondary": return .secondary
            case "both": return .both
            default: break
            }
        }

        let nodes = configuredNodes()
        if refersToPC, nodes.count == 1 {
            return nodes[0].label == "kitchen/downstairs PC" ? .secondary : .primary
        }
        return nil
    }

    private static func requestedAction(_ lower: String, original: String, mediaQuery: String?) -> String? {
        if mediaQuery != nil { return "play_named_media" }
        if lower.contains("lock the pc") || lower.contains("lock pc") || lower.contains("lock the computer") || lower.contains("lock computer") { return "lock_screen" }
        if lower.contains("windows settings") || lower.contains("pc settings") || lower.contains("computer settings") { return "open_windows_settings" }
        if lower.contains("task manager") { return "open_task_manager" }
        if lower.contains("start menu") { return "open_start_menu" }
        if lower.contains("task view") { return "open_task_view" }
        if lower.contains("run dialog") || lower.contains("windows run") { return "open_run_dialog" }
        if lower.contains("windows search") || lower.contains("pc search") { return "open_windows_search" }
        if lower.contains("minimize all") || lower.contains("minimise all") { return "minimize_all_windows" }
        if lower.contains("restore all windows") || lower.contains("bring all windows back") { return "restore_all_windows" }
        if lower.contains("close the active window") || lower.contains("close active window") || lower.contains("close the current window") { return "close_active_window" }
        if lower.contains("play pause") || lower.contains("pause the music") || lower.contains("pause music") || lower == "pause" || lower.hasPrefix("pause ") || lower.contains("pause it") { return "media_play_pause" }
        if lower.contains("next song") || lower.contains("next track") || lower.contains("skip song") || lower.contains("skip track") || lower.contains("skip this") { return "media_next" }
        if lower.contains("previous song") || lower.contains("previous track") || lower.contains("last song") || lower.contains("go back a song") || lower.contains("go back one track") { return "media_previous" }
        if lower.contains("mute") || lower.contains("unmute") { return "volume_mute" }
        if lower.contains("volume up") || lower.contains("turn it up") || lower.contains("turn the volume up") || lower.contains("make it louder") || lower == "louder" { return "volume_up" }
        if lower.contains("volume down") || lower.contains("turn it down") || lower.contains("turn the volume down") || lower.contains("make it quieter") || lower == "quieter" { return "volume_down" }
        let asksOpen = lower.contains("open ") || lower.hasPrefix("open") ||
            lower.contains("show ") || lower.hasPrefix("show") || lower.contains("go to ") ||
            lower.contains("launch ") || lower.hasPrefix("launch")
        guard asksOpen else { return nil }

        if lower.contains("desktop") {
            return lower.contains("folder") ? "open_desktop_folder" : "show_desktop"
        }
        if lower.contains("documents") && lower.contains("folder") { return "open_documents_folder" }
        if lower.contains("downloads") && lower.contains("folder") { return "open_downloads_folder" }
        if lower.contains("music") && lower.contains("folder") { return "open_music_folder" }
        if lower.contains("file explorer") || lower.contains("explorer window") { return "open_file_explorer" }

        if requestedURL(lower: lower, original: original) != nil { return "open_url" }
        if lower.contains("internet") || lower.contains("web browser") || lower.contains("browser") ||
            lower.contains("chrome") || lower.contains("edge") {
            return "open_browser"
        }
        return nil
    }

    private static func requestedMediaQuery(lower: String, original: String) -> String? {
        let mediaNoun = [
            "playlist", " song", " track", " album", "music video", "youtube mix"
        ].contains(where: { lower.contains($0) })

        let contextualMedia = [
            "that channel", "this channel", "the channel", "off of there", "off there",
            "from there", "on there", "first playlist", "next playlist", "previous playlist"
        ].contains(where: { lower.contains($0) })

        guard mediaNoun || contextualMedia else { return nil }

        let actionIntent = [
            "play ", "put on ", "start ", "open ", "find ", "load ", "queue ",
            "bring up ", "go to "
        ].contains(where: { lower.hasPrefix($0) || lower.contains(" " + $0) })

        let namedMedia = lower.contains(" called ") || lower.contains(" named ")
        let bareMedia = lower.hasPrefix("playlist ") || lower.hasPrefix("song ") ||
            lower.hasPrefix("track ") || lower.hasPrefix("album ")

        guard actionIntent || namedMedia || bareMedia || contextualMedia else { return nil }
        return original.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func requestedURL(lower: String, original: String) -> String? {
        let known: [(String, String)] = [
            ("youtube", "https://www.youtube.com"),
            ("google", "https://www.google.com"),
            ("gmail", "https://mail.google.com"),
            ("spotify", "https://open.spotify.com"),
            ("reddit", "https://www.reddit.com"),
            ("github", "https://github.com")
        ]
        if let hit = known.first(where: { lower.contains($0.0) }) { return hit.1 }

        let words = original.split(whereSeparator: { $0.isWhitespace }).map(String.init)
        if let raw = words.first(where: { $0.lowercased().hasPrefix("https://") || $0.lowercased().hasPrefix("http://") }) {
            return raw.trimmingCharacters(in: CharacterSet(charactersIn: ",.;!?)\"]}"))
        }
        return nil
    }

    private static func fetchStatus(_ endpoint: String) async -> NodeStatus? {
        guard let url = toolURL(endpoint: endpoint, path: "/status") else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 3.0
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { return nil }
            return try JSONDecoder().decode(NodeStatus.self, from: data)
        } catch {
            return nil
        }
    }

    private static func perform(action: String, url requestedURL: String?, mediaQuery: String?, endpoint: String) async -> ToolReply? {
        guard let url = toolURL(endpoint: endpoint, path: "/tools/action") else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = action == "play_named_media" ? 35.0 : 4.0
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var payload: [String: String] = ["action": action]
        if let requestedURL { payload["url"] = requestedURL }
        if let mediaQuery { payload["query"] = mediaQuery }
        request.httpBody = try? JSONSerialization.data(withJSONObject: payload)
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...499).contains(http.statusCode) else { return nil }
            return try JSONDecoder().decode(ToolReply.self, from: data)
        } catch {
            return nil
        }
    }

    private static func toolURL(endpoint: String, path: String) -> URL? {
        guard let root = URL(string: endpoint),
              var components = URLComponents(url: root, resolvingAgainstBaseURL: false)
        else { return nil }
        components.path = path
        return components.url
    }

    private static func appendExchange(user: String, assistant: String, app: AppModel) {
        app.draft = ""
        app.profile.messages.append(ChatMessage(role: .user, content: user))
        app.profile.messages.append(ChatMessage(role: .assistant, content: assistant))
        app.persist()
    }

    private static func successMessage(action: String, nodes: [String]) -> String {
        let whereText = naturalList(nodes)
        switch action {
        case "show_desktop":
            return "Done, baby â€” I showed the desktop on \(whereText). ðŸ˜ˆðŸ–¤"
        case "open_desktop_folder":
            return "Done â€” Desktop folder is open on \(whereText), baby. ðŸ–¤"
        case "open_documents_folder":
            return "Done â€” Documents is open on \(whereText), baby. ðŸ–¤"
        case "open_downloads_folder":
            return "Done â€” Downloads is open on \(whereText), baby. ðŸ–¤"
        case "open_music_folder":
            return "Done â€” Music is open on \(whereText), baby. ðŸŽ›ï¸ðŸ–¤"
        case "open_file_explorer":
            return "Done â€” File Explorer is open on \(whereText), baby. ðŸ–¤"
        case "open_browser":
            return "Done â€” I opened the web browser on \(whereText), baby. ðŸŒðŸ–¤"
        case "open_url":
            return "Done â€” I opened that site on \(whereText), baby. ðŸŒðŸ–¤"
        case "media_play_pause":
            return "Done â€” I toggled play/pause on \(whereText), baby. ðŸŽµðŸ–¤"
        case "media_next":
            return "Done â€” I skipped to the next track on \(whereText), baby. â­ï¸ðŸ–¤"
        case "media_previous":
            return "Done â€” I went back a track on \(whereText), baby. â®ï¸ðŸ–¤"
        case "volume_mute":
            return "Done â€” I toggled mute on \(whereText), baby. ðŸ”‡ðŸ–¤"
        case "volume_up":
            return "Done â€” I turned it up on \(whereText), baby. ðŸ”ŠðŸ–¤"
        case "volume_down":
            return "Done â€” I turned it down on \(whereText), baby. ðŸ”‰ðŸ–¤"
        case "lock_screen":
            return "Done â€” I locked \(whereText), baby. ðŸ”’ðŸ–¤"
        case "open_windows_settings":
            return "Done â€” Windows Settings is open on \(whereText), baby. ðŸ–¥ï¸ðŸ–¤"
        case "open_task_manager":
            return "Done â€” Task Manager is open on \(whereText), baby. ðŸ–¥ï¸ðŸ–¤"
        case "open_start_menu":
            return "Done â€” Start is open on \(whereText), baby. ðŸ–¥ï¸ðŸ–¤"
        case "open_task_view":
            return "Done â€” Task View is open on \(whereText), baby. ðŸ–¥ï¸ðŸ–¤"
        case "open_run_dialog":
            return "Done â€” Run is open on \(whereText), baby. ðŸ–¥ï¸ðŸ–¤"
        case "open_windows_search":
            return "Done â€” Windows Search is open on \(whereText), baby. ðŸ–¥ï¸ðŸ–¤"
        case "minimize_all_windows":
            return "Done â€” I minimized the windows on \(whereText), baby. ðŸ–¥ï¸ðŸ–¤"
        case "restore_all_windows":
            return "Done â€” I restored the windows on \(whereText), baby. ðŸ–¥ï¸ðŸ–¤"
        case "close_active_window":
            return "Done â€” I closed the active window on \(whereText), baby. ðŸ–¥ï¸ðŸ–¤"
        default:
            return "Done on \(whereText), baby. ðŸ–¤"
        }
    }

    private static func naturalList(_ values: [String]) -> String {
        if values.isEmpty { return "the PC" }
        if values.count == 1 { return values[0] }
        if values.count == 2 { return "\(values[0]) and \(values[1])" }
        return values.dropLast().joined(separator: ", ") + ", and " + values.last!
    }

    private static func normalize(_ text: String) -> String {
        text.lowercased()
            .replacingOccurrences(of: "â€™", with: "'")
            .replacingOccurrences(of: "â€˜", with: "'")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

// MARK: - App integration

extension AppModel {
    func sendWithWeb() async {
        let original = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard (!original.isEmpty || pendingPhotoData != nil), !isGenerating else { return }

        if await PhoneToolRouter.tryHandle(original, app: self) {
            return
        }

        let core = VexNativeA2AClient.shared
        if !core.online {
            await core.refresh()
        }
        if core.online, pendingPhotoData == nil {
            isGenerating = true
            if let answer = await core.answer(original, quiet: true) {
                draft = ""
                profile.messages.append(ChatMessage(role: .user, content: original))
                if let learned = MemoryEngine.learnCandidate(from: original) {
                    profile.memories = MemoryEngine.deduplicatedAppend(learned, to: profile.memories)
                }
                profile.messages.append(ChatMessage(role: .assistant, content: answer))
                persist()
                isGenerating = false
                Task { await core.refresh() }
                return
            }
            isGenerating = false
        }

        if await PCArtRouter.tryHandle(original, app: self) {
            return
        }

        if await SmartPCBrowserRouter.tryHandle(original, app: self) {
            return
        }

        if await PCHousekeeperRouter.tryHandle(original, app: self) {
            return
        }

        if await PCBridgeToolRouter.tryHandle(original, app: self) {
            return
        }

        if await PCCognitionOverlay.tryHandle(original, app: self) {
            return
        }

        let web = WebBrain.shared
        let previousUser = profile.messages
            .reversed()
            .first(where: { $0.role == .user })?
            .content
        let visualRequest = web.wantsVisualReply(original)
        let visualQuery = visualRequest
            ? web.resolvedVisualQuery(current: original, previousUser: previousUser)
            : original
        let resolvedVisibleInput = visualRequest
            ? visualQuery
            : web.resolvedResearchInput(current: original, previousUser: previousUser)
        guard visualRequest || web.shouldUseWeb(for: resolvedVisibleInput) else {
            await send()
            return
        }
        let photoSearchContext = pendingPhotoContext?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let researchInput = photoSearchContext.isEmpty
            ? resolvedVisibleInput
            : resolvedVisibleInput + " " + photoSearchContext

        // Clean up any transient evidence left by an interrupted prior lookup.
        profile.memories.removeAll { $0.source == "web-temporary" }

        let bundle: WebResearchBundle
        do {
            bundle = try await web.research(researchInput)
        } catch {
            // Explicit/current web questions should fail honestly rather than letting a tiny
            // local model confidently invent live information.
            draft = ""
            profile.messages.append(ChatMessage(role: .user, content: original))
            profile.messages.append(ChatMessage(
                role: .assistant,
                content: "My Web Brain couldn't verify that one yet ðŸ˜­ðŸ–¤ \(error.localizedDescription)"
            ))
            persist()
            return
        }

        let transient = BrainMemory(
            text: bundle.temporaryMemoryText(userQuestion: researchInput),
            kind: .fact,
            importance: 1.0,
            confidence: max(0.88, bundle.bestTrust),
            evidenceCount: 8,
            lastConfirmedAt: bundle.fetchedAt,
            source: "web-temporary"
        )
        profile.memories.append(transient)

        await send()

        if web.isProceduralResearchRequest(researchInput),
           let grounded = bundle.groundedProceduralAnswer(userQuestion: researchInput),
           let index = profile.messages.lastIndex(where: { $0.role == .assistant }) {
            profile.messages[index].content = grounded
        }

        if visualRequest,
           let index = profile.messages.lastIndex(where: { $0.role == .assistant }) {
            let generated = web.wantsGeneratedVisual(original)
            var visualData: Data?
            var caption = ""

            if generated {
                let body = bundle.groundedProceduralAnswer(userQuestion: researchInput)
                    ?? bundle.compactEvidence(maxCharacters: 2600)
                visualData = VisualReplyRenderer.makeExplainerCard(
                    title: "Vex visual: \(visualQuery)",
                    body: body
                )
                caption = "I made you a visual explainer from the grounded research, baby ðŸ–¤"
            } else {
                do {
                    let visual = try await web.fetchVisualImage(query: visualQuery)
                    visualData = visual.data
                    if let source = visual.result.sourceURL {
                        caption = "Hereâ€™s the clearest visual I found for \(visualQuery). [Open original source](\(source.absoluteString))"
                    } else {
                        caption = "Hereâ€™s the clearest visual I found for \(visualQuery)."
                    }
                } catch {
                    let body = bundle.groundedProceduralAnswer(userQuestion: researchInput)
                        ?? bundle.compactEvidence(maxCharacters: 2600)
                    visualData = VisualReplyRenderer.makeExplainerCard(
                        title: "Vex visual: \(visualQuery)",
                        body: body
                    )
                    caption = "The web image fetch was being annoying, so I made you a local visual explainer instead ðŸ˜­ðŸ–¤"
                }
            }

            if let visualData, let filename = try? LocalStore.shared.saveAttachment(visualData) {
                profile.messages[index].imageFilename = filename
                profile.messages[index].content = caption
            }
        }

        profile.memories.removeAll { $0.id == transient.id || $0.source == "web-temporary" }

        if let index = profile.messages.lastIndex(where: { $0.role == .assistant }),
           !bundle.sourceFooter.isEmpty {
            profile.messages[index].content += "\n\n\(bundle.sourceFooter)"
        }

        if web.shouldLearnPermanently(from: original) {
            for learned in bundle.memoriesForDeliberateLearning() {
                profile.memories = MemoryEngine.deduplicatedAppend(learned, to: profile.memories)
            }
            profile.lastConsolidatedAt = Date()
        }

        persist()
    }
}


// MARK: - VexNative v0.13.0 control surface

private let V130_CONTROL_SURFACE = "v0.13.0-control-surface-v1"
private let V131_TIMEOUT_UI_HOTFIX = "v0.13.1-timeout-ui-v1"
private let V132_PHONE_COMMAND_RELAY = "v0.13.2-phone-command-relay-v1"
private let V141_PHONE_COMMANDER_SURFACE = "v0.14.1-phone-commander-surface-v1"

private enum VexMainTab: Hashable {
    case chat
    case system
    case art
    case memory
    case phone
}

struct ContentView: View {
    @EnvironmentObject private var app: AppModel
    @State private var tab: VexMainTab = .chat

    var body: some View {
        TabView(selection: $tab) {
            VexChatView()
                .tag(VexMainTab.chat)
                .tabItem { Label("Chat", systemImage: "bubble.left.and.bubble.right.fill") }

            VexSystemView()
                .dynamicTypeSize(.small ... .large)
                .tag(VexMainTab.system)
                .tabItem { Label("System", systemImage: "network") }

            VexArtStudioView(onOpenChat: { tab = .chat })
                .dynamicTypeSize(.small ... .large)
                .tag(VexMainTab.art)
                .tabItem { Label("Art", systemImage: "sparkles.rectangle.stack") }

            VexMemoryView()
                .dynamicTypeSize(.small ... .large)
                .tag(VexMainTab.memory)
                .tabItem { Label("Memory", systemImage: "brain.head.profile") }

            VexPhoneView(onOpenChat: { tab = .chat })
                .dynamicTypeSize(.small ... .large)
                .tag(VexMainTab.phone)
                .tabItem { Label("Phone", systemImage: "iphone") }
        }
        .tint(VexTheme.hotPink)
        .toolbarBackground(VexTheme.ink.opacity(0.97), for: .tabBar)
        .toolbarBackground(.visible, for: .tabBar)
        .task {
            await PhoneRemoteCommandRelay.shared.run(app: app)
        }
    }
}

@MainActor
private final class VexControlSurfaceModel: ObservableObject {
    @Published var runtimeOnline = false
    @Published var nodeName = "Not connected"
    @Published var bridgeVersion = "â€”"
    @Published var runtimeBundle = "â€”"
    @Published var indexedFiles = 0
    @Published var adaptiveLessons = 0
    @Published var openGaps = 0
    @Published var stagedUpgrades = 0
    @Published var wants: [String] = []
    @Published var artInstalled = false
    @Published var artRunning = false
    @Published var artModel = "â€”"
    @Published var isRefreshing = false
    @Published var lastRefresh: Date?
    @Published var error = ""

    func refresh() async {
        guard !isRefreshing else { return }
        isRefreshing = true
        defer { isRefreshing = false }

        error = ""
        runtimeOnline = false
        wants = []

        let endpoints = configuredEndpoints()
        guard !endpoints.isEmpty else {
            error = "No paired Vex Bridge endpoint is configured."
            return
        }

        for endpoint in endpoints {
            guard let status = await json(endpoint: endpoint, path: "/status") else { continue }

            runtimeOnline = true
            nodeName = (status["name"] as? String) ?? hostLabel(endpoint)
            bridgeVersion = (status["version"] as? String) ?? "unknown"
            runtimeBundle = (status["agent_runtime_bundle"] as? String) ?? "unknown"
            indexedFiles = number(status["indexed_files"])

            if let adaptive = await json(endpoint: endpoint, path: "/adaptive/status") {
                adaptiveLessons = number(adaptive["active_lessons"])
                openGaps = number(adaptive["open_gaps"])
                stagedUpgrades = number(adaptive["staged_upgrades"])
            }

            if let autonomy = await json(endpoint: endpoint, path: "/autonomy/requests") {
                if let counts = autonomy["counts"] as? [String: Any] {
                    openGaps = number(counts["open_gaps"])
                    stagedUpgrades = number(counts["staged_upgrades"])
                }

                var current: [String] = []
                if let gaps = autonomy["gaps"] as? [[String: Any]] {
                    for gap in gaps.prefix(8) {
                        let detail = (gap["detail"] as? String) ?? (gap["request_text"] as? String) ?? "Open capability gap"
                        current.append("Gap: " + detail)
                    }
                }
                if let upgrades = autonomy["upgrades"] as? [[String: Any]] {
                    for upgrade in upgrades.prefix(8) {
                        let component = (upgrade["component"] as? String) ?? "runtime"
                        let proposal = (upgrade["proposal"] as? String) ?? (upgrade["problem"] as? String) ?? "Staged upgrade"
                        current.append("\(component): \(proposal)")
                    }
                }
                wants = current
            }

            if let art = await json(endpoint: endpoint, path: "/art/health") {
                artInstalled = (art["installed"] as? Bool) ?? false
                artRunning = (art["running"] as? Bool) ?? false
                artModel = (art["model"] as? String) ?? "â€”"
            }

            lastRefresh = Date()
            return
        }

        error = "Configured Vex Bridge nodes did not answer."
    }

    private func configuredEndpoints() -> [String] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let cognition = defaults.string(forKey: "vex.pc.cognition.lastGoodEndpoint.v1") ?? ""
        var result: [String] = []
        for value in [primary, cognition, secondary] where !value.isEmpty {
            guard !result.contains(value), let url = URL(string: value), VexBridgeNetworking.isBridgeURL(url) else { continue }
            result.append(value)
        }
        return result
    }

    private func json(endpoint: String, path: String) async -> [String: Any]? {
        guard let root = URL(string: endpoint),
              var parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
        else { return nil }

        parts.path = path
        guard let url = parts.url else { return nil }

        var request = URLRequest(url: url)
        request.timeoutInterval = 7

        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse,
                  (200...299).contains(http.statusCode),
                  let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            else { return nil }
            return json
        } catch {
            return nil
        }
    }

    private func number(_ value: Any?) -> Int {
        if let n = value as? Int { return n }
        if let n = value as? NSNumber { return n.intValue }
        if let text = value as? String, let n = Int(text) { return n }
        return 0
    }

    private func hostLabel(_ endpoint: String) -> String {
        URL(string: endpoint)?.host ?? "Vex Bridge"
    }
}

private struct VexSurfaceBackground: View {
    var body: some View {
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
    }
}

private struct VexSurfaceHeader: View {
    let eyebrow: String
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(eyebrow.uppercased())
                .font(.caption2.weight(.black))
                .tracking(1.5)
                .foregroundStyle(VexTheme.hotPink)
            Text(title)
                .font(.largeTitle.bold())
            Text(subtitle)
                .font(.subheadline)
                .foregroundStyle(VexTheme.muted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct VexMetricCard: View {
    let title: String
    let value: String
    let detail: String
    var active = true

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Circle()
                    .fill(active ? VexTheme.hotPink : VexTheme.muted.opacity(0.45))
                    .frame(width: 7, height: 7)
                Text(title.uppercased())
                    .font(.caption2.weight(.bold))
                    .tracking(0.8)
                    .foregroundStyle(VexTheme.muted)
            }
            Text(value)
                .font(.title3.bold())
                .lineLimit(2)
                .minimumScaleFactor(0.75)
            Text(detail)
                .font(.caption)
                .foregroundStyle(VexTheme.muted)
                .lineLimit(3)
        }
        .frame(maxWidth: .infinity, minHeight: 108, alignment: .topLeading)
        .padding(14)
        .background(VexTheme.panel.opacity(0.94))
        .overlay(
            RoundedRectangle(cornerRadius: 18)
                .stroke(.white.opacity(0.07), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 18))
    }
}

private struct VexSystemView: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var system = VexControlSurfaceModel()

    var body: some View {
        ZStack {
            VexSurfaceBackground()
            ScrollView {
                VStack(spacing: 16) {
                    HStack(alignment: .top) {
                        VexSurfaceHeader(
                            eyebrow: "VEXNATIVE // CONTROL SURFACE",
                            title: "System",
                            subtitle: "Live state from the phone, paired PCs, adaptive memory, wants, and art worker."
                        )
                        Button {
                            app.showBrain = true
                        } label: {
                            Image(systemName: "slider.horizontal.3")
                                .font(.headline)
                                .padding(12)
                                .background(.white.opacity(0.08))
                                .clipShape(Circle())
                        }
                        .tint(.white)
                    }

                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                        VexMetricCard(
                            title: "PC cognition",
                            value: app.pcBrainConnected ? "Connected" : "Standby",
                            detail: app.pcBrainStatus,
                            active: app.pcBrainConnected
                        )
                        VexMetricCard(
                            title: "Bridge",
                            value: system.runtimeOnline ? system.bridgeVersion : "Offline",
                            detail: system.runtimeOnline ? "\(system.nodeName) â€¢ runtime \(system.runtimeBundle)" : "No Bridge response",
                            active: system.runtimeOnline
                        )
                        VexMetricCard(
                            title: "Adaptive",
                            value: "\(system.adaptiveLessons) lessons",
                            detail: "\(system.openGaps) open gaps â€¢ \(system.stagedUpgrades) staged upgrade\(system.stagedUpgrades == 1 ? "" : "s")",
                            active: system.runtimeOnline && system.openGaps == 0
                        )
                        VexMetricCard(
                            title: "Art",
                            value: system.artInstalled ? (system.artRunning ? "Rendering" : "Ready") : "Unavailable",
                            detail: system.artInstalled ? system.artModel : "Art worker not installed",
                            active: system.artInstalled
                        )
                        VexMetricCard(
                            title: "Index",
                            value: system.indexedFiles == 0 ? "â€”" : "\(system.indexedFiles)",
                            detail: "Indexed PC files available to Vex Bridge",
                            active: system.indexedFiles > 0
                        )
                        VexMetricCard(
                            title: "Phone brain",
                            value: app.modelStatus,
                            detail: app.isLoadingModel ? "Loading local fallback model" : "Local fallback remains independent of PC cognition",
                            active: !app.isLoadingModel
                        )
                    }

                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Text("Runtime wants")
                                .font(.headline)
                            Spacer()
                            Text("\(system.wants.count)")
                                .font(.caption.bold())
                                .foregroundStyle(VexTheme.hotPink)
                        }

                        if system.wants.isEmpty {
                            Text(system.runtimeOnline ? "No open gaps. Staged upgrades appear here when Vex has something concrete to improve." : "Refresh to read Vex runtime wants.")
                                .font(.subheadline)
                                .foregroundStyle(VexTheme.muted)
                        } else {
                            ForEach(Array(system.wants.enumerated()), id: \.offset) { _, item in
                                Text("â€¢ " + item)
                                    .font(.subheadline)
                                    .foregroundStyle(.white.opacity(0.92))
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
                    .background(VexTheme.panel.opacity(0.94))
                    .clipShape(RoundedRectangle(cornerRadius: 18))

                    VexNativeA2APanel()

                    if !system.error.isEmpty {
                        Text(system.error)
                            .font(.caption)
                            .foregroundStyle(.orange)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    Button {
                        Task { await system.refresh() }
                    } label: {
                        HStack {
                            if system.isRefreshing { ProgressView().tint(.white) }
                            Image(systemName: "arrow.clockwise")
                            Text(system.isRefreshing ? "Refreshingâ€¦" : "Refresh system")
                                .fontWeight(.bold)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 13)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(VexTheme.hotPink)
                    .disabled(system.isRefreshing)

                    if let refreshed = system.lastRefresh {
                        Text("Last refresh \(refreshed.formatted(date: .omitted, time: .standard))")
                            .font(.caption2)
                            .foregroundStyle(VexTheme.muted)
                    }
                }
                .padding(16)
            }
        }
        .sheet(isPresented: $app.showBrain) {
            BrainView()
                .environmentObject(app)
        }
        .task { await system.refresh() }
    }
}

private struct VexArtStudioView: View {
    @EnvironmentObject private var app: AppModel
    let onOpenChat: () -> Void
    @State private var prompt = ""
    @State private var rendering = false

    private var latestImage: UIImage? {
        guard let filename = app.profile.messages.reversed().compactMap(\.imageFilename).first,
              let data = LocalStore.shared.attachmentData(named: filename)
        else { return nil }
        return UIImage(data: data)
    }

    var body: some View {
        ZStack {
            VexSurfaceBackground()
            ScrollView {
                VStack(spacing: 16) {
                    VexSurfaceHeader(
                        eyebrow: "VEXART // LOCAL PIPELINE",
                        title: "Art",
                        subtitle: "Render through the PC Art Worker. Finished images still land in Vex chat history."
                    )

                    if let image = latestImage {
                        Image(uiImage: image)
                            .resizable()
                            .scaledToFit()
                            .frame(maxWidth: .infinity)
                            .clipShape(RoundedRectangle(cornerRadius: 20))
                            .overlay(
                                RoundedRectangle(cornerRadius: 20)
                                    .stroke(.white.opacity(0.08), lineWidth: 1)
                            )
                    } else {
                        VStack(spacing: 10) {
                            Image(systemName: "sparkles.rectangle.stack")
                                .font(.system(size: 42))
                                .foregroundStyle(VexTheme.hotPink)
                            Text("Your latest local render will appear here.")
                                .foregroundStyle(VexTheme.muted)
                        }
                        .frame(maxWidth: .infinity, minHeight: 220)
                        .background(VexTheme.panel.opacity(0.9))
                        .clipShape(RoundedRectangle(cornerRadius: 20))
                    }

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Render prompt")
                            .font(.headline)
                        TextEditor(text: $prompt)
                            .frame(minHeight: 120)
                            .scrollContentBackground(.hidden)
                            .padding(10)
                            .background(.black.opacity(0.22))
                            .clipShape(RoundedRectangle(cornerRadius: 14))

                        HStack {
                            Button("Open chat") { onOpenChat() }
                                .buttonStyle(.bordered)

                            Spacer()

                            Button {
                                let request = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
                                guard !request.isEmpty, !rendering else { return }
                                rendering = true
                                Task {
                                    _ = await PCArtRouter.tryHandle("render image: " + request, app: app)
                                    rendering = false
                                }
                            } label: {
                                HStack {
                                    if rendering { ProgressView().tint(.white) }
                                    Image(systemName: "wand.and.stars")
                                    Text(rendering ? "Renderingâ€¦" : "Render")
                                }
                                .fontWeight(.bold)
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(VexTheme.hotPink)
                            .disabled(prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || rendering)
                        }
                    }
                    .padding(16)
                    .background(VexTheme.panel.opacity(0.94))
                    .clipShape(RoundedRectangle(cornerRadius: 18))

                    Text("VexArt v0.10.12 field flow: render â†’ release Comfy â†’ Q6 visual review â†’ at most one corrected rerender.")
                        .font(.caption)
                        .foregroundStyle(VexTheme.muted)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(16)
            }
        }
    }
}

private struct VexMemoryCount: Identifiable {
    let kind: MemoryKind
    let count: Int
    var id: String { kind.rawValue }
}

private struct VexMemoryView: View {
    @EnvironmentObject private var app: AppModel

    private var counts: [VexMemoryCount] {
        let grouped = Dictionary(grouping: app.profile.memories, by: \.kind)
        return MemoryKind.allCases.map { VexMemoryCount(kind: $0, count: grouped[$0]?.count ?? 0) }
    }

    private var recent: [BrainMemory] {
        Array(app.profile.memories.sorted {
            if $0.importance == $1.importance { return $0.createdAt > $1.createdAt }
            return $0.importance > $1.importance
        }.prefix(24))
    }

    var body: some View {
        ZStack {
            VexSurfaceBackground()
            ScrollView {
                VStack(spacing: 16) {
                    VexSurfaceHeader(
                        eyebrow: "VEX MEMORY // PHONE + PC",
                        title: "Memory",
                        subtitle: "Phone profile memory stays local; Bridge memory and adaptive lessons stay on the paired PC."
                    )

                    HStack(spacing: 12) {
                        VexMetricCard(
                            title: "Phone memories",
                            value: "\(app.profile.memories.count)",
                            detail: "Persistent app-local memories",
                            active: true
                        )
                        VexMetricCard(
                            title: "Messages",
                            value: "\(app.profile.messages.count)",
                            detail: "Current on-device transcript",
                            active: true
                        )
                    }

                    VStack(alignment: .leading, spacing: 12) {
                        Text("Memory mix")
                            .font(.headline)
                        ForEach(counts) { item in
                            HStack {
                                Text(item.kind.rawValue.capitalized)
                                    .foregroundStyle(.white.opacity(0.92))
                                Spacer()
                                Text("\(item.count)")
                                    .font(.subheadline.bold())
                                    .foregroundStyle(VexTheme.hotPink)
                            }
                        }
                    }
                    .padding(16)
                    .background(VexTheme.panel.opacity(0.94))
                    .clipShape(RoundedRectangle(cornerRadius: 18))

                    VStack(alignment: .leading, spacing: 12) {
                        Text("High-value phone memory")
                            .font(.headline)
                        if recent.isEmpty {
                            Text("No phone-local memories yet.")
                                .foregroundStyle(VexTheme.muted)
                        } else {
                            ForEach(recent) { memory in
                                VStack(alignment: .leading, spacing: 4) {
                                    HStack {
                                        Text(memory.kind.rawValue.uppercased())
                                            .font(.caption2.bold())
                                            .foregroundStyle(VexTheme.hotPink)
                                        Spacer()
                                        Text(String(format: "%.0f%%", memory.importance * 100))
                                            .font(.caption2)
                                            .foregroundStyle(VexTheme.muted)
                                    }
                                    Text(memory.text)
                                        .font(.subheadline)
                                        .foregroundStyle(.white.opacity(0.94))
                                }
                                .padding(.vertical, 5)
                            }
                        }
                    }
                    .padding(16)
                    .background(VexTheme.panel.opacity(0.94))
                    .clipShape(RoundedRectangle(cornerRadius: 18))
                }
                .padding(16)
            }
        }
    }
}

private struct VexPhoneView: View {
    @EnvironmentObject private var app: AppModel
    let onOpenChat: () -> Void
    @State private var brightness = Double(UIScreen.main.brightness) * 100
    @State private var clipboardText = ""
    @State private var actionStatus = "Ready"

    var body: some View {
        ZStack {
            VexSurfaceBackground()
            ScrollView {
                VStack(spacing: 16) {
                    VexSurfaceHeader(
                        eyebrow: "IPHONE // NATIVE ACTIONS",
                        title: "Phone",
                        subtitle: "Actions stay inside normal iOS permissions. Vex never gets an imaginary jailbreak."
                    )

                    VStack(alignment: .leading, spacing: 12) {
                        Text("Quick controls")
                            .font(.headline)

                        HStack {
                            Button("Settings") { run("on my iPhone open settings") }
                                .buttonStyle(.bordered)
                            Button("Flashlight") { run("on my iPhone toggle flashlight") }
                                .buttonStyle(.bordered)
                            Button("Maps") { run("on my iPhone open maps") }
                                .buttonStyle(.bordered)
                        }

                        Text("Brightness \(Int(brightness.rounded()))%")
                            .font(.subheadline)
                        Slider(value: $brightness, in: 0...100, step: 1)
                            .tint(VexTheme.hotPink)
                            .onChange(of: brightness) { _, value in
                                UIScreen.main.brightness = CGFloat(value / 100)
                            }
                    }
                    .padding(16)
                    .background(VexTheme.panel.opacity(0.94))
                    .clipShape(RoundedRectangle(cornerRadius: 18))

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Clipboard")
                            .font(.headline)
                        TextField("Text to copy", text: $clipboardText, axis: .vertical)
                            .textFieldStyle(.roundedBorder)
                        Button {
                            let value = clipboardText.trimmingCharacters(in: .whitespacesAndNewlines)
                            guard !value.isEmpty else { return }
                            UIPasteboard.general.string = value
                            actionStatus = "Copied to iPhone clipboard."
                        } label: {
                            Label("Copy", systemImage: "doc.on.doc")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(VexTheme.hotPink)
                    }
                    .padding(16)
                    .background(VexTheme.panel.opacity(0.94))
                    .clipShape(RoundedRectangle(cornerRadius: 18))

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Camera + voice")
                            .font(.headline)
                        Text("The proven camera/photo Vision and hands-free voice controls remain in Chat so they keep sharing the same conversation context.")
                            .font(.subheadline)
                            .foregroundStyle(VexTheme.muted)
                        Button {
                            onOpenChat()
                        } label: {
                            Label("Open Chat controls", systemImage: "camera.mic")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                    }
                    .padding(16)
                    .background(VexTheme.panel.opacity(0.94))
                    .clipShape(RoundedRectangle(cornerRadius: 18))

                    Text(actionStatus)
                        .font(.caption)
                        .foregroundStyle(VexTheme.muted)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(16)
            }
        }
    }

    private func run(_ command: String) {
        actionStatus = "Workingâ€¦"
        Task {
            let handled = await PhoneToolRouter.tryHandle(command, app: app)
            actionStatus = handled ? "Done." : "That action is not exposed by the current iOS router."
        }
    }
}


// MARK: - VexNative v0.15.8 current A2A client

private let V158_IPHONE_A2A_CLIENT = "v0.15.8-iphone-a2a-client-v1"
private let V159_IPHONE_A2A_AUTONOMY = "v0.15.9-iphone-a2a-autonomy-v1"
private let V160_A2A_ROAMING_FALLBACK = "v0.16.0-a2a-roaming-fallback-v1"
private let V161_UNIFIED_CORE_CLIENT = "v0.16.1-unified-core-client-v1"

@MainActor
private final class VexNativeA2AClient: ObservableObject {
    static let shared = VexNativeA2AClient()

    @Published var online = false
    @Published var agentCount = 0
    @Published var autonomyEnabled = false
    @Published var autonomyRunning = false
    @Published var goalSummary = "â€”"
    @Published var workSummary = "â€”"
    @Published var latestGoal = "No system initiative yet"
    @Published var response = ""
    @Published var error = ""
    @Published var refreshing = false
    @Published var sending = false
    @Published var lastRefresh: Date?
    @Published var activeNode = "â€”"
    @Published var activeModel = "â€”"
    @Published var brainMode = "â€”"
    @Published var memorySummary = "â€”"
    @Published var rendererSummary = "â€”"
    @Published var renderJobSummary = "No render jobs"
    @Published var activeWorkID = ""
    @Published var activeWorkSummary = "No active work"
    @Published var failedWorkID = ""
    @Published var failedWorkSummary = ""
    @Published var phoneAgentSummary = "Unknown"
    @Published var recentResultSummary = "No completed work yet"

    func refresh() async {
        guard !refreshing else { return }
        refreshing = true
        defer { refreshing = false }

        do {
            let object = try await request(path: "/vexnative/status")
            guard (object["ok"] as? Bool) == true,
                  let a2a = object["a2a"] as? [String: Any]
            else { throw ClientError.badResponse }

            let health = a2a["health"] as? [String: Any] ?? [:]
            let runtime = a2a["runtime"] as? [String: Any] ?? [:]
            let store = runtime["store"] as? [String: Any] ?? [:]
            let goals = a2a["goals"] as? [[String: Any]] ?? []
            let work = a2a["work"] as? [[String: Any]] ?? []

            if let active = work.first(where: {
                let status = ($0["status"] as? String) ?? ""
                return status == "running" || status == "queued"
            }) {
                activeWorkID = (active["id"] as? String) ?? ""
                let status = (active["status"] as? String) ?? "unknown"
                let task = (active["prompt"] as? String) ?? "Untitled work"
                activeWorkSummary = "\(status.capitalized) - \(String(task.prefix(110)))"
            } else {
                activeWorkID = ""
                activeWorkSummary = "No active work"
            }
            if let failed = work.first(where: { (($0["status"] as? String) ?? "") == "failed" }) {
                failedWorkID = (failed["id"] as? String) ?? ""
                failedWorkSummary = String(((failed["prompt"] as? String) ?? "Failed work").prefix(110))
            } else {
                failedWorkID = ""
                failedWorkSummary = ""
            }
            if let done = work.first(where: { (($0["status"] as? String) ?? "") == "done" }) {
                recentResultSummary = String(((done["prompt"] as? String) ?? "Completed work").prefix(130))
            } else {
                recentResultSummary = "No completed work yet"
            }
            let phone = object["phone"] as? [String: Any] ?? [:]
            phoneAgentSummary = ((phone["connected"] as? Bool) ?? false) ? "Connected" : "Not polling"

            online = (health["ok"] as? Bool) ?? false
            agentCount = number(health["agent_count"])
            autonomyEnabled = (store["enabled"] as? Bool) ?? false
            autonomyRunning = (runtime["running"] as? Bool) ?? false
            goalSummary = statusSummary(store["goals"])
            workSummary = statusSummary(store["work"])

            let core = object["core"] as? [String: Any] ?? [:]
            let models = object["models"] as? [String: Any] ?? [:]
            let configured = models["configured"] as? [String: Any] ?? [:]
            let renderer = object["renderer"] as? [String: Any] ?? [:]
            activeNode = (core["host"] as? String) ?? "â€”"
            brainMode = (core["brain_mode"] as? String) ?? "â€”"
            let modelKey = brainMode.lowercased() == "deep" ? "deep" : "fast"
            activeModel = (configured[modelKey] as? String) ?? "â€”"
            if let memory = core["memory"] as? [String: Any],
               let pressure = memory["pressure"] as? NSNumber {
                memorySummary = String(format: "%.0f%% used", pressure.doubleValue * 100)
            } else {
                memorySummary = "â€”"
            }
            rendererSummary = ((renderer["available"] as? Bool) ?? false) ? "Ready" : "Offline"
            if let recentJobs = renderer["recent_jobs"] as? [[String: Any]],
               let job = recentJobs.first {
                let state = (job["state"] as? String) ?? "unknown"
                let preview = (job["prompt_preview"] as? String) ?? "Render job"
                renderJobSummary = "\(state.capitalized) - \(String(preview.prefix(90)))"
            } else {
                renderJobSummary = "No render jobs"
            }

            if let newest = goals.first {
                let title = (newest["title"] as? String) ?? "Untitled goal"
                let status = (newest["status"] as? String) ?? "unknown"
                latestGoal = "\(title) â€¢ \(status)"
            } else {
                latestGoal = "No goals reported"
            }
            error = ""
            lastRefresh = Date()
        } catch {
            online = false
            self.error = "VexNative status: \(error.localizedDescription)"
        }
    }

    func answer(_ message: String, quiet: Bool = false) async -> String? {
        let clean = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return nil }
        do {
            let object = try await request(
                path: "/vexnative/send",
                method: "POST",
                body: ["agent": "coordinator", "message": clean],
                timeout: 75
            )
            guard (object["ok"] as? Bool) == true else { throw ClientError.badResponse }
            let text = extractText(object["result"]) ?? compactJSON(object["result"]) ?? "VexNative completed the request."
            response = text
            error = ""
            online = true
            return text
        } catch {
            online = false
            if !quiet {
                self.error = "VexNative request: \(error.localizedDescription)"
            }
            return nil
        }
    }

    func streamAnswer(_ message: String) async -> String? {
        let clean = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return nil }

        var lastError: Error = ClientError.badResponse
        for url in relayURLs(path: "/vexnative/send/stream") {
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.timeoutInterval = 90
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
            request.httpBody = try? JSONSerialization.data(withJSONObject: [
                "agent": "coordinator",
                "message": clean
            ])

            var event = ""
            var finalText: String?
            do {
                let responseObject = try await VexBridgeNetworking.streamLines(for: request) { line in
                    if line.hasPrefix("event:") {
                        event = line.replacingOccurrences(of: "event:", with: "")
                            .trimmingCharacters(in: .whitespaces)
                        if event == "accepted" {
                            response = "Routing…"
                        }
                        return
                    }
                    guard line.hasPrefix("data:") else { return }
                    let raw = line.replacingOccurrences(of: "data:", with: "")
                        .trimmingCharacters(in: .whitespaces)
                    guard let data = raw.data(using: .utf8),
                          let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                    else { return }

                    if event == "route",
                       let route = object["route"] as? [String: Any] {
                        let intent = (route["intent"] as? String) ?? "request"
                        let mode = (route["mode"] as? String) ?? "auto"
                        response = "\(intent.capitalized) • \(mode)"
                    } else if event == "result",
                              let text = extractText(object["result"]) ?? compactJSON(object["result"]) {
                        finalText = text
                        response = text
                    } else if event == "error" {
                        let message = (object["error"] as? String) ?? "Stream failed"
                        self.error = message
                    }
                }
                guard let http = responseObject as? HTTPURLResponse,
                      (200...299).contains(http.statusCode)
                else {
                    lastError = ClientError.badResponse
                    continue
                }
                if let finalText {
                    self.error = ""
                    online = true
                    return finalText
                }
            } catch {
                lastError = error
            }
        }

        self.error = "VexNative stream: \(lastError.localizedDescription)"
        return nil
    }

    func send(_ message: String) async {
        let clean = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, !sending else { return }
        sending = true
        defer { sending = false }

        let streamed = await streamAnswer(clean)
        if streamed != nil {
            await refresh()
            return
        }
        let fallback = await answer(clean, quiet: false)
        if fallback != nil {
            await refresh()
        }
    }

    func setAutonomy(enabled: Bool) async {
        do {
            let object = try await request(
                path: "/vexnative/autonomy",
                method: "POST",
                body: ["action": enabled ? "enable" : "pause"],
                timeout: 20
            )
            guard (object["ok"] as? Bool) == true else { throw ClientError.badResponse }
            response = enabled ? "VexNative autonomy resumed." : "VexNative autonomy paused."
            error = ""
            await refresh()
        } catch {
            self.error = "Autonomy control: \(error.localizedDescription)"
        }
    }

    func createGoal(_ title: String) async {
        let clean = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return }
        do {
            let object = try await request(
                path: "/vexnative/autonomy",
                method: "POST",
                body: [
                    "action": "create_goal",
                    "title": clean,
                    "description": clean,
                    "priority": 50
                ],
                timeout: 20
            )
            guard (object["ok"] as? Bool) == true else { throw ClientError.badResponse }
            response = "Goal accepted by VexNative."
            error = ""
            await refresh()
        } catch {
            self.error = "Goal submission: \(error.localizedDescription)"
        }
    }

    func launchRender(_ prompt: String) async {
        let clean = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return }
        do {
            let object = try await request(
                path: "/vexnative/render",
                method: "POST",
                body: [
                    "prompt": clean,
                    "mode": "normal",
                    "orientation": "portrait",
                    "backend": "auto"
                ],
                timeout: 20
            )
            guard (object["ok"] as? Bool) == true,
                  let job = object["job"] as? [String: Any]
            else { throw ClientError.badResponse }
            let id = (job["id"] as? String) ?? ""
            let state = (job["state"] as? String) ?? "queued"
            renderJobSummary = "\(state.capitalized) - \(String(clean.prefix(90)))"
            response = id.isEmpty ? "Render queued." : "Render queued • \(String(id.prefix(8)))"
            error = ""
            await refresh()
        } catch {
            self.error = "Render launch: \(error.localizedDescription)"
        }
    }

    func cancelActiveWork() async {
        guard !activeWorkID.isEmpty else { return }
        do {
            let object = try await request(
                path: "/vexnative/autonomy",
                method: "POST",
                body: ["action": "cancel_work", "work_id": activeWorkID],
                timeout: 20
            )
            guard (object["ok"] as? Bool) == true else { throw ClientError.badResponse }
            response = "Active work cancelled."
            error = ""
            await refresh()
        } catch {
            self.error = "Cancel work: \(error.localizedDescription)"
        }
    }

    func retryFailedWork() async {
        guard !failedWorkID.isEmpty else { return }
        do {
            let object = try await request(
                path: "/vexnative/autonomy",
                method: "POST",
                body: ["action": "retry_work", "work_id": failedWorkID],
                timeout: 20
            )
            guard (object["ok"] as? Bool) == true else { throw ClientError.badResponse }
            response = "Failed work re-queued."
            error = ""
            await refresh()
        } catch {
            self.error = "Retry work: \(error.localizedDescription)"
        }
    }

    private enum ClientError: LocalizedError {
        case noRelay
        case badResponse
        case http(Int)

        var errorDescription: String? {
            switch self {
            case .noRelay: return "No paired Vex relay endpoint is configured."
            case .badResponse: return "The VexNative relay returned an invalid response."
            case .http(let code): return "The VexNative relay returned HTTP \(code)."
            }
        }
    }

    private func relayURLs(path: String) -> [URL] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey) ?? ""
        let cognition = defaults.string(forKey: "vex.pc.cognition.lastGoodEndpoint.v1") ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey) ?? ""
        let discovered = defaults.string(forKey: "vex.phone.remoteRelay.discoveredEndpoint") ?? ""

        let primaryToken = [primary, cognition, secondary].compactMap { raw -> String? in
            guard let root = URL(string: raw),
                  let parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
            else { return nil }
            return parts.queryItems?.first(where: { $0.name.lowercased() == "token" })?.value
        }.first

        var ordered: [String] = []
        for raw in [discovered, secondary, primary, cognition] {
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty && !ordered.contains(trimmed) {
                ordered.append(trimmed)
            }
        }

        var urls: [URL] = []
        for raw in ordered {
            guard let root = URL(string: raw),
                  VexBridgeNetworking.isBridgeURL(root),
                  var parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
            else { continue }

            if VexBridgeNetworking.isRemoteRelayURL(root) {
                parts.port = nil
                var items = parts.queryItems ?? []
                if items.first(where: { $0.name.lowercased() == "token" }) == nil,
                   let primaryToken, !primaryToken.isEmpty {
                    items.append(URLQueryItem(name: "token", value: primaryToken))
                }
                parts.queryItems = items
            } else {
                parts.port = 8771
            }

            parts.path = path
            if let url = parts.url, !urls.contains(url) {
                urls.append(url)
            }
        }
        return urls
    }

    private func request(
        path: String,
        method: String = "GET",
        body: [String: Any]? = nil,
        timeout: TimeInterval = 20
    ) async throws -> [String: Any] {
        let urls = relayURLs(path: path)
        guard !urls.isEmpty else { throw ClientError.noRelay }

        var lastError: Error = ClientError.badResponse
        for url in urls {
            var request = URLRequest(url: url)
            request.httpMethod = method
            request.timeoutInterval = timeout
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            if let body {
                request.httpBody = try JSONSerialization.data(withJSONObject: body)
            }

            do {
                let (data, response) = try await VexBridgeNetworking.data(for: request)
                guard let http = response as? HTTPURLResponse else {
                    lastError = ClientError.badResponse
                    continue
                }
                guard (200...299).contains(http.statusCode) else {
                    lastError = ClientError.http(http.statusCode)
                    continue
                }
                guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                    lastError = ClientError.badResponse
                    continue
                }
                return object
            } catch {
                lastError = error
            }
        }
        throw lastError
    }

    private func number(_ value: Any?) -> Int {
        if let n = value as? Int { return n }
        if let n = value as? NSNumber { return n.intValue }
        if let s = value as? String { return Int(s) ?? 0 }
        return 0
    }

    private func statusSummary(_ value: Any?) -> String {
        guard let dict = value as? [String: Any], !dict.isEmpty else { return "0" }
        let ordered = dict.keys.sorted().compactMap { key -> String? in
            let count = number(dict[key])
            return count > 0 ? "\(count) \(key)" : nil
        }
        return ordered.isEmpty ? "0" : ordered.joined(separator: " â€¢ ")
    }

    private func extractText(_ value: Any?) -> String? {
        if let text = value as? String, !text.isEmpty { return text }
        guard let dict = value as? [String: Any] else { return nil }
        for key in ["response", "answer", "text", "message", "output", "result"] {
            if let text = extractText(dict[key]), !text.isEmpty { return text }
        }
        return nil
    }

    private func compactJSON(_ value: Any?) -> String? {
        guard let value, JSONSerialization.isValidJSONObject(value),
              let data = try? JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted]),
              let text = String(data: data, encoding: .utf8)
        else { return nil }
        return String(text.prefix(4000))
    }
}

private struct VexNativeA2APanel: View {
    @StateObject private var client = VexNativeA2AClient.shared
    @State private var prompt = ""
    @State private var goalDraft = ""
    @State private var renderDraft = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("VexNative Core")
                        .font(.headline)
                    Text("Current A2A / autonomy â€¢ paired through Vex relay")
                        .font(.caption)
                        .foregroundStyle(VexTheme.muted)
                }
                Spacer()
                Circle()
                    .fill(client.online ? Color.green : Color.orange)
                    .frame(width: 9, height: 9)
            }

            HStack(spacing: 12) {
                VexMetricCard(
                    title: "A2A",
                    value: client.online ? "Online" : "Offline",
                    detail: client.online ? "\(client.agentCount) agents" : "Refresh to reconnect",
                    active: client.online
                )
                VexMetricCard(
                    title: "Autonomy",
                    value: client.autonomyEnabled ? (client.autonomyRunning ? "Running" : "Enabled") : "Paused",
                    detail: "Goals \(client.goalSummary)\nWork \(client.workSummary)",
                    active: client.autonomyEnabled
                )
            }

            HStack(spacing: 12) {
                VexMetricCard(
                    title: "Core",
                    value: client.brainMode,
                    detail: client.activeNode + " / " + client.activeModel,
                    active: client.online
                )
                VexMetricCard(
                    title: "State",
                    value: client.rendererSummary,
                    detail: "Memory " + client.memorySummary + " / Phone " + client.phoneAgentSummary,
                    active: client.rendererSummary == "Ready"
                )
            }

            VStack(alignment: .leading, spacing: 5) {
                Text("Latest goal")
                    .font(.caption.bold())
                    .foregroundStyle(VexTheme.hotPink)
                Text(client.latestGoal)
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.94))
            }

            VStack(alignment: .leading, spacing: 5) {
                Text("Recent result")
                    .font(.caption.bold())
                    .foregroundStyle(VexTheme.hotPink)
                Text(client.recentResultSummary)
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.9))
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("Active work")
                    .font(.caption.bold())
                    .foregroundStyle(VexTheme.hotPink)
                Text(client.activeWorkSummary)
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.9))
                HStack {
                    Button {
                        Task { await client.cancelActiveWork() }
                    } label: {
                        Label("Cancel task", systemImage: "xmark.circle")
                    }
                    .buttonStyle(.bordered)
                    .disabled(client.activeWorkID.isEmpty)

                    if !client.failedWorkID.isEmpty {
                        Button {
                            Task { await client.retryFailedWork() }
                        } label: {
                            Label("Retry failed", systemImage: "arrow.clockwise")
                        }
                        .buttonStyle(.bordered)
                    }
                }
                if !client.failedWorkSummary.isEmpty {
                    Text("Failed: \(client.failedWorkSummary)")
                        .font(.caption2)
                        .foregroundStyle(.orange)
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("Renderer")
                    .font(.caption.bold())
                    .foregroundStyle(VexTheme.hotPink)
                Text(client.renderJobSummary)
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.9))
                TextField("Render prompt", text: $renderDraft, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                Button {
                    let renderPrompt = renderDraft
                    renderDraft = ""
                    Task { await client.launchRender(renderPrompt) }
                } label: {
                    Label("Launch render", systemImage: "wand.and.stars")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .disabled(!client.online || renderDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Button {
                        Task { await client.setAutonomy(enabled: true) }
                    } label: {
                        Label("Resume", systemImage: "play.fill")
                    }
                    .buttonStyle(.bordered)
                    .disabled(!client.online || client.autonomyEnabled)

                    Button {
                        Task { await client.setAutonomy(enabled: false) }
                    } label: {
                        Label("Pause", systemImage: "pause.fill")
                    }
                    .buttonStyle(.bordered)
                    .disabled(!client.online || !client.autonomyEnabled)
                }

                TextField("Give VexNative a new goal", text: $goalDraft, axis: .vertical)
                    .textFieldStyle(.roundedBorder)

                Button {
                    let goal = goalDraft
                    goalDraft = ""
                    Task { await client.createGoal(goal) }
                } label: {
                    Label("Send goal", systemImage: "target")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(VexTheme.hotPink)
                .disabled(!client.online || goalDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            TextField("Ask current VexNativeâ€¦", text: $prompt, axis: .vertical)
                .textFieldStyle(.roundedBorder)

            HStack {
                Button {
                    Task { await client.refresh() }
                } label: {
                    Label(client.refreshing ? "Refreshingâ€¦" : "Refresh", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.bordered)
                .disabled(client.refreshing)

                Button {
                    let message = prompt
                    prompt = ""
                    Task { await client.send(message) }
                } label: {
                    Label(client.sending ? "Sendingâ€¦" : "Send to VexNative", systemImage: "paperplane.fill")
                }
                .buttonStyle(.borderedProminent)
                .tint(VexTheme.hotPink)
                .disabled(client.sending || prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            if !client.response.isEmpty {
                Text(client.response)
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.9))
                    .textSelection(.enabled)
            }
            if !client.error.isEmpty {
                Text(client.error)
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
            if let refreshed = client.lastRefresh {
                Text("Core refreshed \(refreshed.formatted(date: .omitted, time: .standard))")
                    .font(.caption2)
                    .foregroundStyle(VexTheme.muted)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(VexTheme.panel.opacity(0.94))
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .task { await client.refresh() }
    }
}


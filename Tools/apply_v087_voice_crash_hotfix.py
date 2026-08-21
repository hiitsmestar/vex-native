#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")

# v0.8.6 calls stopRecognition() before an input tap exists on the first mic tap.
# AVAudioEngine can terminate the process if removeTap(onBus:) is called with no tap.
# Track the tap lifecycle explicitly and unwind the audio session safely on errors.

old_state = '''    private var silenceTimer: Timer?\n    private var waitingForReply = false\n'''
new_state = '''    private var silenceTimer: Timer?\n    private var waitingForReply = false\n    private var inputTapInstalled = false\n'''
if old_state not in text:
    raise SystemExit("v0.8.6 voice state block not found")
text = text.replace(old_state, new_state, 1)

old_toggle = '''        isHandsFree = true\n        waitingForReply = false\n        try startListening()\n'''
new_toggle = '''        isHandsFree = true\n        waitingForReply = false\n        do {\n            try startListening()\n        } catch {\n            isHandsFree = false\n            waitingForReply = false\n            stopRecognition()\n            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)\n            throw error\n        }\n'''
if old_toggle not in text:
    raise SystemExit("v0.8.6 toggle block not found")
text = text.replace(old_toggle, new_toggle, 1)

old_install = '''        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak request] buffer, _ in request?.append(buffer) }\n        audioEngine.prepare()\n        try audioEngine.start()\n        isListening = true\n'''
new_install = '''        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak request] buffer, _ in request?.append(buffer) }\n        inputTapInstalled = true\n        audioEngine.prepare()\n        do {\n            try audioEngine.start()\n        } catch {\n            if inputTapInstalled {\n                input.removeTap(onBus: 0)\n                inputTapInstalled = false\n            }\n            recognitionRequest?.endAudio()\n            recognitionRequest = nil\n            throw error\n        }\n        isListening = true\n'''
if old_install not in text:
    raise SystemExit("v0.8.6 input tap install block not found")
text = text.replace(old_install, new_install, 1)

old_stop = '''        if audioEngine.isRunning { audioEngine.stop() }\n        audioEngine.inputNode.removeTap(onBus: 0)\n        isListening = false\n'''
new_stop = '''        if audioEngine.isRunning { audioEngine.stop() }\n        if inputTapInstalled {\n            audioEngine.inputNode.removeTap(onBus: 0)\n            inputTapInstalled = false\n        }\n        audioEngine.reset()\n        isListening = false\n'''
if old_stop not in text:
    raise SystemExit("v0.8.6 stopRecognition block not found")
text = text.replace(old_stop, new_stop, 1)

path.write_text(text, encoding="utf-8")
for marker in ["inputTapInstalled", "if inputTapInstalled", "audioEngine.reset()"]:
    if marker not in text:
        raise SystemExit(f"missing v0.8.7 marker: {marker}")
print("Applied v0.8.7 first-tap AVAudioEngine crash hotfix")

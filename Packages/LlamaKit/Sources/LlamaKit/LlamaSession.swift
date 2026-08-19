import Foundation
import llama

public enum LlamaSessionError: LocalizedError {
    case modelLoadFailed
    case contextCreationFailed
    case promptTooLong(Int, Int)
    case tokenizationFailed
    case decodeFailed

    public var errorDescription: String? {
        switch self {
        case .modelLoadFailed:
            return "The GGUF model could not be loaded."
        case .contextCreationFailed:
            return "The local model context could not be created."
        case let .promptTooLong(tokens, capacity):
            return "The prompt is \(tokens) tokens but this phone session is configured for \(capacity). Trim the brain profile or chat history."
        case .tokenizationFailed:
            return "The model tokenizer rejected the prompt."
        case .decodeFailed:
            return "llama.cpp failed while evaluating tokens."
        }
    }
}

private func clearBatch(_ batch: inout llama_batch) {
    batch.n_tokens = 0
}

private func addToken(
    _ batch: inout llama_batch,
    token: llama_token,
    position: llama_pos,
    logits: Bool
) {
    let i = Int(batch.n_tokens)
    batch.token[i] = token
    batch.pos[i] = position
    batch.n_seq_id[i] = 1
    batch.seq_id[i]![0] = 0
    batch.logits[i] = logits ? 1 : 0
    batch.n_tokens += 1
}

public actor LlamaSession {
    private let model: OpaquePointer
    private let context: OpaquePointer
    private let vocab: OpaquePointer
    private let contextSize: Int
    private let promptBatchSize: Int

    public init(modelPath: String, contextSize: Int = 4096) throws {
        llama_backend_init()

        var modelParams = llama_model_default_params()
        #if targetEnvironment(simulator)
        modelParams.n_gpu_layers = 0
        #else
        // A small Q4 model generally benefits from full Metal offload on Apple devices.
        modelParams.n_gpu_layers = 99
        #endif

        guard let loadedModel = llama_model_load_from_file(modelPath, modelParams) else {
            llama_backend_free()
            throw LlamaSessionError.modelLoadFailed
        }

        let threads = max(1, min(6, ProcessInfo.processInfo.processorCount - 2))
        let batchSize = min(contextSize, 512)
        var contextParams = llama_context_default_params()
        contextParams.n_ctx = UInt32(contextSize)
        contextParams.n_batch = UInt32(batchSize)
        contextParams.n_threads = Int32(threads)
        contextParams.n_threads_batch = Int32(threads)

        guard let loadedContext = llama_init_from_model(loadedModel, contextParams) else {
            llama_model_free(loadedModel)
            llama_backend_free()
            throw LlamaSessionError.contextCreationFailed
        }

        guard let modelVocab = llama_model_get_vocab(loadedModel) else {
            llama_free(loadedContext)
            llama_model_free(loadedModel)
            llama_backend_free()
            throw LlamaSessionError.contextCreationFailed
        }

        self.model = loadedModel
        self.context = loadedContext
        self.vocab = modelVocab
        self.contextSize = contextSize
        self.promptBatchSize = batchSize
    }

    deinit {
        llama_free(context)
        llama_model_free(model)
        llama_backend_free()
    }

    public func complete(
        prompt: String,
        maxNewTokens: Int = 420,
        temperature: Float = 0.88,
        topP: Float = 0.92
    ) throws -> String {
        llama_kv_self_clear(context)

        let tokens = try tokenize(prompt, addSpecial: false, parseSpecial: true)
        let usableContext = max(1, contextSize - maxNewTokens - 8)
        guard tokens.count <= usableContext else {
            throw LlamaSessionError.promptTooLong(tokens.count, usableContext)
        }
        guard !tokens.isEmpty else {
            throw LlamaSessionError.tokenizationFailed
        }

        // IMPORTANT: n_batch is only 512. The private Vex brain can easily make the
        // prompt larger than that, so feeding the whole prompt in one llama_decode()
        // call can abort inside llama.cpp on-device. Evaluate the prompt in bounded
        // chunks and request logits only for the final token of the final chunk.
        var batch = llama_batch_init(Int32(promptBatchSize), 0, 1)
        defer { llama_batch_free(batch) }

        var offset = 0
        while offset < tokens.count {
            clearBatch(&batch)
            let end = min(offset + promptBatchSize, tokens.count)

            for index in offset..<end {
                addToken(
                    &batch,
                    token: tokens[index],
                    position: Int32(index),
                    logits: index == tokens.count - 1
                )
            }

            guard llama_decode(context, batch) == 0 else {
                throw LlamaSessionError.decodeFailed
            }
            offset = end
        }

        let samplerParams = llama_sampler_chain_default_params()
        guard let sampler = llama_sampler_chain_init(samplerParams) else {
            throw LlamaSessionError.decodeFailed
        }
        defer { llama_sampler_free(sampler) }

        llama_sampler_chain_add(sampler, llama_sampler_init_top_k(40))
        llama_sampler_chain_add(sampler, llama_sampler_init_top_p(topP, 1))
        llama_sampler_chain_add(sampler, llama_sampler_init_temp(temperature))
        llama_sampler_chain_add(sampler, llama_sampler_init_dist(UInt32.random(in: 1...UInt32.max - 1)))

        var output = ""
        var pendingUTF8: [UInt8] = []
        var position = Int32(tokens.count)

        for _ in 0..<maxNewTokens {
            // -1 means the most recent logits row from the last decode.
            let sampled = llama_sampler_sample(sampler, context, -1)

            if llama_vocab_is_eog(vocab, sampled) {
                break
            }

            let piece = tokenPiece(sampled)
            pendingUTF8.append(contentsOf: piece)

            if let valid = String(bytes: pendingUTF8, encoding: .utf8) {
                output += valid
                pendingUTF8.removeAll(keepingCapacity: true)
            }

            clearBatch(&batch)
            addToken(&batch, token: sampled, position: position, logits: true)
            position += 1

            guard llama_decode(context, batch) == 0 else {
                throw LlamaSessionError.decodeFailed
            }
        }

        if !pendingUTF8.isEmpty {
            output += String(decoding: pendingUTF8, as: UTF8.self)
        }

        return output
    }

    public func modelDescription() -> String {
        var buffer = [CChar](repeating: 0, count: 512)
        let count = buffer.withUnsafeMutableBufferPointer { ptr in
            llama_model_desc(model, ptr.baseAddress, ptr.count)
        }
        guard count > 0 else { return "Local GGUF model" }
        return buffer.withUnsafeBufferPointer { ptr in
            guard let base = ptr.baseAddress else { return "Local GGUF model" }
            return String(cString: base)
        }
    }

    private func tokenize(
        _ text: String,
        addSpecial: Bool,
        parseSpecial: Bool
    ) throws -> [llama_token] {
        let utf8Count = text.utf8.count
        var capacity = max(32, utf8Count + 16)
        var buffer = [llama_token](repeating: 0, count: capacity)

        var count = text.withCString { cString in
            buffer.withUnsafeMutableBufferPointer { ptr in
                llama_tokenize(
                    vocab,
                    cString,
                    Int32(utf8Count),
                    ptr.baseAddress,
                    Int32(ptr.count),
                    addSpecial,
                    parseSpecial
                )
            }
        }

        if count < 0 {
            capacity = Int(-count)
            buffer = [llama_token](repeating: 0, count: capacity)
            count = text.withCString { cString in
                buffer.withUnsafeMutableBufferPointer { ptr in
                    llama_tokenize(
                        vocab,
                        cString,
                        Int32(utf8Count),
                        ptr.baseAddress,
                        Int32(ptr.count),
                        addSpecial,
                        parseSpecial
                    )
                }
            }
        }

        guard count >= 0 else { throw LlamaSessionError.tokenizationFailed }
        return Array(buffer.prefix(Int(count)))
    }

    private func tokenPiece(_ token: llama_token) -> [UInt8] {
        var small = [CChar](repeating: 0, count: 16)
        var count = small.withUnsafeMutableBufferPointer { ptr in
            llama_token_to_piece(vocab, token, ptr.baseAddress, Int32(ptr.count), 0, false)
        }

        if count < 0 {
            var large = [CChar](repeating: 0, count: Int(-count))
            count = large.withUnsafeMutableBufferPointer { ptr in
                llama_token_to_piece(vocab, token, ptr.baseAddress, Int32(ptr.count), 0, false)
            }
            guard count > 0 else { return [] }
            return large.prefix(Int(count)).map { UInt8(bitPattern: $0) }
        }

        guard count > 0 else { return [] }
        return small.prefix(Int(count)).map { UInt8(bitPattern: $0) }
    }
}

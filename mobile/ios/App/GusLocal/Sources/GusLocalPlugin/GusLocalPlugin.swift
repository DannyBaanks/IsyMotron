#if os(iOS) && canImport(Capacitor) && canImport(UIKit)
import Capacitor
import Foundation
import GusModelStore
import GUSBridge
import UniformTypeIdentifiers
import UIKit

@objc(GusLocalPlugin)
public final class GusLocalPlugin: CAPPlugin, CAPBridgedPlugin, UIDocumentPickerDelegate {
    public let identifier = "GusLocalPlugin"
    public let jsName = "GusLocal"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "listModels", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "downloadModel", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "cancelDownload", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "importModels", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "exportModel", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "generate", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "cancel", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "unload", returnType: CAPPluginReturnPromise)
    ]

    private lazy var store: GusModelStore = {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return GusModelStore(modelsDirectory: support.appendingPathComponent("IsyMotron/GUS/Models", isDirectory: true), catalogue: GUSCatalog.models)
    }()
    private var pendingPickerCall: CAPPluginCall?
    private var pickerMode: PickerMode?
    private var downloads: [String: GusDownloadJob] = [:]
    private let inferenceQueue = DispatchQueue(label: "io.github.dannybaanks.isymotron.gus.inference", qos: .userInitiated)
    private let inferenceLock = NSLock()
    private var activeContext: OpaquePointer?

    private enum PickerMode { case importing, exporting(String) }

    @objc public func listModels(_ call: CAPPluginCall) {
        let installed = Set(GUSCatalog.models.compactMap { store.isInstalled(id: $0.id) ? $0.id : nil })
        let models: [[String: Any]] = GUSCatalog.models.map { model in
            ["id": model.id, "name": model.name, "repository": model.repository, "filename": model.filename,
             "revision": model.revision, "url": model.url.absoluteString, "byteCount": model.byteCount,
             "sha256": model.sha256, "licenseName": model.licenseName, "licenseUrl": model.licenseURL.absoluteString,
             "attribution": model.attribution, "installed": installed.contains(model.id)]
        }
        call.resolve(["models": models, "available": true])
    }

    @objc public func downloadModel(_ call: CAPPluginCall) {
        guard let id = call.getString("modelId"), let model = GUSCatalog.models.first(where: { $0.id == id }) else { call.reject("Unknown GUS model ID."); return }
        guard downloads[id] == nil else { call.reject("This model is already downloading."); return }
        let job = GusDownloadJob(model: model, progress: { [weak self] received, total in
            self?.notifyListeners("downloadProgress", data: ["modelId": id, "receivedBytes": received, "totalBytes": total])
        }, completion: { [weak self] result in
            guard let self else { return }
            DispatchQueue.main.async {
                self.downloads[id] = nil
                switch result {
                case .success(let file):
                    defer { try? FileManager.default.removeItem(at: file) }
                    do {
                        _ = try self.store.installDownloadedModel(id: id, from: file)
                        call.resolve(["modelId": id, "installed": true, "sizeBytes": model.byteCount])
                    } catch { call.reject("No se pudo verificar el modelo descargado.", nil, error) }
                case .failure(let error): call.reject("No se pudo verificar el modelo descargado.", nil, error)
                }
            }
        })
        downloads[id] = job
        job.start()
    }

    @objc public func cancelDownload(_ call: CAPPluginCall) {
        let id = call.getString("modelId") ?? ""
        let job = downloads.removeValue(forKey: id)
        job?.cancel()
        call.resolve(["cancelled": job != nil])
    }

    @objc public func importModels(_ call: CAPPluginCall) {
        guard pendingPickerCall == nil else { call.reject("A model file picker is already open."); return }
        pendingPickerCall = call; pickerMode = .importing
        let picker = UIDocumentPickerViewController(forOpeningContentTypes: [.data], asCopy: false)
        picker.allowsMultipleSelection = true; picker.delegate = self
        bridge?.viewController?.present(picker, animated: true)
    }

    @objc public func exportModel(_ call: CAPPluginCall) {
        guard let id = call.getString("modelId"), GUSCatalog.models.contains(where: { $0.id == id }), store.isInstalled(id: id) else { call.reject("Unknown or missing GUS model."); return }
        guard pendingPickerCall == nil else { call.reject("A model file picker is already open."); return }
        pendingPickerCall = call; pickerMode = .exporting(id)
        inferenceQueue.async { [weak self] in
            guard let self else { return }
            guard let source = self.store.modelURL(id: id) else {
                DispatchQueue.main.async { self.pendingPickerCall = nil; self.pickerMode = nil; call.reject("The installed model failed SHA-256 verification.") }
                return
            }
            DispatchQueue.main.async {
                let picker = UIDocumentPickerViewController(forExporting: [source], asCopy: true)
                picker.shouldShowFileExtensions = true; picker.delegate = self
                self.bridge?.viewController?.present(picker, animated: true)
            }
        }
    }

    public func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
        guard let call = pendingPickerCall else { return }
        let mode = pickerMode; pendingPickerCall = nil; pickerMode = nil
        if case .importing = mode { call.resolve(["cancelled": true, "models": []]) }
        else { call.resolve(["cancelled": true]) }
    }

    public func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        guard let call = pendingPickerCall, let mode = pickerMode else { return }
        pendingPickerCall = nil; pickerMode = nil
        inferenceQueue.async { [weak self] in
            guard let self else { return }
            do {
                switch mode {
                case .importing:
                    var imported: [[String: Any]] = []
                    for url in urls {
                        let file = try self.store.importModel(from: url)
                        guard let model = GUSCatalog.models.first(where: { $0.id == file.deletingPathExtension().lastPathComponent }) else { throw GusModelStoreError.unknownModel }
                        imported.append(["id": model.id, "name": model.name])
                    }
                    call.resolve(["cancelled": false, "models": imported])
                case .exporting(let id):
                    guard !urls.isEmpty else { call.resolve(["cancelled": true]); return }
                    call.resolve(["cancelled": false, "modelId": id])
                }
            } catch { call.reject("No se pudo procesar el GGUF; el modelo y su copia externa permanecen intactos.", nil, error) }
        }
    }

    @objc public func generate(_ call: CAPPluginCall) {
        guard let id = call.getString("modelId"), GUSCatalog.models.contains(where: { $0.id == id }), store.isInstalled(id: id),
              let messages = call.getArray("messages") as? [[String: String]], !messages.isEmpty, messages.count <= 64 else { call.reject("Invalid GUS model or messages."); return }
        let contextTokens = call.getInt("contextTokens") ?? 2048
        let maxTokens = call.getInt("maxTokens") ?? 160
        let totalCharacters = messages.reduce(0) { $0 + ($1["content"]?.count ?? 0) }
        guard contextTokens >= 512, contextTokens <= 2048, maxTokens >= 1, maxTokens <= 160, totalCharacters <= 32_000,
              messages.allSatisfy({ ["system", "user", "assistant"].contains($0["role"] ?? "") && ($0["content"]?.count ?? 20_001) <= 12_000 }) else { call.reject("Invalid GUS generation request or limits."); return }
        inferenceQueue.async { [weak self] in
            guard let self else { return }
            guard let modelURL = self.store.modelURL(id: id) else { call.reject("The installed model failed SHA-256 verification."); return }
            var errorBuffer = [CChar](repeating: 0, count: 1024)
            guard let context = modelURL.path.withCString({ path in
                errorBuffer.withUnsafeMutableBufferPointer { buffer in gus_llama_create(path, UInt32(contextTokens), buffer.baseAddress, buffer.count) }
            }) else {
                call.reject(String(cString: errorBuffer)); return
            }
            self.inferenceLock.lock(); self.activeContext = context; self.inferenceLock.unlock()
            defer { gus_llama_destroy(context); self.inferenceLock.lock(); if self.activeContext == context { self.activeContext = nil }; self.inferenceLock.unlock() }
            let result = self.withNativeMessages(messages) { nativeMessages, count in
                var stats = GUSGenerationStats()
                var sampling = gus_llama_default_chat_sampling()
                return errorBuffer.withUnsafeMutableBufferPointer { buffer in
                    gus_llama_generate_chat_sampled(context, nativeMessages, count, nil, UInt32(maxTokens), &sampling, &stats, buffer.baseAddress, buffer.count)
                }
            }
            guard let result else { call.reject(String(cString: errorBuffer)); return }
            let response = String(cString: result); gus_llama_free_text(result); call.resolve(["text": response])
        }
    }

    @objc public func cancel(_ call: CAPPluginCall) {
        inferenceLock.lock(); let context = activeContext; if let context { gus_llama_cancel(context) }; inferenceLock.unlock()
        call.resolve(["cancelled": context != nil])
    }

    @objc public func unload(_ call: CAPPluginCall) { cancel(call) }

    private func withNativeMessages(_ messages: [[String: String]], _ body: (UnsafePointer<GUSChatMessage>, Int) -> UnsafeMutablePointer<CChar>?) -> UnsafeMutablePointer<CChar>? {
        let roles = messages.compactMap { $0["role"] }
        let contents = messages.compactMap { $0["content"] }
        guard roles.count == messages.count, contents.count == messages.count else { return nil }
        var native = [GUSChatMessage](repeating: GUSChatMessage(role: nil, content: nil), count: messages.count)
        return roles.withUnsafeBufferPointer { roleBuffer in
            contents.withUnsafeBufferPointer { contentBuffer in
                var result: UnsafeMutablePointer<CChar>?
                func fill(_ index: Int) {
                    guard index < messages.count else { result = native.withUnsafeBufferPointer { body($0.baseAddress!, $0.count) }; return }
                    roleBuffer[index].withCString { role in contentBuffer[index].withCString { content in native[index] = GUSChatMessage(role: role, content: content); fill(index + 1) } }
                }
                fill(0)
                return result
            }
        }
    }
}

private final class GusDownloadJob: NSObject, URLSessionDownloadDelegate, URLSessionTaskDelegate {
    private let model: GusModelManifest
    private let progress: (Int64, Int64) -> Void
    private let completion: (Result<URL, Error>) -> Void
    private var session: URLSession!
    private var task: URLSessionDownloadTask?
    private let completionLock = NSLock()
    private var completed = false
    private let approvedHosts: Set<String> = ["huggingface.co", "us.aws.cdn.hf.co", "cdn-lfs.huggingface.co", "cas-bridge.xethub.hf.co"]

    init(model: GusModelManifest, progress: @escaping (Int64, Int64) -> Void, completion: @escaping (Result<URL, Error>) -> Void) {
        self.model = model; self.progress = progress; self.completion = completion
        super.init()
        session = URLSession(configuration: .ephemeral, delegate: self, delegateQueue: nil)
    }
    func start() { task = session.downloadTask(with: model.url); task?.resume() }
    func cancel() { finish(.failure(CancellationError())); task?.cancel(); session.invalidateAndCancel() }
    private func finish(_ result: Result<URL, Error>) {
        completionLock.lock(); defer { completionLock.unlock() }
        guard !completed else { return }
        completed = true
        completion(result)
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        guard let url = request.url, url.scheme == "https", let host = url.host?.lowercased(), approvedHosts.contains(host), url.user == nil, url.password == nil else { completionHandler(nil); finish(.failure(GusModelStoreError.unsafeDownloadURL)); return }
        completionHandler(request)
    }
    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didWriteData bytesWritten: Int64, totalBytesWritten: Int64, totalBytesExpectedToWrite: Int64) {
        progress(totalBytesWritten, totalBytesExpectedToWrite > 0 ? totalBytesExpectedToWrite : model.byteCount)
    }
    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didFinishDownloadingTo location: URL) {
        guard let response = downloadTask.response as? HTTPURLResponse else { finish(.failure(GusModelStoreError.unsafeDownloadURL)); return }
        guard (200...299).contains(response.statusCode) else { finish(.failure(GusModelStoreError.httpStatus(response.statusCode))); return }
        guard let finalURL = response.url, finalURL.scheme == "https", finalURL.host.map({ approvedHosts.contains($0.lowercased()) }) == true else { finish(.failure(GusModelStoreError.unsafeDownloadURL)); return }
        let destination = FileManager.default.temporaryDirectory.appendingPathComponent("gus-download-\(UUID().uuidString).gguf")
        do { try FileManager.default.moveItem(at: location, to: destination); finish(.success(destination)) }
        catch { try? FileManager.default.removeItem(at: destination); finish(.failure(error)) }
        session.finishTasksAndInvalidate()
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error { finish(.failure(error)) }
    }
}
#endif

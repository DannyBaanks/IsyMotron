import CryptoKit
import Foundation

public struct GusModelManifest: Codable, Equatable, Sendable {
    public let id: String
    public let name: String
    public let repository: String
    public let filename: String
    public let revision: String
    public let url: URL
    public let byteCount: Int64
    public let sha256: String
    public let licenseName: String
    public let licenseURL: URL
    public let attribution: String

    public init(id: String, name: String, repository: String, filename: String, revision: String, url: URL, byteCount: Int64, sha256: String, licenseName: String, licenseURL: URL, attribution: String) {
        self.id = id
        self.name = name
        self.repository = repository
        self.filename = filename
        self.revision = revision
        self.url = url
        self.byteCount = byteCount
        self.sha256 = sha256
        self.licenseName = licenseName
        self.licenseURL = licenseURL
        self.attribution = attribution
    }
}

public enum GusModelStoreError: LocalizedError {
    case unknownModel
    case invalidManifest(String)
    case invalidSize
    case invalidHash
    case destinationExists
    case unsafeDownloadURL
    case httpStatus(Int)
    case tooManyRedirects

    public var errorDescription: String? {
        switch self {
        case .unknownModel: return "This model is not in the pinned GUS catalogue."
        case .invalidManifest(let detail): return "Invalid pinned GUS model metadata: \(detail)"
        case .invalidSize: return "Model size does not match the pinned catalogue."
        case .invalidHash: return "Model SHA-256 does not match the pinned catalogue."
        case .destinationExists: return "A file already exists at that backup location. Choose another name."
        case .unsafeDownloadURL: return "The model download left an approved HTTPS host."
        case .httpStatus(let status): return "Model download failed with HTTP \(status)."
        case .tooManyRedirects: return "The model download redirected too many times."
        }
    }
}

public protocol GusModelFileAccess {
    func copyImportedFile(from source: URL, to destination: URL, using copier: (URL, URL) throws -> Void) throws
    func copyExportedFile(from source: URL, to destination: URL, using copier: (URL, URL) throws -> Void) throws
}

public struct LocalModelFileAccess: GusModelFileAccess {
    public init() {}

    public func copyImportedFile(from source: URL, to destination: URL, using copier: (URL, URL) throws -> Void) throws {
        let scoped = source.startAccessingSecurityScopedResource()
        defer { if scoped { source.stopAccessingSecurityScopedResource() } }
        var coordinationError: NSError?
        var copyError: Error?
        let coordinator = NSFileCoordinator(filePresenter: nil)
        coordinator.coordinate(readingItemAt: source, options: .withoutChanges, error: &coordinationError) { coordinatedURL in
            do { try copier(coordinatedURL, destination) } catch { copyError = error }
        }
        if let coordinationError { throw coordinationError }
        if let copyError { throw copyError }
    }

    public func copyExportedFile(from source: URL, to destination: URL, using copier: (URL, URL) throws -> Void) throws {
        let scoped = destination.startAccessingSecurityScopedResource()
        defer { if scoped { destination.stopAccessingSecurityScopedResource() } }
        var coordinationError: NSError?
        var copyError: Error?
        let coordinator = NSFileCoordinator(filePresenter: nil)
        coordinator.coordinate(writingItemAt: destination, options: .forReplacing, error: &coordinationError) { coordinatedURL in
            do { try copier(source, coordinatedURL) } catch { copyError = error }
        }
        if let coordinationError { throw coordinationError }
        if let copyError { throw copyError }
    }
}

public final class GusModelStore {
    public let modelsDirectory: URL
    public let catalogue: [GusModelManifest]
    private let modelsByID: [String: GusModelManifest]
    private let fileAccess: GusModelFileAccess
    private let copyFile: (URL, URL) throws -> Void
    private let fileManager: FileManager

    public init(
        modelsDirectory: URL,
        catalogue: [GusModelManifest],
        fileAccess: GusModelFileAccess = LocalModelFileAccess(),
        fileManager: FileManager = .default,
        copyFile: @escaping (URL, URL) throws -> Void = { try FileManager.default.copyItem(at: $0, to: $1) }
    ) {
        self.modelsDirectory = modelsDirectory
        self.catalogue = catalogue
        self.modelsByID = Dictionary(catalogue.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        self.fileAccess = fileAccess
        self.fileManager = fileManager
        self.copyFile = copyFile
    }

    public func modelURL(id: String) -> URL? {
        guard let model = modelsByID[id] else { return nil }
        let url = modelsDirectory.appendingPathComponent(model.id).appendingPathExtension("gguf")
        guard verify(url, matches: model) else { return nil }
        return url
    }

    /// Cheap catalogue display check. Generation and export still call modelURL,
    /// which re-hashes the complete model before native use or external copying.
    public func isInstalled(id: String) -> Bool {
        guard let model = modelsByID[id],
              let attributes = try? fileManager.attributesOfItem(atPath: modelsDirectory.appendingPathComponent(model.id).appendingPathExtension("gguf").path),
              attributes[.type] as? FileAttributeType == .typeRegular,
              let size = attributes[.size] as? NSNumber else { return false }
        return size.int64Value == model.byteCount
    }

    public func installModel(id: String, from source: URL) throws -> URL {
        guard let model = modelsByID[id] else { throw GusModelStoreError.unknownModel }
        try validate(model)
        try fileManager.createDirectory(at: modelsDirectory, withIntermediateDirectories: true)
        let staged = modelsDirectory.appendingPathComponent(".import-\(UUID().uuidString).part")
        defer { try? fileManager.removeItem(at: staged) }
        try fileAccess.copyImportedFile(from: source, to: staged) { coordinatedSource, destination in
            guard self.fileSize(coordinatedSource) == model.byteCount else { throw GusModelStoreError.invalidSize }
            try self.copyFile(coordinatedSource, destination)
        }
        try verify(staged, matches: model, throwOnFailure: true)
        return try adopt(staged, for: model)
    }

    /// Adopts a URLSession temporary download without copying the large GGUF
    /// twice. Download inputs are app-owned temporary files, never picker URLs.
    public func installDownloadedModel(id: String, from source: URL) throws -> URL {
        guard let model = modelsByID[id] else { throw GusModelStoreError.unknownModel }
        try validate(model)
        try fileManager.createDirectory(at: modelsDirectory, withIntermediateDirectories: true)
        let staged = modelsDirectory.appendingPathComponent(".download-\(UUID().uuidString).part")
        defer { try? fileManager.removeItem(at: staged) }
        try fileManager.moveItem(at: source, to: staged)
        try verify(staged, matches: model, throwOnFailure: true)
        return try adopt(staged, for: model)
    }

    public func importModel(from source: URL) throws -> URL {
        try fileManager.createDirectory(at: modelsDirectory, withIntermediateDirectories: true)
        let staged = modelsDirectory.appendingPathComponent(".import-\(UUID().uuidString).part")
        defer { try? fileManager.removeItem(at: staged) }
        try fileAccess.copyImportedFile(from: source, to: staged) { coordinatedSource, destination in
            let size = self.fileSize(coordinatedSource)
            guard self.catalogue.contains(where: { $0.byteCount == size }) else { throw GusModelStoreError.invalidSize }
            try self.copyFile(coordinatedSource, destination)
        }
        guard let model = catalogue.first(where: { verify(staged, matches: $0) }) else {
            let size = fileSize(staged)
            guard catalogue.contains(where: { $0.byteCount == size }) else { throw GusModelStoreError.invalidSize }
            throw GusModelStoreError.invalidHash
        }
        try validate(model)
        return try adopt(staged, for: model)
    }

    public func exportModel(id: String, to destination: URL) throws {
        guard let model = modelsByID[id] else { throw GusModelStoreError.unknownModel }
        let source = modelsDirectory.appendingPathComponent(model.id).appendingPathExtension("gguf")
        try verify(source, matches: model, throwOnFailure: true)
        guard !fileManager.fileExists(atPath: destination.path) else { throw GusModelStoreError.destinationExists }
        let parent = destination.deletingLastPathComponent()
        try fileAccess.copyExportedFile(from: source, to: destination) { sourceURL, targetURL in
            try self.fileManager.createDirectory(at: parent, withIntermediateDirectories: true)
            try self.copyFile(sourceURL, targetURL)
        }
        try verify(destination, matches: model, throwOnFailure: true)
    }

    private func adopt(_ staged: URL, for model: GusModelManifest) throws -> URL {
        let target = modelsDirectory.appendingPathComponent(model.id).appendingPathExtension("gguf")
        if fileManager.fileExists(atPath: target.path) {
            _ = try fileManager.replaceItemAt(target, withItemAt: staged, backupItemName: nil, options: [])
        } else {
            try fileManager.moveItem(at: staged, to: target)
        }
        return target
    }

    private func validate(_ model: GusModelManifest) throws {
        guard model.id.range(of: "^[a-z0-9]+(?:-[a-z0-9]+)*$", options: .regularExpression) != nil else { throw GusModelStoreError.invalidManifest("invalid model ID") }
        guard model.byteCount > 0, model.byteCount <= 3_000_000_000 else { throw GusModelStoreError.invalidManifest("invalid model size") }
        guard model.revision.range(of: "^[a-f0-9]{40}$", options: .regularExpression) != nil,
              model.sha256.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil else { throw GusModelStoreError.invalidManifest("invalid revision or SHA-256") }
        guard model.url.scheme == "https", model.url.host == "huggingface.co", model.url.user == nil, model.url.password == nil,
              model.url.path.contains("/resolve/\(model.revision)/\(model.filename)") else { throw GusModelStoreError.invalidManifest("URL is not pinned to the model revision") }
        guard model.licenseURL.scheme == "https" else { throw GusModelStoreError.invalidManifest("license URL must use HTTPS") }
    }

    private func verify(_ url: URL, matches model: GusModelManifest) -> Bool {
        (try? verify(url, matches: model, throwOnFailure: true)) != nil
    }

    private func verify(_ url: URL, matches model: GusModelManifest, throwOnFailure: Bool) throws {
        guard let attributes = try? fileManager.attributesOfItem(atPath: url.path),
              let size = attributes[.size] as? NSNumber, size.int64Value == model.byteCount else {
            if throwOnFailure { throw GusModelStoreError.invalidSize }
            return
        }
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var hasher = SHA256()
        while true {
            let data = try handle.read(upToCount: 1024 * 1024) ?? Data()
            if data.isEmpty { break }
            hasher.update(data: data)
        }
        let actual = hasher.finalize().map { String(format: "%02x", $0) }.joined()
        guard actual == model.sha256 else {
            if throwOnFailure { throw GusModelStoreError.invalidHash }
            return
        }
    }

    private func fileSize(_ url: URL) -> Int64 {
        guard let attributes = try? fileManager.attributesOfItem(atPath: url.path),
              let size = attributes[.size] as? NSNumber else { return -1 }
        return size.int64Value
    }
}

public struct GusRemoteConfig: Codable, Equatable, Sendable {
    public let baseURL: URL
    public let model: String
    public init(baseURL: URL, model: String) { self.baseURL = baseURL; self.model = model }
}

public protocol GusCredentialVault {
    func readRemoteConfig() throws -> GusRemoteConfig?
    func writeRemoteConfig(_ value: GusRemoteConfig?) throws
    func readAPIKey() throws -> String?
    func writeAPIKey(_ value: String?) throws
}

public final class GusCredentialsStore {
    private let vault: GusCredentialVault
    public init(vault: GusCredentialVault) { self.vault = vault }
    public func remoteConfig() throws -> GusRemoteConfig? { try vault.readRemoteConfig() }
    public func apiKey() throws -> String? { try vault.readAPIKey() }
    public func saveRemoteConfig(_ config: GusRemoteConfig) throws {
        guard config.baseURL.scheme?.lowercased() == "https", config.baseURL.host != nil,
              config.baseURL.user == nil, config.baseURL.password == nil,
              config.baseURL.query == nil, config.baseURL.fragment == nil,
              !config.model.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw GusModelStoreError.invalidManifest("remote endpoint must be HTTPS and include a model")
        }
        try vault.writeRemoteConfig(config)
    }
    public func saveAPIKey(_ key: String) throws {
        guard !key.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, key.count <= 4096 else { throw GusModelStoreError.invalidManifest("invalid API key") }
        try vault.writeAPIKey(key)
    }
    public func clearRemoteConfig() throws {
        try vault.writeRemoteConfig(nil)
        try vault.writeAPIKey(nil)
    }
}

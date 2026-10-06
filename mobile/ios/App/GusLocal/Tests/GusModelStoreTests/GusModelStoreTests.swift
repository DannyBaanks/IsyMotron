import CryptoKit
import Foundation
import XCTest
@testable import GusModelStore

final class GusModelStoreTests: XCTestCase {
    private func digest(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private func manifest(_ data: Data, id: String = "fixture-gguf") -> GusModelManifest {
        GusModelManifest(
            id: id,
            name: "Fixture GGUF",
            repository: "fixture/model",
            filename: "fixture.gguf",
            revision: "0123456789012345678901234567890123456789",
            url: URL(string: "https://huggingface.co/fixture/model/resolve/0123456789012345678901234567890123456789/fixture.gguf")!,
            byteCount: Int64(data.count),
            sha256: digest(data),
            licenseName: "Apache License 2.0",
            licenseURL: URL(string: "https://www.apache.org/licenses/LICENSE-2.0")!,
            attribution: "test fixture"
        )
    }

    private func makeStore(
        root: URL,
        manifest: GusModelManifest,
        access: GusModelFileAccess = LocalModelFileAccess(),
        copyFile: @escaping (URL, URL) throws -> Void = { try FileManager.default.copyItem(at: $0, to: $1) }
    ) -> GusModelStore {
        GusModelStore(modelsDirectory: root.appendingPathComponent("IsyMotron/GUS/Models", isDirectory: true), catalogue: [manifest], fileAccess: access, copyFile: copyFile)
    }

    private func temporaryDirectory() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    func testRejectsIDsOutsideThePinnedCatalogue() throws {
        let data = Data("verified model".utf8)
        let root = try temporaryDirectory()
        let store = makeStore(root: root, manifest: manifest(data))
        let source = root.appendingPathComponent("model.gguf")
        try data.write(to: source)
        XCTAssertThrowsError(try store.installModel(id: "../../outside", from: source))
        XCTAssertNil(store.modelURL(id: "../../outside"))
    }

    func testRejectsCatalogueManifestAboveTheThreeGigabyteSafetyCeiling() throws {
        let data = Data("fixture bytes".utf8)
        let base = manifest(data)
        let model = GusModelManifest(
            id: base.id, name: base.name, repository: base.repository, filename: base.filename,
            revision: base.revision, url: base.url, byteCount: 3_000_000_001,
            sha256: base.sha256, licenseName: base.licenseName, licenseURL: base.licenseURL,
            attribution: base.attribution
        )
        let root = try temporaryDirectory()
        let store = makeStore(root: root, manifest: model)
        let source = root.appendingPathComponent("model.gguf")
        try data.write(to: source)
        XCTAssertThrowsError(try store.installModel(id: model.id, from: source))
        XCTAssertFalse(FileManager.default.fileExists(atPath: store.modelsDirectory.path))
    }

    func testRejectsWrongSizeAndHashWithoutReplacingInstalledModel() throws {
        let valid = Data("known good model".utf8)
        let root = try temporaryDirectory()
        let store = makeStore(root: root, manifest: manifest(valid))
        let original = root.appendingPathComponent("original.gguf")
        try valid.write(to: original)
        let installed = try store.installModel(id: "fixture-gguf", from: original)
        let originalBytes = try Data(contentsOf: installed)
        let wrongSize = root.appendingPathComponent("wrong-size.gguf")
        try Data("x".utf8).write(to: wrongSize)
        XCTAssertThrowsError(try store.installModel(id: "fixture-gguf", from: wrongSize))
        let wrongHash = root.appendingPathComponent("wrong-hash.gguf")
        try Data("known evil model".utf8).write(to: wrongHash)
        XCTAssertEqual(try Data(contentsOf: wrongHash).count, valid.count)
        XCTAssertThrowsError(try store.installModel(id: "fixture-gguf", from: wrongHash))
        XCTAssertEqual(try Data(contentsOf: installed), originalBytes)
    }

    func testCatalogueDisplayUsesSizeButInferenceAccessorRehashes() throws {
        let valid = Data("size-only list check".utf8)
        let root = try temporaryDirectory()
        let model = manifest(valid)
        let store = makeStore(root: root, manifest: model)
        let source = root.appendingPathComponent("model.gguf")
        try valid.write(to: source)
        let installed = try store.installModel(id: model.id, from: source)
        XCTAssertTrue(store.isInstalled(id: model.id))
        try Data(repeating: 0x41, count: valid.count).write(to: installed)
        XCTAssertTrue(store.isInstalled(id: model.id))
        XCTAssertNil(store.modelURL(id: model.id))
    }

    func testImportsOnlyVerifiedBytesAndExportsAUserOwnedCopy() throws {
        let data = Data("catalogued GGUF bytes".utf8)
        let root = try temporaryDirectory()
        let store = makeStore(root: root, manifest: manifest(data))
        let source = root.appendingPathComponent("downloaded.gguf")
        try data.write(to: source)
        let installed = try store.importModel(from: source)
        XCTAssertEqual(try Data(contentsOf: installed), data)
        let backup = root.appendingPathComponent("external-copy.gguf")
        try store.exportModel(id: "fixture-gguf", to: backup)
        XCTAssertEqual(try Data(contentsOf: backup), data)
        XCTAssertThrowsError(try store.exportModel(id: "fixture-gguf", to: backup))
    }

    func testFailedStagedCopyKeepsThePreviouslyInstalledModel() throws {
        let previous = Data("previous valid bytes".utf8)
        let next = Data("replacement valid bytes".utf8)
        let root = try temporaryDirectory()
        let model = manifest(previous)
        let store = makeStore(root: root, manifest: model)
        let oldSource = root.appendingPathComponent("old.gguf")
        try previous.write(to: oldSource)
        let installed = try store.installModel(id: model.id, from: oldSource)
        let newSource = root.appendingPathComponent("new.gguf")
        try next.write(to: newSource)
        let failingStore = makeStore(root: root, manifest: model, copyFile: { _, _ in throw CocoaError(.fileReadUnknown) })
        XCTAssertThrowsError(try failingStore.installModel(id: model.id, from: newSource))
        XCTAssertEqual(try Data(contentsOf: installed), previous)
    }

    func testDeniedOrRevokedPickerAccessLeavesInstalledModelAndStoreUnchanged() throws {
        let data = Data("still installed".utf8)
        let root = try temporaryDirectory()
        let model = manifest(data)
        let store = makeStore(root: root, manifest: model)
        let valid = root.appendingPathComponent("valid.gguf")
        try data.write(to: valid)
        let installed = try store.installModel(id: model.id, from: valid)
        let deniedStore = makeStore(root: root, manifest: model, access: RejectingModelFileAccess())
        XCTAssertThrowsError(try deniedStore.importModel(from: valid))
        XCTAssertEqual(try Data(contentsOf: installed), data)
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: installed.deletingLastPathComponent().path), ["fixture-gguf.gguf"])
    }

    func testAnExportedCatalogueModelRestoresAfterAReinstall() throws {
        let data = Data("reinstall restore fixture".utf8)
        let root = try temporaryDirectory()
        let model = manifest(data)
        let beforeReinstall = makeStore(root: root.appendingPathComponent("before"), manifest: model)
        let source = root.appendingPathComponent("source.gguf")
        try data.write(to: source)
        _ = try beforeReinstall.installModel(id: model.id, from: source)
        let backup = root.appendingPathComponent("external/backup.gguf")
        try FileManager.default.createDirectory(at: backup.deletingLastPathComponent(), withIntermediateDirectories: true)
        try beforeReinstall.exportModel(id: model.id, to: backup)
        let afterReinstall = makeStore(root: root.appendingPathComponent("after"), manifest: model)
        let restored = try afterReinstall.importModel(from: backup)
        XCTAssertEqual(try Data(contentsOf: restored), data)
    }

    func testRemoteCredentialCRUDUsesAnInjectableSecureVault() throws {
        let vault = MemoryCredentialVault()
        let credentials = GusCredentialsStore(vault: vault)
        let config = GusRemoteConfig(baseURL: URL(string: "https://api.example.test/v1")!, model: "remote-model")
        try credentials.saveRemoteConfig(config)
        try credentials.saveAPIKey("secret-fixture-key")
        XCTAssertEqual(try credentials.remoteConfig(), config)
        XCTAssertEqual(try credentials.apiKey(), "secret-fixture-key")
        try credentials.clearRemoteConfig()
        XCTAssertNil(try credentials.remoteConfig())
        XCTAssertNil(try credentials.apiKey())
    }
}

private struct RejectingModelFileAccess: GusModelFileAccess {
    func copyImportedFile(from source: URL, to destination: URL, using copier: (URL, URL) throws -> Void) throws { throw CocoaError(.fileReadNoPermission) }
    func copyExportedFile(from source: URL, to destination: URL, using copier: (URL, URL) throws -> Void) throws { throw CocoaError(.fileWriteNoPermission) }
}

private final class MemoryCredentialVault: GusCredentialVault {
    private var config: GusRemoteConfig?
    private var key: String?
    func readRemoteConfig() throws -> GusRemoteConfig? { config }
    func writeRemoteConfig(_ value: GusRemoteConfig?) throws { config = value }
    func readAPIKey() throws -> String? { key }
    func writeAPIKey(_ value: String?) throws { key = value }
}

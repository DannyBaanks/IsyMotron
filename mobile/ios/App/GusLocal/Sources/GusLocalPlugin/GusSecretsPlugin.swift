import Capacitor
import Foundation
import Security

@objc(GusSecretsPlugin)
public final class GusSecretsPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "GusSecretsPlugin"
    public let jsName = "GusSecrets"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "getRemoteConfig", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "saveRemoteConfig", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getApiKey", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "saveApiKey", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "clearRemoteConfig", returnType: CAPPluginReturnPromise)
    ]

    private let configAccount = "isymotron.gus.remote.config.v1"
    private let keyAccount = "isymotron.gus.remote.api-key.v1"

    @objc public func getRemoteConfig(_ call: CAPPluginCall) {
        do {
            guard let data = try read(account: configAccount),
                  let config = try JSONSerialization.jsonObject(with: data) as? [String: String] else { call.resolve(); return }
            call.resolve(config)
        } catch { call.reject("Could not read remote GUS configuration.", nil, error) }
    }

    @objc public func saveRemoteConfig(_ call: CAPPluginCall) {
        guard let rawURL = call.getString("baseUrl"), let model = call.getString("model")?.trimmingCharacters(in: .whitespacesAndNewlines),
              let url = URL(string: rawURL), url.scheme?.lowercased() == "https", url.host != nil,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil, !model.isEmpty else {
            call.reject("Use an HTTPS endpoint without credentials, query, or fragment and include a model name."); return
        }
        do {
            let normalized = rawURL.replacingOccurrences(of: "/+$", with: "", options: .regularExpression)
            let data = try JSONSerialization.data(withJSONObject: ["baseUrl": normalized, "model": model])
            try write(data, account: configAccount)
            call.resolve()
        } catch { call.reject("Could not store remote GUS configuration.", nil, error) }
    }

    @objc public func getApiKey(_ call: CAPPluginCall) {
        do {
            let key = try read(account: keyAccount).flatMap { String(data: $0, encoding: .utf8) }
            call.resolve(["apiKey": key as Any? ?? NSNull()])
        } catch { call.reject("Could not read the Keychain API key.", nil, error) }
    }

    @objc public func saveApiKey(_ call: CAPPluginCall) {
        guard let key = call.getString("apiKey"), !key.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, key.count <= 4096 else {
            call.reject("API key is empty or too long."); return
        }
        do { try write(Data(key.utf8), account: keyAccount); call.resolve() }
        catch { call.reject("Could not store the API key in Keychain.", nil, error) }
    }

    @objc public func clearRemoteConfig(_ call: CAPPluginCall) {
        do { try delete(account: configAccount); try delete(account: keyAccount); call.resolve() }
        catch { call.reject("Could not clear remote GUS credentials.", nil, error) }
    }

    private func baseQuery(account: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: "io.github.dannybaanks.isymotron.gus", kSecAttrAccount as String: account]
    }

    private func read(account: String) throws -> Data? {
        var query = baseQuery(account: account); query[kSecReturnData as String] = true; query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess else { throw NSError(domain: NSOSStatusErrorDomain, code: Int(status)) }
        return result as? Data
    }

    private func write(_ data: Data, account: String) throws {
        let query = baseQuery(account: account)
        let status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var insert = query; insert[kSecValueData as String] = data; insert[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            let added = SecItemAdd(insert as CFDictionary, nil)
            guard added == errSecSuccess else { throw NSError(domain: NSOSStatusErrorDomain, code: Int(added)) }
        } else if status != errSecSuccess { throw NSError(domain: NSOSStatusErrorDomain, code: Int(status)) }
    }

    private func delete(account: String) throws {
        let status = SecItemDelete(baseQuery(account: account) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw NSError(domain: NSOSStatusErrorDomain, code: Int(status)) }
    }
}

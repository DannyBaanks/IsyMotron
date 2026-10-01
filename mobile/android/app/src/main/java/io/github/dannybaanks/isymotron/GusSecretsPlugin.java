package io.github.dannybaanks.isymotron;

import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.net.URI;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

@CapacitorPlugin(name = "GusSecrets")
public final class GusSecretsPlugin extends Plugin {
    private static final String PREFS = "gus_remote_secure_store";
    private static final String KEY_ALIAS = "isymotron.gus.remote.api-key.v1";
    private android.content.SharedPreferences preferences() { return getContext().getSharedPreferences(PREFS, android.content.Context.MODE_PRIVATE); }

    @PluginMethod public void getRemoteConfig(PluginCall call) {
        String baseUrl = preferences().getString("baseUrl", null); String model = preferences().getString("model", null);
        JSObject result = new JSObject();
        if (baseUrl == null || model == null) call.resolve();
        else { result.put("baseUrl", baseUrl); result.put("model", model); call.resolve(result); }
    }

    @PluginMethod public void saveRemoteConfig(PluginCall call) {
        String baseUrl = call.getString("baseUrl"); String model = call.getString("model");
        try {
            URI uri = URI.create(baseUrl == null ? "" : baseUrl);
            if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null || model == null || model.trim().isEmpty()) throw new IllegalArgumentException("Use an HTTPS endpoint and a model name.");
            preferences().edit().putString("baseUrl", baseUrl.replaceAll("/+$", "")).putString("model", model.trim()).apply();
            call.resolve();
        } catch (Exception error) { call.reject("Invalid remote GUS configuration.", error); }
    }

    @PluginMethod public void getApiKey(PluginCall call) {
        try { JSObject result = new JSObject(); result.put("apiKey", decrypt(preferences().getString("apiKey", null))); call.resolve(result); }
        catch (Exception error) { call.reject("Could not read the encrypted remote API key.", error); }
    }

    @PluginMethod public void saveApiKey(PluginCall call) {
        String apiKey = call.getString("apiKey");
        if (apiKey == null || apiKey.trim().isEmpty() || apiKey.length() > 4096) { call.reject("API key is empty or too long."); return; }
        try { preferences().edit().putString("apiKey", encrypt(apiKey)).apply(); call.resolve(); }
        catch (Exception error) { call.reject("Could not store the remote API key securely.", error); }
    }

    @PluginMethod public void clearRemoteConfig(PluginCall call) {
        preferences().edit().clear().apply(); call.resolve();
    }

    private String encrypt(String value) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey());
        byte[] encrypted = cipher.doFinal(value.getBytes(java.nio.charset.StandardCharsets.UTF_8));
        byte[] iv = cipher.getIV(); byte[] payload = new byte[iv.length + encrypted.length];
        System.arraycopy(iv, 0, payload, 0, iv.length); System.arraycopy(encrypted, 0, payload, iv.length, encrypted.length);
        return Base64.encodeToString(payload, Base64.NO_WRAP);
    }

    private String decrypt(String encoded) throws Exception {
        if (encoded == null) return null;
        byte[] payload = Base64.decode(encoded, Base64.NO_WRAP); if (payload.length < 29) throw new IllegalArgumentException("Stored key payload is truncated.");
        byte[] iv = java.util.Arrays.copyOfRange(payload, 0, 12); byte[] ciphertext = java.util.Arrays.copyOfRange(payload, 12, payload.length);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), new GCMParameterSpec(128, iv));
        return new String(cipher.doFinal(ciphertext), java.nio.charset.StandardCharsets.UTF_8);
    }

    private SecretKey getOrCreateKey() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null);
        java.security.Key existing = store.getKey(KEY_ALIAS, null); if (existing instanceof SecretKey) return (SecretKey) existing;
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setRandomizedEncryptionRequired(true).build());
        return generator.generateKey();
    }
}

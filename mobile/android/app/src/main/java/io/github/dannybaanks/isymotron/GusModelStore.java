package io.github.dannybaanks.isymotron;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import javax.net.ssl.HttpsURLConnection;

/** Verified app-private store. Public construction always uses the generated catalogue. */
public final class GusModelStore {
    private static final long MAX_MODEL_BYTES = 500_000_000L;
    private static final int REDIRECT_LIMIT = 5;
    private final File modelsDir;
    private final Map<String, GusCatalog.Model> catalog;
    private final DownloadTransport transport;
    private final ConcurrentHashMap<String, InputStream> activeBodies = new ConcurrentHashMap<>();

    public interface DownloadTransport { DownloadResponse open(URL url) throws IOException; }
    public interface ProgressListener { void onProgress(String modelId, long received, long total); }

    public static final class DownloadResponse {
        public final int status;
        public final String location;
        public final InputStream body;
        public DownloadResponse(int status, String location, InputStream body) { this.status = status; this.location = location; this.body = body; }
        public static DownloadResponse redirect(int status, String location) { return new DownloadResponse(status, location, null); }
    }

    public GusModelStore(File filesDir) { this(filesDir, generatedCatalog(), new HttpsTransport()); }

    GusModelStore(File filesDir, Map<String, GusCatalog.Model> catalog, DownloadTransport transport) {
        this.modelsDir = new File(new File(filesDir, "gus"), "models");
        this.catalog = Collections.unmodifiableMap(new HashMap<>(catalog));
        this.transport = transport;
    }

    private static Map<String, GusCatalog.Model> generatedCatalog() {
        Map<String, GusCatalog.Model> result = new HashMap<>();
        for (GusCatalog.Model model : GusCatalog.all()) result.put(model.id, model);
        return result;
    }

    public List<GusCatalog.Model> listInstalledModels() {
        List<GusCatalog.Model> result = new ArrayList<>();
        for (GusCatalog.Model model : catalog.values()) {
            File file = new File(modelsDir, model.id + ".gguf");
            if (file.isFile() && file.length() == model.byteCount) result.add(model);
        }
        return Collections.unmodifiableList(result);
    }

    public File installedFile(String modelId) throws IOException {
        GusCatalog.Model model = requireModel(modelId);
        File file = new File(modelsDir, model.id + ".gguf");
        if (!matches(file, model)) throw new IOException("Verified model is not installed: " + modelId);
        return file;
    }

    public synchronized File importStream(String modelId, InputStream input) throws IOException {
        GusCatalog.Model model = requireModel(modelId);
        File staged = stage(input, model.byteCount, model.id, (id, received, total) -> { });
        if (staged.length() != model.byteCount || !model.sha256.equals(sha256(staged))) {
            staged.delete();
            throw new IOException("Downloaded model size or SHA-256 does not match the pinned catalogue.");
        }
        return adopt(staged, model);
    }

    /** Identifies an imported file by complete pinned size and hash, never its filename. */
    public synchronized GusCatalog.Model importAnyModel(InputStream input) throws IOException {
        File staged = stage(input, MAX_MODEL_BYTES, "", (id, received, total) -> { });
        String digest = sha256(staged);
        for (GusCatalog.Model model : catalog.values()) {
            if (model.byteCount == staged.length() && model.sha256.equals(digest)) { adopt(staged, model); return model; }
        }
        staged.delete();
        throw new IOException("This file does not match any model in the pinned GUS catalogue.");
    }

    public File downloadModel(String modelId) throws IOException { return downloadModel(modelId, (id, received, total) -> { }); }

    public synchronized File downloadModel(String modelId, ProgressListener progress) throws IOException {
        GusCatalog.Model model = requireModel(modelId);
        URL current;
        try { current = new URL(model.url); } catch (Exception error) { throw new IOException("Invalid pinned model URL.", error); }
        if (!trustedUrl(current)) throw new IOException("Model source is not an approved HTTPS host.");
        for (int hop = 0; hop <= REDIRECT_LIMIT; hop++) {
            DownloadResponse response = transport.open(current);
            if (isRedirect(response.status)) {
                close(response.body);
                if (hop == REDIRECT_LIMIT || response.location == null) throw new IOException("Too many or malformed model-download redirects.");
                try { current = current.toURI().resolve(response.location).toURL(); }
                catch (Exception error) { throw new IOException("Invalid model-download redirect.", error); }
                if (!trustedUrl(current)) throw new IOException("Model download redirected outside the approved HTTPS hosts.");
                continue;
            }
            if (response.status != 200 || response.body == null) {
                close(response.body);
                throw new IOException("Model download failed with HTTP " + response.status + ".");
            }
            activeBodies.put(modelId, response.body);
            try (InputStream body = response.body) {
                File staged = stage(body, model.byteCount, model.id, progress);
                if (staged.length() != model.byteCount || !model.sha256.equals(sha256(staged))) {
                    staged.delete();
                    throw new IOException("Downloaded model size or SHA-256 does not match the pinned catalogue.");
                }
                return adopt(staged, model);
            } finally {
                activeBodies.remove(modelId, response.body);
            }
        }
        throw new IOException("Model download redirect limit exceeded.");
    }

    public synchronized void exportModel(String modelId, OutputStream destination) throws IOException {
        File source = installedFile(modelId);
        try (InputStream input = new BufferedInputStream(new FileInputStream(source))) {
            OutputStream output = new BufferedOutputStream(destination);
            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
            output.flush();
        }
    }

    public void cancelDownload(String modelId) {
        InputStream body = activeBodies.remove(modelId);
        close(body);
    }

    private GusCatalog.Model requireModel(String id) throws IOException {
        GusCatalog.Model model = catalog.get(id);
        if (model == null) throw new IOException("Unknown GUS model ID.");
        if (model.byteCount <= 0 || model.byteCount > MAX_MODEL_BYTES || !model.sha256.matches("[a-f0-9]{64}")) throw new IOException("Invalid generated GUS model metadata.");
        return model;
    }

    private File stage(InputStream input, long limit, String id, ProgressListener progress) throws IOException {
        if (input == null) throw new IOException("No model data was provided.");
        if (!modelsDir.exists() && !modelsDir.mkdirs()) throw new IOException("Could not create private GUS model storage.");
        File staged = new File(modelsDir, ".import-" + UUID.randomUUID() + ".part");
        boolean complete = false;
        long copied = 0;
        try (InputStream source = new BufferedInputStream(input); OutputStream output = new BufferedOutputStream(new FileOutputStream(staged))) {
            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = source.read(buffer)) != -1) {
                if (Thread.currentThread().isInterrupted()) throw new IOException("Model transfer cancelled.");
                copied += count;
                if (copied > limit || copied > MAX_MODEL_BYTES) throw new IOException("Model file exceeds its pinned size limit.");
                output.write(buffer, 0, count);
                progress.onProgress(id, copied, limit);
            }
            output.flush();
            complete = true;
        } finally { if (!complete && staged.exists()) staged.delete(); }
        return staged;
    }

    private File adopt(File staged, GusCatalog.Model model) throws IOException {
        File destination = new File(modelsDir, model.id + ".gguf");
        // Both files are siblings in app-private storage; Android/Linux rename is atomic and
        // replaces the previous file only after the staged bytes have passed verification.
        if (!staged.renameTo(destination)) { staged.delete(); throw new IOException("Could not atomically install the verified GUS model."); }
        return destination;
    }

    private boolean matches(File file, GusCatalog.Model model) throws IOException { return file.isFile() && file.length() == model.byteCount && model.sha256.equals(sha256(file)); }

    public String sha256(File file) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream input = new BufferedInputStream(new FileInputStream(file))) {
                byte[] buffer = new byte[64 * 1024]; int count;
                while ((count = input.read(buffer)) != -1) digest.update(buffer, 0, count);
            }
            StringBuilder value = new StringBuilder();
            for (byte part : digest.digest()) value.append(String.format("%02x", part));
            return value.toString();
        } catch (NoSuchAlgorithmException impossible) { throw new AssertionError(impossible); }
    }

    private static boolean isRedirect(int status) { return status == 301 || status == 302 || status == 303 || status == 307 || status == 308; }
    private static boolean trustedUrl(URL url) {
        String host = url.getHost().toLowerCase(java.util.Locale.ROOT);
        return "https".equalsIgnoreCase(url.getProtocol()) && url.getUserInfo() == null && (url.getPort() == -1 || url.getPort() == 443) &&
                (host.equals("huggingface.co") || host.equals("us.aws.cdn.hf.co") || host.equals("cdn-lfs.huggingface.co") || host.equals("cas-bridge.xethub.hf.co"));
    }
    private static void close(InputStream stream) { if (stream != null) try { stream.close(); } catch (IOException ignored) { } }

    private static final class HttpsTransport implements DownloadTransport {
        @Override public DownloadResponse open(URL url) throws IOException {
            if (!trustedUrl(url)) throw new IOException("Refusing non-HTTPS or untrusted model URL.");
            HttpsURLConnection connection = (HttpsURLConnection) url.openConnection();
            connection.setInstanceFollowRedirects(false); connection.setConnectTimeout(20_000); connection.setReadTimeout(30_000);
            int status = connection.getResponseCode(); String location = connection.getHeaderField("Location");
            if (isRedirect(status)) { connection.disconnect(); return DownloadResponse.redirect(status, location); }
            if (status != 200) { connection.disconnect(); return new DownloadResponse(status, null, null); }
            InputStream body = connection.getInputStream();
            return new DownloadResponse(status, null, new java.io.FilterInputStream(body) {
                @Override public void close() throws IOException { try { super.close(); } finally { connection.disconnect(); } }
            });
        }
    }
}

package io.github.dannybaanks.isymotron;

import android.content.Intent;
import android.net.Uri;
import androidx.activity.result.ActivityResult;
import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.ActivityCallback;
import java.io.File;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicLong;
import org.json.JSONException;
import org.json.JSONObject;

@CapacitorPlugin(name = "GusLocal")
public final class GusLocalPlugin extends Plugin {
    private final ExecutorService worker = Executors.newCachedThreadPool();
    private final ConcurrentHashMap<String, Future<?>> downloads = new ConcurrentHashMap<>();
    private final AtomicLong activeContext = new AtomicLong(0);
    private GusModelStore store;
    private volatile boolean nativeLibraryLoaded;

    @Override public void load() { store = new GusModelStore(getContext().getFilesDir()); }

    @PluginMethod public void listModels(PluginCall call) {
        JSArray result = new JSArray();
        java.util.Set<String> installed = new java.util.HashSet<>();
        for (GusCatalog.Model model : store.listInstalledModels()) installed.add(model.id);
        for (GusCatalog.Model model : GusCatalog.all()) {
            JSObject row = new JSObject();
            row.put("id", model.id); row.put("name", model.name); row.put("repository", model.repository);
            row.put("filename", model.filename); row.put("revision", model.revision); row.put("url", model.url);
            row.put("byteCount", model.byteCount); row.put("sha256", model.sha256); row.put("licenseName", model.licenseName);
            row.put("licenseUrl", model.licenseUrl); row.put("attribution", model.attribution);
            row.put("installed", installed.contains(model.id));
            result.put(row);
        }
        JSObject response = new JSObject(); response.put("models", result); response.put("available", true); call.resolve(response);
    }

    @PluginMethod public void downloadModel(PluginCall call) {
        String modelId = call.getString("modelId");
        if (GusCatalog.find(modelId) == null) { call.reject("Unknown GUS model ID."); return; }
        Future<?> previous = downloads.get(modelId);
        if (previous != null && !previous.isDone()) { call.reject("This model is already downloading."); return; }
        Future<?> task = worker.submit(() -> {
            try {
                File file = store.downloadModel(modelId, (id, received, total) -> {
                    if (Thread.currentThread().isInterrupted()) throw new java.io.UncheckedIOException(new java.io.IOException("Download cancelled."));
                    JSObject event = new JSObject(); event.put("modelId", id); event.put("receivedBytes", received); event.put("totalBytes", total);
                    notifyListeners("downloadProgress", event);
                });
                JSObject result = new JSObject(); result.put("modelId", modelId); result.put("installed", true); result.put("sizeBytes", file.length()); call.resolve(result);
            } catch (Exception error) { call.reject("No se pudo verificar el modelo descargado.", error); }
            finally { downloads.remove(modelId); }
        });
        downloads.put(modelId, task);
    }

    @PluginMethod public void cancelDownload(PluginCall call) {
        String modelId = call.getString("modelId");
        if (modelId != null) store.cancelDownload(modelId);
        Future<?> task = downloads.remove(modelId);
        if (task != null) task.cancel(true);
        JSObject result = new JSObject(); result.put("cancelled", task != null); call.resolve(result);
    }

    @PluginMethod public void importModels(PluginCall call) {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE); intent.setType("*/*"); intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        startActivityForResult(call, intent, "handleImport");
    }

    @ActivityCallback private void handleImport(PluginCall call, ActivityResult result) {
        if (result.getResultCode() != android.app.Activity.RESULT_OK || result.getData() == null) {
            JSObject cancelled = new JSObject(); cancelled.put("cancelled", true); cancelled.put("models", new JSArray()); call.resolve(cancelled); return;
        }
        List<Uri> uris = new ArrayList<>();
        if (result.getData().getClipData() != null) {
            for (int i = 0; i < result.getData().getClipData().getItemCount(); i++) uris.add(result.getData().getClipData().getItemAt(i).getUri());
        } else if (result.getData().getData() != null) uris.add(result.getData().getData());
        JSArray imported = new JSArray();
        try {
            for (Uri uri : uris) {
                try (InputStream input = getContext().getContentResolver().openInputStream(uri)) {
                    if (input == null) throw new java.io.IOException("Could not read the selected model file.");
                    GusCatalog.Model model = store.importAnyModel(input);
                    JSObject item = new JSObject(); item.put("id", model.id); item.put("name", model.name); imported.put(item);
                }
            }
            JSObject response = new JSObject(); response.put("cancelled", false); response.put("models", imported); call.resolve(response);
        } catch (Exception error) { call.reject("No se pudo importar el modelo; el archivo instalado y la copia externa se conservaron.", error); }
    }

    @PluginMethod public void exportModel(PluginCall call) {
        String modelId = call.getString("modelId");
        GusCatalog.Model model = GusCatalog.find(modelId);
        if (model == null) { call.reject("Unknown GUS model ID."); return; }
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE); intent.setType("application/octet-stream");
        intent.putExtra(Intent.EXTRA_TITLE, model.filename);
        startActivityForResult(call, intent, "handleExport");
    }

    @ActivityCallback private void handleExport(PluginCall call, ActivityResult result) {
        if (result.getResultCode() != android.app.Activity.RESULT_OK || result.getData() == null || result.getData().getData() == null) {
            JSObject cancelled = new JSObject(); cancelled.put("cancelled", true); call.resolve(cancelled); return;
        }
        String modelId = call.getString("modelId");
        try (OutputStream output = getContext().getContentResolver().openOutputStream(result.getData().getData(), "w")) {
            if (output == null) throw new java.io.IOException("The selected destination is no longer available.");
            store.exportModel(modelId, output);
            JSObject response = new JSObject(); response.put("cancelled", false); response.put("modelId", modelId); call.resolve(response);
        } catch (Exception error) { call.reject("No se pudo guardar la copia; el modelo instalado permanece disponible.", error); }
    }

    @PluginMethod public void generate(PluginCall call) {
        String modelId = call.getString("modelId");
        int contextTokens = call.getInt("contextTokens", 2048);
        int maxTokens = call.getInt("maxTokens", 160);
        JSArray messages = call.getArray("messages");
        if (GusCatalog.find(modelId) == null || contextTokens < 512 || contextTokens > 2048 || maxTokens < 1 || maxTokens > 160 || messages == null || messages.length() == 0 || messages.length() > 64) {
            call.reject("Invalid GUS generation request or limits."); return;
        }
        worker.execute(() -> {
            long handle = 0;
            try {
                File model = store.installedFile(modelId);
                String[] roles = new String[messages.length()]; String[] contents = new String[messages.length()]; int total = 0;
                for (int i = 0; i < messages.length(); i++) {
                    JSONObject message = messages.getJSONObject(i);
                    String role = message.getString("role"); String content = message.getString("content");
                    if (!(role.equals("system") || role.equals("user") || role.equals("assistant")) || content.length() > 12_000) throw new IllegalArgumentException("Invalid GUS message.");
                    total += content.length(); if (total > 32_000) throw new IllegalArgumentException("Conversation is too long.");
                    roles[i] = role; contents[i] = content;
                }
                synchronized (this) {
                    if (!nativeLibraryLoaded) { System.loadLibrary("gus_jni"); nativeLibraryLoaded = true; }
                    handle = nativeCreate(model.getAbsolutePath(), contextTokens);
                    activeContext.set(handle);
                }
                String text = nativeGenerate(handle, roles, contents, maxTokens);
                JSObject response = new JSObject(); response.put("text", text); call.resolve(response);
            } catch (UnsatisfiedLinkError error) { call.reject("El runtime local de GUS no está disponible en este dispositivo."); }
            catch (Exception error) { call.reject("No se pudo generar una respuesta local de GUS.", error); }
            finally {
                if (handle != 0) synchronized (this) {
                    if (activeContext.compareAndSet(handle, 0)) try { nativeDestroy(handle); } catch (UnsatisfiedLinkError ignored) { }
                }
            }
        });
    }

    @PluginMethod public void cancel(PluginCall call) {
        long handle;
        synchronized (this) { handle = activeContext.get(); if (handle != 0 && nativeLibraryLoaded) nativeCancel(handle); }
        JSObject result = new JSObject(); result.put("cancelled", handle != 0); call.resolve(result);
    }

    @PluginMethod public void unload(PluginCall call) { cancel(call); }

    @Override protected void handleOnDestroy() {
        for (Future<?> task : downloads.values()) task.cancel(true);
        worker.shutdownNow();
        synchronized (this) {
            long handle = activeContext.get();
            if (handle != 0 && nativeLibraryLoaded) try { nativeCancel(handle); } catch (UnsatisfiedLinkError ignored) { }
        }
    }

    private static native long nativeCreate(String modelPath, int contextTokens);
    private static native String nativeGenerate(long handle, String[] roles, String[] contents, int maxTokens);
    private static native void nativeCancel(long handle);
    private static native void nativeDestroy(long handle);
}

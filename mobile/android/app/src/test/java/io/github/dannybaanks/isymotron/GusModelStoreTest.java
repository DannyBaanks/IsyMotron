package io.github.dannybaanks.isymotron;

import static org.junit.Assert.*;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.Collections;
import java.util.Map;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;

public class GusModelStoreTest {
    @Rule public TemporaryFolder temporaryFolder = new TemporaryFolder();

    private static byte[] bytes(String text) { return text.getBytes(java.nio.charset.StandardCharsets.UTF_8); }
    private static String hash(byte[] data) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(data);
        StringBuilder out = new StringBuilder();
        for (byte value : digest) out.append(String.format("%02x", value));
        return out.toString();
    }
    private GusCatalog.Model fixture(byte[] data) throws Exception {
        return new GusCatalog.Model("fixture-small", "Fixture", "org/repo", "fixture.gguf",
                "0123456789012345678901234567890123456789",
                "https://huggingface.co/org/repo/resolve/0123456789012345678901234567890123456789/fixture.gguf",
                data.length, hash(data), "Apache License 2.0", "https://www.apache.org/licenses/LICENSE-2.0", "fixture attribution");
    }
    private GusModelStore store(File dir, GusCatalog.Model model) {
        return new GusModelStore(dir, Collections.singletonMap(model.id, model), url -> {
            throw new IOException("unexpected network request");
        });
    }

    @Test public void onlyGeneratedCatalogueIdsResolveInProduction() {
        assertNotNull(GusCatalog.find("qwen25-05b-q4km"));
        assertNotNull(GusCatalog.find("smollm2-360m-q4km"));
        assertNull(GusCatalog.find("../../private/file"));
    }

    @Test public void adoptsExactVerifiedBytesIntoPrivateModelDirectory() throws Exception {
        byte[] modelBytes = bytes("small test GGUF bytes");
        GusCatalog.Model model = fixture(modelBytes);
        GusModelStore store = store(temporaryFolder.newFolder("files"), model);
        File installed = store.importStream(model.id, new ByteArrayInputStream(modelBytes));
        assertEquals(model.byteCount, installed.length());
        assertEquals(hash(modelBytes), store.sha256(installed));
        assertTrue(installed.getCanonicalPath().contains("gus" + File.separator + "models"));
    }

    @Test public void rejectsWrongSizeAndHashWithoutReplacingInstalledModel() throws Exception {
        byte[] good = bytes("known good model");
        GusCatalog.Model model = fixture(good);
        GusModelStore store = store(temporaryFolder.newFolder("files"), model);
        File installed = store.importStream(model.id, new ByteArrayInputStream(good));
        byte[] before = Files.readAllBytes(installed.toPath());
        assertThrows(IOException.class, () -> store.importStream(model.id, new ByteArrayInputStream(bytes("x"))));
        byte[] sameSizeBadHash = bytes("known evil model");
        assertEquals(good.length, sameSizeBadHash.length);
        assertThrows(IOException.class, () -> store.importStream(model.id, new ByteArrayInputStream(sameSizeBadHash)));
        assertArrayEquals(before, Files.readAllBytes(installed.toPath()));
    }

    @Test public void rejectsOversizedStreamAndRemovesPartialFile() throws Exception {
        byte[] modelBytes = bytes("tiny");
        GusCatalog.Model model = fixture(modelBytes);
        File root = temporaryFolder.newFolder("oversize");
        GusModelStore store = store(root, model);
        assertThrows(IOException.class, () -> store.importStream(model.id, new ByteArrayInputStream(bytes("much larger than model"))));
        File[] leftovers = new File(root, "gus/models").listFiles();
        assertNotNull(leftovers);
        assertEquals(0, leftovers.length);
    }

    @Test public void rejectsUntrustedDownloadRedirectBeforeOpeningIt() throws Exception {
        byte[] modelBytes = bytes("tiny");
        GusCatalog.Model model = fixture(modelBytes);
        int[] calls = {0};
        GusModelStore store = new GusModelStore(temporaryFolder.newFolder("redirect"), Map.of(model.id, model), url -> {
            calls[0]++;
            return GusModelStore.DownloadResponse.redirect(302, "https://attacker.example/payload");
        });
        assertThrows(IOException.class, () -> store.downloadModel(model.id));
        assertEquals(1, calls[0]);
    }

    @Test public void followsOnlyThePinnedHuggingFaceRedirectHosts() throws Exception {
        byte[] modelBytes = bytes("tiny");
        GusCatalog.Model model = fixture(modelBytes);
        for (String host : new String[] {"us.aws.cdn.hf.co", "cdn-lfs.huggingface.co", "cas-bridge.xethub.hf.co"}) {
            int[] calls = {0};
            GusModelStore store = new GusModelStore(temporaryFolder.newFolder(host.replace('.', '-')), Collections.singletonMap(model.id, model), url -> {
                if (calls[0]++ == 0) return GusModelStore.DownloadResponse.redirect(302, "https://" + host + "/payload");
                return new GusModelStore.DownloadResponse(200, null, new ByteArrayInputStream(modelBytes));
            });
            assertEquals(model.byteCount, store.downloadModel(model.id).length());
            assertEquals(2, calls[0]);
        }
    }

    @Test public void failedOrRevokedPickerStreamLeavesInstalledFileAndNoPartialCopy() throws Exception {
        byte[] good = bytes("previous valid model");
        GusCatalog.Model model = fixture(good);
        File root = temporaryFolder.newFolder("revoked");
        GusModelStore store = store(root, model);
        File installed = store.importStream(model.id, new ByteArrayInputStream(good));
        InputStream revoked = new InputStream() {
            private int emitted;
            @Override public int read() throws IOException {
                if (emitted++ < 4) return 'x';
                throw new IOException("picker access revoked");
            }
        };
        assertThrows(IOException.class, () -> store.importStream(model.id, revoked));
        assertArrayEquals(good, Files.readAllBytes(installed.toPath()));
        assertEquals(1, new File(root, "gus/models").listFiles().length);
    }

    @Test public void exportedCatalogueModelRestoresIntoFreshPrivateStore() throws Exception {
        byte[] modelBytes = bytes("restorable GGUF fixture");
        GusCatalog.Model model = fixture(modelBytes);
        GusModelStore first = store(temporaryFolder.newFolder("first"), model);
        first.importStream(model.id, new ByteArrayInputStream(modelBytes));
        ByteArrayOutputStream backup = new ByteArrayOutputStream();
        first.exportModel(model.id, backup);
        GusModelStore afterReinstall = store(temporaryFolder.newFolder("reinstalled"), model);
        File restored = afterReinstall.importStream(model.id, new ByteArrayInputStream(backup.toByteArray()));
        assertArrayEquals(modelBytes, Files.readAllBytes(restored.toPath()));
    }
}

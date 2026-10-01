import type { CapacitorConfig } from "@capacitor/cli";

/**
 * IsyMotron Móvil. CapacitorHttp sends fetch() through native HTTP: the PC's Link server
 * is plain HTTP on the local network (envelopes are signed and encrypted end to end), and a
 * web page could not reach it because of CORS and mixed content.
 */
const config: CapacitorConfig = {
  appId: "io.github.dannybaanks.isymotron",
  appName: "IsyMotron",
  webDir: "dist",
  backgroundColor: "#0f1410",
  plugins: {
    CapacitorHttp: { enabled: true },
  },
};

export default config;

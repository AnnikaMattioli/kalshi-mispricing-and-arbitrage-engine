import { defineConfig } from "@playwright/test";

const deployed = process.env.DASHBOARD_URL;
const local = "http://127.0.0.1:8765";
export default defineConfig({
  testDir: "./browser-tests",
  use: {baseURL: deployed || local},
  webServer: deployed ? undefined : {
    command: "python3 -m http.server 8765 --bind 127.0.0.1 --directory docs",
    url: local,
    reuseExistingServer: false,
  },
});

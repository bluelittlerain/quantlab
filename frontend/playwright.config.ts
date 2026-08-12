import { defineConfig } from "@playwright/test";
import path from "node:path";

const outputDirectory = path.join(process.env.TEMP ?? "test-results", "quantlab-hk-playwright");
const externalServer = process.env.QUANTLAB_E2E_EXTERNAL_SERVER === "1";
const baseURL = process.env.QUANTLAB_E2E_BASE_URL ?? "http://127.0.0.1:4173";

export default defineConfig({
  testDir: "./e2e",
  globalTimeout: 300_000,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  outputDir: outputDirectory,
  reporter: [["list"]],
  use: {
    baseURL,
    channel: process.env.CI ? undefined : "msedge",
    headless: true,
    viewport: { width: 1366, height: 768 },
    locale: "zh-CN",
    timezoneId: "Asia/Hong_Kong",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: externalServer
    ? undefined
    : {
        command: `"${process.execPath}" node_modules/vite/bin/vite.js --host 127.0.0.1 --port 4173`,
        url: baseURL,
        timeout: 60_000,
        reuseExistingServer: false,
        stdout: "ignore",
        stderr: "ignore",
      },
});

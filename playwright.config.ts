import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/gui/2026-09-01-live-control-room",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  timeout: 240_000,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command: "npm run demo:live",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: false,
    stdout: "pipe",
    stderr: "pipe",
  },
});

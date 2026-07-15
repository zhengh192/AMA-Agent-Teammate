import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chrome", use: { ...devices["Desktop Chrome"], channel: "chrome" } }],
  webServer: [
    {
      command:
        "uv run uvicorn ama_teammate.main:app --app-dir apps/api/src --host 127.0.0.1 --port 8000",
      cwd: "../..",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        AMA_PROVIDER: "mock",
        AMA_METADATA_DATABASE_URL: "sqlite+aiosqlite:///./var/e2e-ama.db",
        AMA_CHECKPOINT_DATABASE_PATH: "./var/e2e-checkpoints.db",
        AMA_ARTIFACT_ROOT: "./var/e2e-artifacts",
        AMA_DEMO_DATABASE_ROOT: "./var/e2e-demo-databases",
        AMA_SKILL_REGISTRY_ROOT: "./var/e2e-skills",
      },
    },
    {
      command: "pnpm dev",
      cwd: ".",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});

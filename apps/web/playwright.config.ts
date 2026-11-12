import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "E:/AgentOpsLab/artifacts/playwright/test-results",
  reporter: [["list"], ["json", { outputFile: "E:/AgentOpsLab/artifacts/playwright/results.json" }]],
  timeout: 90_000,
  workers: 1,
  use: { baseURL: "http://localhost:5173", colorScheme: "dark", contextOptions: { reducedMotion: "reduce" } },
});

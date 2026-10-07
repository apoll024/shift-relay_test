import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: 'shared-operations.spec.ts',
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: 'http://localhost:8182',
    trace: 'retain-on-failure',
    ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH
      ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH } }
      : {}),
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'phone', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
  webServer: [
    {
      command: 'python -m server.e2e_service',
      url: 'http://127.0.0.1:8091/health',
      reuseExistingServer: false,
    },
    {
      command: 'npx expo start --web --host localhost --port 8182',
      url: 'http://localhost:8182',
      timeout: 180_000,
      reuseExistingServer: false,
      env: { EXPO_PUBLIC_API_URL: 'http://127.0.0.1:8091', EXPO_UNSTABLE_BONJOUR: '0' },
    },
  ],
});

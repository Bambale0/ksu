export default {
  testDir: './e2e',
  timeout: 45_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  workers: process.env.CI ? 2 : undefined,
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
  use: {
    baseURL: 'http://127.0.0.1:3017',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run dev -- --hostname 127.0.0.1 --port 3017',
    url: 'http://127.0.0.1:3017',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
};

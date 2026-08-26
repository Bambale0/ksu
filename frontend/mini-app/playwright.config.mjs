export default {
  testDir: './e2e',
  timeout: 35_000,
  expect: { timeout: 6_000 },
  fullyParallel: false,
  workers: process.env.CI ? 2 : undefined,
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    {
      name: 'webkit-mobile',
      use: {
        browserName: 'webkit',
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  use: {
    baseURL: 'http://127.0.0.1:3017',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: 'ROXY_E2E=1 npm run build && node e2e/static-server.mjs out 3017',
    url: 'http://127.0.0.1:3017/mini-app/',
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
};

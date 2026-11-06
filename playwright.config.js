const { defineConfig } = require("@playwright/test");
module.exports = defineConfig({
  testDir: "./tests/browser",
  workers: 1,
  timeout: 30000,
  use: { baseURL: "http://127.0.0.1:8017", headless: true },
  webServer: {
    command:
      "SHOP_TEST_MODE=1 SHOP_INITIAL_PASSWORD=browser-test-123 SHOP_DB=.data/browser-test.sqlite3 PORT=8017 python3 -m app.server",
    url: "http://127.0.0.1:8017",
    reuseExistingServer: false,
  },
});

import { defineConfig } from "@playwright/test";

/**
 * e2e against the real API and Postgres with the fake Cognito (web-shell spec). The static
 * export is served by @atesta/ui/scripts/serve.mjs, which adds the headers CloudFront adds.
 * Needs: `pnpm build` first and ATESTA_E2E_ADMIN_URL (a Postgres superuser URL).
 */
const admin = process.env.ATESTA_E2E_ADMIN_URL ?? "postgresql+psycopg://postgres@localhost:5432/postgres";
const appDb = new URL(admin);
appDb.username = "atesta_app";
appDb.password = "e2e-only";
appDb.pathname = "/atesta_e2e";
const repo = "../..";

export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    locale: "es-ES", // a Spanish browser: the default market; English detection has its own test
    baseURL: "http://localhost:3000",
    trace: "off",
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  webServer: [
    {
      command: "uv run python apps/api/devtools/fake_cognito.py",
      cwd: repo,
      url: "http://localhost:9000/.well-known/jwks.json",
      reuseExistingServer: false,
    },
    {
      command: `uv run python apps/api/devtools/prepare_e2e_db.py '${admin}' && uv run uvicorn atesta_api.main:app --port 8000`,
      cwd: repo,
      url: "http://localhost:8000/health",
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ATESTA_ENV: "local",
        ATESTA_DATABASE_URL: appDb.toString(),
        ATESTA_DB_SSLMODE: "disable",
        ATESTA_COGNITO_REGION: "eu-south-2",
        ATESTA_COGNITO_USER_POOL_ID: "local",
        ATESTA_COGNITO_APP_CLIENT_ID: "local-web",
        ATESTA_COGNITO_DOMAIN: "localhost:9000",
        ATESTA_COGNITO_ISSUER: "http://localhost:9000",
        ATESTA_COGNITO_BASE_URL: "http://localhost:9000",
        ATESTA_WEB_ORIGIN: "http://localhost:3000",
        ATESTA_WEB_BASE_URL: "http://localhost:3000",
        ATESTA_SESSION_KEY: Buffer.from(crypto.getRandomValues(new Uint8Array(32))).toString("base64"),
      },
    },
    {
      command: "node node_modules/@atesta/ui/scripts/serve.mjs",
      url: "http://localhost:3000/",
      reuseExistingServer: false,
      env: { NO_REFERRER: "/invite,/training,/unsubscribe" },
    },
  ],
});

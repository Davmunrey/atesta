import { defineConfig } from "@playwright/test";

/**
 * Portal e2e against the real operator API and Postgres with the fake staff pool (#487). The
 * static export is served by @atesta/ui/scripts/serve.mjs, which adds the headers CloudFront adds.
 * Needs: `pnpm build` first and ATESTA_E2E_ADMIN_URL (a Postgres superuser URL). Ports 3001,
 * 8001 and 9001, so the console's suite (3000, 8000, 9000) is untouched.
 */
const admin = process.env.ATESTA_E2E_ADMIN_URL ?? "postgresql+psycopg://postgres@localhost:5432/postgres";
const operatorDb = new URL(admin);
operatorDb.username = "atesta_operator";
operatorDb.password = "e2e-only";
operatorDb.pathname = "/atesta_e2e";
const repo = "../..";

export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    locale: "es-ES",
    baseURL: "http://localhost:3001",
    trace: "off",
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  webServer: [
    {
      command: "uv run python apps/api/devtools/fake_cognito.py --staff",
      cwd: repo,
      url: "http://localhost:9001/.well-known/jwks.json",
      reuseExistingServer: false,
    },
    {
      command: `uv run python apps/api/devtools/prepare_e2e_db.py '${admin}' --operator && uv run uvicorn atesta_operator.main:app --port 8001`,
      cwd: repo,
      url: "http://localhost:8001/health",
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ATESTA_ENV: "local",
        ATESTA_OPERATOR_DATABASE_URL: operatorDb.toString(),
        ATESTA_DB_SSLMODE: "disable",
        ATESTA_STAFF_COGNITO_REGION: "eu-south-2",
        ATESTA_STAFF_COGNITO_USER_POOL_ID: "local-staff",
        ATESTA_STAFF_COGNITO_APP_CLIENT_ID: "local-operator",
        ATESTA_STAFF_COGNITO_DOMAIN: "localhost:9001",
        ATESTA_STAFF_COGNITO_ISSUER: "http://localhost:9001",
        ATESTA_STAFF_COGNITO_BASE_URL: "http://localhost:9001",
        ATESTA_OPERATOR_WEB_ORIGIN: "http://localhost:3001",
        ATESTA_OPERATOR_SESSION_KEY: Buffer.from(crypto.getRandomValues(new Uint8Array(32))).toString("base64"),
      },
    },
    {
      command: "node node_modules/@atesta/ui/scripts/serve.mjs",
      url: "http://localhost:3001/",
      reuseExistingServer: false,
      env: { PORT: "3001", API_ORIGIN: "http://127.0.0.1:8001" },
    },
  ],
});

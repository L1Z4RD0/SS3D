import { defineConfig, devices } from "@playwright/test";

// Tests E2E: levantan el backend real (contra una base DESECHABLE "_e2e", ver
// backend/scripts/e2e_prepare.py) y el frontend en modo dev, en puertos propios para no
// chocar con lo que tengas corriendo en 8000/5173.
//
//   1. Base de pruebas:  backend\scripts\test_db.ps1 start   (Postgres en el puerto 5499)
//   2. Tests:            npm run test:e2e
const API_PORT = 8001;
const WEB_PORT = 5174;
const isWindows = process.platform === "win32";
const python = process.env.E2E_PYTHON || (isWindows ? "\"venv/Scripts/python.exe\"" : "venv/bin/python");
const databaseUrl = process.env.E2E_DATABASE_URL || "postgresql+psycopg://postgres@127.0.0.1:5499/zola_e2e";

export default defineConfig({
  testDir: "./e2e",
  // Todos los tests comparten el mismo usuario: en serie, para que el refresh token de uno
  // no se cruce con el de otro.
  workers: 1,
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `${python} scripts/e2e_prepare.py && ${python} -m uvicorn app.main:app --port ${API_PORT}`,
      cwd: "../backend",
      url: `http://localhost:${API_PORT}/api/health`,
      env: {
        DATABASE_URL: databaseUrl,
        SECRET_KEY: "e2e-only-secret-key",
        CORS_ORIGINS: `http://localhost:${WEB_PORT}`,
        COOKIE_SECURE: "false",
        DISCORD_WEBHOOK_URL: "",
      },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      env: { VITE_API_URL: `http://localhost:${API_PORT}` },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});

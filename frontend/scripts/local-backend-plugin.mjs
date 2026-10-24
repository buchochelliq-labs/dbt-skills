import { readFileSync, existsSync, mkdtempSync, chmodSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { tmpdir } from "node:os";
import { randomBytes } from "node:crypto";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function startConfiguredBackend() {
  // An explicitly supplied config enables the bundled fictional preview.
  // Without it, proxy the separately launched local backend as before.
  const configPath = process.env.UOL_PREVIEW_CONFIG || resolve(frontendRoot, "server/preview-config.json");
  if (!existsSync(configPath)) return null;
  const config = JSON.parse(readFileSync(configPath, "utf8"));
  if (config.simulation !== true) throw new Error("Bundled preview requires explicit simulation=true");
  const base = dirname(resolve(configPath));
  const executable = resolve(base, config.executable || "uol-backend");
  const project = resolve(base, config.project);
  const fixture = resolve(base, config.fixture);
  const runtime = mkdtempSync(resolve(tmpdir(), "uol-preview-"));
  chmodSync(runtime, 0o700);
  chmodSync(executable, 0o700);
  process.env.UOL_LOCAL_TOKEN = randomBytes(32).toString("hex");
  const childEnv = { ...process.env, UOL_PREVIEW_KEY: randomBytes(32).toString("base64") };
  const child = spawn(executable, ["--project-dir", project,
    "--policy", resolve(project, "modelling.yml"), "--catalog-config", resolve(project, "catalogs.json"),
    "--store", resolve(runtime, "workspace.db"), "--application-store", resolve(runtime, "application.db"),
    "--key-env", "UOL_PREVIEW_KEY", "--fixture-state", fixture,
    "--port", process.env.UOL_BACKEND_PORT || "8765"], { env: childEnv, stdio: ["ignore", "inherit", "inherit"] });
  child.on("error", error => console.error("Bundled backend could not start:", error.message));
  const stop = () => { if (!child.killed) child.kill("SIGTERM"); };
  process.once("exit", stop);
  child.on("exit", code => { if (code) console.error(`Bundled backend stopped (${code}); no fallback used.`); });
  return stop;
}
/** Optional same-origin bridge. Secret stays in server process, never VITE_* or client bundle. */
export function localBackendPlugin() {
  const port = process.env.UOL_BACKEND_PORT || "8765";
  let stopBackend;

  return {
    name: "uol-local-backend",
    configureServer(server) {
      if (server.httpServer) stopBackend = startConfiguredBackend();
      server.httpServer?.once("close", () => stopBackend?.());
      server.middlewares.use("/api", (req, res, next) => {
        const origin = req.headers.origin;
        if (
          origin &&
          ![
            "http://" + req.headers.host,
            "https://" + req.headers.host,
          ].includes(origin)
        ) {
          res.statusCode = 403;
          res.end("Forbidden origin");
          return;
        }
        if (req.method !== "POST") {
          res.statusCode = 405;
          res.end("POST required");
          return;
        }
        next();
      });
    },
    config() {
      return {
        server: {
          proxy: {
            "/api": {
              target: `http://127.0.0.1:${port}`,
              changeOrigin: true,
              configure(proxy) {
                proxy.on("proxyReq", (proxyReq) => {
                  let token = process.env.UOL_LOCAL_TOKEN || "";
                  if (!token && process.env.UOL_TOKEN_FILE) {
                    try {
                      token = readFileSync(
                        process.env.UOL_TOKEN_FILE,
                        "utf8",
                      ).trim();
                    } catch {
                      token = "";
                    } // Fail authentication, not the whole frontend process.
                  }
                  proxyReq.setHeader("Authorization", `Bearer ${token}`);
                  // Browser origin was checked by same-origin middleware above.
                  proxyReq.removeHeader("origin");
                });
                proxy.on("error", (_error, _req, res) => {
                  if (!res.headersSent) {
                    res.writeHead(503, { "Content-Type": "application/json" });
                    res.end(
                      JSON.stringify({
                        error:
                          "Local backend is not running. No demo fallback was used.",
                      }),
                    );
                  }
                });
              },
            },
          },
        },
      };
    },
  };
}

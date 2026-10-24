import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { localBackendPlugin } from "../scripts/local-backend-plugin.mjs";
test("local proxy rejects cross-origin and non-POST requests before forwarding", () => {
  let middleware;
  localBackendPlugin().configureServer({
    middlewares: { use: (_p, fn) => (middleware = fn) },
  });
  let forwarded = false;
  const res = { statusCode: 0, end() {} };
  middleware(
    {
      method: "POST",
      headers: { origin: "https://attacker.example", host: "localhost:5173" },
    },
    res,
    () => (forwarded = true),
  );
  assert.equal(res.statusCode, 403);
  assert.equal(forwarded, false);
  middleware(
    { method: "GET", headers: { host: "localhost:5173" } },
    res,
    () => (forwarded = true),
  );
  assert.equal(res.statusCode, 405);
  assert.equal(forwarded, false);
  middleware(
    {
      method: "POST",
      headers: { origin: "http://localhost:5173", host: "localhost:5173" },
    },
    res,
    () => (forwarded = true),
  );
  assert.equal(forwarded, true);
});
test("missing local token file fails closed without crashing proxy", () => {
  const prior = process.env.UOL_TOKEN_FILE,
    token = process.env.UOL_LOCAL_TOKEN;
  delete process.env.UOL_LOCAL_TOKEN;
  process.env.UOL_TOKEN_FILE = "/nonexistent-uol-test-token";
  try {
    let callback;
    localBackendPlugin()
      .config()
      .server.proxy["/api"].configure({
        on: (name, fn) => {
          if (name === "proxyReq") callback = fn;
        },
      });
    let header, removed;
    callback({ setHeader: (_name, value) => (header = value), removeHeader: name => (removed = name) });
    assert.equal(removed, "origin");
    assert.equal(header, "Bearer ");
  } finally {
    if (prior === undefined) delete process.env.UOL_TOKEN_FILE;
    else process.env.UOL_TOKEN_FILE = prior;
    if (token === undefined) delete process.env.UOL_LOCAL_TOKEN;
    else process.env.UOL_LOCAL_TOKEN = token;
  }
});

test("ordinary dev startup preserves an external backend without opting into frozen preview", () => {
  const names = ["UOL_PREVIEW_CONFIG", "UOL_LOCAL_TOKEN", "UOL_BACKEND_PORT"];
  const prior = Object.fromEntries(names.map(name => [name, process.env[name]]));
  delete process.env.UOL_PREVIEW_CONFIG;
  process.env.UOL_LOCAL_TOKEN = "external-backend-token";
  process.env.UOL_BACKEND_PORT = "9876";
  try {
    const plugin = localBackendPlugin();
    assert.doesNotThrow(() => plugin.configureServer({
      httpServer: { once() {} },
      middlewares: { use() {} },
    }));
    assert.equal(process.env.UOL_LOCAL_TOKEN, "external-backend-token");
    const proxy = plugin.config().server.proxy["/api"];
    assert.equal(proxy.target, "http://127.0.0.1:9876");
    let request;
    proxy.configure({ on: (event, callback) => { if (event === "proxyReq") request = callback; } });
    let authorization;
    request({ setHeader: (_name, value) => { authorization = value; }, removeHeader() {} });
    assert.equal(authorization, "Bearer external-backend-token");
  } finally {
    for (const name of names) {
      if (prior[name] === undefined) delete process.env[name];
      else process.env[name] = prior[name];
    }
  }
});


test("explicit frozen preview opt-in still validates its simulation configuration", () => {
  const directory = mkdtempSync(join(tmpdir(), "uol-plugin-test-"));
  const prior = process.env.UOL_PREVIEW_CONFIG;
  const config = join(directory, "preview.json");
  writeFileSync(config, JSON.stringify({ simulation: false }));
  process.env.UOL_PREVIEW_CONFIG = config;
  try {
    assert.throws(() => localBackendPlugin().configureServer({
      httpServer: { once() {} }, middlewares: { use() {} },
    }), /explicit simulation=true/);
  } finally {
    if (prior === undefined) delete process.env.UOL_PREVIEW_CONFIG;
    else process.env.UOL_PREVIEW_CONFIG = prior;
    rmSync(directory, { recursive: true, force: true });
  }
});

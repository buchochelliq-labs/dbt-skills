import test from "node:test";
import assert from "node:assert/strict";
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

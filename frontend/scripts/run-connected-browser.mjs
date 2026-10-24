import { chromium } from "playwright";
import { readFile } from "node:fs/promises";
import { runConnectedJourney } from "../tests/browser/connected.mjs";
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
    acceptDownloads: true,
  });
  await page.goto(process.argv[2] || "http://localhost:5173", {
    waitUntil: "networkidle",
  });
  const { download, ...result } = await runConnectedJourney(page);
  const failure = await download.failure();
  if (failure) throw new Error(`Context download failed: ${failure}`);
  if (download.suggestedFilename() !== "uol-agent-context.json")
    throw new Error("Unexpected context export filename");
  const context = JSON.parse(await readFile(await download.path(), "utf8"));
  if (
    !Array.isArray(context.facts) ||
    !context.facts.length ||
    !Array.isArray(context.trace)
  )
    throw new Error("Downloaded context lacks resolved facts or trace");
  if (
    !context.facts.every((f) => f.evidence?.providerId && f.evidence?.originId)
  )
    throw new Error("Downloaded context facts lack provenance");
  console.log(
    JSON.stringify({
      ...result,
      exportedFacts: context.facts.length,
      filename: download.suggestedFilename(),
    }),
  );
} catch (error) {
  console.error(error.stack || String(error));
  process.exitCode = 1;
} finally {
  await browser.close();
}

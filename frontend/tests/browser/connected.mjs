/** Runs against the original UI backed by the Python fixture-mode API. No state/API bypasses. */
export async function runConnectedJourney(page) {
  const button = (name) => page.getByRole("button", { name, exact: true });
  await button("Sources").waitFor({ state: "visible" });
  await button("Sources").click();
  await page.getByText("Pages, Genie & governance", { exact: true }).click();
  await button("Pages").click();
  const title = `Persistent browser Page ${Date.now()}`;
  await page.getByLabel("Page title", { exact: true }).fill(title);
  await page.getByRole("button", { name: /^Save (session )?draft$/ }).click();
  await page
    .getByText("Page draft saved. Native state unchanged.", { exact: true })
    .waitFor({ state: "visible" });
  await page.reload({ waitUntil: "networkidle" });
  await button("Sources").waitFor({ state: "visible" });
  await button("Sources").click();
  await page.getByText("Pages, Genie & governance", { exact: true }).click();
  await button("Pages").click();
  const actual = await page
    .getByLabel("Page title", { exact: true })
    .evaluate(el => el.value);
  if (actual !== title)
    throw new Error(
      "Acknowledged Page title did not survive a full browser reload",
    );
  await button("Agent context").click();
  await page
    .getByRole("combobox", {
      name: "Selected definition (optional)",
      exact: true,
    })
    .selectOption("active-customer");
  await page
    .getByRole("combobox", { name: "Business scope", exact: true })
    .selectOption("Service");
  await button("Resolve context").click();
  const exporter = button("Export context JSON");
  await exporter.waitFor({ state: "visible" });
  const downloadPromise = page.waitForEvent("download");
  await exporter.click();
  const download = await downloadPromise;
  return {
    status: "passed",
    scenario:
      "Original UI API save → full reload → resolve → actual context JSON download",
    title,
    download,
  };
}

/** Shared with the CUA browser: no Node imports or application-state access. */
export async function runBrowserJourneys(page, report = () => {}) {
  const results = [];
  const assert = (condition, message) => {
    if (!condition) throw new Error(message);
  };
  const test = async (name, run) => {
    try {
      await run();
      const result = { name, status: "passed" };
      results.push(result);
      await report(result);
    } catch (error) {
      const result = {
        name,
        status: "failed",
        detail: String(error.message || error),
      };
      results.push(result);
      await report(result);
      throw error;
    }
  };
  const button = (name) => page.getByRole("button", { name, exact: true });
  const readField = async (label) =>
    page.evaluate((label) => {
      const input = [
        ...document.querySelectorAll("input,textarea,select"),
      ].find(
        (el) =>
          el.getAttribute("aria-label") === label ||
          [...(el.labels || [])].some((l) =>
            l.textContent.trim().startsWith(label),
          ),
      );
      if (!input) throw new Error(`Missing labeled field: ${label}`);
      return input.value;
    }, label);
  const disabled = async (name) =>
    page.evaluate((name) => {
      const el = [...document.querySelectorAll("button")].find(
        (el) => el.textContent.trim() === name,
      );
      return (
        !!el && (el.disabled || el.getAttribute("aria-disabled") === "true")
      );
    }, name);
  const smoke = async () => {
    const issues = await page.evaluate(() => {
      const visible = (el) =>
        !!el.getClientRects().length &&
        getComputedStyle(el).visibility !== "hidden";
      const name = (el) =>
        el.getAttribute("aria-label") ||
        (el.getAttribute("aria-labelledby") || "")
          .split(/\s+/)
          .map((id) => document.getElementById(id)?.textContent || "")
          .join("")
          .trim() ||
        el.textContent.trim() ||
        el.getAttribute("title");
      return {
        buttons: [...document.querySelectorAll("button")]
          .filter(visible)
          .filter((el) => !name(el))
          .map((el) => el.outerHTML.slice(0, 180)),
        fields: [
          ...document.querySelectorAll(
            "input:not([type=hidden]),textarea,select",
          ),
        ]
          .filter(visible)
          .filter(
            (el) =>
              !el.getAttribute("aria-label") &&
              !el.getAttribute("aria-labelledby") &&
              ![...(el.labels || [])].some((l) => l.textContent.trim()),
          )
          .map((el) => el.outerHTML.slice(0, 180)),
      };
    });
    assert(
      !issues.buttons.length && !issues.fields.length,
      `Unnamed controls: ${JSON.stringify(issues)}`,
    );
  };
  // Repository hydration comes from the API; controls must be ready before journeys start.
  await button("Sources").waitFor({ state: "visible" });
  let originalTitle;
  await test("Pages: required title blocks save, handoff and export", async () => {
    await button("Sources").click();
    await page.getByText("Pages, Genie & governance", { exact: true }).click();
    await button("Pages").click();
    originalTitle = await readField("Page title");
    await page.getByLabel("Page title", { exact: true }).fill("");
    for (const name of [
      "Save session draft",
      "Prepare Page handoff",
      "Export review draft",
    ])
      assert(
        await disabled(name),
        `${name} must be disabled for an empty title`,
      );
    assert(
      (await page.getByRole("alert").count()) > 0,
      "Required-field feedback must be visible",
    );
    await smoke();
  });
  await test("Dirty navigation: keep editing preserves input, discard restores saved title", async () => {
    await button("Connections").click();
    assert(
      await page
        .getByRole("dialog", { name: "Discard unsaved changes?" })
        .isVisible(),
      "Expected discard dialog",
    );
    const focusedInside = await page.evaluate(
      () => !!document.activeElement?.closest('[role="dialog"]'),
    );
    assert(focusedInside, "Opening a dialog must move focus inside it");
    await smoke();
    await button("Keep editing").click();
    assert(
      (await readField("Page title")) === "",
      "Keep editing must preserve unsaved input",
    );
    await button("Connections").click();
    await button("Discard and continue").click();
    assert(
      await page
        .getByRole("heading", { name: "Context, from the right source." })
        .isVisible(),
      "Discard should complete navigation",
    );
    await button("Sources").click();
    const pages = button("Pages");
    if (!(await pages.isVisible()))
      await page
        .getByText("Pages, Genie & governance", { exact: true })
        .click();
    await pages.click();
    assert(
      (await readField("Page title")) === originalTitle,
      "Discard must leave saved page unchanged",
    );
  });
  await test("Pages: server acknowledges save before navigating to persisted draft", async () => {
    const savedTitle = `${originalTitle} · server save`;
    await page.getByLabel("Page title", { exact: true }).fill(savedTitle);
    await button("Save session draft").click();
    await page
      .getByText("Page draft saved. Native state unchanged.", { exact: true })
      .waitFor({ state: "visible" });
    await button("Connections").click();
    await page
      .getByRole("heading", { name: "Context, from the right source." })
      .waitFor({ state: "visible" });
    await button("Sources").click();
    const pages = button("Pages");
    if (!(await pages.isVisible()))
      await page
        .getByText("Pages, Genie & governance", { exact: true })
        .click();
    await pages.click();
    assert(
      (await readField("Page title")) === savedTitle,
      "Acknowledged draft must survive navigation",
    );
  });
  await test("Genie: JSON and instruction edits preserve unrelated configuration", async () => {
    await button("Genie context").click();
    await button("Complete configuration").click();
    const baseline = JSON.parse(
      await readField("Complete serialized_space JSON"),
    );
    const edited = JSON.parse(JSON.stringify(baseline));
    edited.config.uxRegressionMarker = "preserve-existing-config";
    edited.instructions.text_instructions[0].content = [
      "First instruction from JSON",
    ];
    await page
      .getByRole("textbox", {
        name: "Complete serialized_space JSON",
        exact: true,
      })
      .fill(JSON.stringify(edited, null, 2));
    await button("Instructions").click();
    assert(
      (await readField("Native text instructions")) ===
        "First instruction from JSON",
      "Instructions must reflect JSON edits",
    );
    await page
      .getByRole("textbox", { name: "Native text instructions", exact: true })
      .fill("Updated instruction\nSecond instruction");
    await button("Complete configuration").click();
    const after = JSON.parse(await readField("Complete serialized_space JSON"));
    const expected = JSON.parse(JSON.stringify(edited));
    expected.instructions.text_instructions[0].content = [
      "Updated instruction",
      "Second instruction",
    ];
    assert(
      JSON.stringify(after) === JSON.stringify(expected),
      "Instruction editing must preserve every unrelated configuration section",
    );
    await smoke();
    await button("Knowledge graph").click();
    await button("Discard and continue").click();
  });
  await test("Graph: keyboard list opens relationship evidence", async () => {
    await button("Show accessible list").click();
    const firstLabel = await page.evaluate(
      () =>
        document
          .querySelector(".graph-list .object-row")
          ?.textContent.replace(/\s+/g, " ")
          .trim() || "",
    );
    assert(
      firstLabel,
      "Fixture graph must contain an accessible relationship row",
    );
    const row = page.locator(".graph-list .object-row").first();
    await row.press("Enter");
    assert(
      await page
        .getByRole("heading", { name: "Relationship evidence", exact: true })
        .isVisible(),
      "Enter must open relationship inspector",
    );
    await row.press("Tab");
    assert(
      await page.evaluate(() => document.activeElement?.tagName === "BUTTON"),
      "Graph list should support sequential keyboard navigation",
    );
    await smoke();
  });
  await test("Native review: exact description proposal delivers only the selected item", async () => {
    await button("Sources").click();
    await page
      .getByRole("combobox", { name: "Catalog connection", exact: true })
      .selectOption("uc-customer");
    await page.getByRole("button", { name: /^Browse assets/ }).click();
    await page.getByRole("button", { name: "customers", exact: true }).click();
    const stamp = Date.now();
    const proposed = `Customer metadata reviewed by browser journey ${stamp}.`;
    const untouched = `Unselected browser proposal ${stamp}.`;
    const create = async (value) => {
      await button("Suggest an edit").click();
      await page
        .getByRole("dialog", { name: "Propose description change" })
        .waitFor({ state: "visible" });
      await page
        .getByRole("textbox", { name: "Proposed description", exact: true })
        .fill(value);
      await button("Save draft proposal").click();
      await page
        .getByRole("dialog", { name: "Propose description change" })
        .waitFor({ state: "hidden" });
      await page
        .getByText(value, { exact: true })
        .waitFor({ state: "visible" });
      return await page.evaluate(() =>
        document
          .querySelector('.change-card.chosen input[type="checkbox"]')
          ?.getAttribute("aria-label"),
      );
    };
    const selectedLabel = await create(proposed);
    assert(
      selectedLabel,
      "Saved proposal must have a selectable proposal identity",
    );
    const untouchedLabel = await create(untouched);
    assert(
      untouchedLabel && untouchedLabel !== selectedLabel,
      "Second save must create a separate proposal",
    );
    const selectedCard = page
      .locator(".change-card")
      .filter({
        has: page.getByRole("checkbox", { name: selectedLabel, exact: true }),
      });
    await selectedCard
      .getByRole("button", { name: "Review exact change", exact: true })
      .click();
    await page
      .getByText(proposed, { exact: true })
      .waitFor({ state: "visible" });
    await button("Approve proposal").click();
    await selectedCard
      .getByText("Reviewed", { exact: true })
      .waitFor({ state: "visible" });
    await page
      .getByRole("checkbox", { name: selectedLabel, exact: true })
      .check();
    await button("Simulate selected delivery (1)").click();
    await selectedCard
      .getByText("Verified", { exact: true })
      .waitFor({ state: "visible" });
    const untouchedCard = page
      .locator(".change-card")
      .filter({
        has: page.getByRole("checkbox", { name: untouchedLabel, exact: true }),
      });
    assert(
      await untouchedCard.getByText("Draft", { exact: true }).isVisible(),
      "Unselected proposal must remain a draft",
    );
    const receipt = await page.evaluate(
      (label) =>
        [...document.querySelectorAll(".receipt")].find((el) =>
          el.textContent.includes(label.replace("Select ", "")),
        )?.textContent || "",
      selectedLabel,
    );
    assert(
      receipt.includes("Verified") && receipt.includes("matches"),
      "Selected proposal must have a verified matching readback receipt",
    );
    await smoke();
  });
  return results;
}

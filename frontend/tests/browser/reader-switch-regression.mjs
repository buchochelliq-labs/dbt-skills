/** Portable UI-only regression. Run with tab.playwright (CUA) or a Playwright page.
 * Precondition: original UI hydrated, Steward reader, no open modal or unsaved edits.
 * Checks both preserving edits and discarding them before switching readers.
 */
export async function runReaderSwitchRegression(page) {
  const button = (name) => page.getByRole('button', { name, exact: true });
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const field = (name) => page.getByLabel(name, { exact: true });
  const reader = () => page.getByRole('combobox', { name: 'Simulated reader', exact: true });
  const read = (locator) => locator.evaluate(el => el.value);
  const openPages = async () => {
    await button('Sources').click();
    const pages = button('Pages');
    if (!(await pages.isVisible())) await page.getByText('Pages, Genie & governance', { exact: true }).click();
    await pages.click();
    if (await button('Edit').isVisible()) await button('Edit').click();
  };
  await openPages();
  const savedTitle = await read(field('Page title'));
  const unsavedTitle = `Unsaved reader-switch regression ${Date.now()}`;
  await field('Page title').fill(unsavedTitle);
  await button('Agent context').click();
  await reader().selectOption('restricted');
  const guard = page.getByRole('dialog', { name: 'Discard unsaved changes?', exact: true });
  await guard.waitFor({ state: 'visible' });
  check(await page.evaluate(() => !!document.activeElement?.closest('[role="dialog"]')), 'Reader-switch guard must receive focus');
  await button('Keep editing').click();
  check((await read(field('Page title'))) === unsavedTitle, 'Keep editing lost the unsaved title');
  check((await read(reader())) === 'steward', 'Keep editing changed reader');
  await reader().selectOption('restricted');
  await guard.waitFor({ state: 'visible' });
  await button('Discard and continue').click();
  await button('Sources').waitFor({ state: 'visible' });
  check((await read(reader())) === 'restricted', 'Discard did not complete reader change');
  await reader().selectOption('steward');
  await button('Sources').waitFor({ state: 'visible' });
  await openPages();
  check((await read(field('Page title'))) === savedTitle, 'Discard changed the saved Page title');
  return { status: 'passed', savedTitle, unsavedTitle, keepPreservedInputAndReader: true, discardChangedReader: true };
}

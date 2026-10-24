/** Portable browser-only regression for domain membership discovery and deduplication.
 * Precondition: hydrated Steward UI with no dirty edits or open dialog.
 * Test creates fictional metadata.
 */
export async function runMembershipRegression(page) {
  const button = name => page.getByRole('button', { name, exact: true });
  const assert = (v, message) => { if (!v) throw new Error(message); };
  const name = `Membership browser regression ${Date.now()}`;
  const objectRow = () => page.getByRole('button', { name: new RegExp(`^${name}`) });
  const domain = async (name, descendants = false) => {
    await button('Domains').click();
    await page.getByRole('navigation', { name: 'Domain hierarchy', exact: true }).getByRole('button', { name, exact: true }).click();
    await button('Knowledge').click();
    await page.getByRole('checkbox', { name: 'Include descendant domains', exact: true }).setChecked(descendants);
  };
  await domain('Service delivery');
  await button('Add knowledge').click();
  await page.getByLabel('Name', { exact: true }).fill(name);
  await page.getByRole('textbox', { name: 'Definition', exact: true }).fill('Fictional membership acceptance record.');
  await button('Create draft').click();
  await page.getByRole('dialog', { name: 'Add knowledge', exact: true }).waitFor({ state: 'hidden' });
  if (await button('Knowledge').isVisible()) await button('Knowledge').click();
  if (!(await button('Edit revision').isVisible())) await objectRow().click();
  await button('Edit revision').click();
  await page.getByRole('checkbox', { name: 'Customer', exact: true }).check();
  await page.getByRole('checkbox', { name: 'Lifecycle', exact: true }).check();
  await button('Save new revision').click();
  await page.getByRole('dialog', { name: `Edit ${name}`, exact: true }).waitFor({ state: 'hidden' });
  await domain('Customer', false);
  await objectRow().waitFor({ state: 'visible' });
  assert((await objectRow().count()) === 1, 'Direct membership duplicated the record');
  await page.getByRole('checkbox', { name: 'Include descendant domains', exact: true }).check();
  assert((await objectRow().count()) === 1, 'Direct plus descendant membership double-counted the record');
  const visibleRows = await page.locator('.object-list .object-row:visible').count();
  const statsText = await page.getByRole('button', { name: /Knowledge objects$/ }).innerText();
  assert(visibleRows > 0, 'Expected visible domain knowledge rows');
  assert(Number.parseInt(statsText, 10) === visibleRows, 'Knowledge count differs from visible unfiltered rows');
  await domain('Lifecycle', false);
  await objectRow().waitFor({ state: 'visible' });
  await domain('Enterprise', false);
  assert(!(await objectRow().isVisible()), 'Unrelated direct domain included a record');
  await domain('Enterprise', true);
  assert((await objectRow().count()) === 1, 'Multiple matching branches duplicated the record');
  await domain('Service delivery', false);
  await objectRow().click();
  const details = await page.getByRole('main').innerText();
  assert(details.includes('Enterprise / Operations / Service delivery'), 'Additional membership changed primary ownership');
  return { status: 'passed', name, directMembership: true, descendantMembership: true, exclusion: true, deduplicated: true, primaryOwner: 'Service delivery' };
}

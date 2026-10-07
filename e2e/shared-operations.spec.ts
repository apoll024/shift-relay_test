import { expect, test, type Page } from '@playwright/test';

async function signIn(page: Page, account: 'elena' | 'avery' | 'jordan') {
  await page.goto('http://localhost:8182/');
  await page.getByTestId('shared-token-field').fill(`e2e-${account}-token`);
  await page.getByTestId('shared-sign-in').click();
  await expect(page.getByTestId('sign-in-gate')).toHaveCount(0);
}

async function section(page: Page, name: 'tasks' | 'reports' | 'issues') {
  if (await page.getByTestId('side-nav').isVisible()) await page.getByTestId(`nav-${name}`).click();
  else {
    await page.locator('[data-testid="menu-button"]:visible').click();
    await page.getByTestId(`drawer-nav-${name}`).click();
  }
}

test('private token authentication rejects invalid credentials', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('demo-sign-in-elena')).toHaveCount(0);
  await page.getByTestId('shared-token-field').fill('wrong-token');
  await page.getByTestId('shared-sign-in').click();
  await expect(page.getByText('Access token is invalid. Sign in again.')).toBeVisible();
  await expect(page.getByTestId('sign-in-gate')).toBeVisible();
});

test('manager assigns a task and another client completes it with history', async ({
  page,
  browser,
}, info) => {
  await signIn(page, 'elena');
  await section(page, 'tasks');
  const title = `Shared assignment ${info.project.name}`;
  await page.getByTestId('new-task').click();
  await page.getByTestId('task-title-field').fill(title);
  await page.getByTestId('task-description-field').fill('Verify the repaired connection');
  await page.getByTestId('assignee-avery').click();
  await page.getByTestId('save-task').click();
  await expect(page.getByTestId('task-editor')).toHaveCount(0);
  await expect(page.getByText(title, { exact: true })).toBeVisible();
  const context = await browser.newContext({
    viewport: page.viewportSize() ?? { width: 1280, height: 720 },
  });
  const other = await context.newPage();
  await signIn(other, 'avery');
  await section(other, 'tasks');
  await other.getByRole('button', { name: `Update task ${title}`, exact: true }).click();
  await other.getByRole('button', { name: 'Set status Done', exact: true }).click();
  await other.getByTestId('save-task').click();
  await expect(other.getByText('Add a completion note explaining what was done.')).toBeVisible();
  await other.getByTestId('task-note-field').fill('Cable replaced; connection verified');
  await other.getByTestId('save-task').click();
  await expect(other.getByTestId('task-editor')).toHaveCount(0);
  await other.getByRole('button', { name: 'Filter Done tasks', exact: true }).click();
  await expect(other.getByText(title, { exact: true })).toBeVisible();
  await other.getByRole('button', { name: `Update task ${title}`, exact: true }).click();
  await expect(other.getByTestId('task-editor')).toContainText(
    'Cable replaced; connection verified',
  );
  await context.close();
});

test('builder previews, saves, downloads, and configures a disabled email schedule', async ({
  page,
}, info) => {
  await signIn(page, 'elena');
  await section(page, 'reports');
  await page.getByTestId('report-title-field').fill(`Morning review ${info.project.name}`);
  await page.getByTestId('preview-report').click();
  await expect(page.getByText('Outstanding from earlier reports (0)')).toBeVisible();
  await expect(page.getByText('Preview only. Build and save a report to export it.')).toBeVisible();
  await page.getByTestId('save-report').click();
  await expect(page.getByTestId('download-html')).toBeEnabled();
  const downloaded = page.waitForEvent('download');
  await page.getByTestId('download-html').click();
  expect((await downloaded).suggestedFilename()).toMatch(/^shift-relay-.*\.html$/);
  await page.getByTestId('schedule-recipients-field').fill('invalid-address');
  await page.getByTestId('save-schedule').click();
  await expect(page.getByText('Enter valid recipient email addresses (maximum 50).')).toBeVisible();
  await page.getByTestId('schedule-recipients-field').fill('reports@example.test');
  await page.getByTestId('save-schedule').click();
  await expect(page.getByText('Schedule saved with delivery disabled.')).toBeVisible();
});

test('staff cannot access the report builder or schedule', async ({ page }) => {
  await signIn(page, 'jordan');
  await section(page, 'reports');
  await expect(page.getByText('Operations Manager access required')).toBeVisible();
  await expect(page.getByTestId('schedule-editor')).toHaveCount(0);
});

test('photos uploaded by one client are visible to another', async ({ page, browser }) => {
  await signIn(page, 'jordan');
  await page.getByTestId('nav-dashboard').click();
  await page.getByTestId('next-action-button').click();
  const chooser = page.waitForEvent('filechooser');
  await page.getByTestId('sheet-take-photo').click();
  await (await chooser).setFiles('assets/favicon-shift-relay.png');
  await page.getByTestId('walk-save-photos').click();
  await expect(page.getByTestId('walk-draft')).toHaveCount(0);
  const context = await browser.newContext();
  const other = await context.newPage();
  await signIn(other, 'elena');
  await other.getByTestId('nav-photos').click();
  await expect(other.getByTestId('walk-review-photo').first()).toBeVisible();
  await context.close();
});

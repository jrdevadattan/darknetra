import { expect, test } from '@playwright/test';

const CASE_TABS = [
  'Overview',
  'Evidence',
  'Entities',
  'Activity Candidates',
  'Link Analysis',
  'NarcoGraph',
  'Timeline',
  'Alerts',
  'Reports',
];

const REMOVED_SHOWCASES = [
  'Ecommerce',
  'CRM',
  'Finance',
  'Academy',
  'Demo Chat',
  'Mail Dashboard',
];

test('desktop and mobile navigation expose only DARKNETRA workspaces', async ({ page }, testInfo) => {
  await page.goto('/dashboard');
  await expect(page.getByRole('heading', { name: 'Investigator overview' })).toBeVisible();

  if (testInfo.project.name.includes('mobile')) {
    await page.getByRole('button', { name: 'Toggle Sidebar' }).click();
  }

  await expect(page.getByRole('link', { name: 'Cases', exact: true }).first()).toBeVisible();
  const body = page.locator('body');
  for (const label of REMOVED_SHOWCASES) {
    await expect(body).not.toContainText(label);
  }
});

test('fixture case exposes all nine investigation tabs', async ({ page }) => {
  await page.goto('/cases/SYN-DEMO-001');
  await expect(page.getByRole('heading', { name: 'Alias correlation training case' })).toBeVisible();

  const caseNav = page.getByRole('navigation', { name: 'Case sections' });
  for (const label of CASE_TABS) {
    await expect(caseNav.getByRole('link', { name: label, exact: true })).toBeVisible();
  }

  await caseNav.getByRole('link', { name: 'Evidence', exact: true }).click();
  await expect(page).toHaveURL(/\/cases\/SYN-DEMO-001\/evidence$/);
  await expect(
    page.getByText('Live data boundary: Plan 03 · Evidence Vault', { exact: true }),
  ).toBeVisible();
});

test('System Health reports a measured reachable API', async ({ page }) => {
  await page.goto('/system/health');
  await expect(page.getByRole('heading', { name: 'System Health' })).toBeVisible();

  const apiCard = page
    .getByText('DARKNETRA API', { exact: true })
    .locator('xpath=ancestor::*[@data-slot="card"][1]');
  await expect(apiCard.getByText('Verified', { exact: true })).toBeVisible();
  await expect(apiCard.getByText('Reported status: ready', { exact: true })).toBeVisible();
});

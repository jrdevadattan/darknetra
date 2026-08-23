import { expect, test } from '@playwright/test';

function requiredEnvironment(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is required for the real authentication E2E suite.`);
  }
  return value;
}

const ANALYST_USERNAME = 'e2e.analyst.a';
const BOOTSTRAP_USERNAME = 'e2e.bootstrap';
const ANALYST_PASSWORD = requiredEnvironment('DARKNETRA_E2E_ANALYST_A_PASSWORD');
const BOOTSTRAP_PASSWORD = requiredEnvironment('DARKNETRA_E2E_BOOTSTRAP_PASSWORD');
const BOOTSTRAP_NEW_PASSWORD = requiredEnvironment('DARKNETRA_E2E_BOOTSTRAP_NEW_PASSWORD');

async function signIn(
  page: import('@playwright/test').Page,
  username: string,
  password: string,
) {
  await page.goto('/auth/v2/login');
  await page.getByLabel('Username', { exact: true }).fill(username);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
}

test.describe.configure({ mode: 'serial' });

test('bad password stays generic and clears the submitted secret', async ({ page }) => {
  await signIn(page, ANALYST_USERNAME, 'Synthetic-Wrong-Password-42!');

  await expect(page.getByText('Unable to sign in with those credentials.')).toBeVisible();
  await expect(page.getByText('invalid credentials or session')).toHaveCount(0);
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue('');
});

test('real login reaches the dashboard and logout revokes the browser session', async ({ page }) => {
  await signIn(page, ANALYST_USERNAME, ANALYST_PASSWORD);

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole('heading', { name: 'Investigator overview' })).toBeVisible();
  await expect(page.getByText('E2E Analyst A', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/auth\/v2\/login$/);
  await expect(page.getByRole('heading', { name: 'Sign in to DARKNETRA' })).toBeVisible();

  await page.goto('/dashboard');
  await expect(page).toHaveURL(/\/auth\/v2\/login$/);
});

test('bootstrap login is forced through password change before normal work', async ({ page }) => {
  await signIn(page, BOOTSTRAP_USERNAME, BOOTSTRAP_PASSWORD);

  await expect(page).toHaveURL(/\/auth\/v2\/change-password$/);
  await expect(
    page.getByRole('heading', { name: 'Secure your investigator account' }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();

  await page.getByLabel('New password', { exact: true }).fill(BOOTSTRAP_NEW_PASSWORD);
  await page.getByLabel('Confirm new password', { exact: true }).fill(BOOTSTRAP_NEW_PASSWORD);
  await page.getByRole('button', { name: 'Update password' }).click();

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole('heading', { name: 'Investigator overview' })).toBeVisible();

  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/auth\/v2\/login$/);
});

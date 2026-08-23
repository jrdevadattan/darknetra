import { expect, test } from '@playwright/test';

import {
  fulfillJson,
  mockAuthenticatedWorkspace,
  SYNTHETIC_USER,
} from './mock-darknetra-api';

const CSRF_VALUE = 'synthetic-e2e-csrf';

async function installCsrfCookie(page: import('@playwright/test').Page) {
  await page.context().addCookies([
    {
      name: 'darknetra_csrf',
      value: CSRF_VALUE,
      url: 'http://127.0.0.1:3000',
      sameSite: 'Strict',
    },
  ]);
}

test('bad password stays generic and clears the password field', async ({ page }) => {
  await page.route('**/api/v1/auth/login', (route) =>
    fulfillJson(route, { detail: 'invalid credentials or session' }, 401),
  );

  await page.goto('/auth/v2/login');
  await page.getByLabel('Username').fill('investigator');
  await page.getByLabel('Password').fill('synthetic-wrong-password');
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page.getByText('Unable to sign in with those credentials.')).toBeVisible();
  await expect(page.getByText('invalid credentials or session')).toHaveCount(0);
  await expect(page.getByLabel('Password')).toHaveValue('');
});

test('normal login enters the dashboard and logout clears the session UX', async ({ page }) => {
  await installCsrfCookie(page);
  await mockAuthenticatedWorkspace(page);
  await page.route('**/api/v1/auth/login', async (route) => {
    expect(route.request().postDataJSON()).toEqual({
      username: 'investigator',
      password: 'Synthetic-Only-Password-42!',
    });
    await fulfillJson(route, { user: SYNTHETIC_USER });
  });
  await page.route('**/api/v1/auth/logout', async (route) => {
    expect(route.request().headers()['x-csrf-token']).toBe(CSRF_VALUE);
    await route.fulfill({ status: 204, body: '' });
  });

  await page.goto('/auth/v2/login');
  await page.getByLabel('Username').fill('investigator');
  await page.getByLabel('Password').fill('Synthetic-Only-Password-42!');
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole('heading', { name: 'Investigator overview' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();

  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/auth\/v2\/login$/);
  await expect(page.getByRole('heading', { name: 'Sign in to DARKNETRA' })).toBeVisible();
});

test('forced-change login cannot enter the dashboard until password update succeeds', async ({ page }) => {
  await installCsrfCookie(page);
  await mockAuthenticatedWorkspace(page);
  await page.route('**/api/v1/auth/login', (route) =>
    fulfillJson(route, {
      user: {
        ...SYNTHETIC_USER,
        username: 'bootstrap',
        display_name: 'Bootstrap Investigator',
        must_change_password: true,
      },
    }),
  );
  await page.route('**/api/v1/auth/change-password', async (route) => {
    expect(route.request().headers()['x-csrf-token']).toBe(CSRF_VALUE);
    expect(route.request().postDataJSON()).toEqual({
      new_password: 'Replacement-Password-42!',
    });
    await fulfillJson(route, SYNTHETIC_USER);
  });

  await page.goto('/auth/v2/login');
  await page.getByLabel('Username').fill('bootstrap');
  await page.getByLabel('Password').fill('Temporary-Password-42!');
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page).toHaveURL(/\/auth\/v2\/change-password$/);
  await expect(
    page.getByRole('heading', { name: 'Secure your investigator account' }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();

  await page.getByLabel('New password', { exact: true }).fill('Replacement-Password-42!');
  await page
    .getByLabel('Confirm new password', { exact: true })
    .fill('Replacement-Password-42!');
  await page.getByRole('button', { name: 'Update password' }).click();

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole('heading', { name: 'Investigator overview' })).toBeVisible();
});

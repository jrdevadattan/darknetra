import { expect, test } from '@playwright/test';

test('System Health reports an unavailable API without a false green state', async ({ page }) => {
  await page.goto('/system/health');
  await expect(page.getByRole('heading', { name: 'System Health' })).toBeVisible();
  await expect(page.getByText('DARKNETRA API unreachable', { exact: true })).toBeVisible();
  await expect(page.getByText('Offline', { exact: true })).toBeVisible();
  await expect(page.getByText('Verified', { exact: true })).toHaveCount(0);
});

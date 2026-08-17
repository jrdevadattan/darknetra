import { expect, test } from '@playwright/test';

test('System Health reports an unavailable API without a false green state', async ({ page }) => {
  await page.goto('/system/health');
  await expect(page.getByRole('heading', { name: 'System Health' })).toBeVisible();

  const offlineState = page.getByTestId('async-state-offline');
  await expect(offlineState).toBeVisible();
  await expect(offlineState.getByText('DARKNETRA API unreachable', { exact: true })).toBeVisible();
  await expect(offlineState).toContainText('reported as unavailable rather than shown as a false green state');
  await expect(page.getByText('Verified', { exact: true })).toHaveCount(0);
});

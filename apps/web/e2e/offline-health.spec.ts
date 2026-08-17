import { expect, test } from '@playwright/test';

test('protected workspace reports authentication service outage without false content', async ({ page }) => {
  await page.goto('/system/health');

  const offlineState = page.getByTestId('async-state-offline');
  await expect(offlineState).toBeVisible();
  await expect(
    offlineState.getByText('Authentication service unavailable', { exact: true }),
  ).toBeVisible();
  await expect(offlineState).toContainText('session could not be verified');
  await expect(page.getByRole('heading', { name: 'System Health' })).toHaveCount(0);
  await expect(page.getByText('Verified', { exact: true })).toHaveCount(0);
});

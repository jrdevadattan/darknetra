import { expect, test } from '@playwright/test';

function requiredEnvironment(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is required for the real authorization E2E suite.`);
  }
  return value;
}

const ANALYST_A_USERNAME = 'e2e.analyst.a';
const ANALYST_A_PASSWORD = requiredEnvironment('DARKNETRA_E2E_ANALYST_A_PASSWORD');
const CASE_A_ID = '00000000-0000-4000-8000-000000000ca1';
const CASE_B_ID = '00000000-0000-4000-8000-000000000cb1';
const UNKNOWN_CASE_ID = '00000000-0000-4000-8000-000000000fff';

async function signIn(page: import('@playwright/test').Page) {
  await page.goto('/auth/v2/login');
  await page.getByLabel('Username', { exact: true }).fill(ANALYST_A_USERNAME);
  await page.getByLabel('Password', { exact: true }).fill(ANALYST_A_PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

async function openCaseAndCaptureApi(
  page: import('@playwright/test').Page,
  caseId: string,
): Promise<{ status: number; body: unknown; unavailableCopy: string | null }> {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'GET' &&
      response.url().endsWith(`/api/v1/cases/${caseId}`),
  );

  await page.goto(`/cases/${caseId}`);
  const response = await responsePromise;
  const body = await response.json();
  const unavailable = page.getByTestId('async-state-error');
  const unavailableCopy = (await unavailable.count()) > 0 ? await unavailable.innerText() : null;
  return { status: response.status(), body, unavailableCopy };
}

test('inaccessible and unknown case IDs have the same 404 response and browser experience', async ({
  page,
}) => {
  await signIn(page);

  const ownCase = await openCaseAndCaptureApi(page, CASE_A_ID);
  expect(ownCase.status).toBe(200);
  await expect(
    page.getByRole('heading', { name: 'E2E Analyst A synthetic case' }),
  ).toBeVisible();

  const inaccessibleCase = await openCaseAndCaptureApi(page, CASE_B_ID);
  expect(inaccessibleCase.status).toBe(404);
  expect(inaccessibleCase.body).toEqual({ detail: 'resource not found' });
  expect(inaccessibleCase.unavailableCopy).toContain('Case unavailable');
  await expect(page.getByText('E2E Analyst B synthetic case')).toHaveCount(0);

  const unknownCase = await openCaseAndCaptureApi(page, UNKNOWN_CASE_ID);
  expect(unknownCase.status).toBe(404);
  expect(unknownCase.body).toEqual(inaccessibleCase.body);
  expect(unknownCase.unavailableCopy).toBe(inaccessibleCase.unavailableCopy);
});

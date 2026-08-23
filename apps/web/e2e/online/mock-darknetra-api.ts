import type { Page, Route } from '@playwright/test';

export const SYNTHETIC_USER = {
  id: '2b18f363-8fc0-44aa-8312-7f4792e663af',
  username: 'investigator',
  display_name: 'Investigator One',
  global_roles: ['ANALYST'],
  must_change_password: false,
};

export const SYNTHETIC_CASE = {
  id: '4d61f3aa-b46e-4ed2-b516-e91ec5930abc',
  case_code: 'CHD-2026-001',
  title: 'Live synthetic case',
  status: 'OPEN',
  sensitivity: 'STANDARD',
  owner_user_id: SYNTHETIC_USER.id,
  source_authority_summary: 'Authorized synthetic browser fixture',
  created_at: '2026-08-17T09:30:00Z',
  updated_at: '2026-08-17T10:45:00Z',
  closed_at: null,
};

export function fulfillJson(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

export async function mockAuthenticatedWorkspace(page: Page) {
  await page.route('**/api/v1/auth/me', (route) => fulfillJson(route, SYNTHETIC_USER));
  await page.route(/\/api\/v1\/cases\?/, (route) =>
    fulfillJson(route, {
      items: [SYNTHETIC_CASE],
      limit: 100,
      offset: 0,
      has_more: false,
    }),
  );
  await page.route(`**/api/v1/cases/${SYNTHETIC_CASE.id}`, (route) =>
    fulfillJson(route, SYNTHETIC_CASE),
  );
}

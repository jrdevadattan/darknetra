import { FIXTURE_CASES } from '@/features/cases/fixtures';

export interface OverviewMetric {
  id: string;
  label: string;
  value: number;
  description: string;
  href: string;
}

export interface FixtureOverviewSnapshot {
  metrics: OverviewMetric[];
  recentCases: typeof FIXTURE_CASES;
}

export function getFixtureOverviewSnapshot(): FixtureOverviewSnapshot {
  const activeCases = FIXTURE_CASES.filter((item) => item.status !== 'CLOSED').length;
  const pendingReviews = FIXTURE_CASES.reduce((sum, item) => sum + item.pendingReviews, 0);
  const openAlerts = FIXTURE_CASES.reduce((sum, item) => sum + item.openAlerts, 0);

  return {
    metrics: [
      {
        id: 'active-cases',
        label: 'Active fixture cases',
        value: activeCases,
        description: 'Open or review-stage controlled cases',
        href: '/cases?scope=active',
      },
      {
        id: 'integrity-warnings',
        label: 'Fixture integrity warnings',
        value: 1,
        description: 'Exercises awaiting integrity review',
        href: '/cases?integrity=warning',
      },
      {
        id: 'pending-reviews',
        label: 'Pending link reviews',
        value: pendingReviews,
        description: 'Fixture candidates requiring human disposition',
        href: '/cases?review=pending',
      },
      {
        id: 'open-alerts',
        label: 'Open fixture alerts',
        value: openAlerts,
        description: 'Controlled alerts awaiting review',
        href: '/cases?alerts=open',
      },
      {
        id: 'failed-jobs',
        label: 'Failed jobs',
        value: 0,
        description: 'Real worker health begins in Plan 01 · Task 7',
        href: '/system/health?jobs=failed',
      },
    ],
    recentCases: [...FIXTURE_CASES]
      .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt))
      .slice(0, 4),
  };
}

'use client';

import { AsyncState } from '@/components/darknetra/async-state';
import { ApiError } from '@/lib/api/errors';

import { CasesTable } from './cases-table';
import { useCases } from './queries';

export function CasesLiveView() {
  const casesQuery = useCases({ limit: 100, offset: 0 });

  if (casesQuery.isPending) {
    return <AsyncState state="loading" />;
  }

  if (casesQuery.isError) {
    if (casesQuery.error instanceof ApiError && casesQuery.error.status === 0) {
      return (
        <AsyncState
          state="offline"
          title="Case service offline"
          description="The case API could not be reached. No fixture data is substituted."
        />
      );
    }

    if (
      casesQuery.error instanceof ApiError &&
      (casesQuery.error.status === 401 || casesQuery.error.status === 403)
    ) {
      return (
        <AsyncState
          state="error"
          title="Case access denied"
          description="This session is not authorized to list cases."
        />
      );
    }

    return (
      <AsyncState
        state="error"
        title="Cases unavailable"
        description="The visible case list could not be loaded from the API."
      />
    );
  }

  if (casesQuery.data.items.length === 0) {
    return (
      <AsyncState
        state="empty"
        title="No visible cases"
        description="No cases are currently visible to this authenticated user."
      />
    );
  }

  return (
    <div className="space-y-4">
      {casesQuery.isFetching ? (
        <AsyncState
          state="stale"
          title="Refreshing cases"
          description="Showing the last successful case list while a fresh response is requested."
        />
      ) : null}
      {casesQuery.data.hasMore ? (
        <AsyncState
          state="partial"
          title="Case list truncated"
          description="Showing the first 100 visible cases. Narrower server-side filters arrive in a later plan."
        />
      ) : null}
      <CasesTable cases={casesQuery.data.items} />
    </div>
  );
}

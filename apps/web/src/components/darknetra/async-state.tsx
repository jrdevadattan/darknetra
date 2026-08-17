import { AlertCircle, CircleOff, Clock3, Info, WifiOff } from 'lucide-react';

import { Skeleton } from '@/components/ui/skeleton';

export type AsyncStateKind = 'loading' | 'empty' | 'error' | 'partial' | 'stale' | 'offline';

const COPY: Record<Exclude<AsyncStateKind, 'loading'>, { title: string; detail: string }> = {
  empty: { title: 'No records', detail: 'No records match the current scope.' },
  error: { title: 'Unable to load', detail: 'The requested data could not be loaded.' },
  partial: { title: 'Partial data', detail: 'Some data is unavailable or not implemented yet.' },
  stale: { title: 'Stale data', detail: 'This view may not include the latest analysis.' },
  offline: { title: 'Offline', detail: 'The required service is not currently reachable.' },
};

const ICONS = {
  empty: CircleOff,
  error: AlertCircle,
  partial: Info,
  stale: Clock3,
  offline: WifiOff,
} as const;

export function AsyncState({
  state,
  title,
  description,
}: {
  state: AsyncStateKind;
  title?: string;
  description?: string;
}) {
  if (state === 'loading') {
    return (
      <div data-testid="async-state-loading" role="status" className="space-y-2 rounded-xl border p-4">
        <span className="sr-only">Loading</span>
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    );
  }

  const copy = COPY[state];
  const Icon = ICONS[state];
  return (
    <div
      data-testid={`async-state-${state}`}
      role={state === 'error' ? 'alert' : 'status'}
      className="flex gap-3 rounded-xl border bg-muted/20 p-4"
    >
      <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <div>
        <p className="font-medium">{title ?? copy.title}</p>
        <p className="mt-1 text-muted-foreground text-sm">{description ?? copy.detail}</p>
      </div>
    </div>
  );
}

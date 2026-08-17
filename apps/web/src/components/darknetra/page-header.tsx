import type { ReactNode } from 'react';

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col justify-between gap-4 border-b pb-5 sm:flex-row sm:items-end">
      <div className="min-w-0">
        {eyebrow ? <p className="font-medium text-muted-foreground text-xs uppercase tracking-wider">{eyebrow}</p> : null}
        <h1 className="mt-1 font-semibold text-2xl tracking-tight sm:text-3xl">{title}</h1>
        {description ? <p className="mt-2 max-w-3xl text-muted-foreground text-sm">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

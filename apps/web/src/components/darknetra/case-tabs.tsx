'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { cn } from '@/lib/utils';
import { CASE_NAVIGATION } from '@/navigation/darknetra-navigation';

export function CaseTabs({ caseId }: { caseId: string }) {
  const pathname = usePathname();
  const base = `/cases/${caseId}`;

  return (
    <nav aria-label="Case sections" className="overflow-x-auto border-b">
      <div className="flex min-w-max gap-1">
        {CASE_NAVIGATION.map((item) => {
          const href = item.segment ? `${base}/${item.segment}` : base;
          const active = item.segment ? pathname.startsWith(href) : pathname === base;
          return (
            <Link
              key={item.title}
              href={href}
              aria-current={active ? 'page' : undefined}
              className={cn(
                'border-b-2 border-transparent px-3 py-2 text-sm text-muted-foreground hover:text-foreground',
                active && 'border-primary font-medium text-foreground',
              )}
            >
              {item.title}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

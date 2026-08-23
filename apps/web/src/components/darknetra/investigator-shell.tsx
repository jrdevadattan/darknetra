import type { CSSProperties, ReactNode } from 'react';

import { cookies } from 'next/headers';

import { LayoutControls } from '@/app/(main)/dashboard/_components/header/layout-controls';
import { SearchDialog } from '@/app/(main)/dashboard/_components/header/search-dialog';
import { ThemeSwitcher } from '@/app/(main)/dashboard/_components/header/theme-switcher';
import { AppSidebar } from '@/app/(main)/dashboard/_components/sidebar/app-sidebar';
import { Separator } from '@/components/ui/separator';
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar';
import { SessionControls } from '@/features/auth/session-controls';
import { cn } from '@/lib/utils';
import { getPreference } from '@/server/server-actions';

export async function InvestigatorShell({ children }: { children: ReactNode }) {
  const cookieStore = await cookies();
  const defaultOpen = cookieStore.get('sidebar_state')?.value !== 'false';
  const [variant, collapsible] = await Promise.all([
    getPreference('sidebar_variant'),
    getPreference('sidebar_collapsible'),
  ]);

  return (
    <SidebarProvider
      defaultOpen={defaultOpen}
      style={{ '--sidebar-width': 'calc(var(--spacing) * 68)' } as CSSProperties}
    >
      <AppSidebar variant={variant} collapsible={collapsible} />
      <SidebarInset
        className={cn(
          '[html[data-content-layout=centered]_&>*]:mx-auto',
          '[html[data-content-layout=centered]_&>*]:w-full',
          '[html[data-content-layout=centered]_&>*]:max-w-screen-2xl',
          'peer-data-[variant=inset]:border',
          '[--dashboard-header-height:--spacing(12)]',
          'min-w-0 overflow-x-clip',
        )}
      >
        <header className="flex h-12 shrink-0 items-center border-b bg-background/95 backdrop-blur">
          <div className="flex w-full items-center justify-between px-4 lg:px-6">
            <div className="flex items-center gap-1 lg:gap-2">
              <SidebarTrigger className="-ml-1" />
              <Separator orientation="vertical" className="mx-2 h-4" />
              <SearchDialog />
            </div>
            <div className="flex items-center gap-2">
              <LayoutControls />
              <ThemeSwitcher />
              <SessionControls />
            </div>
          </div>
        </header>
        <main className="min-h-0 min-w-0 flex-1 overflow-x-hidden p-4 md:p-6">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  );
}

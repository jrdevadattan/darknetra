'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

import { useAuthSession, useLogout } from './session-gate';

export function LogoutButton() {
  const logoutMutation = useLogout();

  return (
    <div className="flex items-center gap-2">
      {logoutMutation.isError ? (
        <span role="alert" className="text-destructive text-xs">
          Unable to sign out.
        </span>
      ) : null}
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={logoutMutation.isPending}
        onClick={() => logoutMutation.mutate()}
      >
        {logoutMutation.isPending ? 'Signing out…' : 'Sign out'}
      </Button>
    </div>
  );
}

export function SessionControls() {
  const session = useAuthSession();
  if (!session.data) return null;

  const roleLabel = session.data.global_roles.join(' · ');
  return (
    <div className="flex items-center gap-2">
      <div className="hidden text-right sm:block">
        <p className="max-w-44 truncate font-medium text-xs">{session.data.display_name}</p>
        <p className="max-w-44 truncate text-muted-foreground text-[11px]">{session.data.username}</p>
      </div>
      {roleLabel ? (
        <Badge variant="outline" className="hidden md:inline-flex">
          {roleLabel}
        </Badge>
      ) : null}
      <LogoutButton />
    </div>
  );
}

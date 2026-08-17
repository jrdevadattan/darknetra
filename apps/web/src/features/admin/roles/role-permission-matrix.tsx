'use client';

import { AsyncState } from '@/components/darknetra/async-state';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ApiError } from '@/lib/api/errors';

import { useRolePolicies } from './queries';

export function RolePermissionMatrix() {
  const rolesQuery = useRolePolicies();

  if (rolesQuery.isPending) {
    return <AsyncState state="loading" />;
  }

  if (rolesQuery.isError) {
    if (rolesQuery.error instanceof ApiError && rolesQuery.error.status === 0) {
      return (
        <AsyncState
          state="offline"
          title="Role policy service offline"
          description="The role policy API could not be reached."
        />
      );
    }

    if (
      rolesQuery.error instanceof ApiError &&
      (rolesQuery.error.status === 401 || rolesQuery.error.status === 403)
    ) {
      return (
        <AsyncState
          state="error"
          title="Role administration access denied"
          description="This session is not authorized to read the role policy matrix."
        />
      );
    }

    return (
      <AsyncState
        state="error"
        title="Role policy unavailable"
        description="The backend role policy could not be loaded."
      />
    );
  }

  if (rolesQuery.data.roles.length === 0) {
    return (
      <AsyncState
        state="empty"
        title="No role policies returned"
        description="The backend returned an empty role policy matrix."
      />
    );
  }

  return (
    <div className="rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Role</TableHead>
            <TableHead>Permissions from policy API</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rolesQuery.data.roles.map((rolePolicy) => (
            <TableRow key={rolePolicy.role}>
              <TableCell className="font-medium">{rolePolicy.role}</TableCell>
              <TableCell>
                {rolePolicy.permissions.length ? (
                  <div className="flex flex-wrap gap-1.5">
                    {rolePolicy.permissions.map((permission) => (
                      <Badge key={permission} variant="outline">
                        {permission}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <span className="text-muted-foreground text-sm">No permissions</span>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

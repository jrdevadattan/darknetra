'use client';

import { AsyncState } from '@/components/darknetra/async-state';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ApiError } from '@/lib/api/errors';

import { useUsers } from './queries';

export function UserTable() {
  const usersQuery = useUsers();

  if (usersQuery.isPending) {
    return <AsyncState state="loading" />;
  }

  if (usersQuery.isError) {
    if (usersQuery.error instanceof ApiError && usersQuery.error.status === 0) {
      return (
        <AsyncState
          state="offline"
          title="User directory offline"
          description="The user directory API could not be reached."
        />
      );
    }

    if (
      usersQuery.error instanceof ApiError &&
      (usersQuery.error.status === 401 || usersQuery.error.status === 403)
    ) {
      return (
        <AsyncState
          state="error"
          title="User administration access denied"
          description="This session is not authorized to read the user directory."
        />
      );
    }

    return (
      <AsyncState
        state="error"
        title="User directory unavailable"
        description="The user directory could not be loaded."
      />
    );
  }

  if (usersQuery.data.items.length === 0) {
    return (
      <AsyncState
        state="empty"
        title="No users returned"
        description="The backend returned an empty user directory."
      />
    );
  }

  return (
    <div className="rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Display name</TableHead>
            <TableHead>Username</TableHead>
            <TableHead>Roles</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {usersQuery.data.items.map((user) => (
            <TableRow key={user.id}>
              <TableCell className="font-medium">{user.display_name}</TableCell>
              <TableCell>{user.username}</TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-1.5">
                  {user.global_roles.map((role) => (
                    <Badge key={role} variant="outline">
                      {role}
                    </Badge>
                  ))}
                </div>
              </TableCell>
              <TableCell>
                <Badge variant={user.is_active ? 'secondary' : 'outline'}>
                  {user.is_active ? 'Active' : 'Inactive'}
                </Badge>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

'use client';

import { useQuery } from '@tanstack/react-query';

import { listUsers } from '@/lib/api/admin';
import { queryKeys } from '@/lib/query/keys';

export function useUsers() {
  return useQuery({
    queryKey: queryKeys.admin.users,
    queryFn: listUsers,
  });
}

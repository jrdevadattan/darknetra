'use client';

import { useQuery } from '@tanstack/react-query';

import { listRolePolicies } from '@/lib/api/admin';
import { queryKeys } from '@/lib/query/keys';

export function useRolePolicies() {
  return useQuery({
    queryKey: queryKeys.admin.roles,
    queryFn: listRolePolicies,
  });
}

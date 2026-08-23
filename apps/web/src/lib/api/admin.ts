import type { GlobalRole } from "@/lib/api/auth";
import { apiFetch } from "@/lib/api/client";

export interface ApiUserSummary {
  id: string;
  username: string;
  display_name: string;
  is_active: boolean;
  global_roles: GlobalRole[];
}

export interface ApiUserList {
  items: ApiUserSummary[];
}

export interface ApiRolePolicy {
  role: GlobalRole;
  permissions: string[];
}

export interface ApiRolePolicyList {
  roles: ApiRolePolicy[];
}

export function listUsers(): Promise<ApiUserList> {
  return apiFetch<ApiUserList>("/api/v1/users");
}

export function listRolePolicies(): Promise<ApiRolePolicyList> {
  return apiFetch<ApiRolePolicyList>("/api/v1/admin/roles");
}

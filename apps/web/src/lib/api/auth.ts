import { apiFetch } from "@/lib/api/client";

export type GlobalRole =
  | "ADMIN"
  | "CASE_OWNER"
  | "COLLECTOR"
  | "ANALYST"
  | "REVIEWER"
  | "AUDITOR"
  | "VIEWER";

export interface AuthUser {
  id: string;
  username: string;
  display_name: string;
  global_roles: GlobalRole[];
  must_change_password: boolean;
}

export interface AuthResponse {
  user: AuthUser;
}

export function login(username: string, password: string): Promise<AuthResponse> {
  return apiFetch<AuthResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function getCurrentUser(): Promise<AuthUser> {
  return apiFetch<AuthUser>("/api/v1/auth/me");
}

export function refreshSession(): Promise<AuthResponse> {
  return apiFetch<AuthResponse>("/api/v1/auth/refresh", { method: "POST" });
}

export function changePassword(options: {
  newPassword: string;
  currentPassword?: string;
}): Promise<AuthUser> {
  return apiFetch<AuthUser>("/api/v1/auth/change-password", {
    method: "POST",
    body: JSON.stringify({
      new_password: options.newPassword,
      current_password: options.currentPassword,
    }),
  });
}

export function logout(): Promise<void> {
  return apiFetch<void>("/api/v1/auth/logout", { method: "POST" });
}

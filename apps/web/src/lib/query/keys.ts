import type { CaseListParams } from "@/lib/api/cases";

export const queryKeys = {
  auth: {
    all: ["auth"] as const,
    me: ["auth", "me"] as const,
  },
  cases: {
    all: ["cases"] as const,
    list: (params: CaseListParams = {}) => ["cases", "list", params] as const,
    detail: (caseId: string) => ["cases", "detail", caseId] as const,
    members: (caseId: string) => ["cases", "members", caseId] as const,
  },
  admin: {
    all: ["admin"] as const,
    users: ["admin", "users"] as const,
    roles: ["admin", "roles"] as const,
  },
  intelligence: {
    all: ["intelligence"] as const,
    integrations: ["intelligence", "integrations"] as const,
  },
} as const;

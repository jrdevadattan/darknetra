import type { S } from "./types";
export function can(
  user: S<"UserMe">,
  caseData: S<"Case">,
  permission: "write" | "manage" | "export" | "archive",
) {
  if (user.global_role === "ADMIN") return true;
  if (user.global_role !== "INVESTIGATOR") return false;
  const role = caseData.my_role;
  return permission === "archive"
    ? role === "OWNER"
    : permission === "write"
      ? ["OWNER", "LEAD", "ANALYST"].includes(role ?? "")
      : ["OWNER", "LEAD"].includes(role ?? "");
}
export const writable = (user: S<"UserMe">, caseData: S<"Case">) =>
  caseData.status === "OPEN" && can(user, caseData, "write");

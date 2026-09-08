import type { components } from "./generated/api";
export type S<K extends keyof components["schemas"]> = components["schemas"][K];
export type Page<T> = {
  items: T[];
  next_cursor?: string | null;
  total?: number | null;
};
export type CaseMessage = S<"darknetra__api__v1__schemas__threads__Message">;
export type PrivateMessage = S<"darknetra__api__v1__schemas__chats__Message">;
export type CaseRun = S<"darknetra__api__v1__schemas__threads__Run">;
export type PrivateRun = S<"darknetra__api__v1__schemas__chats__Run">;
export type CaseView =
  | "overview"
  | "evidence"
  | "search"
  | "entities"
  | "relationships"
  | "findings"
  | "monitoring"
  | "alerts"
  | "reports"
  | "members"
  | "audit";

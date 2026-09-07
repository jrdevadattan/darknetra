export type Page<T> = { items: T[]; next_cursor?: string | null; total?: number | null };

export type User = {
  id: string;
  username: string;
  display_name: string;
  global_role: "ADMIN" | "INVESTIGATOR" | "VIEWER";
  must_change_password: boolean;
};

export type Case = {
  id: string;
  code: string;
  title: string;
  status: "OPEN" | "CLOSED" | "ARCHIVED";
  my_role?: "OWNER" | "LEAD" | "ANALYST" | "VIEWER" | null;
  demo: boolean;
};

export type Chat = { id: string; title: string; status: string; updated_at: string; last_message_at: string | null };

export type Thread = {
  id: string;
  case_id: string;
  title: string;
  status: "OPEN" | "CLOSED";
  harness: string;
  active_run_id?: string | null;
  last_message_at?: string | null;
};

export type Claim = { text?: string; evidence_codes?: string[]; evidence_ids?: string[]; kind?: string };
export type MessageBlock = { type?: string; text?: string; content?: string };
export type ThreadMessage = {
  id: string;
  role: "USER" | "ASSISTANT" | "SYSTEM" | "TOOL";
  blocks: MessageBlock[];
  claims: Claim[];
  at: string;
  run_id?: string | null;
};

export type RunRef = { run_id: string; thread_id: string; status: string };
export type ActivityNode = {
  id: string;
  kind: "agent" | "tool" | "stage";
  label: string;
  status: "queued" | "running" | "completed" | "failed" | "denied" | "cancelled" | "interrupted";
  phase?: string;
  summary?: string;
  duration_ms?: number | null;
  evidence_codes?: string[];
  error_code?: string | null;
};
export type ExecutionSnapshot = {
  run_id: string;
  run_status: string;
  cursor: number;
  nodes: ActivityNode[];
  edges: { source_id: string; target_id: string }[];
  events: ActivityNode[];
  truncated: boolean;
  cost_usd?: number;
  cost_complete?: boolean | null;
};

export type CaseDigest = {
  new_evidence: number;
  new_monitor_hits: number;
  open_alerts: number;
  pending_candidates: number;
};

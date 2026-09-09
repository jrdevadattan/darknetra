export type Activity = {
  id: string;
  label: string;
  status: string;
  detail?: string;
  at?: string;
  finishedAt?: string;
  kind?: "action" | "update";
  result?: string;
  sources?: RunSource[];
  targetUrl?: string;
  coverage?: {
    attempted: number;
    retrieved: number;
    failed: number;
    skipped: number;
    pending: number;
    complete: false;
    stopReason?: string;
    inventoriesTruncated?: number;
    frontierTruncated?: boolean;
    outputTruncated?: boolean;
    omittedRecords?: number;
  };
};
export type RunSource = {
  id: string;
  title: string;
  kind: "page" | "index" | "lead" | "file";
  status:
    | "retrieved"
    | "listed"
    | "analysed"
    | "unavailable"
    | "supplied"
    | "referenced";
  url?: string;
  file?: string;
  sha256?: string;
  at?: string;
  excerpt?: string;
  parentId?: string;
  parentRelation?: "lists" | "links to" | "has text section";
  favicon?: string;
  reviewNeeded?: boolean;
};
export type ChatAttachment = { name: string; label: string; size: number };
export type SpecialistAgent = {
  id: string;
  name: string;
  role?: string;
  task: string;
  status:
    "pending" | "running" | "completed" | "error" | "stopped" | "unverified";
  result?: string;
  activity?: Activity[];
  at?: string;
  finishedAt?: string;
  historyLimited?: boolean;
};
export type ChatMode = "normal" | "thinking" | "netra";
export type NetraGoal = {
  status:
    | "starting"
    | "active"
    | "complete"
    | "blocked"
    | "paused"
    | "limit_reached"
    | "unavailable";
  objective?: string;
  tokensUsed?: number;
  turns: number;
};
export type ChatMessage = {
  language?: import("./languages").LanguageCode;
  id: string;
  role: "user" | "assistant";
  text: string;
  at: string;
  status: "running" | "done" | "error" | "stopped";
  error?: string;
  activity: Activity[];
  mode?: ChatMode;
  netra?: NetraGoal;
  attachments?: ChatAttachment[];
  agents?: SpecialistAgent[];
  finishedAt?: string;
  historyLimited?: boolean;
  generatedImage?: GeneratedBoardImage;
  monitoring?: {
    monitorId?: string;
    caseId?: string;
    summary: string;
    nextRunAt?: string;
  };
};
export type GeneratedBoardImage = {
  file: string;
  sha256: string;
  size: number;
  provider: "imagegen";
};
export type Case = {
  id: string;
  title: string;
  notes: string;
  createdAt: string;
};
export type Chat = {
  id: string;
  caseId: string | null;
  title: string;
  sessionId?: string;
  createdAt: string;
  archivedAt?: string;
  messages: ChatMessage[];
  board?: import("./case-board").BoardSnapshot;
};
export type MonitorRun = {
  id: string;
  at: string;
  finishedAt?: string;
  trigger: "scheduled" | "manual" | "chat";
  status: "running" | "done" | "error" | "stopped" | "skipped";
  messageId?: string;
  error?: string;
};
export type CaseMonitor = {
  id: string;
  caseId: string;
  chatId: string;
  title: string;
  prompt: string;
  cron: string;
  timezone: string;
  enabled: boolean;
  createdAt: string;
  nextRunAt: string;
  runs: MonitorRun[];
  sourceChatId?: string;
  scopeKey?: string;
};
export type WorkspaceNotification = {
  id: string;
  at: string;
  kind: "complete" | "error";
  title: string;
  body: string;
  caseId: string;
  chatId: string;
  read?: boolean;
};
export type WorkspaceData = {
  preferences?: { language?: import("./languages").LanguageCode };
  version: 1;
  cases: Case[];
  chats: Chat[];
  monitors?: CaseMonitor[];
  notifications?: WorkspaceNotification[];
};

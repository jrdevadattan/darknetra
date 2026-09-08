"use client";
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useQueryClient } from "@tanstack/react-query";
import {
  Sparkles,
  Search,
  FileSearch,
  GitBranch,
  ArrowUp,
  Paperclip,
  SlidersHorizontal,
  LockKeyhole,
  ShieldCheck,
  Copy,
  Check,
  X,
} from "lucide-react";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import {
  PromptInput,
  PromptInputBody,
  PromptInputTextarea,
  PromptInputFooter,
  PromptInputTools,
  PromptInputSubmit,
} from "@/components/ai-elements/prompt-input";
import {
  Sources,
  SourcesContent,
  SourcesTrigger,
} from "@/components/ai-elements/sources";
const ActivityPanel = dynamic(
  () => import("./activity").then((m) => m.ActivityPanel),
  { ssr: false },
);
import { api, useApi, usePaged, invalidateCase } from "@/lib/api";
import { useRun } from "@/lib/use-run";
import { writable } from "@/lib/permissions";
import type { CaseMessage, PrivateMessage, S } from "@/lib/types";
import {
  Button,
  ErrorBanner,
  Modal,
  Field,
  Loading,
  LoadMore,
  StatusBadge,
  EvidenceChip,
  date,
  money,
} from "./shared";

const markdownComponents = {
  a: ({ children }: { children?: React.ReactNode }) => <span>{children}</span>,
  img: () => (
    <span className="text-muted-foreground">[External image omitted]</span>
  ),
};
const providers = [
  ["AUTO", "Automatic"],
  ["CLAUDE", "Claude"],
  ["NIM", "NVIDIA NIM"],
  ["OFFLINE", "Local model"],
];
export function ChatWorkspace({
  user,
  caseData,
  chatId,
  initialRunId,
  showActivity,
  onActivity,
  onSelect,
  onRun,
  onEvidence,
}: {
  user: S<"UserMe">;
  caseData?: S<"Case">;
  chatId?: string;
  initialRunId?: string;
  showActivity: boolean;
  onActivity: (value: boolean) => void;
  onSelect: (id: string, runId?: string) => void;
  onRun: (id: string) => void;
  onEvidence: (id: string) => void;
}) {
  const client = useQueryClient(),
    prefix = caseData ? `/cases/${caseData.id}/threads` : "/chats",
    base = chatId ? `${prefix}/${chatId}` : null;
  const meta = useApi<S<"Thread"> | S<"Chat">>(base, 5000);
  const messages = usePaged<CaseMessage | PrivateMessage>(
    base ? base + "/messages" : null,
    5000,
  );
  const [runId, setRunId] = useState(initialRunId ?? null);
  const [pendingRun, setPendingRun] = useState<string | null>(null);
  const [text, setText] = useState(""),
    [provider, setProvider] = useState("AUTO"),
    [budget, setBudget] = useState("2");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    [settings, setSettings] = useState(false),
    [attach, setAttach] = useState(false),
    [attachments, setAttachments] = useState<string[]>([]),
    [copied, setCopied] = useState<string>();
  const evidence = usePaged<S<"Evidence">>(
    attach && caseData ? `/cases/${caseData.id}/evidence` : null,
  );
  const allowed = !caseData || writable(user, caseData);
  const activeRun =
    meta.data && "active_run_id" in meta.data ? meta.data.active_run_id : null;
  const latestRun = !messages.hasNextPage
    ? ([...messages.items].reverse().find((m) => m.run_id)?.run_id ?? null)
    : null;
  const currentRunId =
    activeRun || pendingRun || latestRun || initialRunId || null;
  const currentRun = useRun(base, currentRunId, caseData?.id);
  const inspectingHistory = Boolean(runId && runId !== currentRunId);
  const historicalRun = useRun(
    inspectingHistory ? base : null,
    inspectingHistory ? runId : null,
    caseData?.id,
  );
  const run = inspectingHistory ? historicalRun : currentRun;
  const running = currentRun.active;
  useEffect(() => {
    if (messages.hasNextPage && !messages.isFetching && !messages.error)
      void messages.fetchNextPage();
  }, [
    messages.hasNextPage,
    messages.isFetching,
    messages.error,
    messages.fetchNextPage,
  ]);
  useEffect(() => {
    if (pendingRun && latestRun === pendingRun) setPendingRun(null);
  }, [pendingRun, latestRun]);
  const runtime = meta.data
    ? "harness" in meta.data
      ? meta.data.harness
      : meta.data.provider
    : provider;
  useEffect(() => {
    if (initialRunId) setRunId(initialRunId);
    else if (activeRun) setRunId(activeRun);
    else if (!runId && !messages.hasNextPage && messages.items.length)
      setRunId(
        [...messages.items].reverse().find((m) => m.run_id)?.run_id ?? null,
      );
  }, [initialRunId, activeRun, messages.items, runId]);
  const pickRun = (id: string) => {
    setRunId(id);
    onRun(id);
    onActivity(true);
  };
  async function send() {
    if (
      !text.trim() ||
      busy ||
      running ||
      messages.hasNextPage ||
      !allowed ||
      meta.data?.status === "CLOSED"
    )
      return;
    setError(null);
    setBusy(true);
    try {
      let id = chatId;
      if (!id) {
        const created = await api<{ id: string }>(
          prefix,
          "POST",
          caseData
            ? {
                title: text.trim().slice(0, 80),
                harness: provider === "AUTO" ? null : provider,
                budget_usd: Number(budget),
              }
            : {
                title: text.trim().slice(0, 80),
                provider,
                budget_usd: Number(budget),
              },
        );
        id = created.id;
        // Keep the new conversation usable even when starting its first run fails.
        try {
          const started = await api<{ run_id: string }>(
            `${prefix}/${id}/messages`,
            "POST",
            { content: text.trim(), ...(caseData ? { attachments } : {}) },
          );
          await client.invalidateQueries({ queryKey: ["api", prefix] });
          onSelect(id, started.run_id);
        } catch (reason) {
          await client.invalidateQueries({ queryKey: ["api", prefix] });
          client.setQueryData(["draft", prefix, id], { text, error: reason });
          onSelect(id);
        }
      } else {
        const started = await api<{ run_id: string }>(
          base + "/messages",
          "POST",
          { content: text.trim(), ...(caseData ? { attachments } : {}) },
        );
        setPendingRun(started.run_id);
        setText("");
        setAttachments([]);
        pickRun(started.run_id);
        await client.invalidateQueries({ queryKey: ["api", base] });
        await client.invalidateQueries({
          queryKey: ["api", base + "/messages"],
        });
      }
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (!chatId) return;
    const draft = client.getQueryData<{ text: string; error: unknown }>([
      "draft",
      prefix,
      chatId,
    ]);
    if (draft) {
      setText(draft.text);
      setError(draft.error);
      client.removeQueries({ queryKey: ["draft", prefix, chatId] });
    }
  }, [chatId, client, prefix]);
  async function cancel() {
    if (!currentRunId || !allowed) return;
    setBusy(true);
    setError(null);
    try {
      await api(`${base}/runs/${currentRunId}/cancel`, "POST");
      await client.invalidateQueries({ queryKey: ["api", base] });
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  }
  const starter = caseData
    ? [
        [
          "Review case evidence",
          "Summarise captured material",
          "Summarise the evidence in this case and cite every claim.",
          FileSearch,
        ],
        [
          "Find a connection",
          "Explore supported relationships",
          "Identify candidate connections in the case evidence, with citations and uncertainty.",
          GitBranch,
        ],
        [
          "Search the sources",
          "Search within the case scope",
          "Search the captured case evidence for relevant observations and cite the sources.",
          Search,
        ],
        [
          "Plan the next steps",
          "Turn open questions into tasks",
          "What questions remain unanswered in this case? Suggest evidence-based next steps.",
          Sparkles,
        ],
      ]
    : [
        [
          "Think it through",
          "Structure an idea or question",
          "Help me structure a research question and an evidence collection plan.",
          Sparkles,
        ],
        [
          "Understand a concept",
          "Get a clear explanation",
          "Explain the difference between an observation, a candidate finding, and a confirmed finding.",
          FileSearch,
        ],
      ];
  return (
    <div className="chat-workspace">
      <section
        className="chat-column"
        aria-label={caseData ? "Case conversation" : "Private conversation"}
      >
        {chatId && (
          <header className="chat-heading">
            <div>
              <h1>{meta.data?.title ?? "Conversation"}</h1>
              <p>
                {runtime} · Budget {money(meta.data?.budget_usd)} · Spent{" "}
                {money(meta.data?.spent_usd)}
              </p>
            </div>
            <div className="flex gap-2 items-center">
              <StatusBadge status={meta.data?.status} />
              <Button
                size="icon-sm"
                variant="ghost"
                disabled={!meta.data || !allowed || running}
                aria-label="Conversation settings"
                onClick={() => setSettings(true)}
              >
                <SlidersHorizontal />
              </Button>
            </div>
          </header>
        )}
        {meta.isLoading || messages.isLoading ? (
          <Loading label="Loading conversation" />
        ) : (
          <>
            <ErrorBanner
              error={meta.error || messages.error}
              retry={() => {
                void meta.refetch();
                void messages.refetch();
              }}
            />
            {!messages.items.length ? (
              <div className="welcome">
                <Sparkles
                  className="welcome-mark"
                  size={35}
                  strokeWidth={1.35}
                />
                <span className="eyebrow">
                  {caseData
                    ? "YOUR CASE WORKSPACE"
                    : "A LITTLE CLARITY GOES A LONG WAY"}
                </span>
                <h1>
                  {caseData ? "Every investigation" : "What are we"}
                  <br />
                  <span>
                    {caseData ? "starts with a question." : "working on today?"}
                  </span>
                </h1>
                <p>
                  {caseData
                    ? "Explore the evidence, connect the dots, and follow your agents at every step. You stay in control of the findings."
                    : "A private space to explore ideas, ask questions, and think things through. Start a case when you need evidence, tools, and a shared investigation."}
                </p>
                <div className="starter-grid">
                  {starter.map(([title, description, prompt, Icon]) => {
                    const I = Icon as typeof Sparkles;
                    return (
                      <button
                        className="starter-card"
                        key={String(title)}
                        onClick={() => setText(String(prompt))}
                      >
                        <I />
                        <strong>{String(title)}</strong>
                        <span>{String(description)}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : (
              <Conversation className="min-h-0 flex-1">
                <ConversationContent className="conversation-content gap-8">
                  {messages.items.map((message) => {
                    const isCase = "claims" in message,
                      content = isCase
                        ? message.blocks
                            .map((b) => b.text ?? "")
                            .filter(Boolean)
                            .join("\n\n")
                        : message.text;
                    const assistant = message.role === "ASSISTANT",
                      claims = isCase ? message.claims : [],
                      codes = Array.from(
                        new Set(
                          claims
                            .flatMap((c) => c.evidence_codes)
                            .concat(
                              isCase
                                ? message.blocks.flatMap((b) =>
                                    (b.evidence ?? []).map((e) => e.code),
                                  )
                                : [],
                            ),
                        ),
                      );
                    return (
                      <Message
                        key={message.id}
                        from={
                          assistant
                            ? "assistant"
                            : message.role === "USER"
                              ? "user"
                              : "system"
                        }
                        className="max-w-full"
                      >
                        <div className="message-author">
                          {assistant ? (
                            <span className="assistant-avatar">
                              <Sparkles size={14} />
                            </span>
                          ) : (
                            <span className="user-avatar">
                              {user.display_name.slice(0, 1)}
                            </span>
                          )}
                          <span>
                            {assistant
                              ? "Darknetra"
                              : message.role === "USER"
                                ? "You"
                                : message.role.toLowerCase()}
                          </span>
                          <span className="ml-auto text-[9px]">
                            {date(message.at)}
                          </span>
                        </div>
                        <MessageContent className="text-[13px] leading-7">
                          {assistant ? (
                            <MessageResponse
                              components={markdownComponents}
                              skipHtml
                              controls={false}
                            >
                              {content}
                            </MessageResponse>
                          ) : (
                            <p className="whitespace-pre-wrap break-words">
                              {content}
                            </p>
                          )}
                        </MessageContent>
                        {assistant && (
                          <div className="message-meta">
                            {isCase ? (
                              <StatusBadge
                                status={
                                  message.verification?.ok
                                    ? "Citations checked"
                                    : "Needs review"
                                }
                              />
                            ) : (
                              <span className="flex items-center gap-1">
                                <LockKeyhole size={10} /> Private chat · no case
                                evidence
                              </span>
                            )}
                            <span>
                              {isCase ? message.harness : message.provider}
                            </span>
                            {message.run_id && (
                              <button
                                className="hover:text-primary"
                                onClick={() => pickRun(message.run_id!)}
                              >
                                View run{" "}
                                <GitBranch className="inline" size={10} />
                              </button>
                            )}
                            <button
                              aria-label="Copy message"
                              onClick={async () => {
                                try {
                                  await navigator.clipboard.writeText(content);
                                  setCopied(message.id);
                                } catch (reason) {
                                  setError(reason);
                                }
                              }}
                            >
                              {copied === message.id ? (
                                <Check size={12} />
                              ) : (
                                <Copy size={12} />
                              )}
                            </button>
                          </div>
                        )}
                        {codes.length > 0 && (
                          <Sources className="mt-3">
                            <SourcesTrigger count={codes.length} />
                            <SourcesContent>
                              <div className="flex flex-wrap gap-2">
                                {codes.map((code) => (
                                  <EvidenceChip
                                    key={code}
                                    code={code}
                                    onClick={() => onEvidence(code)}
                                  />
                                ))}
                              </div>
                              {claims.map((c, i) => (
                                <div
                                  key={i}
                                  className="mt-2 border-t pt-2 max-w-xl"
                                >
                                  <div className="flex gap-2 mb-1">
                                    <StatusBadge status={c.kind} />
                                    <StatusBadge
                                      status={
                                        c.verified
                                          ? "Verified citation"
                                          : "Unverified"
                                      }
                                    />
                                  </div>
                                  <p className="text-xs text-foreground leading-relaxed">
                                    {c.text}
                                  </p>
                                  {c.reason && (
                                    <p className="text-[10px] text-muted-foreground">
                                      {c.reason}
                                    </p>
                                  )}
                                </div>
                              ))}
                            </SourcesContent>
                          </Sources>
                        )}
                        {assistant &&
                          isCase &&
                          claims.length > 0 &&
                          !codes.length && (
                            <p className="draft-label mt-2">
                              Claims have no linked evidence. Human review is
                              required.
                            </p>
                          )}
                      </Message>
                    );
                  })}
                  <LoadMore {...messages} />
                  {running && (
                    <div
                      role="status"
                      className="flex items-center gap-2 text-xs text-muted-foreground"
                    >
                      <span className="live-dot" />
                      {currentRun.snapshot?.nodes
                        .filter((n) => n.status === "running")
                        .at(-1)?.summary ||
                        "Run in progress. Waiting for a verified response…"}
                    </div>
                  )}
                </ConversationContent>
                <ConversationScrollButton />
              </Conversation>
            )}
          </>
        )}
        <div className="composer-wrap">
          <ErrorBanner error={error || run.error} />
          {currentRun.info?.error && (
            <p role="alert" className="draft-label mb-2">
              {String(currentRun.info.error.code ?? currentRun.info.status)}:{" "}
              {String(
                currentRun.info.error.message ??
                  "The run ended without completing.",
              )}
            </p>
          )}
          <PromptInput
            className="composer-frame"
            maxFiles={0}
            onSubmit={send}
            onError={(e) =>
              queueMicrotask(() => setError(new Error(e.message)))
            }
          >
            <PromptInputBody>
              <PromptInputTextarea
                aria-label="Message"
                placeholder={
                  caseData
                    ? "Ask about the evidence. Give your agent a direction…"
                    : "Ask anything. Start somewhere…"
                }
                value={text}
                onChange={(e) => setText(e.target.value)}
                maxLength={caseData ? 32000 : 16000}
                disabled={!allowed || meta.data?.status === "CLOSED"}
              />
            </PromptInputBody>
            <PromptInputFooter>
              <PromptInputTools>
                {caseData && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Attach case evidence"
                    disabled={!allowed || running}
                    onClick={() => setAttach(true)}
                  >
                    <Paperclip size={15} />
                  </Button>
                )}
                {!chatId ? (
                  <>
                    <select
                      className="composer-select"
                      aria-label="Model provider"
                      value={provider}
                      onChange={(e) => setProvider(e.target.value)}
                    >
                      {providers.map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                    <label className="flex items-center gap-1 text-[10px] text-muted-foreground">
                      $
                      <input
                        className="composer-budget"
                        aria-label="Run budget in USD"
                        type="number"
                        min="0.01"
                        max={caseData ? 1000 : 100}
                        step="0.01"
                        value={budget}
                        onChange={(e) => setBudget(e.target.value)}
                        required
                      />
                    </label>
                  </>
                ) : (
                  <span className="text-[10px] text-muted-foreground px-2">
                    {runtime}
                  </span>
                )}
                {attachments.length > 0 && (
                  <button
                    type="button"
                    className="text-[10px] text-primary"
                    onClick={() => setAttach(true)}
                  >
                    {attachments.length} sources
                  </button>
                )}
              </PromptInputTools>
              <PromptInputSubmit
                aria-label={running ? "Stop run" : "Send message"}
                status={running ? "streaming" : "ready"}
                onStop={() => void cancel()}
                disabled={
                  busy ||
                  !allowed ||
                  meta.data?.status === "CLOSED" ||
                  messages.hasNextPage ||
                  (!running && !text.trim())
                }
              >
                {running ? undefined : <ArrowUp size={17} />}
              </PromptInputSubmit>
            </PromptInputFooter>
          </PromptInput>
          <p className="composer-note">
            {!allowed
              ? "Your case role allows viewing. An analyst or lead can start a run."
              : meta.data?.status === "CLOSED"
                ? "This conversation is closed. Reopen it in conversation settings."
                : caseData
                  ? "AI assists. Evidence supports. You confirm.  ·  Enter to send, Shift + Enter for a new line"
                  : "Private to you. Case evidence and research tools are available in case conversations."}
          </p>
        </div>
      </section>
      {showActivity && (
        <ActivityPanel
          run={run}
          onClose={() => onActivity(false)}
          onEvidence={onEvidence}
        />
      )}
      <Modal
        open={attach}
        onClose={() => setAttach(false)}
        title="Attach case evidence"
        description="Choose captured evidence for this message. Upload new material in the Evidence view."
      >
        <ErrorBanner error={evidence.error} />
        {evidence.isLoading ? (
          <Loading />
        ) : (
          <div className="space-y-2 max-h-80 overflow-auto">
            {evidence.items.map((e) => (
              <label
                className="flex items-center gap-3 rounded-lg border p-3 text-xs"
                key={e.id}
              >
                <input
                  type="checkbox"
                  checked={attachments.includes(e.code)}
                  onChange={(event) =>
                    setAttachments(
                      event.target.checked
                        ? [...attachments, e.code]
                        : attachments.filter((c) => c !== e.code),
                    )
                  }
                />
                <span>
                  <strong className="font-mono text-primary">{e.code}</strong>
                  <span className="block text-muted-foreground mt-1">
                    {e.original_filename || e.kind}
                  </span>
                </span>
                <StatusBadge status={e.status} />
              </label>
            ))}
            <LoadMore {...evidence} />
            {!evidence.items.length && (
              <p className="muted">No captured evidence yet.</p>
            )}
          </div>
        )}
        <Button onClick={() => setAttach(false)}>
          Use {attachments.length} selected sources
        </Button>
      </Modal>
      {settings && meta.data && base && (
        <ConversationSettings
          data={meta.data}
          isCase={Boolean(caseData)}
          base={base}
          onClose={() => setSettings(false)}
          onSave={async () => {
            await client.invalidateQueries({ queryKey: ["api", prefix] });
            if (caseData) await invalidateCase(client, caseData.id);
            setSettings(false);
          }}
        />
      )}
    </div>
  );
}
function ConversationSettings({
  data,
  isCase,
  base,
  onClose,
  onSave,
}: {
  data: S<"Thread"> | S<"Chat">;
  isCase: boolean;
  base: string;
  onClose: () => void;
  onSave: () => Promise<void>;
}) {
  const [title, setTitle] = useState(data.title),
    [budget, setBudget] = useState(String(data.budget_usd)),
    [status, setStatus] = useState(data.status),
    [provider, setProvider] = useState(
      "provider" in data ? data.provider : "AUTO",
    ),
    [goal, setGoal] = useState("goal" in data ? (data.goal ?? "") : ""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>();
  return (
    <Modal open onClose={onClose} title="Conversation settings">
      <form
        className="content-stack"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            await api(base, "PATCH", {
              title,
              budget_usd: Number(budget),
              status,
              ...(isCase ? { goal } : { provider }),
            });
            await onSave();
          } catch (reason) {
            setError(reason);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="Title">
          <input
            required
            maxLength={isCase ? 300 : 200}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        {isCase ? (
          <Field label="Goal">
            <textarea value={goal} onChange={(e) => setGoal(e.target.value)} />
          </Field>
        ) : (
          <Field label="Provider">
            <select
              value={provider}
              onChange={(e) =>
                setProvider(e.target.value as S<"Chat">["provider"])
              }
            >
              {provider === "DETERMINISTIC" && (
                <option value="DETERMINISTIC" disabled>
                  Deterministic (case mode only)
                </option>
              )}
              {providers.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </Field>
        )}
        <Field label="Run budget (USD)">
          <input
            type="number"
            min="0.01"
            max={isCase ? 1000 : 100}
            step="0.01"
            value={budget}
            required
            onChange={(e) => setBudget(e.target.value)}
          />
        </Field>
        <Field label="Status">
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option>OPEN</option>
            <option>CLOSED</option>
          </select>
        </Field>
        <ErrorBanner error={error} />
        <Button disabled={busy}>{busy ? "Saving…" : "Save changes"}</Button>
      </form>
    </Modal>
  );
}

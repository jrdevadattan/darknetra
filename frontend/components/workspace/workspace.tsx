"use client";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Archive,
  ArchiveRestore,
  ArrowUp,
  Bot,
  Brain,
  Check,
  ChevronRight,
  Copy,
  Eye,
  FolderOpen,
  Layers3,
  LoaderCircle,
  Menu,
  MessageSquare,
  MoreHorizontal,
  Network,
  PanelRight,
  Paperclip,
  Plus,
  Square,
  X,
  ShieldCheck,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { CaseMarkdown, FileIcon, LinkedText } from "./source-ui";
import { WorkspaceSettings } from "./settings";
import { NetraStatus } from "./netra-status";
import { ActivityPanel } from "./activity-panel";
import { PanelResize, usePanelWidth } from "./panel-resize";
import { CaseMonitoring } from "./monitoring";
import { CaseBoard } from "./case-board";
import { NotificationInbox } from "./notifications";
import { assistantNotice } from "@/lib/assistant-display";
import type {
  Case,
  Chat,
  ChatMessage,
  ChatAttachment,
  WorkspaceData,
} from "@/lib/chat-types";

const empty: WorkspaceData = { version: 1, cases: [], chats: [] };
async function request<T>(url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "The request failed.");
  return result;
}

export function Workspace({ initialCaseId }: { initialCaseId?: string }) {
  const [navigationWidth, resizeNavigation] = usePanelWidth(
    "darknetra-navigation-width",
    250,
  );
  const [activityWidth, resizeActivity] = usePanelWidth(
    "darknetra-activity-width",
    520,
  );
  const router = useRouter();
  const params = useSearchParams();
  const selectedCaseId = params.get("case") || initialCaseId || null;
  const chatId = params.get("chat");
  const [data, setData] = useState<WorkspaceData>(empty);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [text, setText] = useState("");
  const [thinking, setThinking] = useState(false);
  const [netra, setNetra] = useState(false);
  const [newCase, setNewCase] = useState(false);
  const [boardCase, setBoardCase] = useState<string>();
  const [caseTitle, setCaseTitle] = useState("");
  const [caseNotes, setCaseNotes] = useState("");
  const [savingCase, setSavingCase] = useState(false);
  const [sending, setSending] = useState<string | null>(null);
  const sendingRef = useRef(false);
  const [mobile, setMobile] = useState(false);
  const [caseFolders, setCaseFolders] = useState<Record<string, boolean>>({});
  const [archiving, setArchiving] = useState<string | null>(null);
  const [activity, setActivity] = useState(false);
  const [activityLeft, setActivityLeft] = useState(true);
  const [selectedRun, setSelectedRun] = useState<string>();
  const openedRun = useRef("");
  const [copied, setCopied] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploaded, setUploaded] = useState<{
    chatId: string | null;
    files: ChatAttachment[];
  }>({ chatId: null, files: [] });
  const uploadInput = useRef<HTMLInputElement>(null);
  const attachments = uploaded.chatId === chatId ? uploaded.files : [];
  const bottom = useRef<HTMLDivElement>(null);
  const chat = data.chats.find((item) => item.id === chatId);
  const caseId = selectedCaseId || chat?.caseId || null;
  const caseData = data.cases.find((item) => item.id === caseId);
  const lastAssistant = chat?.messages.findLast(
    (item) => item.role === "assistant",
  );
  const running = chat?.messages.some((item) => item.status === "running");
  const busy = running || sending === (chatId || "new");
  const activityMessage =
    chat?.messages.find(
      (item) => item.id === selectedRun && item.role === "assistant",
    ) || lastAssistant;
  const runIndex =
    chat?.messages.findIndex((item) => item.id === activityMessage?.id) ?? -1;
  const runFiles = chat?.messages
    .slice(0, runIndex)
    .findLast((item) => item.role === "user")?.attachments;

  useEffect(() => {
    if (
      lastAssistant?.status === "running" &&
      openedRun.current !== lastAssistant.id
    ) {
      openedRun.current = lastAssistant.id;
      setSelectedRun(lastAssistant.id);
      setActivity(true);
    }
  }, [lastAssistant?.id, lastAssistant?.status]);
  useEffect(() => {
    setActivityLeft(localStorage.getItem("activity-side") !== "right");
    try {
      const saved: unknown = JSON.parse(
        localStorage.getItem("darknetra-case-folders") || "{}",
      );
      if (saved && typeof saved === "object" && !Array.isArray(saved))
        setCaseFolders(
          Object.fromEntries(
            Object.entries(saved).filter(
              ([, value]) => typeof value === "boolean",
            ),
          ),
        );
    } catch {
      /* Folder controls still work when browser storage is unavailable. */
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      setData(await request<WorkspaceData>("/api/workspace"));
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 3000);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [
    chat?.messages.length,
    lastAssistant?.text,
    lastAssistant?.activity.length,
  ]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobile(false);
        setNewCase(false);
        setActivity(false);
      }
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, []);

  function setFolderExpanded(id: string, expanded: boolean) {
    const next = { ...caseFolders, [id]: expanded };
    setCaseFolders(next);
    try {
      localStorage.setItem("darknetra-case-folders", JSON.stringify(next));
    } catch {
      /* Keep the current session usable. */
    }
  }
  const folderExpanded = (id: string) => caseFolders[id] ?? caseId === id;

  function navigate(nextCase: string | null, nextChat: string | null = null) {
    if (nextCase) setFolderExpanded(nextCase, true);
    const query = new URLSearchParams();
    if (nextCase) query.set("case", nextCase);
    if (nextChat) query.set("chat", nextChat);
    router.push("/" + (query.size ? "?" + query : ""));
    setText("");
    setError("");
    setMobile(false);
    setActivity(false);
    setSelectedRun(undefined);
  }
  function receive(id: string, message: ChatMessage) {
    setData((previous) => ({
      ...previous,
      chats: previous.chats.map((item) =>
        item.id === id
          ? {
              ...item,
              messages: [
                ...item.messages.filter((entry) => entry.id !== message.id),
                message,
              ],
            }
          : item,
      ),
    }));
  }
  async function ensureChat() {
    if (chatId) return chatId;
    const created = await request<Chat>("/api/workspace", {
      type: "chat",
      caseId,
    });
    setData((previous) => ({
      ...previous,
      chats: [created, ...previous.chats],
    }));
    const query = new URLSearchParams({ chat: created.id });
    if (caseId) query.set("case", caseId);
    router.replace("/?" + query);
    return created.id;
  }
  async function upload(files: File[]) {
    if (!files.length || uploading || busy || chat?.archivedAt) return;
    if (attachments.length + files.length > 8) {
      setError("Attach up to 8 files per message.");
      return;
    }
    if (files.some((file) => file.size > 32 * 1024 * 1024)) {
      setError("Files must be 32 MiB or smaller.");
      return;
    }
    setUploading(true);
    setError("");
    try {
      const id = await ensureChat();
      for (const file of files) {
        const form = new FormData();
        form.append("file", file);
        const response = await fetch(`/api/chat/${id}/files`, {
          method: "POST",
          body: form,
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Upload failed.");
        setUploaded((previous) => ({
          chatId: id,
          files: [
            ...(previous.chatId === id ? previous.files : []),
            result as ChatAttachment,
          ],
        }));
      }
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setUploading(false);
    }
  }
  async function send() {
    if (
      (!text.trim() && !attachments.length) ||
      busy ||
      uploading ||
      chat?.archivedAt ||
      sendingRef.current
    )
      return;
    sendingRef.current = true;
    const content = text.trim() || "Please review the attached files.";
    setSending(chatId || "new");
    setError("");
    try {
      const id = await ensureChat();
      setSending(id);
      const response = await fetch(`/api/chat/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: content,
          mode: netra ? "netra" : thinking ? "thinking" : "normal",
          attachments: attachments.map((file) => file.name),
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        }),
      });
      if (!response.ok)
        throw new Error(
          (await response.json()).error || "Could not start Ollama.",
        );
      setText("");
      setSelectedRun(undefined);
      setActivity(true);
      setUploaded((previous) =>
        previous.chatId === id ? { chatId: id, files: [] } : previous,
      );
      await refresh();
      if (!response.body)
        throw new Error(
          "The reply stream is unavailable. Refresh to reconnect.",
        );
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let pending = "";
      for (;;) {
        const chunk = await reader.read();
        if (chunk.done) break;
        pending += decoder.decode(chunk.value, { stream: true });
        let boundary;
        while ((boundary = pending.indexOf("\n\n")) !== -1) {
          const block = pending.slice(0, boundary);
          pending = pending.slice(boundary + 2);
          if (block.startsWith("data: "))
            receive(id, JSON.parse(block.slice(6)).message);
        }
      }
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      sendingRef.current = false;
      setSending(null);
      await refresh();
    }
  }
  async function stop() {
    if (!chatId) return;
    try {
      const response = await fetch(`/api/chat/${chatId}`, { method: "DELETE" });
      if (!response.ok) throw new Error((await response.json()).error);
      await refresh();
    } catch (reason) {
      setError((reason as Error).message);
    }
  }
  async function create(event: React.FormEvent) {
    event.preventDefault();
    setSavingCase(true);
    setError("");
    try {
      const item = await request<Case>("/api/workspace", {
        type: "case",
        title: caseTitle,
        notes: caseNotes,
      });
      await refresh();
      setNewCase(false);
      setCaseTitle("");
      setCaseNotes("");
      navigate(item.id);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setSavingCase(false);
    }
  }
  async function changeArchive(item: Chat, archived: boolean) {
    setArchiving(item.id);
    try {
      const updated = await request<Chat>("/api/workspace", {
        type: "archive-chat",
        chatId: item.id,
        archived,
      });
      setData((previous) => ({
        ...previous,
        chats: previous.chats.map((entry) =>
          entry.id === item.id
            ? { ...entry, archivedAt: updated.archivedAt }
            : entry,
        ),
      }));
      if (archived && chatId === item.id) navigate(item.caseId);
      if (!archived && item.caseId) setFolderExpanded(item.caseId, true);
    } finally {
      setArchiving(null);
    }
  }
  async function archiveFromChat(item: Chat, archived: boolean) {
    try {
      await changeArchive(item, archived);
    } catch (reason) {
      setError((reason as Error).message);
    }
  }
  const chatLink = (item: Chat) => (
    <div
      key={item.id}
      className={`nav-chat-row ${chatId === item.id ? "active" : ""}`}
    >
      <button
        className="nav-item"
        onClick={() => navigate(item.caseId, item.id)}
        title={item.title}
      >
        <MessageSquare size={15} />
        <span>{item.title}</span>
        {item.messages.some((message) => message.status === "running") && (
          <LoaderCircle className="spin" size={13} />
        )}
      </button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className="chat-options icon-button"
            aria-label={`Options for ${item.title}`}
            title="Chat options"
            disabled={archiving !== null}
          >
            {archiving === item.id ? (
              <LoaderCircle className="spin" size={15} />
            ) : (
              <MoreHorizontal size={16} />
            )}
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onSelect={() => void archiveFromChat(item, true)}>
            <Archive size={16} />
            Archive chat
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
  return (
    <div
      className="cli-workspace"
      style={
        {
          "--navigation-width": `${navigationWidth}px`,
          "--activity-width": `${activityWidth}px`,
        } as CSSProperties
      }
    >
      {mobile && (
        <button
          className="nav-overlay"
          aria-label="Close navigation"
          onClick={() => setMobile(false)}
        />
      )}
      <aside
        className={`sidebar ${mobile ? "open" : ""}`}
        aria-label="Workspace navigation"
        id="workspace-navigation"
      >
        <PanelResize
          label="Resize navigation sidebar"
          width={navigationWidth}
          onResize={resizeNavigation}
          minimum={180}
          maximum={360}
          initial={250}
        />
        <button
          className="brand"
          type="button"
          aria-label="Open workspace home"
          onClick={() => navigate(null)}
        >
          <span className="brand-mark">
            <Layers3 size={21} />
          </span>
          darknetra<span className="brand-period">.</span>
        </button>
        <div className="sidebar-actions">
          <button className="primary-button" onClick={() => navigate(null)}>
            <Plus size={16} />
            New chat
          </button>
          <button
            className="icon-button"
            aria-label="Create case"
            title="Create case"
            onClick={() => setNewCase(true)}
          >
            <FolderOpen size={18} />
          </button>
        </div>
        <nav className="sidebar-nav">
          <div className="nav-section-title">
            Cases
            <button aria-label="New case" onClick={() => setNewCase(true)}>
              <Plus size={14} />
            </button>
          </div>
          {data.cases.map((item) => (
            <div key={item.id}>
              <div
                className={`case-folder-row ${caseId === item.id ? "active" : ""}`}
              >
                <button
                  className="folder-toggle"
                  aria-label={`${folderExpanded(item.id) ? "Collapse" : "Expand"} ${item.title}`}
                  title={`${folderExpanded(item.id) ? "Collapse" : "Expand"} folder`}
                  aria-expanded={folderExpanded(item.id)}
                  aria-controls={`case-chats-${item.id}`}
                  onClick={() =>
                    setFolderExpanded(item.id, !folderExpanded(item.id))
                  }
                >
                  <ChevronRight size={14} />
                </button>
                <button
                  className="nav-item"
                  onClick={() => navigate(item.id)}
                  title={item.title}
                >
                  <FolderOpen size={15} />
                  <span>{item.title}</span>
                </button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      className="case-folder-menu icon-button"
                      aria-label={`Case options: ${item.title}`}
                      title="Case options"
                    >
                      <MoreHorizontal size={16} />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start">
                    <DropdownMenuItem onSelect={() => setBoardCase(item.id)}>
                      <Network size={15} />
                      Create knowledge graph
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onSelect={() =>
                        setFolderExpanded(item.id, !folderExpanded(item.id))
                      }
                    >
                      <FolderOpen size={15} />
                      {folderExpanded(item.id)
                        ? "Collapse folder"
                        : "Expand folder"}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
              <div
                className="case-chats"
                id={`case-chats-${item.id}`}
                hidden={!folderExpanded(item.id)}
              >
                <button className="nav-item" onClick={() => navigate(item.id)}>
                  <Plus size={14} />
                  <span>New case chat</span>
                </button>
                {data.chats.some(
                  (entry) => entry.caseId === item.id && entry.board,
                ) && (
                  <button
                    className="nav-item"
                    onClick={() => setBoardCase(item.id)}
                  >
                    <Network size={14} />
                    <span>Knowledge graph</span>
                  </button>
                )}
                {data.chats
                  .filter(
                    (entry) =>
                      entry.caseId === item.id &&
                      !entry.archivedAt &&
                      !entry.board,
                  )
                  .map(chatLink)}
              </div>
            </div>
          ))}
          {!data.cases.length && (
            <p className="nav-empty">Create a case to organise your work.</p>
          )}
          <div className="nav-section-title">Chats</div>
          {data.chats
            .filter((item) => !item.caseId && !item.archivedAt)
            .map(chatLink)}
        </nav>
        <footer className="sidebar-footer">
          <Bot size={17} />
          <div>
            Ollama<small>Local workspace</small>
          </div>
        </footer>
      </aside>
      <main className="chat-main">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobile(true)}
            >
              <Menu size={19} />
            </button>
            <span>{caseId ? "Cases" : "Chat"}</span>
            <ChevronRight size={14} />
            <strong>{caseData?.title || "Ollama"}</strong>
          </div>
          <div className="topbar-actions">
            <CaseMonitoring
              key={caseId || "none"}
              caseId={caseId}
              onOpenChat={(id) => navigate(caseId, id)}
              onChange={refresh}
            />
            <WorkspaceSettings
              data={data}
              onRestore={(item) => changeArchive(item, false)}
              onOpen={(item) => navigate(item.caseId, item.id)}
            />
            <NotificationInbox
              onOpen={(caseId, chatId) => navigate(caseId, chatId)}
            />
            <button
              className={`icon-button ${activity ? "selected" : ""}`}
              aria-label="Toggle agent activity"
              onClick={() => setActivity(!activity)}
            >
              <PanelRight size={18} />
            </button>
          </div>
        </header>
        <div
          className={`chat-body ${activityLeft ? "activity-on-left" : "activity-on-right"}`}
        >
          <section className="chat-column" aria-label="Conversation">
            {chat && (
              <div className="chat-heading">
                <h1>{chat.title}</h1>
                <span>Ollama{chat.sessionId ? " · Saved session" : ""}</span>
              </div>
            )}
            {loading ? (
              <div className="welcome">
                <LoaderCircle className="spin" />
                <p>Opening workspace…</p>
              </div>
            ) : (caseId && !caseData) || (chatId && !chat) ? (
              <div className="welcome">
                <p>This case or chat could not be found.</p>
                <button onClick={() => navigate(null)}>Open workspace</button>
              </div>
            ) : !chat?.messages.length ? (
              <div className="welcome">
                <div className="welcome-mark">
                  <Bot size={32} strokeWidth={1.4} />
                </div>
                <span className="eyebrow">
                  {caseData ? "CASE CHAT" : "OLLAMA"}
                </span>
                <h1>
                  What are we
                  <br />
                  <span>working on today?</span>
                </h1>
                <p>
                  {caseData?.notes ||
                    "Ask a question, research a topic, or work through an idea. Ollama takes it from here."}
                </p>
                <div className="starter-grid">
                  <button
                    onClick={() =>
                      setText(
                        caseData
                          ? "Help me research this case. What information do you need to begin?"
                          : "Help me think through an idea.",
                      )
                    }
                  >
                    <MessageSquare size={19} />
                    <strong>
                      {caseData ? "Start with this case" : "Think it through"}
                    </strong>
                    <span>Turn a question into a conversation</span>
                  </button>
                  <button
                    onClick={() => setText("Help me plan the next steps.")}
                  >
                    <Layers3 size={19} />
                    <strong>Plan the next steps</strong>
                    <span>Work out what to do next</span>
                  </button>
                </div>
              </div>
            ) : (
              <div className="conversation-content">
                {chat.messages.map((message) => (
                  <article
                    key={message.id}
                    className={`chat-message ${message.role}`}
                  >
                    <div className="message-author">
                      <span
                        className={
                          message.role === "assistant"
                            ? "assistant-avatar"
                            : "user-avatar"
                        }
                      >
                        {message.role === "assistant" ? (
                          <ShieldCheck size={15} />
                        ) : (
                          "Y"
                        )}
                      </span>
                      <strong>
                        {message.role === "assistant"
                          ? "Lead Investigator"
                          : "You"}
                      </strong>
                      <time>
                        {new Date(message.at).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </time>
                    </div>
                    {!!message.attachments?.length && (
                      <div className="message-attachments">
                        {message.attachments.map((file) => (
                          <a
                            key={file.name}
                            className="file-chip"
                            href={`/api/chat/${chat.id}/files?name=${encodeURIComponent(file.name)}`}
                            download={file.label}
                          >
                            <FileIcon name={file.label} size={14} />
                            <span>{file.label}</span>
                            <small>
                              {Math.max(1, Math.ceil(file.size / 1024))} KB
                            </small>
                          </a>
                        ))}
                      </div>
                    )}
                    {message.netra && <NetraStatus goal={message.netra} />}
                    <div className="message-text">
                      {message.role === "assistant" ? (
                        <CaseMarkdown
                          chatId={chat.id}
                          files={chat.messages.flatMap(
                            (m) => m.attachments || [],
                          )}
                          sources={[
                            ...message.activity.flatMap((a) => a.sources || []),
                            ...(message.agents || []).flatMap(
                              (a) =>
                                a.activity?.flatMap((s) => s.sources || []) ||
                                [],
                            ),
                          ]}
                        >
                          {message.text}
                        </CaseMarkdown>
                      ) : (
                        <p>
                          <LinkedText text={message.text} />
                        </p>
                      )}
                    </div>
                    {message.monitoring && (
                      <aside
                        className="monitoring-receipt"
                        aria-label="Monitoring status"
                      >
                        <strong>{message.monitoring.summary}</strong>
                        {message.monitoring.nextRunAt && (
                          <span>
                            Next check:{" "}
                            {new Date(
                              message.monitoring.nextRunAt,
                            ).toLocaleString()}
                          </span>
                        )}
                        {message.monitoring.monitorId && (
                          <button
                            type="button"
                            onClick={() =>
                              window.dispatchEvent(
                                new Event("darknetra-open-monitoring"),
                              )
                            }
                          >
                            Manage monitoring
                          </button>
                        )}
                      </aside>
                    )}
                    {message.status === "running" && (
                      <button
                        className="run-progress"
                        onClick={() => {
                          setSelectedRun(message.id);
                          setActivity(true);
                        }}
                      >
                        <LoaderCircle className="spin" size={14} />
                        {message.activity.at(-1)?.label ||
                          "Reviewing the case…"}
                      </button>
                    )}
                    {message.error && (
                      <p className="error-banner" role="alert">
                        {assistantNotice(message.error)}
                      </p>
                    )}
                    {message.status === "stopped" && (
                      <p className="muted">Stopped</p>
                    )}
                    {message.role === "assistant" && message.text && (
                      <div className="message-actions">
                        <button
                          className="view-run-button"
                          onClick={() => {
                            setSelectedRun(message.id);
                            setActivity(true);
                          }}
                        >
                          <PanelRight size={13} />
                          View run
                          {message.agents?.length
                            ? ` · ${message.agents.length} specialists`
                            : ""}
                        </button>
                        <button
                          className="copy-button"
                          aria-label="Copy message"
                          onClick={async () => {
                            try {
                              await navigator.clipboard.writeText(message.text);
                              setCopied(message.id);
                            } catch {
                              setError("Could not copy the message.");
                            }
                          }}
                        >
                          {copied === message.id ? (
                            <Check size={13} />
                          ) : (
                            <Copy size={13} />
                          )}
                        </button>
                      </div>
                    )}
                  </article>
                ))}
                <div ref={bottom} />
              </div>
            )}
            <div className="composer-wrap">
              {error && !newCase && (
                <div className="error-banner" role="alert">
                  {assistantNotice(error)}
                  <button
                    aria-label="Dismiss error"
                    onClick={() => setError("")}
                  >
                    <X size={13} />
                  </button>
                </div>
              )}
              {chat?.archivedAt ? (
                <div className="archived-chat-banner" role="status">
                  <Archive size={21} />
                  <div>
                    <strong>This chat is archived</strong>
                    <p>
                      Restore it to continue the conversation. Scheduled
                      monitoring stays active.
                    </p>
                  </div>
                  {busy && (
                    <button
                      className="icon-button"
                      aria-label="Stop reply"
                      onClick={() => void stop()}
                    >
                      <Square size={15} />
                    </button>
                  )}
                  <button
                    className="archive-restore"
                    disabled={archiving !== null}
                    onClick={() => void archiveFromChat(chat, false)}
                  >
                    {archiving === chat.id ? (
                      <LoaderCircle className="spin" size={16} />
                    ) : (
                      <ArchiveRestore size={16} />
                    )}
                    Restore chat
                  </button>
                </div>
              ) : (
                <>
                  <form
                    className="composer"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void send();
                    }}
                  >
                    {!!attachments.length && (
                      <div
                        className="composer-attachments"
                        aria-label="Attached files"
                      >
                        {attachments.map((file) => (
                          <span className="file-chip" key={file.name}>
                            <Paperclip size={14} />
                            <span>{file.label}</span>
                            <button
                              type="button"
                              aria-label={`Remove attachment ${file.label}`}
                              onClick={() =>
                                setUploaded((previous) => ({
                                  ...previous,
                                  files: previous.files.filter(
                                    (item) => item.name !== file.name,
                                  ),
                                }))
                              }
                            >
                              <X size={13} />
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                    <textarea
                      aria-label="Message"
                      placeholder={
                        caseData
                          ? netra
                            ? "Describe the category, region or references for Netra to investigate…"
                            : "Message Ollama about this case…"
                          : netra
                            ? "Give Netra a focused investigation objective…"
                            : "Message Ollama…"
                      }
                      value={text}
                      maxLength={32000}
                      rows={2}
                      onChange={(event) => setText(event.target.value)}
                      onKeyDown={(event) => {
                        if (
                          event.key === "Enter" &&
                          !event.shiftKey &&
                          !event.nativeEvent.isComposing
                        ) {
                          event.preventDefault();
                          void send();
                        }
                      }}
                    />
                    <div className="composer-toolbar">
                      <input
                        ref={uploadInput}
                        type="file"
                        multiple
                        hidden
                        aria-label="Upload files"
                        onChange={(event) => {
                          const files = Array.from(event.target.files || []);
                          event.target.value = "";
                          void upload(files);
                        }}
                      />
                      <button
                        className="icon-button"
                        type="button"
                        aria-label="Upload files"
                        title="Attach files · up to 32 MiB each"
                        disabled={uploading || busy || loading}
                        onClick={() => uploadInput.current?.click()}
                      >
                        {uploading ? (
                          <LoaderCircle className="spin" size={16} />
                        ) : (
                          <Paperclip size={16} />
                        )}
                      </button>
                      <button
                        className={`mode-button ${thinking ? "selected" : ""}`}
                        type="button"
                        aria-pressed={thinking}
                        disabled={netra}
                        onClick={() => setThinking(!thinking)}
                      >
                        <Brain size={14} />
                        {thinking ? "Thinking" : "Normal"}
                      </button>
                      <button
                        className={`mode-button netra-toggle ${netra ? "selected" : ""}`}
                        type="button"
                        aria-label="Netra mode"
                        aria-pressed={netra}
                        title="Netra · Specialist research and source verification · up to 10 minutes per request"
                        onClick={() => setNetra(!netra)}
                      >
                        <Eye size={17} />
                        <span>Netra</span>
                      </button>
                      <span>{uploading ? "Uploading…" : "Ollama"}</span>
                      {busy ? (
                        <button
                          className="send-button"
                          type="button"
                          aria-label="Stop reply"
                          onClick={() => void stop()}
                        >
                          <Square size={14} />
                        </button>
                      ) : (
                        <button
                          className="send-button"
                          aria-label="Send message"
                          disabled={
                            (!text.trim() && !attachments.length) ||
                            uploading ||
                            loading ||
                            Boolean(sending) ||
                            (Boolean(chatId) && !chat) ||
                            (Boolean(caseId) && !caseData)
                          }
                        >
                          <ArrowUp size={18} />
                        </button>
                      )}
                    </div>
                  </form>
                  <p className="composer-note">
                    {sending && sending !== chatId
                      ? "Ollama is replying in another chat."
                      : netra
                        ? "Netra · Public web + Tor sources · Specialist review · Up to 10 minutes"
                        : "Enter to send · Shift + Enter for a new line"}
                  </p>
                </>
              )}
            </div>
          </section>
          {activity && (
            <ActivityPanel
              width={activityWidth}
              onResize={resizeActivity}
              side={activityLeft ? "left" : "right"}
              key={activityMessage?.id || "empty"}
              message={activityMessage}
              files={runFiles}
              chatId={chat?.id}
              onClose={() => setActivity(false)}
              onSwap={() => {
                setActivityLeft(!activityLeft);
                localStorage.setItem(
                  "activity-side",
                  activityLeft ? "right" : "left",
                );
              }}
            />
          )}
        </div>
      </main>
      {boardCase && (
        <CaseBoard
          key={boardCase}
          caseId={boardCase}
          onClose={() => setBoardCase(undefined)}
          onChange={() => void refresh()}
          onOpenChat={(id) => {
            navigate(boardCase, id);
            setBoardCase(undefined);
          }}
        />
      )}
      {newCase && (
        <div
          className="modal-backdrop"
          onClick={(event) => {
            if (event.target === event.currentTarget && !savingCase)
              setNewCase(false);
          }}
        >
          <section
            className="case-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="case-dialog-title"
          >
            <header>
              <div>
                <h2 id="case-dialog-title">Create a case</h2>
                <p>Give your conversations a shared context.</p>
              </div>
              <button
                className="icon-button"
                aria-label="Close case dialog"
                disabled={savingCase}
                onClick={() => setNewCase(false)}
              >
                <X size={18} />
              </button>
            </header>
            <form onSubmit={(event) => void create(event)}>
              <label>
                Case title
                <input
                  aria-label="Case title"
                  autoFocus
                  required
                  maxLength={300}
                  placeholder="Name this case"
                  value={caseTitle}
                  onChange={(event) => setCaseTitle(event.target.value)}
                />
              </label>
              <label>
                Notes <span>(optional)</span>
                <textarea
                  aria-label="Case notes"
                  maxLength={8000}
                  rows={4}
                  placeholder="What should Ollama know?"
                  value={caseNotes}
                  onChange={(event) => setCaseNotes(event.target.value)}
                />
              </label>
              {error && (
                <p className="error-banner" role="alert">
                  {assistantNotice(error)}
                </p>
              )}
              <button
                className="primary-button"
                disabled={savingCase || !caseTitle.trim()}
              >
                {savingCase ? "Creating…" : "Create case"}
              </button>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}

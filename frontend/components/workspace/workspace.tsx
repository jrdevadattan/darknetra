"use client";
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  MessageSquare,
  Plus,
  FolderOpen,
  Plug,
  Settings2,
  LogOut,
  ChevronRight,
  PanelRight,
  Menu,
  ShieldCheck,
  Files,
  Search,
  Network,
  ScanFace,
  ListChecks,
  Radio,
  Bell,
  FileText,
  Users,
  History,
  LayoutDashboard,
  Sparkles,
  X,
} from "lucide-react";
import { api, ApiError, SESSION_EXPIRED, useApi, usePaged } from "@/lib/api";
import type { CaseView, S } from "@/lib/types";
import {
  Button,
  Loading,
  ErrorBanner,
  Modal,
  Field,
  LoadMore,
  StatusBadge,
  EmptyState,
} from "./shared";
import { Brand, Login, ChangePassword } from "./login";
const ChatWorkspace = dynamic(
  () => import("./chat").then((m) => m.ChatWorkspace),
  { loading: () => <Loading label="Opening conversation" /> },
);
const CaseViews = dynamic(
  () => import("./case-views").then((m) => m.CaseViews),
  { loading: () => <Loading /> },
);
const EvidenceDetail = dynamic(() =>
  import("./evidence-detail").then((m) => m.EvidenceDetail),
);
const Plugins = dynamic(() => import("./global-views").then((m) => m.Plugins), {
  loading: () => <Loading />,
});
const Settings = dynamic(
  () => import("./global-views").then((m) => m.Settings),
  { loading: () => <Loading /> },
);

const caseViews = [
  ["overview", "Overview", LayoutDashboard],
  ["evidence", "Evidence", Files],
  ["search", "Search & retrieval", Search],
  ["entities", "Entities", ScanFace],
  ["relationships", "Relationships", Network],
  ["findings", "Findings", ListChecks],
  ["monitoring", "Monitoring", Radio],
  ["alerts", "Alerts", Bell],
  ["reports", "Reports", FileText],
  ["members", "Sharing & policy", Users],
  ["audit", "Audit trail", History],
] as const;
export function Workspace({ initialCaseId }: { initialCaseId?: string }) {
  const client = useQueryClient(),
    me = useApi<S<"UserMe">>("/auth/me");
  useEffect(() => {
    const expire = () => {
      void client.cancelQueries().then(() => {
        client.setQueryData(["api", "/auth/me"], null);
        client.removeQueries({
          predicate: (q) => q.queryKey[1] !== "/auth/me",
        });
      });
    };
    window.addEventListener(SESSION_EXPIRED, expire);
    return () => window.removeEventListener(SESSION_EXPIRED, expire);
  }, [client]);
  if (me.isLoading)
    return (
      <div className="centered-page">
        <Loading />
      </div>
    );
  if (me.data === null || me.error?.status === 401 || me.error?.status === 403)
    return (
      <Login
        onLogin={(u) => {
          client.removeQueries({
            predicate: (q) => q.queryKey[1] !== "/auth/me",
          });
          client.setQueryData(["api", "/auth/me"], u);
        }}
      />
    );
  if (me.error)
    return (
      <div className="centered-page">
        <ErrorBanner error={me.error} retry={() => void me.refetch()} />
      </div>
    );
  if (!me.data) return <Loading />;
  if (me.data.must_change_password)
    return <ChangePassword onDone={() => void me.refetch()} />;
  return (
    <AuthenticatedWorkspace user={me.data} initialCaseId={initialCaseId} />
  );
}
function AuthenticatedWorkspace({
  user,
  initialCaseId,
}: {
  user: S<"UserMe">;
  initialCaseId?: string;
}) {
  const router = useRouter(),
    params = useSearchParams(),
    client = useQueryClient();
  const caseId = params.get("case") || initialCaseId,
    chatId = params.get(caseId ? "thread" : "chat") || undefined,
    view = params.get("view") || "chat",
    runId = params.get("run") || undefined;
  const cases = usePaged<S<"Case">>("/cases"),
    chats = usePaged<S<"Chat">>("/chats"),
    selectedCase = useApi<S<"Case">>(caseId ? `/cases/${caseId}` : null),
    threads = usePaged<S<"Thread">>(caseId ? `/cases/${caseId}/threads` : null),
    health = useApi<S<"Health">>("/health/ready", 30000);
  const [newCase, setNewCase] = useState(false),
    [activity, setActivity] = useState(false),
    [mobile, setMobile] = useState(false),
    [evidenceId, setEvidenceId] = useState<string>(),
    [error, setError] = useState<unknown>(),
    [loggingOut, setLoggingOut] = useState(false);
  function navigate(values: Record<string, string | undefined>) {
    const query = new URLSearchParams();
    Object.entries(values).forEach(([k, v]) => {
      if (v) query.set(k, v);
    });
    setEvidenceId(undefined);
    setMobile(false);
    router.push("/" + (query.size ? "?" + query : ""));
  }
  const newChat = (inCase = false) =>
    navigate(inCase && caseId ? { case: caseId } : {});
  const selectChat = (id: string, run?: string) =>
    navigate(caseId ? { case: caseId, thread: id, run } : { chat: id, run });
  const name =
    view === "plugins"
      ? "Tools & integrations"
      : view === "settings"
        ? "Settings"
        : selectedCase.data?.title || "Private workspace";
  async function logout() {
    setLoggingOut(true);
    setError(null);
    try {
      await api("/auth/logout", "POST");
      await client.cancelQueries();
      client.setQueryData(["api", "/auth/me"], null);
      client.removeQueries({ predicate: (q) => q.queryKey[1] !== "/auth/me" });
      router.replace("/");
    } catch (reason) {
      setError(reason);
    } finally {
      setLoggingOut(false);
    }
  }
  return (
    <div
      className="workspace"
      onKeyDown={(event) => {
        if (event.key === "Escape") setMobile(false);
      }}
    >
      {mobile && (
        <button
          className="nav-overlay"
          aria-label="Close navigation"
          onClick={() => setMobile(false)}
        />
      )}
      <aside
        id="workspace-navigation"
        className={`sidebar ${mobile ? "open" : ""}`}
        aria-label="Workspace navigation"
      >
        <Brand />
        <div className="sidebar-top">
          <Button
            className="flex-1 justify-start text-xs"
            size="sm"
            onClick={() => newChat()}
          >
            <Plus size={15} />
            New chat
          </Button>
          {["ADMIN", "INVESTIGATOR"].includes(user.global_role) && (
            <Button
              size="icon-sm"
              variant="outline"
              aria-label="Create case"
              onClick={() => setNewCase(true)}
            >
              <FolderOpen size={15} />
            </Button>
          )}
        </div>
        <nav className="sidebar-main">
          <button
            className={`nav-item ${!caseId && view === "chat" && !chatId ? "active" : ""}`}
            onClick={() => newChat()}
          >
            <Sparkles />
            <span>Workspace</span>
          </button>
          <button
            className={`nav-item ${view === "plugins" ? "active" : ""}`}
            onClick={() => navigate({ view: "plugins" })}
          >
            <Plug />
            <span>Tools & integrations</span>
          </button>
          <div className="nav-section-title">
            Cases
            <button
              aria-label="New case"
              onClick={() => setNewCase(true)}
              disabled={!["ADMIN", "INVESTIGATOR"].includes(user.global_role)}
            >
              <Plus size={13} />
            </button>
          </div>
          <ErrorBanner error={cases.error} />
          {cases.items.map((c) => (
            <div key={c.id}>
              <button
                title={c.title}
                className={`nav-item ${caseId === c.id ? "active" : ""}`}
                onClick={() => navigate({ case: c.id })}
              >
                <span
                  className={`case-indicator ${caseId === c.id ? "selected" : ""}`}
                />
                <span>{c.title}</span>
                {c.demo && <small>SYN</small>}
              </button>
              {caseId === c.id && (
                <div className="border-l ml-4 pl-1">
                  {caseViews.map(([id, label, Icon]) => (
                    <button
                      key={id}
                      className={`nav-item nav-sub ${view === id ? "active" : ""}`}
                      onClick={() => navigate({ case: c.id, view: id })}
                    >
                      <Icon />
                      <span>{label}</span>
                    </button>
                  ))}
                  <div className="nav-section-title !mt-3 !ml-5">
                    Conversations
                    <button
                      aria-label="New case conversation"
                      onClick={() => newChat(true)}
                    >
                      <Plus size={12} />
                    </button>
                  </div>
                  {threads.items.map((t) => (
                    <button
                      className={`nav-item nav-sub ${chatId === t.id && view === "chat" ? "active" : ""}`}
                      key={t.id}
                      title={t.title}
                      onClick={() => selectChat(t.id)}
                    >
                      <MessageSquare />
                      <span>{t.title}</span>
                      {t.active_run_id && <i className="live-dot" />}
                    </button>
                  ))}
                  <ErrorBanner error={threads.error} />
                  <LoadMore {...threads} />
                </div>
              )}
            </div>
          ))}
          <LoadMore {...cases} />
          {!cases.items.length && !cases.isLoading && (
            <p className="text-[11px] text-muted-foreground px-3 py-2">
              Your cases will appear here.
            </p>
          )}
          <div className="nav-section-title">
            Private chats
            <LockIcon />
          </div>
          <ErrorBanner error={chats.error} />
          {chats.items.map((c) => (
            <button
              title={c.title}
              className={`nav-item ${!caseId && chatId === c.id ? "active" : ""}`}
              key={c.id}
              onClick={() => navigate({ chat: c.id })}
            >
              <MessageSquare />
              <span>{c.title}</span>
              {c.status === "CLOSED" && <small>Closed</small>}
            </button>
          ))}
          <LoadMore {...chats} />
        </nav>
        <footer className="sidebar-footer">
          <button
            className={`nav-item ${view === "settings" ? "active" : ""}`}
            onClick={() => navigate({ view: "settings" })}
          >
            <Settings2 />
            <span>Settings</span>
          </button>
          <div className="flex gap-2 items-center px-2 py-3">
            <span className="user-avatar">
              {user.display_name
                .split(" ")
                .map((n) => n[0])
                .slice(0, 2)
                .join("")}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-xs truncate">{user.display_name}</p>
              <p className="text-[9px] text-muted-foreground mt-1 capitalize">
                {user.global_role.toLowerCase()}
              </p>
            </div>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Sign out"
              disabled={loggingOut}
              onClick={() => void logout()}
            >
              <LogOut size={14} />
            </Button>
          </div>
        </footer>
      </aside>
      <main className="main-workspace">
        <header className="topbar">
          <div className="breadcrumb">
            <Button
              className="mobile-menu-button"
              variant="ghost"
              size="icon-sm"
              aria-label="Open navigation"
              aria-controls="workspace-navigation"
              aria-expanded={mobile}
              onClick={() => setMobile(true)}
            >
              <Menu />
            </Button>
            <span className="desktop-label">
              {caseId ? "Cases" : "Workspace"}
            </span>
            <ChevronRight
              size={13}
              className="text-muted-foreground desktop-label"
            />
            <strong>{name}</strong>
            {selectedCase.data?.demo && (
              <span className="synthetic-label desktop-label">SYNTHETIC</span>
            )}
          </div>
          <div className="toolbar">
            <span className="status-pill desktop-label">
              <i />
              {health.data
                ? health.data.checks.harness?.message?.includes("deterministic")
                  ? "Deterministic mode"
                  : "Connected"
                : "Checking connection"}
            </span>
            {caseId && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => navigate({ case: caseId, view: "members" })}
              >
                <Users size={13} />
                <span className="desktop-label">Share case</span>
              </Button>
            )}
            {view === "chat" && (
              <Button
                size="icon-sm"
                variant={activity ? "secondary" : "ghost"}
                aria-label="Toggle agent activity"
                onClick={() => setActivity(!activity)}
              >
                <PanelRight size={16} />
              </Button>
            )}
          </div>
        </header>
        {caseId && selectedCase.data && (
          <div className="environment-bar">
            <span className="flex items-center gap-2">
              <ShieldCheck />
              {selectedCase.data.code} ·{" "}
              {selectedCase.data.my_role || user.global_role} ·{" "}
              {selectedCase.data.status}
            </span>
            <span>
              {selectedCase.data.source_policy.tor_enabled
                ? "Tor permitted by case policy"
                : "Surface & captured evidence"}
            </span>
          </div>
        )}
        <ErrorBanner error={error} />
        <div className="workspace-body">
          <div className="main-content">
            {view === "plugins" ? (
              <div className="case-content">
                <Plugins user={user} />
              </div>
            ) : view === "settings" ? (
              <div className="case-content">
                <Settings user={user} />
              </div>
            ) : caseId && selectedCase.isLoading ? (
              <Loading label="Opening case" />
            ) : selectedCase.error ? (
              <ErrorBanner
                error={selectedCase.error}
                retry={() => void selectedCase.refetch()}
              />
            ) : view !== "chat" && selectedCase.data ? (
              <div className="case-content">
                <CaseViews
                  key={`${caseId}-${view}`}
                  caseData={selectedCase.data}
                  user={user}
                  view={
                    caseViews.some(([id]) => id === view)
                      ? (view as CaseView)
                      : "overview"
                  }
                  onEvidence={setEvidenceId}
                />
              </div>
            ) : (
              <ChatWorkspace
                key={`${caseId || "private"}-${chatId || "new"}`}
                user={user}
                caseData={selectedCase.data}
                chatId={chatId}
                initialRunId={runId}
                showActivity={activity}
                onActivity={setActivity}
                onEvidence={setEvidenceId}
                onSelect={selectChat}
                onRun={(id) => {
                  const q = new URLSearchParams(params.toString());
                  q.set("run", id);
                  if (caseId) q.set("case", caseId);
                  router.replace("/?" + q, { scroll: false });
                }}
              />
            )}
          </div>
        </div>
      </main>
      {newCase && (
        <NewCase
          onClose={() => setNewCase(false)}
          onCreated={async (id) => {
            await client.invalidateQueries({ queryKey: ["api", "/cases"] });
            setNewCase(false);
            navigate({ case: id });
          }}
        />
      )}
      {evidenceId && selectedCase.data && (
        <EvidenceDetail
          key={evidenceId}
          caseId={selectedCase.data.id}
          user={user}
          caseData={selectedCase.data}
          evidenceId={evidenceId}
          onClose={() => setEvidenceId(undefined)}
        />
      )}
    </div>
  );
}
function LockIcon() {
  return <ShieldCheck size={11} />;
}
function NewCase({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (id: string) => Promise<void>;
}) {
  const [title, setTitle] = useState(""),
    [scope, setScope] = useState(""),
    [authority, setAuthority] = useState(""),
    [demo, setDemo] = useState(false),
    [error, setError] = useState<unknown>(),
    [busy, setBusy] = useState(false);
  return (
    <Modal
      open
      onClose={onClose}
      title="Open a new case"
      description="A shared space for evidence, conversations, monitoring, and findings."
    >
      <form
        className="content-stack"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            const c = await api<S<"Case">>("/cases", "POST", {
              title,
              scope_notes: scope || null,
              authority_ref: authority || null,
              demo,
            });
            await onCreated(c.id);
          } catch (reason) {
            setError(reason);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="Case title">
          <input
            required
            maxLength={300}
            placeholder="A clear name for the investigation"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <Field label="Scope notes">
          <textarea
            rows={3}
            placeholder="What are you investigating?"
            value={scope}
            onChange={(e) => setScope(e.target.value)}
          />
        </Field>
        <Field label="Authority reference">
          <input
            placeholder="Your authorisation reference"
            value={authority}
            onChange={(e) => setAuthority(e.target.value)}
          />
        </Field>
        <Field label="Case type">
          <select
            value={demo ? "synthetic" : "investigation"}
            onChange={(e) => setDemo(e.target.value === "synthetic")}
          >
            <option value="investigation">Investigation</option>
            <option value="synthetic">Synthetic / training</option>
          </select>
        </Field>
        <ErrorBanner error={error} />
        <Button disabled={busy}>
          {busy ? "Creating…" : "Create case"}
          <Plus size={15} />
        </Button>
      </form>
    </Modal>
  );
}

"use client";
import { useState } from "react";
import { useTheme } from "next-themes";
import { useQueryClient } from "@tanstack/react-query";
import {
  Plug,
  Wrench,
  Search,
  Monitor,
  Moon,
  Sun,
  RefreshCw,
  KeyRound,
} from "lucide-react";
import { api, useApi, usePaged } from "@/lib/api";
import type { S } from "@/lib/types";
import {
  Button,
  PanelHeader,
  ErrorBanner,
  Loading,
  LoadMore,
  Field,
  Modal,
  StatusBadge,
  EmptyState,
  date,
} from "./shared";

export function Plugins({ user }: { user: S<"UserMe"> }) {
  const plugins = usePaged<S<"Plugin">>("/plugins"),
    tools = usePaged<S<"ToolInfo">>("/tools"),
    client = useQueryClient();
  const [tab, setTab] = useState("plugins"),
    [search, setSearch] = useState(""),
    [filter, setFilter] = useState("all"),
    [pending, setPending] = useState<string>(),
    [error, setError] = useState<unknown>();
  const matches = (name: string, enabled: boolean) =>
    name.toLowerCase().includes(search.toLowerCase()) &&
    (filter === "all" || (filter === "enabled" ? enabled : !enabled));
  return (
    <>
      <PanelHeader
        title="Tools & integrations"
        description="Your agents choose from the tools available to the workspace and permitted by each case."
      />
      <div className="flex flex-wrap gap-3 mb-6">
        <div className="page-tabs !mb-0">
          {["plugins", "tools"].map((t) => (
            <Button
              key={t}
              size="sm"
              variant={tab === t ? "secondary" : "ghost"}
              onClick={() => setTab(t)}
            >
              {t === "plugins" ? <Plug size={14} /> : <Wrench size={14} />}
              {t === "plugins" ? "Integrations" : "Tool catalog"}
            </Button>
          ))}
        </div>
        <input
          className="!max-w-xs"
          aria-label="Search integrations and tools"
          placeholder="Search integrations and tools…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="!w-auto"
          aria-label="Availability filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">All states</option>
          <option value="enabled">Enabled</option>
          <option value="disabled">Disabled</option>
        </select>
      </div>
      <ErrorBanner error={error || plugins.error || tools.error} />
      {tab === "plugins" ? (
        <>
          {plugins.isLoading ? (
            <Loading />
          ) : (
            <div className="plugin-grid">
              {plugins.items
                .filter((p) => matches(p.id, p.enabled))
                .map((p) => (
                  <article key={p.id} className="panel-card plugin-card">
                    <div className="plugin-icon">
                      <Plug size={19} />
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <h3>{p.id.replaceAll("_", " ")}</h3>
                      <StatusBadge status={p.status} />
                    </div>
                    <p>
                      {p.tools.length} tools ·{" "}
                      {p.requires_network
                        ? "Network access"
                        : "Local processing"}
                    </p>
                    <p className="mt-3">
                      {p.unavailable_reason ||
                        (p.installed
                          ? "Bundled, reviewed integration. Case policy determines which tools may run."
                          : "Integration is not installed on this server.")}
                    </p>
                    <div className="flex flex-wrap gap-1 mt-3">
                      {p.tools.map((t) => (
                        <span key={t} className="status-pill">
                          {t}
                        </span>
                      ))}
                    </div>
                    <footer>
                      <span className="muted !text-[10px]">
                        {p.installation_kind}
                      </span>
                      {user.global_role === "ADMIN" ? (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={Boolean(pending)}
                          onClick={async () => {
                            setError(null);
                            setPending(p.id);
                            try {
                              await api(`/admin/plugins/${p.id}`, "PATCH", {
                                enabled: !p.enabled,
                                manifest_hash: p.manifest_hash,
                              });
                              await client.invalidateQueries({
                                predicate: (q) =>
                                  q.queryKey[0] === "api" &&
                                  /plugins|tools/.test(String(q.queryKey[1])),
                              });
                            } catch (reason) {
                              setError(reason);
                            } finally {
                              setPending(undefined);
                            }
                          }}
                        >
                          {pending === p.id
                            ? "Saving…"
                            : p.enabled
                              ? "Disable"
                              : "Enable"}
                        </Button>
                      ) : (
                        <span className="text-[10px]">
                          {p.enabled ? "Enabled" : "Disabled"}
                        </span>
                      )}
                    </footer>
                  </article>
                ))}
            </div>
          )}
          <LoadMore {...plugins} />
        </>
      ) : (
        <>
          {tools.isLoading ? (
            <Loading />
          ) : (
            <div className="space-y-3">
              {tools.items
                .filter((t) =>
                  matches(
                    `${t.name} ${t.display_name} ${t.description}`,
                    t.enabled,
                  ),
                )
                .map((t) => (
                  <details className="panel-card !p-4" key={t.name}>
                    <summary className="flex cursor-pointer items-center justify-between gap-4">
                      <div>
                        <h3 className="text-sm font-medium">
                          {t.display_name || t.name}
                        </h3>
                        <p className="text-[10px] text-muted-foreground mt-1">
                          {t.name} · {t.kind} ·{" "}
                          {(t.invocation_transports ?? []).join(", ") ||
                            "Internal"}
                        </p>
                      </div>
                      <StatusBadge
                        status={t.enabled ? t.health.status : "disabled"}
                      />
                    </summary>
                    <div className="mt-4 text-xs text-muted-foreground space-y-3">
                      <p>
                        {t.description ||
                          "No description supplied by the registry."}
                      </p>
                      {t.health.message && <p>{t.health.message}</p>}
                      <div className="flex flex-wrap gap-2">
                        <span className="status-pill">{t.lane}</span>
                        <span className="status-pill">
                          {t.requires_network ? "Requires network" : "Local"}
                        </span>
                        {t.policy_tags.map((p) => (
                          <span key={p} className="status-pill">
                            {p}
                          </span>
                        ))}
                      </div>
                      <p>
                        Permitted roles:{" "}
                        {(t.allowed_roles ?? []).join(", ") ||
                          "Determined by case policy"}
                        {t.rate_cap_per_hour != null
                          ? ` · ${t.rate_cap_per_hour} requests / hour`
                          : ""}
                      </p>
                    </div>
                  </details>
                ))}
            </div>
          )}
          <LoadMore {...tools} />
        </>
      )}
    </>
  );
}
export function Settings({ user }: { user: S<"UserMe"> }) {
  const { theme, setTheme } = useTheme(),
    health = useApi<S<"Health">>("/health/ready", 30000),
    config = useApi<S<"Settings">>(
      user.global_role === "ADMIN" ? "/admin/settings" : null,
    ),
    client = useQueryClient();
  const [edit, setEdit] = useState(false);
  return (
    <>
      <PanelHeader
        title="Workspace settings"
        description="Make this workspace yours. Check the services that power your investigations."
      />
      <div className="content-stack max-w-4xl">
        <section className="panel-card">
          <h2 className="font-medium mb-1">Appearance</h2>
          <p className="muted mb-5">Choose a theme that works for you.</p>
          <div className="flex gap-3">
            {[
              ["dark", "Dark", Moon],
              ["light", "Light", Sun],
              ["system", "System", Monitor],
            ].map(([id, label, Icon]) => {
              const I = Icon as typeof Moon;
              return (
                <Button
                  key={String(id)}
                  variant={theme === id ? "default" : "outline"}
                  onClick={() => setTheme(String(id))}
                >
                  <I size={15} />
                  {String(label)}
                </Button>
              );
            })}
          </div>
        </section>
        <section className="panel-card">
          <div className="flex justify-between mb-5">
            <div>
              <h2 className="font-medium">Service health</h2>
              <p className="muted mt-1">
                Availability is checked again when an agent starts a run.
              </p>
            </div>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Refresh service health"
              onClick={() => void health.refetch()}
            >
              <RefreshCw size={15} />
            </Button>
          </div>
          <ErrorBanner error={health.error} />
          {health.isLoading && <Loading />}
          {Object.entries(health.data?.checks ?? {}).map(([name, check]) => (
            <div
              className="flex justify-between gap-4 border-t py-3"
              key={name}
            >
              <div>
                <h3 className="text-xs capitalize">{name}</h3>
                {check.message && (
                  <p className="text-[11px] text-muted-foreground mt-1">
                    {check.message}
                  </p>
                )}
              </div>
              <StatusBadge status={check.status} />
            </div>
          ))}
        </section>
        <section className="panel-card">
          <div className="flex justify-between mb-3">
            <h2 className="font-medium">Models & execution</h2>
            {config.data && (
              <Button size="sm" variant="outline" onClick={() => setEdit(true)}>
                Edit defaults
              </Button>
            )}
          </div>
          <ErrorBanner error={config.error} />
          {config.data ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-8 gap-y-3 text-xs">
              <dt className="text-muted-foreground">Case lead</dt>
              <dd>{config.data.case_lead_model}</dd>
              <dt className="text-muted-foreground">Worker</dt>
              <dd>{config.data.worker_model}</dd>
              <dt className="text-muted-foreground">Local model</dt>
              <dd>{config.data.offline_model}</dd>
              <dt className="text-muted-foreground">Embeddings</dt>
              <dd>{config.data.embedding_model}</dd>
              <dt className="text-muted-foreground">Network</dt>
              <dd>
                {config.data.offline_mode
                  ? "Offline mode"
                  : "Allowed within case policy"}
              </dd>
            </dl>
          ) : (
            <p className="muted">
              Select a provider when you create a conversation. An administrator
              manages workspace model defaults.
            </p>
          )}
          <p className="text-[11px] text-muted-foreground mt-4 leading-relaxed">
            Claude, NVIDIA NIM, and local providers use the server’s configured
            endpoints and credentials. The selected runtime is shown on each
            conversation.
          </p>
        </section>
        <Tokens />
        <section className="panel-card">
          <h2 className="font-medium">Your account</h2>
          <p className="muted mt-2">
            {user.display_name} · {user.username} · {user.global_role}
          </p>
        </section>
      </div>
      {edit && config.data && (
        <ModelSettings
          data={config.data}
          onClose={() => setEdit(false)}
          onSave={async () => {
            await client.invalidateQueries({
              queryKey: ["api", "/admin/settings"],
            });
            await client.invalidateQueries({
              queryKey: ["api", "/health/ready"],
            });
            setEdit(false);
          }}
        />
      )}
    </>
  );
}
function ModelSettings({
  data,
  onClose,
  onSave,
}: {
  data: S<"Settings">;
  onClose: () => void;
  onSave: () => Promise<void>;
}) {
  const [form, setForm] = useState({
      case_lead_model: data.case_lead_model,
      worker_model: data.worker_model,
      offline_model: data.offline_model,
      offline_mode: data.offline_mode,
      demo_mode: data.demo_mode,
    }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>();
  return (
    <Modal
      open
      onClose={onClose}
      title="Model defaults"
      description="Changes affect new runs throughout this workspace."
    >
      <form
        className="content-stack"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await api("/admin/settings", "PATCH", form);
            await onSave();
          } catch (reason) {
            setError(reason);
          } finally {
            setBusy(false);
          }
        }}
      >
        {(["case_lead_model", "worker_model", "offline_model"] as const).map(
          (key) => (
            <Field key={key} label={key.replaceAll("_", " ")}>
              <input
                value={form[key]}
                maxLength={200}
                required
                onChange={(e) => setForm({ ...form, [key]: e.target.value })}
              />
            </Field>
          ),
        )}
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={form.offline_mode}
            onChange={(e) =>
              setForm({ ...form, offline_mode: e.target.checked })
            }
          />
          Offline mode
        </label>
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={form.demo_mode}
            onChange={(e) => setForm({ ...form, demo_mode: e.target.checked })}
          />
          Demo mode
        </label>
        <ErrorBanner error={error} />
        <Button disabled={busy}>Save defaults</Button>
      </form>
    </Modal>
  );
}
function Tokens() {
  const tokens = usePaged<S<"TokenInfo">>("/auth/tokens"),
    client = useQueryClient();
  const [open, setOpen] = useState(false),
    [created, setCreated] = useState<string>(),
    [name, setName] = useState(""),
    [days, setDays] = useState("30"),
    [caseId, setCaseId] = useState(""),
    [scopes, setScopes] = useState<string[]>(["cases:read"]),
    [error, setError] = useState<unknown>(),
    [busy, setBusy] = useState(false);
  return (
    <section className="panel-card">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-medium">API access tokens</h2>
        <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
          <KeyRound size={14} />
          Create token
        </Button>
      </div>
      <ErrorBanner error={error || tokens.error} />
      {tokens.items.map((t) => (
        <div
          key={t.id}
          className="flex items-center justify-between gap-3 py-3 border-t"
        >
          <div>
            <p className="text-xs">{t.name}</p>
            <p className="text-[10px] text-muted-foreground mt-1">
              {t.scopes.join(" · ")} · Expires {date(t.expires_at)}
            </p>
          </div>
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await api(`/auth/tokens/${t.id}`, "DELETE");
                await client.invalidateQueries({
                  queryKey: ["api", "/auth/tokens"],
                });
              } catch (reason) {
                setError(reason);
              } finally {
                setBusy(false);
              }
            }}
          >
            Revoke
          </Button>
        </div>
      ))}
      <LoadMore {...tokens} />
      <Modal
        open={open}
        onClose={() => {
          setOpen(false);
          setCreated(undefined);
        }}
        title="Create API token"
        description="The token is displayed once. Keep it in your secret store."
      >
        {created ? (
          <div className="space-y-3">
            <p className="text-xs">Copy this token before closing.</p>
            <textarea
              aria-label="New API token"
              readOnly
              value={created}
              rows={4}
            />
            <Button
              onClick={() => {
                setOpen(false);
                setCreated(undefined);
              }}
            >
              Done
            </Button>
          </div>
        ) : (
          <form
            className="content-stack"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError(null);
              try {
                const t = await api<S<"TokenCreated">>("/auth/tokens", "POST", {
                  name,
                  scopes,
                  case_id: caseId || null,
                  expires_in_days: Number(days),
                });
                setCreated(t.token);
                await client.invalidateQueries({
                  queryKey: ["api", "/auth/tokens"],
                });
              } catch (reason) {
                setError(reason);
              } finally {
                setBusy(false);
              }
            }}
          >
            <Field label="Name">
              <input
                value={name}
                maxLength={200}
                required
                onChange={(e) => setName(e.target.value)}
              />
            </Field>
            <Field label="Case ID (optional)">
              <input
                value={caseId}
                onChange={(e) => setCaseId(e.target.value)}
                placeholder="Restrict to one case UUID"
              />
            </Field>
            <Field label="Expires in days">
              <input
                type="number"
                min="1"
                max="365"
                required
                value={days}
                onChange={(e) => setDays(e.target.value)}
              />
            </Field>
            <fieldset className="space-y-2">
              <legend className="text-xs mb-2">Scopes</legend>
              {[
                "cases:read",
                "evidence:write",
                "threads:run",
                "alerts:read",
                "alerts:handle",
                "monitor:run",
                "reports:generate",
              ].map((s) => (
                <label className="flex items-center gap-2 text-xs" key={s}>
                  <input
                    type="checkbox"
                    checked={scopes.includes(s)}
                    onChange={(e) =>
                      setScopes(
                        e.target.checked
                          ? [...scopes, s]
                          : scopes.filter((v) => v !== s),
                      )
                    }
                  />
                  {s}
                </label>
              ))}
            </fieldset>
            <ErrorBanner error={error} />
            <Button disabled={busy || !scopes.length}>Create token</Button>
          </form>
        )}
      </Modal>
    </section>
  );
}

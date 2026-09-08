"use client";

import { useState, type FormEvent } from "react";
import {
  BookOpenCheck,
  Plus,
  Settings2,
  Shield,
  Trash2,
  UserRoundCog,
  Users,
} from "lucide-react";
import { can } from "@/lib/permissions";
import { useApi, usePaged } from "@/lib/api";
import type { S } from "@/lib/types";
import {
  Button,
  EmptyState,
  ErrorBanner,
  Field,
  LoadMore,
  Loading,
  PanelHeader,
  StatusBadge,
  date,
} from "./shared";
import {
  CASE_ROLES,
  FormFeedback,
  SOURCE_CLASSES,
  humanize,
  splitList,
  useCaseAction,
} from "./case-forms";

type ViewProps = { caseData: S<"Case">; user: S<"UserMe"> };

export function MembersView({ caseData, user }: ViewProps) {
  const members = useApi<S<"CaseMember">[]>(`/cases/${caseData.id}/members`);
  const action = useCaseAction(caseData.id);
  const manageable =
    can(user, caseData, "manage") && caseData.status === "OPEN";
  const policy = caseData.source_policy;
  const [allowedSources, setAllowedSources] = useState<string[]>(
    policy.allowed_source_classes,
  );
  const [pluginMode, setPluginMode] = useState<"inherit" | "none" | "list">(
    policy.enabled_plugins == null
      ? "inherit"
      : policy.enabled_plugins.length
        ? "list"
        : "none",
  );
  const [pluginList, setPluginList] = useState(
    policy.enabled_plugins?.join(", ") ?? "",
  );

  async function addMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const result = await action.run<S<"CaseMember">>(
      `/cases/${caseData.id}/members`,
      "POST",
      {
        user_id: String(data.get("user_id")),
        role: String(data.get("role")) as S<"MemberCreate">["role"],
      } satisfies S<"MemberCreate">,
      "Member added",
    );
    if (result) form.reset();
  }

  async function changeMember(userId: string, role: S<"MemberPatch">["role"]) {
    await action.run<S<"CaseMember">>(
      `/cases/${caseData.id}/members/${userId}`,
      "PATCH",
      { role } satisfies S<"MemberPatch">,
      "Member role updated",
    );
  }

  async function removeMember(userId: string) {
    await action.run<void>(
      `/cases/${caseData.id}/members/${userId}`,
      "DELETE",
      undefined,
      "Member removed",
    );
  }

  function toggleSource(source: string) {
    setAllowedSources((current) =>
      current.includes(source)
        ? current.filter((item) => item !== source)
        : [...current, source],
    );
  }

  async function savePolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const number = (name: string) => Number(data.get(name));
    const retention = String(data.get("retention_days") ?? "").trim();
    const sourcePolicy: S<"SourcePolicy"> = {
      allowed_source_classes:
        allowedSources as S<"SourcePolicy">["allowed_source_classes"],
      tor_enabled: data.get("tor_enabled") === "on",
      person_lookup_enabled: data.get("person_lookup_enabled") === "on",
      telegram_enabled: data.get("telegram_enabled") === "on",
      max_requests_per_hour: {
        surface: number("surface"),
        dark: number("dark"),
        chain: number("chain"),
        identity: number("identity"),
        telegram: number("telegram"),
      },
      retention_days: retention ? Number(retention) : null,
      enabled_plugins:
        pluginMode === "inherit"
          ? null
          : pluginMode === "none"
            ? []
            : splitList(pluginList),
    };
    await action.run<S<"Case">>(
      `/cases/${caseData.id}`,
      "PATCH",
      { source_policy: sourcePolicy } satisfies S<"CasePatch">,
      "Case policy updated",
    );
  }

  return (
    <div className="content-stack">
      <PanelHeader
        title="Members & policy"
        description="Case membership, collection boundaries, rate caps, and reviewed plugin scope."
      />
      <FormFeedback
        busy={action.busy}
        error={action.error}
        message={action.message}
      />
      <section className="panel-card">
        <h2 className="flex items-center gap-2">
          <Users size={17} />
          Case members
        </h2>
        <ErrorBanner
          error={members.error}
          retry={() => void members.refetch()}
        />
        {members.isLoading ? (
          <Loading label="Loading members" />
        ) : members.data?.length ? (
          <div className="table-wrap mt-4">
            <table className="data-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Role</th>
                  <th>Added</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {members.data.map((member) => (
                  <tr key={member.user.id ?? member.user.display}>
                    <td>
                      <strong>{member.user.display}</strong>
                      <span className="muted block font-mono text-xs">
                        {member.user.id ?? "System actor"}
                      </span>
                    </td>
                    <td>
                      {manageable && member.user.id ? (
                        <select
                          aria-label={`Role for ${member.user.display}`}
                          value={member.role}
                          onChange={(event) =>
                            void changeMember(
                              member.user.id!,
                              event.target.value as S<"MemberPatch">["role"],
                            )
                          }
                        >
                          {CASE_ROLES.map((role) => (
                            <option key={role}>{role}</option>
                          ))}
                        </select>
                      ) : (
                        <StatusBadge status={member.role} />
                      )}
                    </td>
                    <td>{date(member.added_at)}</td>
                    <td>
                      {manageable && member.user.id ? (
                        <Button
                          size="icon"
                          variant="ghost"
                          aria-label={`Remove ${member.user.display}`}
                          onClick={() => void removeMember(member.user.id!)}
                        >
                          <Trash2 size={14} />
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No members returned"
            description="The case currently has no visible membership records."
            icon={<Users size={23} />}
          />
        )}
        {manageable ? (
          <form
            className="mt-5 grid gap-3 border-t border-border pt-5 md:grid-cols-[1fr_180px_auto]"
            onSubmit={(event) => void addMember(event)}
          >
            <Field label="Exact user UUID">
              <input
                required
                name="user_id"
                type="text"
                pattern="[0-9a-fA-F-]{36}"
                placeholder="00000000-0000-0000-0000-000000000000"
              />
            </Field>
            <Field label="Case role">
              <select name="role" defaultValue="ANALYST">
                {CASE_ROLES.map((role) => (
                  <option key={role}>{role}</option>
                ))}
              </select>
            </Field>
            <Button type="submit" className="self-end" disabled={action.busy}>
              <Plus size={14} />
              Add member
            </Button>
          </form>
        ) : null}
      </section>

      <section className="panel-card">
        <h2 className="flex items-center gap-2">
          <Settings2 size={17} />
          Case source policy
        </h2>
        <p className="muted mt-2 text-sm">
          Policy changes preserve every backend field and are audited.
        </p>
        <form
          className="mt-5 content-stack"
          onSubmit={(event) => void savePolicy(event)}
        >
          <fieldset disabled={!manageable}>
            <legend className="mb-2 text-sm font-medium">
              Allowed source classes
            </legend>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {SOURCE_CLASSES.map((source) => (
                <label className="flex items-center gap-2 text-sm" key={source}>
                  <input
                    type="checkbox"
                    checked={allowedSources.includes(source)}
                    onChange={() => toggleSource(source)}
                  />
                  {humanize(source)}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="grid gap-3 md:grid-cols-3">
            <label className="flex items-center gap-2 text-sm">
              <input
                disabled={!manageable}
                defaultChecked={policy.tor_enabled}
                name="tor_enabled"
                type="checkbox"
              />
              Tor collector enabled
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                disabled={!manageable}
                defaultChecked={policy.person_lookup_enabled}
                name="person_lookup_enabled"
                type="checkbox"
              />
              Person lookup enabled
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                disabled={!manageable}
                defaultChecked={policy.telegram_enabled}
                name="telegram_enabled"
                type="checkbox"
              />
              Telegram enabled
            </label>
          </div>
          <div>
            <h3 className="mb-3 text-sm font-medium">Hourly request caps</h3>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {(
                ["surface", "dark", "chain", "identity", "telegram"] as const
              ).map((lane) => (
                <Field key={lane} label={humanize(lane)}>
                  <input
                    disabled={!manageable}
                    required
                    min={0}
                    type="number"
                    name={lane}
                    defaultValue={policy.max_requests_per_hour[lane]}
                  />
                </Field>
              ))}
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <Field
              label="Retention days"
              hint="Blank means no scheduled retention expiry."
            >
              <input
                disabled={!manageable}
                min={1}
                type="number"
                name="retention_days"
                defaultValue={policy.retention_days ?? ""}
              />
            </Field>
            <Field
              label="Enabled plugins"
              hint="Inherit uses the backend-reviewed default; none sends an explicit empty list."
            >
              <select
                disabled={!manageable}
                value={pluginMode}
                onChange={(event) =>
                  setPluginMode(event.target.value as typeof pluginMode)
                }
              >
                <option value="inherit">
                  Inherit reviewed defaults (null)
                </option>
                <option value="none">None (empty list)</option>
                <option value="list">Selected plugin IDs</option>
              </select>
            </Field>
          </div>
          {pluginMode === "list" ? (
            <Field
              label="Reviewed plugin IDs"
              hint="Comma- or line-separated exact catalog IDs."
            >
              <textarea
                disabled={!manageable}
                value={pluginList}
                onChange={(event) => setPluginList(event.target.value)}
                rows={3}
              />
            </Field>
          ) : null}
          {manageable ? (
            <Button
              className="self-start"
              disabled={action.busy || allowedSources.length === 0}
              type="submit"
            >
              <Shield size={15} />
              Save policy
            </Button>
          ) : (
            <p className="muted text-sm">
              Owner or lead access is required to edit this policy.
            </p>
          )}
        </form>
      </section>
    </div>
  );
}

function auditDetail(event: S<"AuditEvent">) {
  const detail = event.detail;
  if (typeof detail.rationale === "string") return detail.rationale;
  if (typeof detail.reason === "string") return detail.reason;
  if (
    Array.isArray(detail.fields) &&
    detail.fields.every((value) => typeof value === "string")
  )
    return `Fields: ${detail.fields.join(", ")}`;
  if (typeof detail.format === "string") return `Format: ${detail.format}`;
  return null;
}

export function AuditView({ caseData }: ViewProps) {
  const [actionFilter, setActionFilter] = useState("");
  const audit = usePaged<S<"AuditEvent">>(
    `/cases/${caseData.id}/audit${actionFilter ? `?action=${encodeURIComponent(actionFilter)}` : ""}`,
  );
  return (
    <div className="content-stack">
      <PanelHeader
        title="Case audit"
        description="Append-only activity for this case. Access is enforced by the audit role."
      />
      <section className="panel-card">
        <div className="max-w-md">
          <Field label="Exact action">
            <input
              value={actionFilter}
              onChange={(event) => setActionFilter(event.target.value)}
              placeholder="evidence.verify"
            />
          </Field>
        </div>
        <ErrorBanner error={audit.error} retry={() => void audit.refetch()} />
        {audit.isLoading ? (
          <Loading label="Loading audit events" />
        ) : audit.items.length ? (
          <div className="mt-5 space-y-3">
            {audit.items.map((event) => (
              <article
                className="rounded-xl border border-border p-4"
                key={event.id}
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <BookOpenCheck size={15} />
                    <strong className="text-sm">{event.action}</strong>
                  </div>
                  <span className="muted text-xs">{date(event.at)}</span>
                </div>
                <p className="muted mt-2 text-sm">
                  {event.actor.display}
                  {event.target_type ? ` · ${humanize(event.target_type)}` : ""}
                  {event.target_id ? ` · ${event.target_id}` : ""}
                </p>
                {auditDetail(event) ? (
                  <p className="mt-2 text-sm">{auditDetail(event)}</p>
                ) : null}
                <div className="muted mt-3 flex flex-wrap gap-3 font-mono text-xs">
                  {event.request_id ? (
                    <span>request {event.request_id}</span>
                  ) : null}
                  {event.result_hash ? (
                    <span className="break-all">hash {event.result_hash}</span>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="No audit events found"
            description="No events match this action filter, or your role cannot view the case audit."
            icon={<UserRoundCog size={23} />}
          />
        )}
        <LoadMore {...audit} />
      </section>
    </div>
  );
}

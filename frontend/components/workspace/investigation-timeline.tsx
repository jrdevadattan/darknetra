"use client";
import { useMemo, useState } from "react";
import {
  CircleAlert,
  List,
  LoaderCircle,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import type { ChatMessage } from "@/lib/chat-types";
import {
  activityPresentation,
  matchesActivity,
  type ActivityFilter,
} from "@/lib/activity-presentation";
import { ActivitySteps, SpecialistAgents, type SourceOptions } from "./agents";

export function InvestigationTimeline({
  message,
  ...options
}: { message: ChatMessage } & SourceOptions) {
  const [filter, setFilter] = useState<ActivityFilter>("all");
  const [query, setQuery] = useState("");
  const allSteps = useMemo(
    () => [
      ...message.activity,
      ...(message.agents || []).flatMap((agent) => agent.activity || []),
    ],
    [message],
  );
  const counts = { all: allSteps.length, working: 0, attention: 0 };
  for (const step of allSteps) {
    const state = activityPresentation(step).state;
    if (state === "working" || state === "attention") counts[state]++;
  }
  const lead = message.activity.filter((step) =>
    matchesActivity(step, filter, query, "Lead Investigator"),
  );
  const specialists = (message.agents || []).flatMap((agent) => {
    const activity = (agent.activity || []).filter((step) =>
      matchesActivity(step, filter, query, agent.name),
    );
    const noActions =
      !agent.activity?.length &&
      (filter === "all" ||
        (filter === "working" &&
          ["pending", "running"].includes(agent.status)) ||
        (filter === "attention" &&
          ["error", "unverified", "stopped"].includes(agent.status))) &&
      `${agent.name} ${agent.task}`
        .toLowerCase()
        .includes(query.trim().toLowerCase());
    return activity.length || noActions ? [{ ...agent, activity }] : [];
  });
  const shown =
    lead.length +
    specialists.reduce((sum, agent) => sum + (agent.activity?.length || 0), 0);
  const filtered = filter !== "all" || !!query.trim();
  return (
    <div className="investigation-timeline">
      <div className="timeline-toolbar">
        <div
          className="timeline-filter-group"
          role="group"
          aria-label="Filter activity"
        >
          {(
            [
              ["all", "All activity", List],
              ["working", "Working", LoaderCircle],
              ["attention", "Needs attention", CircleAlert],
            ] as const
          ).map(([id, label, Icon]) => (
            <button
              type="button"
              key={id}
              aria-pressed={filter === id}
              onClick={() => setFilter(id)}
            >
              <Icon size={13} />
              <span>{label}</span>
              <small>{counts[id]}</small>
            </button>
          ))}
        </div>
        <div className="timeline-search">
          <Search size={15} />
          <input
            aria-label="Search activity"
            placeholder="Search steps, websites or investigators…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {query && (
            <button
              type="button"
              className="icon-button"
              aria-label="Clear activity search"
              onClick={() => setQuery("")}
            >
              <X size={14} />
            </button>
          )}
        </div>
        <div className="timeline-section-caption">
          <span>
            {filtered
              ? `${shown} of ${counts.all} steps`
              : `${counts.all} recorded steps`}
          </span>
          <span>
            {message.agents?.length || 0} specialist
            {message.agents?.length === 1 ? "" : "s"}
          </span>
        </div>
      </div>
      {!!lead.length && (
        <section
          className="lead-timeline"
          aria-label="Lead investigator activity"
        >
          <h3>
            <ShieldCheck size={14} />
            Lead investigator<span>{lead.length}</span>
          </h3>
          <ActivitySteps
            steps={lead}
            limited={message.historyLimited}
            {...options}
          />
        </section>
      )}
      <SpecialistAgents agents={specialists} timeline {...options} />
      {!lead.length && !specialists.length && (
        <div className="timeline-empty-state">
          <Search size={24} />
          <strong>
            {filtered
              ? "No matching activity"
              : message.status === "running"
                ? "The investigation is getting started"
                : "No recorded activity"}
          </strong>
          <p>
            {filtered
              ? "Try another website, investigator or status."
              : message.status === "running"
                ? "Recorded checks and investigator updates will appear here."
                : "No individual steps were saved for this reply. You can still read its report in Output."}
          </p>
          {filtered && (
            <button
              type="button"
              onClick={() => {
                setFilter("all");
                setQuery("");
              }}
            >
              Show all activity
            </button>
          )}
        </div>
      )}
    </div>
  );
}

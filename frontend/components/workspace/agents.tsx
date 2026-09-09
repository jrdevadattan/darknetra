"use client";
import { useLanguage } from "./language";
import { useState } from "react";
import {
  Check,
  ChevronDown,
  CircleAlert,
  LoaderCircle,
  ShieldCheck,
  Square,
  ArrowUpRight,
  Clock3,
  Terminal,
} from "lucide-react";
import { activityPresentation } from "@/lib/activity-presentation";
import type {
  Activity,
  ChatAttachment,
  SpecialistAgent,
} from "@/lib/chat-types";
import {
  ActionIcon,
  CaseMarkdown,
  InvestigatorIcon,
  SiteIcon,
  SourceCard,
} from "./source-ui";

const labels: Record<string, string> = {
  pending: "Starting",
  running: "Working",
  in_progress: "Working",
  completed: "Completed",
  done: "Completed",
  error: "Failed",
  failed: "Failed",
  stopped: "Stopped",
  unverified: "Unverified",
};
export type SourceOptions = {
  chatId?: string;
  files?: ChatAttachment[];
  onInspectSource?: (id: string) => void;
};
export function ActivitySteps({
  steps,
  limited,
  ...options
}: { steps: Activity[]; limited?: boolean } & SourceOptions) {
  return (
    <>
      {limited && (
        <p className="activity-empty">
          Earlier activity is outside the retained history window.
        </p>
      )}
      <ol className="run-timeline">
        {steps.map((step) => (
          <TimelineStep key={step.id} step={step} {...options} />
        ))}
      </ol>
    </>
  );
}
function TimelineStep({
  step,
  ...options
}: { step: Activity } & SourceOptions) {
  const { t } = useLanguage();
  const view = activityPresentation(step);
  const [open, setOpen] = useState(
    step.kind === "update" || view.state === "working",
  );
  return (
    <li data-activity-id={step.id} className={`timeline-step is-${view.state}`}>
      <span className="timeline-marker">
        {view.url ? (
          <SiteIcon url={view.url} favicon={view.source?.favicon} size={16} />
        ) : (
          <ActionIcon label={view.title} size={17} />
        )}
      </span>
      <details
        className="timeline-entry"
        open={open}
        onToggle={(event) => setOpen(event.currentTarget.open)}
      >
        <summary className="timeline-heading">
          <span className="timeline-title">
            <strong>{view.title}</strong>
            {view.subtitle && (
              <span className="timeline-preview" title={view.subtitle}>
                {view.subtitle}
              </span>
            )}
            <span className="timeline-caption">
              {view.at && (
                <time dateTime={view.at}>
                  {new Date(view.at).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </time>
              )}
              {view.duration && (
                <span>
                  <Clock3 size={11} />
                  {view.duration}
                </span>
              )}
              {!!step.sources?.length && (
                <span>
                  {step.sources.length} source
                  {step.sources.length === 1 ? "" : "s"}
                </span>
              )}
            </span>
          </span>
          <span className="timeline-row-meta">
            <span className={`step-status ${view.state}`}>
              {view.state === "working" ? (
                <LoaderCircle size={12} className="spin" />
              ) : view.state === "attention" ? (
                <CircleAlert size={12} />
              ) : view.state === "complete" ? (
                <Check size={12} />
              ) : (
                <Clock3 size={12} />
              )}
              {t(view.status)}
            </span>
            <ChevronDown size={14} />
          </span>
        </summary>
        {open && (
          <div className="timeline-body">
            {view.url &&
              !step.sources?.some((source) => source.url === view.url) && (
                <a
                  className="active-website"
                  href={view.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <SiteIcon url={view.url} size={12} />
                  <span>{view.url}</span>
                  <ArrowUpRight size={14} />
                </a>
              )}
            {step.detail && !view.technical && (
              <div className="activity-detail">
                <CaseMarkdown
                  chatId={options.chatId}
                  files={options.files}
                  sources={step.sources}
                >
                  {step.detail}
                </CaseMarkdown>
              </div>
            )}
            {step.result && <p className="timeline-result">{step.result}</p>}
            {!!step.sources?.length && (
              <div className="timeline-sources">
                {step.sources.map((source) => (
                  <SourceCard
                    key={source.id}
                    source={source}
                    onInspect={options.onInspectSource}
                    chatId={options.chatId}
                    files={options.files}
                  />
                ))}
              </div>
            )}
            {view.technical && (
              <details className="activity-technical">
                <summary>
                  <Terminal size={13} />
                  Technical details
                  <ChevronDown size={12} />
                </summary>
                <pre>{step.detail}</pre>
              </details>
            )}
            {!step.detail && !step.result && !step.sources?.length && (
              <p>
                {view.state === "working"
                  ? "Updates will appear here as the check progresses."
                  : "No additional details were recorded for this step."}
              </p>
            )}
          </div>
        )}
      </details>
    </li>
  );
}
function SpecialistCard({
  agent,
  timeline,
  ...options
}: { agent: SpecialistAgent; timeline: boolean } & SourceOptions) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(true);
  return (
    <article className="specialist-card" data-agent-id={agent.id}>
      <header>
        <button
          type="button"
          className="specialist-toggle"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          <span className="investigator-icon">
            <InvestigatorIcon name={agent.role || agent.name} />
          </span>
          <span className="specialist-identity">
            <strong>{agent.name}</strong>
            <small>{agent.activity?.length || 0} steps</small>
          </span>
          <span className={`agent-status ${agent.status}`}>
            {["pending", "running"].includes(agent.status) ? (
              <LoaderCircle size={12} className="spin" />
            ) : agent.status === "completed" ? (
              <Check size={12} />
            ) : agent.status === "stopped" ? (
              <Square size={12} />
            ) : (
              <CircleAlert size={12} />
            )}{" "}
            {t(labels[agent.status])}
          </span>
          <ChevronDown size={14} className={open ? "" : "collapsed"} />
        </button>
      </header>
      {open && (
        <div className="specialist-body">
          {agent.task && <p className="agent-assignment">{agent.task}</p>}
          {timeline && (
            <ActivitySteps
              steps={agent.activity || []}
              limited={agent.historyLimited}
              {...options}
            />
          )}
          {timeline && !agent.activity?.length && (
            <p className="activity-empty">
              {["running", "pending"].includes(agent.status)
                ? "Waiting for the first recorded action…"
                : "No separate tool actions were recorded."}
            </p>
          )}
          {agent.result && (
            <details className="specialist-report">
              <summary>
                <ActionIcon label="Reading an attached file" size={14} />
                View specialist report
              </summary>
              <div className="agent-result">
                <CaseMarkdown
                  chatId={options.chatId}
                  files={options.files}
                  sources={agent.activity?.flatMap((a) => a.sources || [])}
                >
                  {agent.result}
                </CaseMarkdown>
              </div>
            </details>
          )}
          {agent.status === "unverified" && (
            <small>Completion was not confirmed.</small>
          )}
        </div>
      )}
    </article>
  );
}
export function SpecialistAgents({
  agents,
  timeline = false,
  ...options
}: { agents?: SpecialistAgent[]; timeline?: boolean } & SourceOptions) {
  if (!agents?.length) return null;
  return (
    <section className="specialist-agents" aria-label="Case specialists">
      <h3>
        <ShieldCheck size={15} />
        Case specialists
      </h3>
      {agents.map((agent) => (
        <SpecialistCard
          key={agent.id}
          agent={agent}
          timeline={timeline}
          {...options}
        />
      ))}
    </section>
  );
}

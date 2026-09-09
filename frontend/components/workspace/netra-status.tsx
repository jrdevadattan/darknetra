"use client";
import { Eye, Check, CircleAlert, LoaderCircle, Pause } from "lucide-react";
import type { NetraGoal } from "@/lib/chat-types";

const labels: Record<NetraGoal["status"], string> = {
  starting: "Preparing the review",
  active: "Investigation in progress",
  complete: "Scoped review complete",
  blocked: "Needs more information",
  paused: "Review stopped",
  limit_reached: "Review limit reached",
  unavailable: "Goal not confirmed",
};

export function NetraStatus({ goal }: { goal: NetraGoal }) {
  const active = ["starting", "active"].includes(goal.status);
  const Icon = active
    ? LoaderCircle
    : goal.status === "complete"
      ? Check
      : goal.status === "paused"
        ? Pause
        : CircleAlert;
  return (
    <section
      className={`netra-status ${goal.status}`}
      aria-label="Netra investigation"
      aria-live="polite"
    >
      <span className="netra-mark">
        <Eye size={19} />
      </span>
      <div className="netra-status-copy">
        <strong>
          Netra <span>Pass {goal.turns}</span>
        </strong>
        <p>
          <Icon size={13} className={active ? "spin" : ""} />
          {labels[goal.status]}
        </p>
        {goal.objective && (
          <details>
            <summary>Investigation objective</summary>
            <p>{goal.objective}</p>
          </details>
        )}
        {["limit_reached", "unavailable", "paused", "blocked"].includes(
          goal.status,
        ) && (
          <small>
            Review the available findings and unresolved checks before
            continuing.
          </small>
        )}
      </div>
    </section>
  );
}

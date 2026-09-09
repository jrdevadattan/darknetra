import { open, readdir, type FileHandle } from "node:fs/promises";
import { homedir } from "node:os";
import path from "node:path";
import type { ChatMessage, SpecialistAgent } from "./chat-types";
import {
  commandLabel,
  commandTarget,
  helperResult,
  publicUpdate,
  recordActivity,
} from "./run-activity";

export type CollaborationItem = {
  tool?: string;
  prompt?: string;
  receiver_thread_ids?: string[];
  agents_states?: Record<string, { status: string; message?: string | null }>;
};

export function updateAgents(message: ChatMessage, item: CollaborationItem) {
  const ids = new Set([
    ...(item.receiver_thread_ids || []),
    ...Object.keys(item.agents_states || {}),
  ]);
  if (!ids.size) return;
  message.agents ||= [];
  for (const id of ids) {
    let agent = message.agents.find((entry) => entry.id === id);
    if (!agent) {
      agent = { id, name: "Case Specialist", task: "", status: "pending" };
      message.agents.push(agent);
    }
    if (item.prompt && ["spawn_agent", "send_input"].includes(item.tool || ""))
      agent.task = item.prompt.slice(0, 2000);
    const state = item.agents_states?.[id];
    if (state) {
      const status: Record<string, SpecialistAgent["status"]> = {
        pending_init: "pending",
        running: "running",
        completed: "completed",
        errored: "error",
        interrupted: "stopped",
        shutdown: "stopped",
        not_found: "unverified",
      };
      // Closing an already completed specialist does not erase the result.
      if (!(
        state.status === "shutdown" &&
        ["completed", "error"].includes(agent.status)
      ))
        agent.status = status[state.status] || "unverified";
      if (state.message) agent.result = state.message.slice(0, 16000);
    }
  }
}

export function settleAgents(message: ChatMessage) {
  for (const agent of message.agents || [])
    if (["pending", "running"].includes(agent.status))
      agent.status = message.status === "stopped" ? "stopped" : "unverified";
  for (const step of [
    message.activity,
    ...(message.agents || []).map((a) => a.activity || []),
  ].flat()) {
    if (["running", "in_progress"].includes(step.status)) {
      step.status = message.status === "stopped" ? "stopped" : "unverified";
      step.finishedAt ||= new Date().toISOString();
    }
  }
}

export function agentIdentity(record: unknown, id: string, parent: string) {
  const meta = record as {
    type?: string;
    payload?: {
      id?: string;
      parent_thread_id?: string;
      agent_nickname?: string;
      agent_role?: string;
      source?: {
        subagent?: {
          thread_spawn?: {
            parent_thread_id?: string;
            agent_nickname?: string;
            agent_role?: string;
          };
        };
      };
    };
  };
  const p = meta?.payload;
  const spawn = p?.source?.subagent?.thread_spawn;
  if (
    meta?.type !== "session_meta" ||
    p?.id !== id ||
    (p.parent_thread_id || spawn?.parent_thread_id) !== parent
  )
    return;
  const name = p.agent_nickname || spawn?.agent_nickname;
  if (typeof name !== "string" || !name.trim()) return;
  return {
    name: name.slice(0, 100),
    role: (p.agent_role || spawn?.agent_role)?.slice(0, 100),
  };
}

export function applyAgentRecords(
  message: ChatMessage,
  id: string,
  metadata: { timestamp?: string; agent_path?: string },
  records: unknown[],
) {
  const threshold = Math.max(
    Date.parse(message.at) - 1000,
    Date.parse(metadata.timestamp || message.at) - 1000,
  );
  let turn: string | undefined;
  for (const record of records) {
    const row = record as {
      type?: string;
      timestamp?: string;
      payload?: {
        type?: string;
        thread_id?: string;
        turn_id?: string;
        started_at?: number;
        started_at_ms?: number;
        completed_at_ms?: number;
        last_agent_message?: string;
        error?: unknown;
        item?: {
          type?: string;
          id?: string;
          command?: string[];
          status?: string;
          aggregated_output?: string;
          exit_code?: number;
          phase?: string;
          content?: { type?: string; text?: string }[];
          query?: string;
        };
      };
    };
    if (row.type !== "event_msg" || !row.payload) continue;
    const event = row.payload;
    if (event.type === "task_started") {
      // Forked sessions include the parent's older history; only this child's
      // own current turn is eligible to update the card.
      if (!event.started_at || event.started_at * 1000 < threshold) {
        turn = undefined;
        continue;
      }
      turn = event.turn_id;
      updateAgents(message, { agents_states: { [id]: { status: "running" } } });
      const agent = message.agents!.find((a) => a.id === id)!;
      agent.at ||= new Date(event.started_at * 1000).toISOString();
    }
    const item = event.item;
    // Exact child identity also permits bounded-tail reads when task_started
    // has fallen outside the window. Forked parent items can never pass this.
    if (
      item &&
      event.thread_id === id &&
      Date.parse(row.timestamp || "") >= threshold &&
      ["item_started", "item_completed"].includes(event.type || "")
    ) {
      let agent = message.agents?.find((a) => a.id === id);
      if (!agent) {
        updateAgents(message, {
          agents_states: { [id]: { status: "running" } },
        });
        agent = message.agents!.find((a) => a.id === id)!;
      }
      agent.activity ||= [];
      const at = event.started_at_ms
        ? new Date(event.started_at_ms).toISOString()
        : row.timestamp!;
      const completed = event.type === "item_completed";
      if (
        item.type === "AgentMessage" &&
        item.phase === "commentary" &&
        completed
      ) {
        const text = (item.content || [])
          .filter((c) => c.type === "Text" && typeof c.text === "string")
          .map((c) => c.text)
          .join("\n");
        agent.historyLimited =
          publicUpdate(
            agent.activity,
            item.id || `update:${row.timestamp}`,
            text,
            at,
          ) || agent.historyLimited;
      }
      if (["CommandExecution", "WebSearch"].includes(item.type || "")) {
        const command = Array.isArray(item.command)
          ? item.command.join(" ")
          : "";
        agent.historyLimited =
          recordActivity(agent.activity, {
            id: item.id || `${item.type}:${row.timestamp}`,
            label:
              item.type === "WebSearch"
                ? "Searching public sources"
                : commandLabel(command),
            at,
            finishedAt: completed ? row.timestamp : undefined,
            status: completed
              ? item.exit_code && item.exit_code !== 0
                ? "failed"
                : item.status || "completed"
              : "running",
            detail:
              typeof item.query === "string"
                ? item.query.slice(0, 500)
                : undefined,
            ...(item.type === "CommandExecution"
              ? {
                  targetUrl: commandTarget(command),
                  ...helperResult(command, item.aggregated_output),
                }
              : {}),
          }) || agent.historyLimited;
      }
    }
    if (!turn || event.turn_id !== turn) continue;
    if (event.type === "task_complete") {
      updateAgents(message, {
        agents_states: {
          [id]: {
            status: event.error ? "errored" : "completed",
            message: event.last_agent_message,
          },
        },
      });
      message.agents!.find((a) => a.id === id)!.finishedAt = row.timestamp;
    }
    if (event.type === "turn_aborted")
      updateAgents(message, {
        agents_states: { [id]: { status: "interrupted" } },
      });
  }
  const agent = message.agents?.find((a) => a.id === id);
  if (agent && !agent.task && metadata.agent_path)
    agent.task = `Assignment: ${metadata.agent_path.split("/").at(-1)?.replaceAll("_", " ")}`;
}

async function firstRecord(file: FileHandle) {
  let text = "";
  for (let position = 0; position < 256 * 1024; position += 4096) {
    const buffer = Buffer.alloc(4096);
    const { bytesRead } = await file.read(buffer, 0, buffer.length, position);
    text += buffer.subarray(0, bytesRead).toString("utf8");
    if (text.includes("\n")) return JSON.parse(text.split("\n")[0]);
    if (bytesRead < 4096) break;
  }
  return JSON.parse(text);
}

// Collaboration v2 may omit child ids from exec JSON. Session metadata supplies
// the relationship; no child content is read until its exact parent is verified.
export async function enrichAgentNames(message: ChatMessage, parent: string) {
  const root = path.join(
    process.env.CODEX_HOME || path.join(homedir(), ".codex"),
    "sessions",
  );
  const dates = new Set([
    new Date().toISOString().slice(0, 10),
    message.at.slice(0, 10),
  ]);
  for (const date of dates) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) continue;
    const directory = path.join(root, ...date.split("-"));
    try {
      const names = await readdir(directory, { withFileTypes: true });
      for (const entry of names) {
        if (!entry.isFile() || !entry.name.endsWith(".jsonl")) continue;
        const file = await open(path.join(directory, entry.name), "r");
        try {
          const meta = await firstRecord(file);
          const id = meta?.payload?.id;
          if (typeof id !== "string" || !/^[a-f0-9-]{36}$/i.test(id)) continue;
          const identity = agentIdentity(meta, id, parent);
          if (!identity) continue;
          const size = (await file.stat()).size;
          const start = Math.max(0, size - 1024 * 1024);
          const buffer = Buffer.alloc(Math.min(size, 1024 * 1024));
          const { bytesRead } = await file.read(
            buffer,
            0,
            buffer.length,
            start,
          );
          const lines = buffer
            .subarray(0, bytesRead)
            .toString("utf8")
            .split("\n");
          if (start) lines.shift();
          const records = lines.flatMap((line) => {
            try {
              const row = JSON.parse(line);
              return row.type === "event_msg" ? [row] : [];
            } catch {
              return [];
            }
          });
          applyAgentRecords(message, id, meta.payload, records);
          const agent = message.agents?.find((a) => a.id === id);
          if (agent)
            Object.assign(
              agent,
              identity,
              start ? { historyLimited: true } : {},
            );
        } catch {
          /* A session may still be flushing its current record. */
        } finally {
          await file.close();
        }
      }
    } catch {
      /* Metadata can arrive after the spawn event; retry on the next event. */
    }
  }
}

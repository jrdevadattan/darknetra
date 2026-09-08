"use client";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  api,
  ApiError,
  authorizedFetch,
  readError,
  useApi,
  invalidateCase,
} from "./api";
import type { S } from "./types";
import { EventParser, terminal } from "./stream";

export type RunInfo = {
  id: string;
  status: string;
  harness?: string;
  provider?: string;
  cost_usd: number | string;
  cost_complete?: boolean;
  error?: Record<string, unknown> | null;
};
export function useRun(
  base: string | null,
  runId: string | null,
  caseId?: string,
) {
  const client = useQueryClient();
  const path = base && runId ? base + "/runs/" + runId : null;
  const meta = useApi<RunInfo>(path, (data) =>
    terminal(data?.status) ? false : 3000,
  );
  const snapshot = useApi<S<"ExecutionSnapshot">>(
    path && caseId ? path + "/execution" : null,
    (data) => (terminal(data?.run_status) ? false : 3000),
  );
  const [connection, setConnection] = useState("idle");
  const [streamError, setStreamError] = useState<unknown>(null);
  const finished = terminal(meta.data?.status, snapshot.data?.run_status);
  // Polling is a fallback for a lost SSE connection, including its final message.
  useEffect(() => {
    if (!path || !finished) return;
    void client.invalidateQueries({ queryKey: ["api", base + "/messages"] });
    if (caseId)
      void client.invalidateQueries({ queryKey: ["api", path + "/execution"] });
  }, [path, base, caseId, client, finished]);
  useEffect(() => {
    if (!path || finished) return;
    const controller = new AbortController();
    let cursor = 0,
      attempts = 0;
    const pause = () =>
      new Promise<void>((resolve) => {
        const done = () => {
          clearTimeout(timer);
          controller.signal.removeEventListener("abort", done);
          resolve();
        };
        const timer = setTimeout(done, Math.min(1000 * 2 ** attempts, 10_000));
        controller.signal.addEventListener("abort", done, { once: true });
      });
    const reconcile = async () => {
      await client.invalidateQueries({ queryKey: ["api", base + "/messages"] });
      await client.invalidateQueries({ queryKey: ["api", path] });
      if (caseId) await invalidateCase(client, caseId);
    };
    async function listen() {
      setStreamError(null);
      while (!controller.signal.aborted) {
        try {
          setConnection(attempts ? "reconnecting" : "connecting");
          if (caseId) {
            const current = await api<S<"ExecutionSnapshot">>(
              path + "/execution",
              "GET",
              undefined,
              controller.signal,
            );
            cursor = current.cursor;
            client.setQueryData(["api", path + "/execution"], current);
            if (terminal(current.run_status)) {
              await reconcile();
              setConnection("complete");
              return;
            }
          }
          const response = await authorizedFetch(path + "/events", {
            headers: {
              "Last-Event-ID": String(cursor),
              Accept: "text/event-stream",
            },
            signal: controller.signal,
          });
          if (!response.ok) throw await readError(response);
          if (!response.body) throw new Error("Run stream is unavailable.");
          setConnection("live");
          setStreamError(null);
          attempts = 0;
          const reader = response.body.getReader(),
            decoder = new TextDecoder(),
            parser = new EventParser();
          let ended = false;
          try {
            while (!controller.signal.aborted) {
              const part = await reader.read();
              if (part.done) break;
              for (const frame of parser.push(
                decoder.decode(part.value, { stream: true }),
              )) {
                if (frame.id <= cursor) continue;
                cursor = frame.id;
                if (frame.event === "activity.updated") {
                  const update = frame.data as S<"ActivityUpdate">;
                  client.setQueryData<S<"ExecutionSnapshot">>(
                    ["api", path + "/execution"],
                    (previous) => {
                      if (
                        !previous ||
                        !update.id ||
                        frame.id <= previous.cursor
                      )
                        return previous;
                      const nodes = previous.nodes.filter(
                        (node) => node.id !== update.id,
                      );
                      return {
                        ...previous,
                        cursor: frame.id,
                        nodes: [
                          ...nodes,
                          { ...update, terminal_inferred: false },
                        ].sort((a, b) => a.seq - b.seq),
                        edges:
                          update.parent_id &&
                          !previous.edges.some((e) => e.target === update.id)
                            ? [
                                ...previous.edges,
                                { source: update.parent_id, target: update.id },
                              ]
                            : previous.edges,
                        events: [...previous.events, update].slice(-10_000),
                        truncated:
                          previous.truncated ||
                          previous.events.length >= 10_000,
                      };
                    },
                  );
                }
                if (frame.event === "message.completed")
                  await client.invalidateQueries({
                    queryKey: ["api", base + "/messages"],
                  });
                if (frame.event === "store.changed" && caseId)
                  void invalidateCase(client, caseId);
                if (frame.event === "run.finished") {
                  ended = true;
                  await reconcile();
                  setConnection("complete");
                  break;
                }
              }
              if (ended) break;
            }
          } finally {
            await reader.cancel().catch(() => {});
            reader.releaseLock();
          }
          if (ended) return;
          if (!caseId) {
            const current = await api<RunInfo>(path!);
            if (terminal(current.status)) {
              await reconcile();
              setConnection("complete");
              return;
            }
          }
        } catch (error) {
          if (controller.signal.aborted) return;
          if (
            error instanceof ApiError &&
            [401, 403, 404].includes(error.status)
          ) {
            setStreamError(error);
            setConnection("unavailable");
            return;
          }
          setStreamError(error);
          setConnection("reconnecting");
        }
        attempts++;
        await pause();
      }
    }
    void listen();
    return () => controller.abort();
  }, [base, path, caseId, client, finished]);
  const active = Boolean(runId) && !finished;
  return {
    info: meta.data,
    snapshot: snapshot.data,
    loading: meta.isLoading,
    error: meta.error ?? snapshot.error,
    streamError,
    connection: finished ? "complete" : connection,
    active,
  };
}

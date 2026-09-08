"use client";

import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2 } from "lucide-react";
import { api, invalidateCase } from "@/lib/api";
import { ErrorBanner } from "./shared";

export function useCaseAction(caseId: string) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);

  const run = useCallback(
    async <T,>(
      path: string,
      method: string,
      body?: unknown,
      success?: string,
    ) => {
      setBusy(true);
      setError(null);
      setMessage(null);
      try {
        const result = await api<T>(path, method, body);
        await invalidateCase(queryClient, caseId);
        setMessage(success ?? "Saved");
        return result;
      } catch (caught) {
        setError(caught);
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    [caseId, queryClient],
  );

  const clear = useCallback(() => {
    setError(null);
    setMessage(null);
  }, []);

  const fail = useCallback((reason: unknown) => {
    setError(reason);
    setMessage(null);
  }, []);

  return { busy, error, message, run, clear, fail };
}

export function FormFeedback({
  busy,
  error,
  message,
}: {
  busy?: boolean;
  error?: unknown;
  message?: string | null;
}) {
  return (
    <div aria-live="polite" className="content-stack">
      {busy ? (
        <p className="muted flex items-center gap-2">
          <Loader2 size={14} className="animate-spin" />
          Saving changes…
        </p>
      ) : null}
      {message ? (
        <p className="flex items-center gap-2 text-sm text-emerald-400">
          <CheckCircle2 size={15} />
          {message}
        </p>
      ) : null}
      <ErrorBanner error={error} />
    </div>
  );
}

export const SOURCE_CLASSES = [
  "SYNTHETIC",
  "SEIZED",
  "UPLOAD",
  "OSINT_SURFACE",
  "OSINT_DARK",
  "CHAIN",
  "TELEGRAM",
  "REPORT",
] as const;
export const CASE_ROLES = ["OWNER", "LEAD", "ANALYST", "VIEWER"] as const;
export const ITEM_TYPES = [
  "KEYWORD",
  "ALIAS",
  "WALLET",
  "PGP_FINGERPRINT",
  "ONION_DOMAIN",
  "TELEGRAM_CHANNEL",
  "IMAGE_HASH",
] as const;

export const DEFAULT_SOURCES: Record<(typeof ITEM_TYPES)[number], string[]> = {
  KEYWORD: ["web_search", "onion_search"],
  ALIAS: ["web_search", "onion_search", "username_lookup"],
  WALLET: ["chain_lookup", "sanctions_check"],
  PGP_FINGERPRINT: ["keyserver_lookup", "onion_search"],
  ONION_DOMAIN: ["onion_lookup", "onion_fetch"],
  TELEGRAM_CHANNEL: ["telegram_channel_read"],
  IMAGE_HASH: ["evidence"],
};

export function splitList(value: string) {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function humanize(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

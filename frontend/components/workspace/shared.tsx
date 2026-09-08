"use client";

import type { ReactNode } from "react";
import { AlertCircle, ArrowRight, Loader2, SearchX, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogHeader,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { ApiError } from "@/lib/api";
export { Button, Badge };

export function ErrorBanner({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  if (!error) return null;
  return (
    <div role="alert" className="error-banner">
      <AlertCircle size={17} />
      <div>
        <strong>
          {error instanceof ApiError
            ? error.code.replaceAll("_", " ")
            : "Something went wrong"}
        </strong>
        <p>{error instanceof Error ? error.message : "Please try again."}</p>
        {error instanceof ApiError && error.requestId && (
          <small>Request {error.requestId}</small>
        )}
      </div>
      {retry && (
        <Button size="sm" variant="outline" onClick={retry}>
          Retry
        </Button>
      )}
    </div>
  );
}
export function EmptyState({
  title,
  description,
  children,
  icon,
}: {
  title: string;
  description?: string;
  children?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon ?? <SearchX size={24} />}</div>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {children}
    </div>
  );
}
export function Loading({ label = "Loading workspace" }: { label?: string }) {
  return (
    <div className="loading-state" role="status">
      <Loader2 size={18} className="animate-spin" />
      {label}…
    </div>
  );
}
export function PanelHeader({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: ReactNode;
}) {
  return (
    <header className="panel-heading">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </header>
  );
}
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="form-field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!value) onClose();
      }}
    >
      <DialogContent
        className={cn("max-h-[90dvh] overflow-y-auto", wide && "sm:max-w-3xl")}
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {description ??
              "Changes use your authenticated workspace permissions."}
          </DialogDescription>
        </DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  );
}
export function StatusBadge({ status }: { status?: string | null }) {
  return (
    <span
      className={cn(
        "status-pill",
        /^(ok|READY|DONE|OPEN|completed|CONFIRMED|ENABLED|ACTIVE|AVAILABLE)$/i.test(
          status ?? "",
        )
          ? "status-good"
          : /error|fail|denied|quarantin|unavailable|interrupted/i.test(
                status ?? "",
              )
            ? "status-bad"
            : "status-neutral",
      )}
    >
      <i />
      {status?.replaceAll("_", " ") ?? "Unknown"}
    </span>
  );
}
export function LoadMore({
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
}: {
  hasNextPage?: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => unknown;
}) {
  return hasNextPage ? (
    <Button
      variant="outline"
      className="mx-auto mt-4 flex"
      disabled={isFetchingNextPage}
      onClick={() => void fetchNextPage()}
    >
      {isFetchingNextPage ? "Loading…" : "Load more"}
      <ArrowRight size={14} />
    </Button>
  ) : null;
}
export const date = (value?: string | null) =>
  value
    ? new Date(value).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "—";
export const money = (value?: number | string | null) =>
  "$" + Number(value ?? 0).toFixed(4);
export function EvidenceChip({
  code,
  onClick,
}: {
  code: string;
  onClick?: () => void;
}) {
  return (
    <button className="evidence-chip" onClick={onClick} disabled={!onClick}>
      {code}
      <ArrowRight size={11} />
    </button>
  );
}

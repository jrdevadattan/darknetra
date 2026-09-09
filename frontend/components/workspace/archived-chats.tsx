"use client";

import { useState } from "react";
import {
  Archive,
  ArchiveRestore,
  ArrowUpRight,
  Clock3,
  FolderOpen,
  LoaderCircle,
  MessageSquare,
  Search,
} from "lucide-react";
import type { Chat, WorkspaceData } from "@/lib/chat-types";

export function ArchivedChats({
  data,
  onRestore,
  onOpen,
}: {
  data: WorkspaceData;
  onRestore: (chat: Chat) => Promise<void>;
  onOpen: (chat: Chat) => void;
}) {
  const [query, setQuery] = useState("");
  const [restoring, setRestoring] = useState<string | null>(null);
  const [error, setError] = useState("");
  const archived = data.chats
    .filter((chat) => chat.archivedAt)
    .sort((a, b) => b.archivedAt!.localeCompare(a.archivedAt!));
  const caseName = (chat: Chat) =>
    data.cases.find((item) => item.id === chat.caseId)?.title ||
    "Personal chat";
  const matches = archived.filter((chat) =>
    `${chat.title} ${caseName(chat)}`
      .toLowerCase()
      .includes(query.trim().toLowerCase()),
  );

  async function restore(chat: Chat) {
    setRestoring(chat.id);
    setError("");
    try {
      await onRestore(chat);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setRestoring(null);
    }
  }

  return (
    <section className="archived-chats" aria-label="Archived conversations">
      <div className="archive-intro">
        <strong>Out of the sidebar. Still here.</strong>
        <p>
          Open a saved conversation or restore it to its original folder.
          Archiving keeps messages and files; scheduled monitoring continues.
        </p>
      </div>
      {archived.length > 0 && (
        <label className="archive-search">
          <Search size={16} aria-hidden="true" />
          <input
            type="search"
            aria-label="Search archived chats"
            placeholder="Search chats or cases…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      )}
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      <div className="archive-list" aria-live="polite">
        {matches.map((chat) => (
          <article
            className="archive-card"
            key={chat.id}
            aria-label={chat.title}
          >
            <div className="archive-card-icon">
              <MessageSquare size={18} />
            </div>
            <div className="archive-card-content">
              <button
                className="archive-chat-title"
                onClick={() => onOpen(chat)}
                title={`Open ${chat.title}`}
              >
                {chat.title}
              </button>
              <span className="archive-case">
                <FolderOpen size={12} />
                {caseName(chat)}
              </span>
              <time
                dateTime={chat.archivedAt}
                title={new Date(chat.archivedAt!).toLocaleString()}
              >
                Archived{" "}
                {new Date(chat.archivedAt!).toLocaleDateString(undefined, {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                })}
              </time>
              {data.monitors?.some(
                (monitor) => monitor.chatId === chat.id && monitor.enabled,
              ) && (
                <span className="archive-monitor">
                  <Clock3 size={12} />
                  Monitoring active
                </span>
              )}
            </div>
            <div className="archive-card-actions">
              <button
                className="icon-button"
                title="Open chat"
                aria-label={`Open ${chat.title}`}
                onClick={() => onOpen(chat)}
              >
                <ArrowUpRight size={17} />
              </button>
              <button
                className="archive-restore"
                disabled={restoring !== null}
                onClick={() => void restore(chat)}
              >
                {restoring === chat.id ? (
                  <LoaderCircle size={15} className="spin" />
                ) : (
                  <ArchiveRestore size={15} />
                )}
                {restoring === chat.id ? "Restoring…" : "Restore"}
              </button>
            </div>
          </article>
        ))}
        {!matches.length && (
          <div className="archive-empty">
            {archived.length ? <Search size={28} /> : <Archive size={28} />}
            <strong>
              {archived.length ? "No matching chats" : "No archived chats yet"}
            </strong>
            <p>
              {archived.length
                ? "Try another chat title or case name."
                : "Use a chat’s three-dot menu in the sidebar to archive it. You can restore it here anytime."}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}

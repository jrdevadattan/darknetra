"use client";
import { useEffect, useState } from "react";
import { Bell, BellRing, LoaderCircle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { WorkspaceNotification } from "@/lib/chat-types";

async function api(body?: unknown) {
  const response = await fetch("/api/notifications", {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(data.error || "Notification request failed.");
  return data;
}
export function NotificationSettings() {
  const [supported, setSupported] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [failuresOnly, setFailuresOnly] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  useEffect(() => {
    const available =
      window.isSecureContext &&
      "Notification" in window &&
      "serviceWorker" in navigator &&
      "PushManager" in window;
    setSupported(available);
    if (!available) {
      setStatus(
        "Push is unavailable in this browser. Updates are still saved in Notifications.",
      );
      return;
    }
    void navigator.serviceWorker
      .getRegistration("/")
      .then(async (reg) => {
        const subscription = await reg?.pushManager.getSubscription();
        if (subscription) {
          const saved = await api({
            action: "status",
            endpoint: subscription.endpoint,
          });
          setEnabled(saved.enabled && Notification.permission === "granted");
          setFailuresOnly(saved.failuresOnly);
        }
        if (Notification.permission === "denied")
          setStatus(
            "Notifications are blocked. Allow them in this site's browser settings, then enable them here.",
          );
      })
      .catch(() =>
        setStatus("Could not check notification settings. Try again."),
      );
  }, []);
  async function act(action: "enable" | "disable" | "test") {
    setBusy(true);
    setStatus("");
    try {
      // Permission must be requested from the user's button click.
      if (
        action === "enable" &&
        (await Notification.requestPermission()) !== "granted"
      )
        throw new Error(
          "Notifications were not allowed. You can enable them later in browser settings.",
        );
      const registration = await navigator.serviceWorker.register("/sw.js", {
        scope: "/",
      });
      await navigator.serviceWorker.ready;
      let subscription = await registration.pushManager.getSubscription();
      if (action === "enable") {
        const { publicKey } = await api();
        const key = Uint8Array.from(
          atob(publicKey.replace(/-/g, "+").replace(/_/g, "/")),
          (c) => c.charCodeAt(0),
        );
        if (!subscription)
          subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: key,
          });
        await api({
          action: "subscribe",
          subscription: subscription.toJSON(),
          failuresOnly,
        });
        setEnabled(true);
        setStatus("Push notifications enabled for this browser.");
      } else if (subscription && action === "disable") {
        await api({ action: "unsubscribe", endpoint: subscription.endpoint });
        await subscription.unsubscribe();
        setEnabled(false);
        setStatus("Push notifications disabled for this browser.");
      } else if (subscription) {
        await api({ action: "test", endpoint: subscription.endpoint });
        setStatus(
          "Test sent to the browser push service. Check your device's notifications.",
        );
      } else {
        setEnabled(false);
        throw new Error("Enable notifications on this browser first.");
      }
    } catch (error) {
      setStatus((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function preference(value: boolean) {
    setBusy(true);
    setStatus("");
    try {
      const subscription = await (
        await navigator.serviceWorker.getRegistration("/")
      )?.pushManager.getSubscription();
      if (!subscription) throw new Error("Enable notifications again.");
      await api({
        action: "subscribe",
        subscription: subscription.toJSON(),
        failuresOnly: value,
      });
      setFailuresOnly(value);
    } catch (error) {
      setStatus((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <fieldset className="notification-settings">
      <legend>
        <BellRing size={17} /> Push notifications
      </legend>
      <p>
        Get an alert when a monitoring check finishes or needs attention, even
        with this tab closed. Case details stay inside the workspace.
      </p>
      <div className="notification-controls">
        <button
          type="button"
          className="primary-button"
          disabled={!supported || busy}
          onClick={() => void act(enabled ? "disable" : "enable")}
        >
          {busy && <LoaderCircle size={14} className="spin" />}
          {enabled ? "Disable notifications" : "Enable notifications"}
        </button>
        {enabled && (
          <button
            type="button"
            className="secondary-button"
            disabled={busy}
            onClick={() => void act("test")}
          >
            Send test notification
          </button>
        )}
      </div>
      {enabled && (
        <label className="notification-preference">
          <input
            type="checkbox"
            checked={failuresOnly}
            disabled={busy}
            onChange={(e) => void preference(e.target.checked)}
          />{" "}
          Only alert me when a check fails
        </label>
      )}
      {status && <p role="status">{status}</p>}
      <small>
        The app container must remain running. Delivery follows your browser and
        device notification settings.
      </small>
    </fieldset>
  );
}

export function NotificationInbox({
  onOpen,
}: {
  onOpen: (caseId: string, chatId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<WorkspaceNotification[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      try {
        const result = await api();
        if (alive) {
          setItems(result.notifications);
          setError("");
        }
      } catch {
        if (alive) setError("Notifications could not be loaded.");
      }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);
  async function read(id?: string) {
    try {
      await api({ action: "read", id });
      setItems((items) =>
        items.map((n) => (!id || n.id === id ? { ...n, read: true } : n)),
      );
    } catch {
      setError("Could not mark notifications as read.");
    }
  }
  const unread = items.filter((n) => !n.read).length;
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          className="icon-button notification-bell"
          aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
          title="Notifications"
        >
          <Bell size={18} />
          {unread > 0 && (
            <span className="notification-count">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </button>
      </DialogTrigger>
      <DialogContent className="notifications-dialog">
        <DialogHeader>
          <DialogTitle>Notifications</DialogTitle>
          <DialogDescription>
            Recent monitoring results from this workspace.
          </DialogDescription>
        </DialogHeader>
        {!!unread && (
          <button className="secondary-button" onClick={() => void read()}>
            Mark all read
          </button>
        )}
        {error && <p role="alert">{error}</p>}
        <div className="notification-list">
          {!items.length && (
            <p className="muted">
              No updates yet. Completed monitoring checks will appear here.
            </p>
          )}
          {items.map((n) => (
            <button
              key={n.id}
              className={`notification-item ${n.read ? "read" : "unread"}`}
              onClick={() => {
                void read(n.id);
                setOpen(false);
                onOpen(n.caseId, n.chatId);
              }}
            >
              <strong>{n.title}</strong>
              <span>{n.body}</span>
              <time>{new Date(n.at).toLocaleString()}</time>
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

import { randomUUID } from "node:crypto";
import { nextOccurrence } from "./monitors";
import type { ChatMessage, WorkspaceData } from "./chat-types";

// Only the submitted message is considered. Attachments, retrieved text and
// assistant replies can never create schedules. Questions/quotes are not orders.
export function monitoringIntent(text: string) {
  const plain = text
    .replace(/```[\s\S]*?```/g, "")
    .replace(/^\s*>.*$/gm, "")
    .replace(/"[^"\n]*"|“[^”\n]*”/g, "")
    .replace(/https?:\/\/\S+/gi, "URL")
    .trim();
  const request =
    /(?:^|[.!?]\s+)(?:(?:please|also)\s+)*(?:(?:can|could|would)\s+(?:you|u)\s+(?:please\s+)?|(?:i want you to|i need you to)\s+)?(?:(?:start|begin)\s+monitoring|monitor|watch|keep (?:an eye on|checking)|check .+?\b(?:every|hourly|daily|weekly))\b/i;
  if (
    !request.test(plain) ||
    /\b(?:do not|don't|dont|stop|pause|cancel|never)\s+(?:\w+\s+){0,2}(?:monitor|watch|checking)/i.test(
      plain,
    )
  )
    return null;
  const commonError =
    "Monitoring was not started. Specify an interval such as every 15 minutes, hourly, or daily at 09:00, or use Case monitoring for a custom schedule.";
  if (/\b(?:once|one time|one-off)\b|\b(?:UTC|GMT)\s*[+-]/i.test(plain))
    return { error: commonError };
  let cron = "0 * * * *",
    label = "every hour (default)";
  const every = plain.match(
    /\bevery\s+(?:(\d+|one|two|three|four|five|ten|fifteen|thirty)\s+)?(minutes?|mins?|hours?|hrs?|days?|weeks?|seconds?)\b/i,
  );
  const words: Record<string, number> = {
    one: 1,
    two: 2,
    three: 3,
    four: 4,
    five: 5,
    ten: 10,
    fifteen: 15,
    thirty: 30,
  };
  if (every) {
    const count = every[1]
      ? words[every[1].toLowerCase()] || Number(every[1])
      : 1;
    const unit = every[2].toLowerCase();
    if (/^(min)/.test(unit) && count > 0 && count <= 30 && 60 % count === 0) {
      cron = count === 1 ? "* * * * *" : `*/${count} * * * *`;
      label = `every ${count} minute${count === 1 ? "" : "s"}`;
    } else if (
      /^(h)/.test(unit) &&
      count > 0 &&
      count <= 12 &&
      24 % count === 0
    ) {
      cron = count === 1 ? "0 * * * *" : `0 */${count} * * *`;
      label = `every ${count} hour${count === 1 ? "" : "s"}`;
    } else if (/^day/.test(unit) && count === 1) {
      cron = "0 9 * * *";
      label = "daily at 09:00";
    } else if (/^week/.test(unit) && count === 1) {
      cron = "0 9 * * 1";
      label = "weekly on Monday at 09:00";
    } else return { error: commonError };
  } else if (/\bdaily\b/i.test(plain)) {
    cron = "0 9 * * *";
    label = "daily at 09:00";
  } else if (/\bweekly\b/i.test(plain)) {
    cron = "0 9 * * 1";
    label = "weekly on Monday at 09:00";
  } else if (/\bhourly\b/i.test(plain)) {
    label = "every hour";
  } else if (
    /\b(?:every|each|nightly|monthly|tomorrow|tonight|later|until|for \d+ (?:minute|hour|day)|at \d)\b/i.test(
      plain,
    )
  )
    return { error: commonError };
  const at = plain.match(/\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b/i);
  if (at) {
    let hour = Number(at[1]);
    const minute = Number(at[2] || "0");
    if (at[3]) {
      if (hour < 1 || hour > 12) return { error: commonError };
      hour = (hour % 12) + (at[3].toLowerCase() === "pm" ? 12 : 0);
    }
    if (hour > 23 || minute > 59 || !/^(daily|weekly)/.test(label))
      return { error: commonError };
    const clock = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
    cron = `${minute} ${hour} * * ${label.startsWith("weekly") ? "1" : "*"}`;
    label = label.startsWith("weekly")
      ? `weekly on Monday at ${clock}`
      : `daily at ${clock}`;
  }
  // Never silently ignore a second frequency, requested end time or named day.
  if (
    /\b(?:until|ending|for \d+ (?:minutes?|hours?|days?)|monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekdays|weekends)\b/i.test(
      plain,
    )
  )
    return { error: commonError };
  return { cron, label };
}

export function registerChatMonitor(
  data: WorkspaceData,
  chatId: string,
  text: string,
  message: ChatMessage,
  timezone: string,
) {
  const intent = monitoringIntent(text);
  if (!intent) return;
  if (intent.error || !intent.cron) {
    message.monitoring = { summary: intent.error! };
    return;
  }
  try {
    // Accept an explicit unambiguous timezone; otherwise use the browser zone.
    const withoutUrls = text.replace(/https?:\/\/\S+/gi, "");
    const zone = withoutUrls.match(
      /\b(?:UTC|GMT|[A-Za-z_]+\/[A-Za-z_]+)\b/,
    )?.[0];
    if (zone) timezone = zone === "GMT" ? "UTC" : zone;
    if (/\b(?:IST|EST|CST|PST|EDT|PDT)\b/.test(withoutUrls))
      throw new Error("Use a timezone such as Asia/Kolkata or UTC.");
    const nextRunAt = nextOccurrence(intent.cron, timezone);
    const chat = data.chats.find((c) => c.id === chatId)!;
    data.monitors ||= [];
    const urls = [
      ...new Set(
        (text.match(/https?:\/\/[^\s<>"`]+/gi) || []).map((u) =>
          u.replace(/[.,!?;)]+$/, ""),
        ),
      ),
    ].sort();
    const scopeKey = urls.length ? urls.join("\n") : "conversation";
    const existing = data.monitors.find(
      (m) => m.sourceChatId === chatId && m.scopeKey === scopeKey,
    );
    if (!existing && data.monitors.length >= 50)
      throw new Error("This workspace supports up to 50 schedules.");
    if (!chat.caseId) {
      chat.caseId = randomUUID();
      data.cases.unshift({
        id: chat.caseId,
        title: text.slice(0, 120),
        notes: "Created from a monitoring request in chat.",
        createdAt: message.at,
      });
    }
    const monitor = existing || {
      id: randomUUID(),
      caseId: chat.caseId,
      chatId,
      sourceChatId: chatId,
      scopeKey,
      title: text.slice(0, 120),
      prompt: text.slice(0, 8000),
      cron: intent.cron,
      timezone,
      enabled: true,
      createdAt: message.at,
      nextRunAt,
      runs: [],
    };
    Object.assign(monitor, {
      cron: intent.cron,
      timezone,
      enabled: true,
      nextRunAt,
      prompt: text.slice(0, 8000),
    });
    monitor.runs.unshift({
      id: randomUUID(),
      at: message.at,
      trigger: "chat",
      status: "running",
      messageId: message.id,
    });
    if (!existing) data.monitors.unshift(monitor);
    message.monitoring = {
      monitorId: monitor.id,
      caseId: chat.caseId,
      summary: `Monitoring ${existing ? "updated" : "started"}: ${intent.label} · ${timezone}. This reply is the first check.`,
      nextRunAt,
    };
  } catch (error) {
    message.monitoring = {
      summary: `Monitoring was not started. ${(error as Error).message}`,
    };
  }
}

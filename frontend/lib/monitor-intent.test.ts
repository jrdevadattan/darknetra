import { expect, test, vi } from "vitest";
vi.mock("./push", () => ({
  deliverPush: vi.fn(async () => ({ sent: 0, failed: 0 })),
}));
import { monitoringIntent, registerChatMonitor } from "./monitor-intent";
import type { ChatMessage, WorkspaceData } from "./chat-types";

test("direct monitoring requests support common intervals without turning questions or quoted text into schedules", () => {
  expect(
    monitoringIntent("Please monitor https://example.com every 15 minutes")
      ?.cron,
  ).toBe("*/15 * * * *");
  expect(monitoringIntent("Can u monitor this site?")?.cron).toBe("0 * * * *");
  expect(
    monitoringIntent("Start monitoring this case daily at 9 pm UTC")?.cron,
  ).toBe("0 21 * * *");
  expect(monitoringIntent("Keep checking this every two hours")?.cron).toBe(
    "0 */2 * * *",
  );
  for (const message of [
    "How do I monitor a site?",
    "Don't monitor this",
    "Monitoring should be easier",
    "> monitor this site",
    'The page says "monitor this"',
    "```\nmonitor this\n```",
    "Please stop monitoring this",
    "Can you explain monitoring?",
  ])
    expect(monitoringIntent(message)).toBeNull();
  for (const message of [
    "Monitor this every 7 minutes",
    "Monitor this every second",
    "Monitor this tomorrow",
    "Monitor this weekly on Friday",
    "Monitor this hourly for 2 days",
  ])
    expect(monitoringIntent(message)?.error).toBeTruthy();
});
test("chat schedules create a case if needed, stay in their conversation, update in place and never create a case on invalid schedules", () => {
  const data: WorkspaceData = {
    version: 1,
    cases: [],
    chats: [
      {
        id: "SYNTHETIC-chat",
        caseId: null,
        title: "SYNTHETIC",
        createdAt: "2026-09-08T00:00:00Z",
        messages: [],
      },
    ],
  };
  const message: ChatMessage = {
    id: "SYNTHETIC-reply",
    role: "assistant",
    text: "",
    at: new Date().toISOString(),
    status: "running",
    activity: [],
  };
  registerChatMonitor(
    data,
    "SYNTHETIC-chat",
    "Monitor https://example.com every 7 minutes",
    message,
    "UTC",
  );
  expect(data.cases).toHaveLength(0);
  registerChatMonitor(
    data,
    "SYNTHETIC-chat",
    "Monitor https://example.com/source every hour",
    message,
    "Asia/Kolkata",
  );
  expect(data.cases).toHaveLength(1);
  expect(data.monitors).toHaveLength(1);
  expect(data.monitors![0].timezone).toBe("Asia/Kolkata");
  expect(data.monitors![0].chatId).toBe("SYNTHETIC-chat");
  expect(data.monitors![0].runs[0].trigger).toBe("chat");
  registerChatMonitor(
    data,
    "SYNTHETIC-chat",
    "Please monitor https://example.com/source every 15 minutes",
    { ...message, id: "SYNTHETIC-second" },
    "UTC",
  );
  expect(data.monitors).toHaveLength(1);
  expect(data.monitors![0].cron).toBe("*/15 * * * *");
  expect(data.monitors![0].runs).toHaveLength(2);
});

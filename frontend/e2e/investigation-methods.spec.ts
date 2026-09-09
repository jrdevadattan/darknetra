import { expect, test } from "@playwright/test";
import type { ChatMessage, SpecialistAgent } from "../lib/chat-types";

test("new specialists review supplied records, suggest departmental requests, and revisit gaps on upload", async ({
  page,
}) => {
  test.setTimeout(240_000);
  await page.goto("/");
  await page.locator("input[type=file]").setInputFiles({
    name: "SYNTHETIC-case-notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "SYNTHETIC training data only. No real people, accounts or shipments. Case SYNTHETIC-RECORDS-001. Jurisdiction has not been established. Financial note: transaction reference SYNTHETIC-TX-001, but network, asset unit and time are absent. Parcel note: SYNTHETIC-PARCEL-001 arrival scan 2026-09-08T09:00:00Z; handover event absent from the export. All identifiers are fictitious. No external research or contact is needed.",
    ),
  });
  await expect(page.getByLabel("Attached files")).toContainText(
    "SYNTHETIC-case-notes.txt",
  );
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill(
      "SYNTHETIC departmental-records test. Delegate the financial gap to financial_analyst and the parcel gap to logistics_liaison using those exact native roles. Have both read the investigation-methods and records-requests skill references and actually read the attached notes with file-text. Wait for both reports. Give a short prioritized next-leads list naming the needed records, likely custodian, identifiers/time scope/timezone, purpose, upload format and unsent/awaiting state. These are invented identifiers: no web research, department contact or formal legal instrument. Do not invent jurisdiction or missing details.",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  const reply = page.locator(".chat-message.assistant .message-text").last();
  await expect(page.locator(".chat-message.assistant")).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "Stop reply", exact: true }),
  ).toHaveCount(0, { timeout: 180_000 });
  await expect(reply).toContainText(
    /custodian|records team|compliance|carrier/i,
  );
  await expect(reply).toContainText(/timezone|time zone|UTC/i);
  await expect(reply).toContainText(/not sent|unsent|awaiting|suggested/i);
  const chatId = new URL(page.url()).searchParams.get("chat");
  const data = await (await page.request.get("/api/workspace")).json();
  const message: ChatMessage = data.chats
    .find((c: { id: string }) => c.id === chatId)
    .messages.at(-1);
  for (const name of ["Financial Analyst", "Postal Records Liaison"]) {
    const specialist: SpecialistAgent | undefined = message.agents?.find(
      (a) => a.name === name,
    );
    expect(specialist?.status).toBe("completed");
    expect(specialist?.result).toBeTruthy();
    expect(
      specialist?.activity?.some((a) =>
        a.sources?.some((s) => s.kind === "file" && s.sha256),
      ),
    ).toBe(true);
  }
  await page.getByRole("tab", { name: "Timeline", exact: true }).click();
  await expect(page.locator(".specialist-card")).toHaveCount(2);
  await page.screenshot({
    path: "test-results/departmental-specialists.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Close activity", exact: true })
    .click();

  await page.locator("input[type=file]").setInputFiles({
    name: "SYNTHETIC-carrier-supplement.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "SYNTHETIC carrier export supplement, supplied by the case user. SYNTHETIC-PARCEL-001: handover event at 2026-09-08T10:05:00Z. Event definition: custody handover recorded by carrier. Coverage 2026-09-08T09:00:00Z to 2026-09-08T11:00:00Z, timezone UTC, exported 2026-09-08T12:00:00Z. No sender identity or parcel contents are established. Financial fields remain missing; no transaction supplement is supplied.",
    ),
  });
  await expect(page.getByLabel("Attached files")).toContainText(
    "SYNTHETIC-carrier-supplement.txt",
  );
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill(
      "Read the attached SYNTHETIC carrier supplement with file-text and revisit your previous records requests. Say what was actually received and which gap remains. Do not delegate or make external requests. Keep it brief; do not infer identities or contents.",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.locator(".chat-message.assistant")).toHaveCount(2);
  await expect(
    page.getByRole("button", { name: "Stop reply", exact: true }),
  ).toHaveCount(0, { timeout: 100_000 });
  await expect(reply).toContainText(/10:05|handover/i);
  await expect(reply).toContainText(/received|provided|supplied/i);
  await expect(reply).toContainText(/financial|transaction|network/i);
  await expect(reply).toContainText(/missing|awaiting|unresolved|remain/i);
  await page.reload();
  await expect(reply).toContainText(/10:05|handover/i);
});

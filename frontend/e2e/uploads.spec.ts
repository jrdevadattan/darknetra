import { expect, test } from "@playwright/test";

test("uploaded text and image reach the CLI, persist, and stay scoped to the chat", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await page.goto("/");
  const marker = `SYNTHETIC_FILE_${Date.now()}`;
  const png = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 100;
    canvas.height = 100;
    const context = canvas.getContext("2d")!;
    context.fillStyle = "#ff0000";
    context.fillRect(0, 0, 100, 100);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await page.locator("input[type=file]").setInputFiles([
    {
      name: "SYNTHETIC-notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(`The secret word is ${marker}.`),
    },
    {
      name: "SYNTHETIC-color.png",
      mimeType: "image/png",
      buffer: Buffer.from(png, "base64"),
    },
  ]);
  await expect(page.getByLabel("Attached files")).toContainText(
    "SYNTHETIC-notes.txt",
  );
  await expect(page.getByLabel("Attached files")).toContainText(
    "SYNTHETIC-color.png",
  );
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill(
      "SYNTHETIC check: use the skill file-text command to read the attached notes. Reply with their secret word and the dominant color in the attached image. Do not search the web.",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  const reply = page.locator(".chat-message.assistant .message-text").last();
  await expect(reply).toContainText(marker, { timeout: 130000 });
  await expect(reply).toContainText(/red/i);
  await expect(
    page.getByRole("button", { name: "Stop reply", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("tab", { name: "Evidence graph", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(page.locator(".evidence-canvas")).toContainText(
    "SYNTHETIC-notes.txt",
  );
  await expect(
    page.getByRole("article", { name: "Selected graph item" }),
  ).toContainText("SHA-256");
  await page.reload();
  await expect(page.locator(".message-attachments")).toContainText(
    "SYNTHETIC-notes.txt",
  );
  const href = await page
    .getByRole("link", { name: /SYNTHETIC-notes/ })
    .getAttribute("href");
  const downloaded = await page.request.get(href!);
  expect(downloaded.status()).toBe(200);
  expect(await downloaded.text()).toContain(marker);
  const origin = new URL(page.url()).origin;
  const other = await (
    await page.request.post("/api/workspace", {
      headers: { origin },
      data: { type: "chat" },
    })
  ).json();
  const filename = new URL(href!, origin).searchParams.get("name");
  expect(
    (
      await page.request.get(`/api/chat/${other.id}/files?name=${filename}`)
    ).status(),
  ).toBe(404);
  expect(
    (
      await page.request.post(`/api/chat/${other.id}`, {
        headers: { origin },
        data: { text: "SYNTHETIC cross-chat check", attachments: [filename] },
      })
    ).status(),
  ).toBe(400);
  await page.screenshot({
    path: "test-results/upload-chat.png",
    fullPage: true,
  });
});

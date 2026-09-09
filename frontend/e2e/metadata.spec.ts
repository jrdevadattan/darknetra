import { expect, test } from "@playwright/test";
import { createHash } from "node:crypto";
import { syntheticImage } from "./fixtures/synthetic-image.mjs";

test("image investigation runs metadata in the CLI and shows findings after reload", async ({
  page,
}) => {
  test.setTimeout(540000);
  const bytes = syntheticImage();
  const hash = createHash("sha256").update(bytes).digest("hex");
  const origin = "http://127.0.0.1:3100";
  const caseTitle = `SYNTHETIC image investigation ${Date.now()}`;
  const created = await (
    await page.request.post("/api/workspace", {
      headers: { origin },
      data: {
        type: "case",
        title: caseTitle,
        notes:
          "Synthetic camera metadata fixture only; no real person, location or case.",
      },
    })
  ).json();
  await page.goto(`/?case=${created.id}`);
  await page.locator("input[type=file]").setInputFiles({
    name: "SYNTHETIC-metadata.png",
    mimeType: "image/png",
    buffer: bytes,
  });
  await expect(page.getByLabel("Attached files")).toContainText(
    "SYNTHETIC-metadata.png",
  );
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill(
      "SYNTHETIC offline image investigation: examine this supplied test image and report its useful embedded camera, time and location information, with limitations. Do not search the web. The image and all its tags are synthetic; do not infer a real place or person.",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  const reply = page.locator(".chat-message.assistant .message-text").last();
  await expect(reply).toContainText(/2020/, { timeout: 140000 });
  await expect(
    page.getByRole("button", { name: "Stop reply", exact: true }),
  ).toHaveCount(0, { timeout: 25000 });
  await expect(reply).toContainText(/SYNTHETIC camera/i);
  const inspector = page.getByRole("article", { name: "Selected graph item" });
  await expect(inspector).toContainText("SHA-256");
  await expect(inspector).toContainText(hash);
  await expect(inspector).toContainText("DateTimeOriginal");
  await expect(inspector).toContainText("GPSLatitude");
  await expect(inspector).not.toContainText("System:FileModifyDate");
  await page.reload();
  await page.getByRole("button", { name: "View run", exact: true }).click();
  await expect(inspector).toContainText("DateTimeOriginal");
  await expect(inspector).toContainText(hash);
  const attachment = page
    .locator(".message-attachments")
    .getByRole("link", { name: /SYNTHETIC-metadata/ })
    .first();
  const response = await page.request.get(
    (await attachment.getAttribute("href"))!,
  );
  expect(response.status()).toBe(200);
  expect(
    createHash("sha256")
      .update(await response.body())
      .digest("hex"),
  ).toBe(hash);
  await page.screenshot({
    path: "test-results/metadata-chat.png",
    fullPage: true,
  });
  await page
    .getByRole("button", {
      name: `Case options: ${caseTitle}`,
      exact: true,
    })
    .click();
  await page
    .getByRole("menuitem", { name: "Create knowledge graph", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("Case knowledge graph");
  await expect(
    page.locator(".board-scroll svg image[href^='data:image/png']"),
  ).toHaveCount(1);
  await page
    .getByRole("button", { name: "Generate with ImageGen", exact: true })
    .click();
  await expect(page.locator(".board-status")).toContainText(
    "ImageGen is creating",
    { timeout: 20000 },
  );
  const generated = page.getByRole("img", {
    name: "ImageGen case knowledge graph",
    exact: true,
  });
  await expect(generated).toBeVisible({ timeout: 330000 });
  await expect
    .poll(() =>
      generated.evaluate(
        (img: HTMLImageElement) => img.complete && img.naturalWidth >= 512,
      ),
    )
    .toBe(true);
  const imageUrl = (await generated.getAttribute("src"))!;
  const saved = await page.request.get(imageUrl);
  expect(saved.status()).toBe(200);
  expect(saved.headers()["content-type"]).toMatch(/^image\//);
  expect((await saved.body()).length).toBeGreaterThan(10000);
  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download image", exact: true })
    .click();
  await (
    await downloadPromise
  ).saveAs("test-results/SYNTHETIC-case-board-generated.png");
  await page.screenshot({
    path: "test-results/case-board-imagegen.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "Source cards", exact: true }).click();
  await page
    .getByRole("button", {
      name: "Inspect SYNTHETIC-metadata.png",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("complementary", { name: "Board card details" }),
  ).toContainText(hash);
  await page.getByRole("button", { name: "Close card details" }).click();
  const sourceDownload = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export source cards", exact: true })
    .click();
  await (
    await sourceDownload
  ).saveAs("test-results/SYNTHETIC-case-board-sources.png");
  const otherCase = await (
    await page.request.post("/api/workspace", {
      headers: { origin },
      data: { type: "case", title: "SYNTHETIC isolated case" },
    })
  ).json();
  expect(
    (
      await page.request.get(imageUrl.replace(created.id, otherCase.id))
    ).status(),
  ).toBe(404);
  const board = await (
    await page.request.get(`/api/cases/${created.id}/board`)
  ).json();
  const photo = board.board.cards.find(
    (c: { kind: string }) => c.kind === "image",
  );
  expect(
    (
      await page.request.get(
        `/api/cases/${otherCase.id}/board/image?chat=${photo.chatId}&name=${encodeURIComponent(photo.file)}`,
      )
    ).status(),
  ).toBe(404);
  await page.reload();
  await page
    .getByRole("button", {
      name: `Case options: ${caseTitle}`,
      exact: true,
    })
    .click();
  await page
    .getByRole("menuitem", { name: "Create knowledge graph", exact: true })
    .click();
  await expect(generated).toBeVisible();
  expect(await generated.getAttribute("src")).toBe(imageUrl);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await page
    .getByRole("button", { name: "Open navigation", exact: true })
    .click();
  await page
    .getByRole("button", { name: `Case options: ${caseTitle}`, exact: true })
    .click();
  await page
    .getByRole("menuitem", { name: "Create knowledge graph", exact: true })
    .click();
  await expect(generated).toBeVisible();
  await expect
    .poll(() =>
      page
        .locator(".board-scroll")
        .evaluate((el) => el.scrollWidth <= el.clientWidth + 1),
    )
    .toBe(true);
  await expect(
    page.getByRole("button", { name: "Close knowledge graph" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/case-board-mobile.png",
    fullPage: true,
  });
});

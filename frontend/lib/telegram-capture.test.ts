import { expect, test, vi } from "vitest";
import { createHmac } from "node:crypto";
import { copyFile, mkdir, mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { persistTelegramCapture } from "./telegram-capture";

test("the app commits signed CLI receipts locally and rejects altered output without changing the cursor", async () => {
  const source = process.cwd();
  const root = await mkdtemp(path.join(tmpdir(), "SYNTHETIC-capture-"));
  const scripts = path.join(root, "skills/darknetra-osint/scripts");
  await mkdir(scripts, { recursive: true });
  for (const file of ["telegram.mjs", "telegram-commit.mjs"])
    await copyFile(
      path.join(source, "skills/darknetra-osint/scripts", file),
      path.join(scripts, file),
    );
  const token = "123456:SYNTHETIC_token";
  try {
    vi.spyOn(process, "cwd").mockReturnValue(root);
    vi.stubEnv("TELEGRAM_BOT_TOKEN", token);
    vi.stubEnv("TELEGRAM_CHAT_ID", "-100123");
    const payload = JSON.stringify({
      bot: { id: 123456, is_bot: true, username: "SYNTHETIC_bot" },
      chatId: "-100123",
      updates: [
        {
          update_id: 55,
          message: {
            message_id: 55,
            date: 1700000000,
            chat: { id: -100123 },
            text: "SYNTHETIC source",
          },
        },
      ],
    });
    const receipt = {
      payload,
      signature: createHmac("sha256", token).update(payload).digest("hex"),
    };
    const output = (value: typeof receipt) =>
      JSON.stringify({
        ok: true,
        data: { provider: "telegram", pendingStorage: true, receipt: value },
      });
    const command =
      "node .agents/skills/darknetra-osint/scripts/osint.mjs telegram-read '-100123'";
    expect(await persistTelegramCapture(command, output(receipt))).toContain(
      "1 new messages",
    );
    const archivePath = path.join(root, ".codex-chat/telegram/123456.json");
    const archive = await readFile(archivePath, "utf8");
    expect(JSON.parse(archive).nextOffset).toBe(56);
    expect(archive).not.toContain(token);
    expect(
      await persistTelegramCapture(
        command,
        output({
          ...receipt,
          payload: payload.replace("SYNTHETIC source", "SYNTHETIC forged"),
        }),
      ),
    ).toContain("could not be saved");
    expect(await readFile(archivePath, "utf8")).toBe(archive);
    expect(await persistTelegramCapture(command, output(receipt))).toContain(
      "0 new messages",
    );
  } finally {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    await rm(root, { recursive: true, force: true });
  }
});

import { execFile } from "node:child_process";
import path from "node:path";

const state = globalThis as typeof globalThis & {
  telegramCaptureQueue?: Promise<unknown>;
};

/** Persists only reader-signed Telegram captures. Never sends or fetches messages. */
export async function persistTelegramCapture(
  command = "",
  output = "",
): Promise<string | undefined> {
  if (
    !/osint\.mjs["']?\s+telegram-read\b/.test(command) ||
    output.length > 4 * 1024 * 1024
  )
    return;
  let receipt;
  try {
    const data = JSON.parse(output);
    if (
      data.ok !== true ||
      data.data?.provider !== "telegram" ||
      data.data.pendingStorage !== true ||
      !data.data.receipt
    )
      return;
    receipt = JSON.stringify(data.data.receipt);
  } catch {
    return;
  }
  const operation = (state.telegramCaptureQueue || Promise.resolve()).then(
    () =>
      new Promise<string>((resolve) => {
        const child = execFile(
          process.execPath,
          [
            path.resolve(
              process.cwd(),
              "skills/darknetra-osint/scripts/telegram-commit.mjs",
            ),
          ],
          { timeout: 10000, maxBuffer: 4096, windowsHide: true },
          (error, stdout) => {
            try {
              const saved = JSON.parse(stdout);
              if (
                !error &&
                saved.ok === true &&
                Number.isInteger(saved.newCount) &&
                Number.isInteger(saved.savedCount)
              ) {
                resolve(
                  `Telegram capture saved: ${saved.newCount} new messages; ${saved.savedCount} recorded in the configured source archive.`,
                );
                return;
              }
            } catch {
              /* Never expose credential-bearing subprocess diagnostics. */
            }
            resolve(
              "Telegram messages were received, but the local capture could not be saved. The cursor was not advanced; storage needs review.",
            );
          },
        );
        child.stdin?.on("error", () => {});
        child.stdin?.end(receipt);
      }),
  );
  state.telegramCaptureQueue = operation.catch(() => {});
  return operation;
}

import { createHash } from "node:crypto";
import {
  mkdir,
  readFile,
  readdir,
  realpath,
  stat,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { homedir } from "node:os";
import type { GeneratedBoardImage } from "./chat-types";
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
export function boardImageDirectory(chatId: string) {
  if (!uuid.test(chatId)) throw Error("Board not found");
  return path.resolve(
    process.env.CODEX_CHAT_DATA_DIR || ".codex-chat",
    "board-images",
    chatId,
  );
}
// Codex's native ImageGen stores output under generated_images/<thread_id>/.
// Use the actual thread.started event, never a path supplied by model text.
export async function saveBoardImage(
  sessionId: string,
  chatId: string,
): Promise<GeneratedBoardImage | undefined> {
  if (!uuid.test(sessionId)) throw Error("Invalid generation session");
  const expected = path.resolve(
    process.env.CODEX_HOME || path.join(homedir(), ".codex"),
    "generated_images",
  );
  const directory = path.join(expected, sessionId);
  let root: string, folder: string;
  try {
    root = await realpath(expected);
    folder = await realpath(directory);
  } catch {
    return;
  }
  if (path.dirname(folder) !== root || path.basename(folder) !== sessionId)
    throw Error("Image must belong to the current generation session");
  for (const name of (await readdir(folder)).sort().reverse()) {
    if (!/\.(?:png|jpe?g|webp)$/i.test(name)) continue;
    const source = await realpath(path.join(folder, name));
    if (path.dirname(source) !== folder) continue;
    const info = await stat(source);
    if (!info.isFile() || info.size > 32 * 1024 * 1024) continue;
    const bytes = await readFile(source),
      hex = bytes.subarray(0, 12).toString("hex");
    const extension = hex.startsWith("89504e470d0a1a0a")
      ? "png"
      : hex.startsWith("ffd8ff")
        ? "jpg"
        : bytes.subarray(0, 4).toString() === "RIFF" &&
            bytes.subarray(8, 12).toString() === "WEBP"
          ? "webp"
          : undefined;
    if (!extension) continue;
    const sha256 = createHash("sha256").update(bytes).digest("hex");
    const file = `${sha256}.${extension}`;
    const output = boardImageDirectory(chatId);
    await mkdir(output, { recursive: true, mode: 0o700 });
    try {
      await writeFile(path.join(output, file), bytes, {
        flag: "wx",
        mode: 0o600,
      });
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
    }
    return { file, sha256, size: bytes.length, provider: "imagegen" };
  }
}

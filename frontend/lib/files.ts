import { randomUUID } from "node:crypto";
import { mkdir, open, realpath, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { loadWorkspace } from "./store";
import type { ChatAttachment } from "./chat-types";

export const MAX_FILE_BYTES = 32 * 1024 * 1024;
export function chatInputDirectory(chatId: string) {
  if (!/^[a-f0-9-]{36}$/i.test(chatId)) throw new Error("Chat not found");
  return path.resolve(
    process.env.CODEX_CHAT_DATA_DIR || ".codex-chat",
    "inputs",
    chatId,
  );
}

export async function requireChat(chatId: string) {
  if (!(await loadWorkspace()).chats.some((chat) => chat.id === chatId))
    throw new Error("Chat not found");
}

export async function attachment(
  chatId: string,
  name: string,
): Promise<ChatAttachment & { path: string; image: boolean }> {
  if (!/^[a-f0-9-]{36}_[a-zA-Z0-9._-]{1,160}$/.test(name))
    throw new Error("File not found");
  try {
    const root = await realpath(chatInputDirectory(chatId));
    const file = await realpath(path.join(root, name));
    if (path.dirname(file) !== root) throw new Error("File not found");
    const info = await stat(file);
    if (!info.isFile() || info.size > MAX_FILE_BYTES)
      throw new Error("File not found");
    const handle = await open(file, "r");
    const header = Buffer.alloc(12);
    try {
      await handle.read(header, 0, 12, 0);
    } finally {
      await handle.close();
    }
    const image =
      header
        .subarray(0, 8)
        .equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])) ||
      header.subarray(0, 3).equals(Buffer.from([255, 216, 255])) ||
      (header.toString("ascii", 0, 4) === "RIFF" &&
        header.toString("ascii", 8, 12) === "WEBP");
    return { name, label: name.slice(37), size: info.size, path: file, image };
  } catch {
    throw new Error("File not found");
  }
}

export async function saveUpload(
  chatId: string,
  request: Request,
): Promise<ChatAttachment> {
  await requireChat(chatId);
  const type = request.headers.get("content-type") || "";
  if (!type.startsWith("multipart/form-data;"))
    throw new Error("Choose a file to upload.");
  const limit = MAX_FILE_BYTES + 64 * 1024;
  if (Number(request.headers.get("content-length")) > limit)
    throw new Error("Files must be 32 MiB or smaller.");
  const reader = request.body?.getReader();
  if (!reader) throw new Error("Choose a file to upload.");
  const chunks: Uint8Array[] = [];
  let bytes = 0;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    bytes += value.byteLength;
    if (bytes > limit) {
      await reader.cancel();
      throw new Error("Files must be 32 MiB or smaller.");
    }
    chunks.push(value);
  }
  const form = await new Response(Buffer.concat(chunks), {
    headers: { "content-type": type },
  }).formData();
  const file = form.get("file");
  if (!(file instanceof File) || form.getAll("file").length !== 1)
    throw new Error("Upload one file at a time.");
  if (file.size > MAX_FILE_BYTES)
    throw new Error("Files must be 32 MiB or smaller.");
  const label =
    file.name
      .replaceAll("\\", "/")
      .split("/")
      .at(-1)!
      .replace(/[^a-zA-Z0-9._-]/g, "_")
      .slice(-160) || "file";
  const name = `${randomUUID()}_${label}`;
  const folder = chatInputDirectory(chatId);
  await mkdir(folder, { recursive: true });
  await writeFile(
    path.join(folder, name),
    Buffer.from(await file.arrayBuffer()),
    { flag: "wx", mode: 0o600 },
  );
  return { name, label, size: file.size };
}

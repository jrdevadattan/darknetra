import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createChat } from "./store";
import { attachment, saveUpload, MAX_FILE_BYTES } from "./files";

let folder: string;
beforeEach(async () => {
  folder = await mkdtemp(path.join(tmpdir(), "darknetra-SYNTHETIC-upload-"));
  vi.stubEnv("CODEX_CHAT_DATA_DIR", folder);
});
afterEach(async () => {
  vi.unstubAllEnvs();
  await rm(folder, { recursive: true, force: true });
});

test("uploads get unique names and cannot be retrieved from another chat", async () => {
  const first = await createChat();
  const second = await createChat();
  const request = () => {
    const form = new FormData();
    form.append("file", new File(["SYNTHETIC upload"], "../../notes.txt"));
    return new Request("http://localhost/api/chat/files", {
      method: "POST",
      body: form,
    });
  };
  const file = await saveUpload(first.id, request());
  const duplicate = await saveUpload(first.id, request());
  expect(file.name).not.toEqual(duplicate.name);
  expect(file.label).toEqual("notes.txt");
  await expect(attachment(first.id, file.name)).resolves.toMatchObject({
    size: 16,
    image: false,
  });
  await expect(attachment(second.id, file.name)).rejects.toThrow(
    "File not found",
  );
  await expect(attachment(first.id, "../workspace.json")).rejects.toThrow(
    "File not found",
  );
});

test("oversized bodies are rejected before multipart parsing", async () => {
  const chat = await createChat();
  await expect(
    saveUpload(
      chat.id,
      new Request("http://localhost/files", {
        method: "POST",
        headers: {
          "content-type": "multipart/form-data; boundary=SYNTHETIC",
          "content-length": String(MAX_FILE_BYTES + 65537),
        },
        body: "SYNTHETIC",
      }),
    ),
  ).rejects.toThrow("32 MiB");
});

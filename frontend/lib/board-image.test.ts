import { afterEach, expect, test, vi } from "vitest";
import {
  mkdtemp,
  mkdir,
  readFile,
  rm,
  writeFile,
  symlink,
} from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import { saveBoardImage } from "./board-image";
let temp = "";
afterEach(async () => {
  vi.unstubAllEnvs();
  if (temp) await rm(temp, { recursive: true, force: true });
});
test("ImageGen capture is restricted to the actual CLI session and saves immutable image bytes", async () => {
  temp = await mkdtemp(path.join(tmpdir(), "SYNTHETIC-board-"));
  vi.stubEnv("CODEX_HOME", path.join(temp, "runtime"));
  vi.stubEnv("CODEX_CHAT_DATA_DIR", path.join(temp, "data"));
  const session = "11111111-1111-4111-8111-111111111111",
    chat = "22222222-2222-4222-8222-222222222222";
  const source = path.join(temp, "runtime", "generated_images", session);
  await mkdir(source, { recursive: true });
  const bytes = Buffer.from("89504e470d0a1a0a53594e544845544943", "hex");
  await writeFile(path.join(source, "SYNTHETIC.png"), bytes);
  const image = await saveBoardImage(session, chat);
  expect(image).toMatchObject({
    sha256: expect.stringMatching(/^[a-f0-9]{64}$/),
    size: bytes.length,
  });
  expect(
    await readFile(path.join(temp, "data", "board-images", chat, image!.file)),
  ).toEqual(bytes);
  await expect(
    saveBoardImage("33333333-3333-4333-8333-333333333333", chat),
  ).resolves.toBeUndefined();
  await expect(saveBoardImage("../other", chat)).rejects.toThrow();
  const escaped = "44444444-4444-4444-8444-444444444444";
  await mkdir(path.join(temp, "outside"));
  await writeFile(path.join(temp, "outside", "SYNTHETIC.png"), bytes);
  await symlink(
    path.join(temp, "outside"),
    path.join(temp, "runtime", "generated_images", escaped),
    process.platform === "win32" ? "junction" : "dir",
  );
  await expect(saveBoardImage(escaped, chat)).rejects.toThrow();
});

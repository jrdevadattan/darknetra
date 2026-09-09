import { expect, test } from "vitest";
import { mkdtemp, mkdir, writeFile, symlink, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { inputFile, analyzeFile } from "./files.mjs";

test("offline analysis rejects missing files, traversal and symlinks to another chat", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "darknetra-SYNTHETIC-"));
  const previous = process.env.DARKNETRA_INPUT_DIR;
  try {
    const inputs = path.join(root, "chat-a");
    const other = path.join(root, "chat-b");
    await mkdir(inputs);
    await mkdir(other);
    await writeFile(path.join(inputs, "sample.txt"), "SYNTHETIC");
    await writeFile(path.join(other, "private.txt"), "SYNTHETIC OTHER CHAT");
    await symlink(
      other,
      path.join(inputs, "link"),
      process.platform === "win32" ? "junction" : "dir",
    );
    process.env.DARKNETRA_INPUT_DIR = inputs;
    await expect(inputFile("../chat-b/private.txt")).rejects.toThrow("inside");
    await expect(inputFile("link/private.txt")).rejects.toThrow("inside");
    await expect(inputFile("missing.txt")).rejects.toThrow("missing");
    await expect(inputFile(path.join(other, "private.txt"))).rejects.toThrow(
      "filename",
    );
    await expect(analyzeFile("file-info", "sample.txt")).resolves.toMatchObject(
      {
        file: "sample.txt",
        size: 9,
        sha256: expect.stringMatching(/^[a-f0-9]{64}$/),
      },
    );
    await expect(analyzeFile('file-text','sample.txt')).resolves.toMatchObject({text:'SYNTHETIC',truncated:false});
    await writeFile(path.join(inputs,'long.txt'),'SYNTHETIC '.repeat(2000));
    const long = await analyzeFile('file-text','long.txt');
    expect(long.truncated).toBe(true);
    expect(long.text).toHaveLength(16000);
    await writeFile(path.join(inputs,'binary.dat'),Buffer.from([0,0,0,0]));
    await expect(analyzeFile('file-text','binary.dat')).rejects.toThrow('binary');
    await writeFile(
      path.join(inputs, "rules.yar"),
      'include "../chat-b/private.txt"',
    );
    await expect(
      analyzeFile("yara", "sample.txt", "rules.yar"),
    ).rejects.toThrow("without includes");
  } finally {
    if (previous === undefined) delete process.env.DARKNETRA_INPUT_DIR;
    else process.env.DARKNETRA_INPUT_DIR = previous;
    await rm(root, { recursive: true, force: true });
  }
});

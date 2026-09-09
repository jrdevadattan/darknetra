import { mkdir, realpath, symlink } from "node:fs/promises";
import path from "node:path";
import { chatInputDirectory } from "./files";

/** A repo-scoped skill, discoverable by Codex before its first model request. */
export async function prepareSkills(directory: string) {
  if (process.env.TELEGRAM_BOT_TOKEN && process.env.TELEGRAM_CHAT_ID)
    await mkdir(path.resolve(process.cwd(), ".codex-chat", "telegram"), {
      recursive: true,
      mode: 0o700,
    });
  const skillName = "darknetra-osint";
  const source = path.resolve(process.cwd(), "skills", skillName);
  const folder = path.join(directory, ".agents", "skills");
  const target = path.join(folder, skillName);
  await mkdir(folder, { recursive: true });
  try {
    await symlink(
      source,
      target,
      process.platform === "win32" ? "junction" : "dir",
    );
  } catch (error) {
    if (
      (error as NodeJS.ErrnoException).code !== "EEXIST" ||
      (await realpath(target)) !== (await realpath(source))
    )
      throw error;
  }
  const inputDirectory = chatInputDirectory(path.basename(directory));
  await mkdir(inputDirectory, { recursive: true });
  return inputDirectory;
}

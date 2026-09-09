import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { homedir } from "node:os";
import path from "node:path";

// Use the CLI's documented metadata API to clear the previous objective before
// a new user-requested Netra run. No model turn or network listener is started.
export function clearNativeGoal(sessionId: string): Promise<void> {
  if (!/^[a-f0-9-]{36}$/i.test(sessionId))
    return Promise.reject(new Error("Invalid investigation session"));
  const root = process.env.CODEX_HOME;
  if (!root || path.resolve(root) === path.join(homedir(), ".codex"))
    return Promise.reject(
      new Error(
        "Netra requires the app's private CLI home. Use the Docker app.",
      ),
    );
  return new Promise((resolve, reject) => {
    const child = spawn(
      process.env.CODEX_BIN || "codex",
      [
        "app-server",
        "--stdio",
        "-c",
        "features.goals=true",
        "-c",
        "features.apps=false",
        "-c",
        "features.plugins=false",
        "-c",
        "features.remote_plugin=false",
        "-c",
        "features.hooks=false",
      ],
      {
        cwd: root,
        shell: false,
        windowsHide: true,
        stdio: "pipe",
        env: process.env,
      },
    );
    let settled = false;
    const lines = createInterface({ input: child.stdout });
    const finish = (error?: Error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      lines.close();
      child.kill();
      if (error) reject(error);
      else resolve();
    };
    const timer = setTimeout(
      () =>
        finish(
          new Error(
            "The CLI did not acknowledge the new investigation request.",
          ),
        ),
      10_000,
    );
    const send = (id: number, method: string, params: unknown) =>
      child.stdin.write(
        JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n",
      );
    child.stderr.resume();
    child.on("error", () =>
      finish(new Error("Could not open the CLI goal controls.")),
    );
    child.on("close", () =>
      finish(
        new Error(
          "The CLI goal controls closed before confirming the request.",
        ),
      ),
    );
    child.stdin.on("error", () =>
      finish(new Error("Could not send the goal request to the CLI.")),
    );
    lines.on("line", (line) => {
      try {
        const reply = JSON.parse(line);
        if (![1, 2].includes(reply.id)) return;
        if (reply.error)
          return finish(
            new Error(
              "The CLI could not reset this chat's previous objective.",
            ),
          );
        if (reply.id === 1 && reply.result) {
          child.stdin.write(
            JSON.stringify({
              jsonrpc: "2.0",
              method: "initialized",
              params: {},
            }) + "\n",
          );
          send(2, "thread/goal/clear", { threadId: sessionId });
        } else if (reply.id === 2 && typeof reply.result?.cleared === "boolean")
          finish();
      } catch {
        /* Ignore non-protocol diagnostics; never expose their content. */
      }
    });
    send(1, "initialize", {
      clientInfo: { name: "darknetra_goal_control", version: "0.1.0" },
      capabilities: { experimentalApi: true },
    });
  });
}

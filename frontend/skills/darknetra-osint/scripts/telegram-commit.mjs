// Internal CLI persistence entrypoint, invoked by the app's save process only.
import { telegramCommit } from "./telegram.mjs";
let input = "";
process.stdin.setEncoding("utf8");
try {
  for await (const chunk of process.stdin) {
    input += chunk.toString();
    if (Buffer.byteLength(input) > 4 * 1024 * 1024) throw new Error();
  }
  const saved = await telegramCommit(JSON.parse(input));
  console.log(
    JSON.stringify({
      ok: true,
      newCount: saved.newCount,
      savedCount: saved.savedCount,
    }),
  );
} catch {
  console.log(JSON.stringify({ ok: false }));
  process.exitCode = 1;
}

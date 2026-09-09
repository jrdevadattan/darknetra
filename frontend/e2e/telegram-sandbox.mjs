// Run only inside a disposable verification container. No real updates are consumed.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { telegramCommit } from "/app/skills/darknetra-osint/scripts/telegram.mjs";

const args = [
  "sandbox",
  "-P",
  "research",
  "-c",
  'permissions.research.extends=":read-only"',
  "-c",
  "permissions.research.network.enabled=true",
  "-c",
  "features.use_legacy_landlock=true",
  "--",
  "node",
];
const directory = `/app/.codex-chat/telegram/SYNTHETIC-${randomUUID()}`;
const env = {
  TELEGRAM_BOT_TOKEN: "123456:SYNTHETIC_token",
  TELEGRAM_CHAT_ID: "-100123",
};
const synthetic = `
  import assert from 'node:assert/strict';
  import { writeFile, readFile } from 'node:fs/promises';
  import { telegramRead } from '/app/skills/darknetra-osint/scripts/telegram.mjs';
  const result = await telegramRead('-100123', {
    env: { ...${JSON.stringify(env)}, DARKNETRA_TELEGRAM_READ_ONLY: '1' },
    directory: ${JSON.stringify(directory)},
    call: async (method) => {
      if(method === 'getMe') return {id:123456,is_bot:true,username:'SYNTHETIC_bot'};
      if(method === 'getWebhookInfo') return {url:''};
      if(method === 'getUpdates') return [{update_id:10,message:{message_id:10,date:1700000000,chat:{id:-100123,title:'SYNTHETIC group'},text:'SYNTHETIC captured message'}}];
      throw new Error('Unexpected SYNTHETIC operation');
    }
  });
  assert.equal(result.pendingStorage, true);
  assert.equal(result.savedCount, 0);
  await assert.rejects(readFile(result.archivePath), {code:'ENOENT'});
  await assert.rejects(writeFile('/app/.codex-chat/SYNTHETIC-denied.txt','SYNTHETIC'), {code:'EACCES'});
  await assert.rejects(writeFile('/app/SYNTHETIC-denied.txt','SYNTHETIC'), {code:'EACCES'});
  console.log(JSON.stringify(result.receipt));
`;
const receipt = JSON.parse(
  execFileSync("codex", [...args, "--input-type=module", "-e", synthetic], {
    encoding: "utf8",
  }),
);
const saved = await telegramCommit(receipt, { env, directory });
assert.equal(saved.savedCount, 1);
assert.equal((await telegramCommit(receipt, { env, directory })).newCount, 0);
console.log(
  JSON.stringify({
    syntheticCaptureSaved: true,
    readOnlySandboxVerified: true,
    replayDeduplicated: true,
  }),
);
const status = JSON.parse(
  execFileSync(
    "codex",
    [
      ...args,
      "/app/skills/darknetra-osint/scripts/osint.mjs",
      "telegram-status",
    ],
    { encoding: "utf8" },
  ),
);
assert.equal(status.ok, true);
assert.equal(status.data.receivesOrdinaryMessages, true);
assert.equal(status.data.webhookConfigured, false);
console.log(
  JSON.stringify({ liveBotAccessVerified: true, realMessagesConsumed: false }),
);

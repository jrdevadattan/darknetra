import { test, expect } from "vitest";
import { mkdtemp, readFile, writeFile, mkdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import {
  telegramRead,
  telegramStatus,
  telegramJson,
  telegramCommit,
} from "./telegram.mjs";

const env = {
  TELEGRAM_BOT_TOKEN: "123456:SYNTHETIC_token",
  TELEGRAM_CHAT_ID: "-100123",
};
const bot = { id: 123456, is_bot: true, username: "SYNTHETIC_bot" };
const message = (id, chat = -100123, text = "SYNTHETIC message") => ({
  update_id: id,
  message: {
    message_id: id,
    date: 1700000000,
    chat: { id: chat, title: "SYNTHETIC group", type: "supergroup" },
    text,
  },
});
async function fixture(run) {
  const directory = await mkdtemp(path.join(tmpdir(), "SYNTHETIC-telegram-"));
  try {
    await run(directory);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}
function transport(updates, seen = []) {
  return async (method, params) => {
    seen.push({ method, params });
    if (method === "getMe") return bot;
    if (method === "getWebhookInfo") return { url: "" };
    if (method === "getChatMember") return { status: "administrator" };
    if (method === "getChat")
      return {
        id: -100123,
        title: "SYNTHETIC group",
        username: "SYNTHETIC_group",
        type: "supergroup",
      };
    if (method === "getUpdates") return updates;
    throw new Error("Unexpected SYNTHETIC API call");
  };
}

test("reader persists only the configured chat before advancing its durable cursor, deduplicating replay", async () =>
  fixture(async (directory) => {
    const seen = [];
    const options = {
      env,
      directory,
      call: transport(
        [message(10), message(11, -999, "SYNTHETIC unrelated private text")],
        seen,
      ),
    };
    const first = await telegramRead("-100123", options);
    expect(first.savedCount).toBe(1);
    const saved = JSON.parse(await readFile(first.archivePath, "utf8"));
    expect(saved.nextOffset).toBe(12);
    expect(saved.messages).toHaveLength(1);
    expect(JSON.stringify(saved)).not.toContain("unrelated");
    expect(JSON.stringify(saved)).not.toContain(env.TELEGRAM_BOT_TOKEN);
    const second = await telegramRead("-100123", options);
    expect(second.savedCount).toBe(1);
    expect(second.newCount).toBe(0);
    expect(seen.filter((x) => x.method === "getUpdates")[1].params.offset).toBe(
      12,
    );
  }));

test("reader rejects absent or mismatched chat binding before any network access", async () => {
  const call = async () => {
    throw new Error("SYNTHETIC network must not run");
  };
  await expect(telegramRead("-999", { env, call })).rejects.toMatchObject({
    code: "POLICY_DENIED",
  });
  await expect(
    telegramRead("-100123", {
      env: { TELEGRAM_BOT_TOKEN: env.TELEGRAM_BOT_TOKEN },
      call,
    }),
  ).rejects.toMatchObject({ code: "CONFIGURATION" });
});

test("active webhooks and concurrent readers do not consume updates or change stored data", async () =>
  fixture(async (directory) => {
    const call = async (method) => {
      if (method === "getMe") return bot;
      if (method === "getWebhookInfo")
        return { url: "https://example.com/SYNTHETIC" };
      throw new Error("SYNTHETIC getUpdates must not run");
    };
    await expect(
      telegramRead("-100123", { env, directory, call }),
    ).rejects.toMatchObject({ code: "CONFIGURATION" });
    await mkdir(path.join(directory, "123456.lock"));
    await expect(
      telegramRead("-100123", { env, directory, call: transport([]) }),
    ).rejects.toMatchObject({ code: "CONFIGURATION" });
  }));

test("corrupt archives fail closed instead of resetting the cursor or discarding data", async () =>
  fixture(async (directory) => {
    const archive = path.join(directory, "123456.json");
    await writeFile(archive, "SYNTHETIC broken JSON");
    await expect(
      telegramRead("-100123", { env, directory, call: transport([]) }),
    ).rejects.toMatchObject({ code: "CONFIGURATION" });
    expect(await readFile(archive, "utf8")).toBe("SYNTHETIC broken JSON");
  }));

test("channel posts and edits are preserved as distinct events and an empty poll retains saved history", async () =>
  fixture(async (directory) => {
    const original = message(12).message;
    const events = [
      { update_id: 12, channel_post: original },
      {
        update_id: 13,
        edited_channel_post: {
          ...original,
          text: "SYNTHETIC edit",
          edit_date: 1700000010,
        },
      },
    ];
    await telegramRead("-100123", { env, directory, call: transport(events) });
    const result = await telegramRead("-100123", {
      env,
      directory,
      call: transport([]),
    });
    expect(result.newCount).toBe(0);
    expect(result.savedCount).toBe(2);
    expect(result.messages.map((x) => x.kind)).toEqual([
      "channel_post",
      "edited_channel_post",
    ]);
  }));

test("status reports membership and privacy limitations without exposing a token", async () => {
  const result = await telegramStatus({ env, call: transport([]) });
  expect(result).toMatchObject({
    bot: "SYNTHETIC_bot",
    membership: "administrator",
    receivesOrdinaryMessages: true,
    chatId: "-100123",
    chatUsername: "SYNTHETIC_group",
  });
  expect(JSON.stringify(result)).not.toContain(env.TELEGRAM_BOT_TOKEN);
});

test("status rejects a mismatched Telegram chat response", async () => {
  const base = transport([]);
  await expect(
    telegramStatus({
      env,
      call: (method, params) =>
        method === "getChat"
          ? Promise.resolve({ id: -999 })
          : base(method, params),
    }),
  ).rejects.toMatchObject({ code: "UPSTREAM_UNAVAILABLE" });
});

test("read-only CLI captures do not write or advance storage until their signed receipt is committed", async () =>
  fixture(async (directory) => {
    const readonly = { ...env, DARKNETRA_TELEGRAM_READ_ONLY: "1" };
    const draft = await telegramRead("-100123", {
      env: readonly,
      directory,
      call: transport([
        message(30),
        message(31, -999, "SYNTHETIC unrelated private text"),
      ]),
    });
    expect(draft.pendingStorage).toBe(true);
    expect(draft.savedCount).toBe(0);
    expect(draft.newCount).toBe(1);
    expect(JSON.stringify(draft.receipt)).not.toContain(
      "unrelated private text",
    );
    await expect(readFile(draft.archivePath)).rejects.toMatchObject({
      code: "ENOENT",
    });
    const saved = await telegramCommit(draft.receipt, { env, directory });
    expect(saved.savedCount).toBe(1);
    expect(
      JSON.parse(await readFile(saved.archivePath, "utf8")).nextOffset,
    ).toBe(32);
    expect(
      (await telegramCommit(draft.receipt, { env, directory })).newCount,
    ).toBe(0);
    await expect(
      telegramCommit(
        {
          ...draft.receipt,
          payload: draft.receipt.payload.replace(
            "SYNTHETIC message",
            "SYNTHETIC forged",
          ),
        },
        { env, directory },
      ),
    ).rejects.toMatchObject({ code: "POLICY_DENIED" });
    await expect(
      telegramCommit(draft.receipt, {
        env: { ...env, TELEGRAM_CHAT_ID: "-999" },
        directory,
      }),
    ).rejects.toMatchObject({ code: "POLICY_DENIED" });
  }));

test("transport blocks write methods, redirects and secret-bearing upstream errors", async () => {
  await expect(
    telegramJson("sendMessage", {}, env.TELEGRAM_BOT_TOKEN),
  ).rejects.toMatchObject({ code: "POLICY_DENIED" });
  let requestOptions;
  await expect(
    telegramJson("getMe", {}, env.TELEGRAM_BOT_TOKEN, async (_url, options) => {
      requestOptions = options;
      throw new Error(`SYNTHETIC leak ${env.TELEGRAM_BOT_TOKEN}`);
    }),
  ).rejects.toThrow("Telegram request failed");
  expect(requestOptions.redirect).toBe("error");
  await expect(
    telegramJson(
      "getMe",
      {},
      env.TELEGRAM_BOT_TOKEN,
      async () =>
        new Response(
          JSON.stringify({ ok: false, description: env.TELEGRAM_BOT_TOKEN }),
          { status: 401 },
        ),
    ),
  ).rejects.toThrow("Telegram authentication failed");
});

test("reader requests supported message types even when the bot previously used a different update filter", async () =>
  fixture(async (directory) => {
    const base = transport([]);
    const call = async (method, params) => {
      if (method !== "getUpdates") return base(method, params);
      const types = JSON.parse(params.allowed_updates || '["callback_query"]');
      return types.includes("message") &&
        types.includes("channel_post") &&
        types.includes("edited_message") &&
        types.includes("edited_channel_post")
        ? [message(21)]
        : [];
    };
    const result = await telegramRead("-100123", { env, directory, call });
    expect(result.newCount).toBe(1);
    expect(result.messages[0].text).toBe("SYNTHETIC message");
  }));

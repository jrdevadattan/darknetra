import { mkdir, readFile, open, rename, rmdir, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { createHmac, timingSafeEqual } from "node:crypto";

const fail = (code, message) => Object.assign(new Error(message), { code });
const METHODS = new Set([
  "getMe",
  "getWebhookInfo",
  "getChatMember",
  "getChat",
  "getUpdates",
]);
const KINDS = [
  "message",
  "channel_post",
  "edited_message",
  "edited_channel_post",
];
const MAX_ARCHIVE = 16 * 1024 * 1024;
const defaultDirectory = fileURLToPath(
  new URL("../../../.codex-chat/telegram/", import.meta.url),
);

function configuration(env) {
  const token = env.TELEGRAM_BOT_TOKEN || "";
  if (!/^\d+:[A-Za-z0-9_-]+$/.test(token))
    throw fail(
      "AUTH_REQUIRED",
      "Set TELEGRAM_BOT_TOKEN in local server configuration.",
    );
  const chatId = env.TELEGRAM_CHAT_ID || "";
  if (!/^-\d+$/.test(chatId) || !Number.isSafeInteger(Number(chatId)))
    throw fail(
      "CONFIGURATION",
      "Set TELEGRAM_CHAT_ID to the confirmed group/channel numeric ID.",
    );
  return { token, chatId };
}

// Telegram requires the token in its URL path. Never log URLs or propagate fetch errors.
// No redirects, media downloads, writes, webhook changes or automatic retries.
export async function telegramJson(method, params, token, request = fetch) {
  if (!METHODS.has(method))
    throw fail("POLICY_DENIED", "Unsupported Telegram operation.");
  const url = new URL(`https://api.telegram.org/bot${token}/${method}`);
  for (const [key, value] of Object.entries(params))
    url.searchParams.set(key, String(value));
  let response;
  try {
    response = await request(url, {
      method: "GET",
      redirect: "error",
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    throw fail("UPSTREAM_UNAVAILABLE", "Telegram request failed or timed out.");
  }
  if (!response.ok) {
    const code = response.status;
    throw fail(
      code === 401
        ? "AUTH_REQUIRED"
        : code === 429
          ? "RATE_LIMITED"
          : "UPSTREAM_UNAVAILABLE",
      code === 401
        ? "Telegram authentication failed. Check the local bot token."
        : code === 409
          ? "Telegram reports a competing update reader or webhook."
          : code === 429
            ? "Telegram rate limit reached. Wait before trying again."
            : "Telegram API request failed.",
    );
  }
  let body = "";
  try {
    let size = 0;
    const chunks = [];
    for await (const chunk of response.body) {
      size += chunk.byteLength;
      if (size > 2 * 1024 * 1024) throw new Error();
      chunks.push(Buffer.from(chunk));
    }
    body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    if (!body.ok || body.result === undefined) throw new Error();
  } catch {
    throw fail(
      "UPSTREAM_UNAVAILABLE",
      "Telegram returned an invalid or oversized response.",
    );
  }
  return body.result;
}

function client(options) {
  const config = configuration(options.env || process.env);
  return {
    ...config,
    call:
      options.call ||
      ((method, params = {}) => telegramJson(method, params, config.token)),
  };
}

async function identity(call) {
  const bot = await call("getMe", {});
  if (!bot.is_bot || !Number.isSafeInteger(bot.id) || bot.id <= 0)
    throw fail(
      "UPSTREAM_UNAVAILABLE",
      "Telegram did not return a valid bot identity.",
    );
  return bot;
}

export async function telegramStatus(options = {}) {
  const { chatId, call } = client(options);
  const bot = await identity(call);
  const webhook = await call("getWebhookInfo", {});
  const member = await call("getChatMember", {
    chat_id: chatId,
    user_id: bot.id,
  });
  const chat = await call("getChat", { chat_id: chatId });
  if (String(chat.id) !== chatId)
    throw fail(
      "UPSTREAM_UNAVAILABLE",
      "Telegram returned a different chat binding.",
    );
  return {
    provider: "telegram",
    bot: bot.username,
    botId: bot.id,
    chatId,
    chatTitle: String(chat.title || "").slice(0, 256),
    chatUsername: typeof chat.username === "string" ? chat.username : undefined,
    chatType: chat.type,
    webhookConfigured: Boolean(webhook.url),
    membership: member.status,
    receivesOrdinaryMessages:
      member.status === "administrator" ||
      (member.status === "member" && bot.can_read_all_group_messages === true),
    text: "Bot status only; no messages consumed. History from before the bot joined is unavailable. Collection runs on demand.",
  };
}

function event(update, chatId) {
  const kind = KINDS.find((key) => update[key]);
  const message = kind && update[kind];
  if (!message || String(message.chat?.id) !== chatId) return null;
  if (
    !Number.isSafeInteger(message.message_id) ||
    !Number.isSafeInteger(message.date)
  )
    throw fail(
      "UPSTREAM_UNAVAILABLE",
      "Telegram returned a malformed message.",
    );
  const timestamp = new Date(message.date * 1000);
  if (Number.isNaN(timestamp.valueOf()))
    throw fail(
      "UPSTREAM_UNAVAILABLE",
      "Telegram returned an invalid message date.",
    );
  return {
    updateId: update.update_id,
    messageId: message.message_id,
    chatId,
    chatTitle: String(message.chat.title || "").slice(0, 256),
    kind,
    date: timestamp.toISOString(),
    text:
      typeof message.text === "string"
        ? message.text
        : typeof message.caption === "string"
          ? message.caption
          : "",
    senderId: message.from?.id ?? message.sender_chat?.id ?? null,
    senderName:
      message.from?.username ||
      message.sender_chat?.title ||
      message.from?.first_name ||
      null,
    hasMedia: Boolean(
      message.photo ||
      message.video ||
      message.document ||
      message.audio ||
      message.voice ||
      message.sticker,
    ),
  };
}

export async function telegramRead(requestedChatId, options = {}) {
  const { chatId, call, token } = client(options);
  const deferred =
    (options.env || process.env).DARKNETRA_TELEGRAM_READ_ONLY === "1";
  if (requestedChatId !== chatId)
    throw fail(
      "POLICY_DENIED",
      "Request exactly the configured Telegram chat ID. Other chats are not available.",
    );
  const bot = await identity(call);
  const webhook = await call("getWebhookInfo", {});
  if (webhook.url)
    throw fail(
      "CONFIGURATION",
      "This bot has an active webhook. The reader will not replace it.",
    );
  const directory = options.directory || defaultDirectory;
  if (!deferred) await mkdir(directory, { recursive: true });
  const lock = path.join(directory, `${bot.id}.lock`);
  try {
    if (!deferred) await mkdir(lock);
  } catch {
    throw fail(
      "CONFIGURATION",
      "Telegram reader is busy or a previous run left a lock. Inspect it before retrying.",
    );
  }
  try {
    const archivePath = path.join(directory, `${bot.id}.json`);
    let archive = {
      version: 1,
      botId: bot.id,
      chatId,
      nextOffset: 0,
      messages: [],
    };
    try {
      if ((await stat(archivePath)).size > MAX_ARCHIVE) throw new Error();
      archive = JSON.parse(await readFile(archivePath, "utf8"));
      if (
        archive.version !== 1 ||
        archive.botId !== bot.id ||
        archive.chatId !== chatId ||
        !Number.isSafeInteger(archive.nextOffset) ||
        archive.nextOffset < 0 ||
        !Array.isArray(archive.messages) ||
        archive.messages.some(
          (m) =>
            m.chatId !== chatId ||
            !Number.isSafeInteger(m.updateId) ||
            typeof m.text !== "string",
        )
      )
        throw new Error();
    } catch (error) {
      if (error.code !== "ENOENT")
        throw fail(
          "CONFIGURATION",
          "Telegram archive is invalid, oversized or bound to another chat. Existing data was preserved.",
        );
    }
    // The offset acknowledges only the previous batch, which has already been saved.
    const updates = await call("getUpdates", {
      offset: archive.nextOffset,
      limit: 100,
      timeout: 0,
      allowed_updates: JSON.stringify(KINDS),
    });
    if (
      !Array.isArray(updates) ||
      updates.length > 100 ||
      updates.some(
        (u) => !Number.isSafeInteger(u?.update_id) || u.update_id < 0,
      )
    )
      throw fail(
        "UPSTREAM_UNAVAILABLE",
        "Telegram returned invalid updates. The cursor was not advanced.",
      );
    const previouslySaved = archive.messages.length;
    const known = new Set(archive.messages.map((m) => m.updateId));
    let newCount = 0;
    for (const update of updates) {
      const record = event(update, chatId);
      if (record && !known.has(record.updateId)) {
        archive.messages.push(record);
        known.add(record.updateId);
        newCount++;
      }
      archive.nextOffset = Math.max(archive.nextOffset, update.update_id + 1);
    }
    archive.fetchedAt = new Date().toISOString();
    const serialized = JSON.stringify(archive, null, 2);
    if (Buffer.byteLength(serialized) > MAX_ARCHIVE)
      throw fail(
        "SIZE_LIMIT",
        "Telegram archive reached its size limit. Back it up before extending storage; no existing data was removed.",
      );
    let receipt;
    if (deferred) {
      // The read-only CLI returns an authenticated capture. Only the app's existing
      // save process can commit it; no cursor is acknowledged ahead of durable storage.
      const payload = JSON.stringify({
        bot,
        chatId,
        at: archive.fetchedAt,
        updates: updates.map((update) =>
          event(update, chatId) ? update : { update_id: update.update_id },
        ),
      });
      receipt = {
        payload,
        signature: createHmac("sha256", token).update(payload).digest("hex"),
      };
    } else {
      const temporary = `${archivePath}.tmp`;
      const file = await open(temporary, "w", 0o600);
      try {
        await file.writeFile(serialized);
        await file.sync();
      } finally {
        await file.close();
      }
      await rename(temporary, archivePath);
      // Directory handles are not supported by Node on Windows. Flush rename
      // metadata on platforms that expose this operation, before releasing the lock.
      if (process.platform !== "win32") {
        const folder = await open(directory, "r");
        try {
          await folder.sync();
        } finally {
          await folder.close();
        }
      }
    }
    // Bounded output; the archive retains complete text and all captured events.
    const messages = archive.messages.slice(-20).map((m) => ({
      ...m,
      text: m.text.slice(0, 700),
      textTruncated: m.text.length > 700,
    }));
    return {
      provider: "telegram",
      bot: bot.username,
      chatId,
      fetchedAt: archive.fetchedAt,
      newCount,
      savedCount: deferred ? previouslySaved : archive.messages.length,
      pendingStorage: deferred,
      receipt,
      archivePath,
      messages,
      truncated:
        archive.messages.length > 20 || messages.some((m) => m.textTruncated),
      moreUpdatesMayBePending: updates.length === 100,
      text:
        (deferred
          ? "Messages received; local storage confirmation is pending. "
          : "") +
        (messages.length
          ? messages
              .map(
                (m) =>
                  `${m.date} ${m.senderName || "Sender"}: ${m.text || "[Non-text message; media not downloaded]"}`,
              )
              .join("\n")
          : "No messages have been captured. Send a new command to the bot in the configured chat and read again. This is not evidence that the chat has no history."),
      limitations:
        "On-demand collection of available bot updates, retained by Telegram for at most 24 hours. Not historical export. Edits are separate events; media is not downloaded and deletions are not tracked.",
    };
  } finally {
    if (!deferred) await rmdir(lock);
  }
}

// Local persistence only: verifies a reader-authenticated receipt, then reuses the
// same locked, bounded writer. No network request or model-generated facts.
export async function telegramCommit(receipt, options = {}) {
  const env = options.env || process.env;
  const { token, chatId } = configuration(env);
  if (
    !receipt ||
    typeof receipt.payload !== "string" ||
    Buffer.byteLength(receipt.payload) > 3 * 1024 * 1024 ||
    !/^[a-f0-9]{64}$/.test(receipt.signature || "")
  )
    throw fail("VALIDATION", "Invalid Telegram capture receipt.");
  const expected = createHmac("sha256", token).update(receipt.payload).digest();
  if (!timingSafeEqual(expected, Buffer.from(receipt.signature, "hex")))
    throw fail("POLICY_DENIED", "Telegram capture could not be authenticated.");
  const capture = JSON.parse(receipt.payload);
  if (
    capture.chatId !== chatId ||
    String(capture.bot?.id) !== token.split(":")[0]
  )
    throw fail(
      "POLICY_DENIED",
      "Telegram capture belongs to a different bot or chat.",
    );
  return telegramRead(chatId, {
    ...options,
    env: { ...env, DARKNETRA_TELEGRAM_READ_ONLY: "0" },
    call: async (method) => {
      if (method === "getMe") return capture.bot;
      if (method === "getWebhookInfo") return { url: "" };
      if (method === "getUpdates") return capture.updates;
      throw fail(
        "POLICY_DENIED",
        "Capture storage cannot make external requests.",
      );
    },
  });
}

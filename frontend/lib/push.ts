import webpush from "web-push";
import { randomUUID } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import type { WorkspaceNotification } from "./chat-types";

type Subscription = {
  endpoint: string;
  keys: { p256dh: string; auth: string };
};
type Device = { subscription: Subscription; failuresOnly: boolean };
type PushStore = {
  keys: { publicKey: string; privateKey: string };
  devices: Device[];
};
const shared = globalThis as typeof globalThis & {
  darknetraPushQueue?: Promise<unknown>;
};
async function update<T>(
  change: (state: PushStore) => T,
  persist = true,
): Promise<T> {
  const operation = (shared.darknetraPushQueue || Promise.resolve()).then(
    async () => {
      const file = path.join(
        process.env.CODEX_CHAT_DATA_DIR ||
          path.join(process.cwd(), ".codex-chat"),
        "push-private.json",
      );
      let state: PushStore;
      let created = false;
      try {
        state = JSON.parse(await readFile(file, "utf8"));
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ENOENT")
          throw new Error("Notification storage could not be read.");
        state = { keys: webpush.generateVAPIDKeys(), devices: [] };
        created = true;
      }
      const result = change(state);
      if (!persist && !created) return result;
      await mkdir(path.dirname(file), { recursive: true });
      const temp = file + "." + randomUUID() + ".tmp";
      await writeFile(temp, JSON.stringify(state), { mode: 0o600 });
      await rename(temp, file);
      return result;
    },
  );
  shared.darknetraPushQueue = operation.catch(() => {});
  return operation;
}

export function validateSubscription(value: unknown): Subscription {
  const v = value as Subscription;
  if (!v || typeof v.endpoint !== "string" || v.endpoint.length > 4096)
    throw new Error("Invalid browser subscription.");
  const url = new URL(v.endpoint);
  const host = url.hostname;
  const allowed =
    host === "fcm.googleapis.com" ||
    host === "web.push.apple.com" ||
    host === "updates.push.services.mozilla.com" ||
    host === "updates-autopush.stage.mozaws.net" ||
    /^(?:[a-z0-9-]+\.)+notify\.windows\.com$/.test(host);
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    (url.port && url.port !== "443") ||
    !allowed
  )
    throw new Error("This browser's push service is not supported.");
  for (const [key, size] of [
    ["p256dh", 65],
    ["auth", 16],
  ] as const) {
    const value = v.keys?.[key];
    if (
      typeof value !== "string" ||
      !/^[\w-]+={0,2}$/.test(value) ||
      Buffer.from(value, "base64url").length !== size
    )
      throw new Error("Invalid browser subscription keys.");
  }
  return {
    endpoint: v.endpoint,
    keys: { p256dh: v.keys.p256dh, auth: v.keys.auth },
  };
}
export function pushPublicKey() {
  return update((s) => s.keys.publicKey, false);
}
export function saveSubscription(value: unknown, failuresOnly: boolean) {
  const subscription = validateSubscription(value);
  return update((s) => {
    const existing = s.devices.find(
      (d) => d.subscription.endpoint === subscription.endpoint,
    );
    if (existing) Object.assign(existing, { subscription, failuresOnly });
    else {
      if (s.devices.length >= 50)
        throw new Error("Too many notification devices.");
      s.devices.push({ subscription, failuresOnly });
    }
  });
}
export function removeSubscription(endpoint: string) {
  return update((s) => {
    s.devices = s.devices.filter((d) => d.subscription.endpoint !== endpoint);
  });
}
export function subscriptionStatus(endpoint: string) {
  return update((s) => {
    const d = s.devices.find((d) => d.subscription.endpoint === endpoint);
    return { enabled: !!d, failuresOnly: d?.failuresOnly || false };
  }, false);
}

export async function deliverPush(
  notification: WorkspaceNotification,
  onlyEndpoint?: string,
) {
  const state = await update((s) => s, false);
  const devices = state.devices.filter(
    (d) =>
      (!onlyEndpoint || d.subscription.endpoint === onlyEndpoint) &&
      (onlyEndpoint || !d.failuresOnly || notification.kind === "error"),
  );
  const payload = JSON.stringify({
    title: notification.title,
    body: notification.body,
    tag: notification.id,
    url: notification.chatId
      ? `/?case=${encodeURIComponent(notification.caseId)}&chat=${encodeURIComponent(notification.chatId)}`
      : "/",
  });
  let sent = 0,
    failed = 0;
  await Promise.all(
    devices.map(async (d) => {
      try {
        await webpush.sendNotification(d.subscription, payload, {
          TTL: 3600,
          timeout: 10000,
          vapidDetails: {
            subject:
              process.env.DARKNETRA_VAPID_SUBJECT ||
              "https://darknetra.invalid",
            publicKey: state.keys.publicKey,
            privateKey: state.keys.privateKey,
          },
        });
        sent++;
      } catch (error) {
        failed++;
        if ([404, 410].includes((error as { statusCode: number }).statusCode))
          await removeSubscription(d.subscription.endpoint);
        // Provider responses may contain subscription secrets: never log/return them.
      }
    }),
  );
  return { sent, failed };
}

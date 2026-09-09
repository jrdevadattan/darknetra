import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { createECDH } from "node:crypto";
import { tmpdir } from "node:os";
import path from "node:path";
import webpush from "web-push";
import {
  deliverPush,
  pushPublicKey,
  saveSubscription,
  subscriptionStatus,
  validateSubscription,
} from "./push";
let directory: string;
beforeEach(async () => {
  directory = await mkdtemp(path.join(tmpdir(), "SYNTHETIC-push-"));
  vi.stubEnv("CODEX_CHAT_DATA_DIR", directory);
});
afterEach(async () => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  await rm(directory, { recursive: true, force: true });
});
function subscription(suffix: string) {
  const key = createECDH("prime256v1");
  key.generateKeys();
  return {
    endpoint: `https://fcm.googleapis.com/fcm/send/SYNTHETIC-${suffix}`,
    keys: {
      p256dh: key.getPublicKey().toString("base64url"),
      auth: Buffer.alloc(16).toString("base64url"),
    },
  };
}
test("push endpoints reject local/arbitrary servers and malformed keys; only public VAPID keys are exposed", async () => {
  const sub = subscription("validation");
  expect(validateSubscription(sub)).toEqual(sub);
  for (const endpoint of [
    "http://127.0.0.1:3000/",
    "https://example.com/",
    "https://fcm.googleapis.com.attacker.invalid/",
    "https://user:pass@fcm.googleapis.com/",
    "https://fcm.googleapis.com:444/",
  ])
    expect(() => validateSubscription({ ...sub, endpoint })).toThrow();
  expect(() =>
    validateSubscription({ ...sub, keys: { ...sub.keys, auth: "bad" } }),
  ).toThrow();
  const publicKey = await pushPublicKey();
  expect(Buffer.from(publicKey, "base64url")).toHaveLength(65);
  expect(await pushPublicKey()).toBe(publicKey);
  const privateStore = JSON.parse(
    await readFile(path.join(directory, "push-private.json"), "utf8"),
  );
  expect(privateStore.keys.privateKey).not.toBe(publicKey);
});
test("deliveries honor device preferences, retain generic content, and remove expired subscriptions", async () => {
  const all = subscription("all"),
    failures = subscription("failures");
  await saveSubscription(all, false);
  await saveSubscription(failures, true);
  const send = vi
    .spyOn(webpush, "sendNotification")
    .mockResolvedValue({ statusCode: 201, body: "", headers: {} });
  const notice = {
    id: "SYNTHETIC-event",
    at: new Date().toISOString(),
    kind: "complete" as const,
    title: "Monitoring check complete",
    body: "A case review is ready.",
    caseId: "SYNTHETIC-case",
    chatId: "SYNTHETIC-chat",
  };
  expect(await deliverPush(notice)).toEqual({ sent: 1, failed: 0 });
  expect(send).toHaveBeenCalledTimes(1);
  const payload = JSON.parse(send.mock.calls[0][1] as string);
  expect(payload.url).toBe("/?case=SYNTHETIC-case&chat=SYNTHETIC-chat");
  send.mockRejectedValue({
    statusCode: 410,
    body: "SYNTHETIC secret provider diagnostics",
  });
  expect(await deliverPush({ ...notice, kind: "error" })).toEqual({
    sent: 0,
    failed: 2,
  });
  expect((await subscriptionStatus(all.endpoint)).enabled).toBe(false);
  expect((await subscriptionStatus(failures.endpoint)).enabled).toBe(false);
});

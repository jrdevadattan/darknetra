self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) =>
  event.waitUntil(self.clients.claim()),
);
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    /* Generic fallback. */
  }
  const url = new URL(
    typeof data.url === "string" ? data.url : "/",
    self.location.origin,
  );
  const target =
    url.origin === self.location.origin ? url.pathname + url.search : "/";
  event.waitUntil(
    self.registration.showNotification(data.title || "DARKNETRA update", {
      body: data.body || "Open the workspace to review an update.",
      tag: data.tag || "darknetra-update",
      data: { url: target },
    }),
  );
});
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(
    event.notification.data?.url || "/",
    self.location.origin,
  );
  if (url.origin !== self.location.origin) return;
  event.waitUntil(
    (async () => {
      const clients = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });
      const client = clients.find((c) => new URL(c.url).origin === url.origin);
      if (client) {
        await client.navigate(url.href);
        await client.focus();
      } else await self.clients.openWindow(url.href);
    })(),
  );
});

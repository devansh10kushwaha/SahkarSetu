/* SahkarSetu service worker — minimal, safe.
   Strategy: network-first for everything; offline fallback page for navigations.
   No aggressive caching so demo data always stays fresh. */
const CACHE = "sahkarsetu-v2";
const OFFLINE_URL = "/static/offline.html";

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.add(OFFLINE_URL)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  // Navigations: try network, fall back to the offline page when dead.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(() => caches.match(OFFLINE_URL))
    );
    return;
  }
  // Static assets: stale-while-revalidate — instant from cache, refreshed in the
  // background, so a redeploy reaches returning users without a hard refresh.
  if (req.url.includes("/static/") && !req.url.includes("/api/")) {
    event.respondWith(
      caches.open(CACHE).then((cache) =>
        cache.match(req).then((hit) => {
          const fresh = fetch(req)
            .then((resp) => {
              if (resp && resp.status === 200) cache.put(req, resp.clone());
              return resp;
            })
            .catch(() => hit);
          return hit || fresh;
        })
      )
    );
  }
});

/*
 * Offline cache for Unwatched Roads.
 *
 * - Road data (/data/...) and built assets (/assets/...) are cache-first. Data URLs carry
 *   ?v=<build version> and asset names carry a hash, so a new deploy is never masked.
 * - stats.json and page loads are network-first, falling back to the cached copy offline.
 * - Carto basemap files are cached as they are used, so a map already seen still draws offline.
 */
const VERSION = 'unwatched-roads-v1';
const STATIC = `${VERSION}-static`;
const TILES = `${VERSION}-tiles`;
const MAX_TILES = 400;

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k)));
      await self.clients.claim();
    })(),
  );
});

async function cacheFirst(request, cacheName, limit) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(request);
  if (hit) return hit;
  const res = await fetch(request);
  if (res.ok) {
    await cache.put(request, res.clone());
    if (limit) {
      const keys = await cache.keys();
      if (keys.length > limit) await Promise.all(keys.slice(0, keys.length - limit).map((k) => cache.delete(k)));
    }
  }
  return res;
}

async function networkFirst(request, cacheKey) {
  const cache = await caches.open(STATIC);
  try {
    const res = await fetch(request);
    if (res.ok) await cache.put(cacheKey, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(cacheKey);
    if (hit) return hit;
    throw err;
  }
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);

  if (url.hostname.endsWith('cartocdn.com')) {
    event.respondWith(cacheFirst(request, TILES, MAX_TILES));
    return;
  }
  if (url.origin !== self.location.origin) return;

  if (request.mode === 'navigate') {
    // /m and /gov are the same single page.
    event.respondWith(networkFirst(request, new URL('index.html', self.registration.scope).href));
    return;
  }
  if (url.pathname.endsWith('/data/stats.json')) {
    event.respondWith(networkFirst(request, url.origin + url.pathname));
    return;
  }
  if (url.pathname.includes('/data/') || url.pathname.includes('/assets/')) {
    event.respondWith(cacheFirst(request, STATIC));
  }
});

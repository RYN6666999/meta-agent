/* ═══════════════════════════════════════
   房多多經營系統 — Service Worker
   策略：Cache-First（全離線可用）
═══════════════════════════════════════ */
const CACHE = 'fdd-crm-v3';
const ASSETS = [
  './',
  './index.html',
  './login.html',
  './admin.html',
  './crm.css',
  './crm.js',
  './manifest.json',
  './icon.svg',
];

/* 安裝：預快取所有靜態資源 */
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(ASSETS))
  );
  self.skipWaiting(); // 立即接管
});

/* 啟動：清掉舊快取 */
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

/* 攔截請求：Cache-First */
self.addEventListener('fetch', e => {
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});

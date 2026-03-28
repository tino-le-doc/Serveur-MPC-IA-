/**
 * Service Worker — MCP IA PWA
 * Gestion du cache, offline fallback, et synchronisation en arrière-plan
 */

const CACHE_NAME    = 'mcp-ia-v1';
const API_CACHE     = 'mcp-ia-api-v1';
const OFFLINE_URL   = '/offline.html';

// Ressources à mettre en cache immédiatement
const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js',
];

// ─── Install ──────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch(() => {
        // Continuer même si certains assets échouent
      });
    })
  );
  self.skipWaiting();
});

// ─── Activate ─────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_NAME && k !== API_CACHE)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ─── Fetch ────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Requêtes API → Network first, puis cache court terme
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstWithCache(request));
    return;
  }

  // Ressources statiques → Cache first
  if (request.method === 'GET') {
    event.respondWith(cacheFirstWithNetwork(request));
    return;
  }
});

async function networkFirstWithCache(request) {
  try {
    const response = await fetch(request.clone());
    // Mettre en cache les réponses GET de l'API (sauf auth)
    if (response.ok && request.method === 'GET' && !request.url.includes('/login') && !request.url.includes('/register')) {
      const cache = await caches.open(API_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached || new Response(
      JSON.stringify({ error: 'Hors ligne — données non disponibles', offline: true }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}

async function cacheFirstWithNetwork(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return caches.match('/') || new Response('Hors ligne', { status: 503 });
  }
}

// ─── Push Notifications ───────────────────────
self.addEventListener('push', (event) => {
  if (!event.data) return;
  const data = event.data.json();
  event.waitUntil(
    self.registration.showNotification(data.title || 'MCP IA', {
      body:    data.body    || '',
      icon:    '/icons/icon-192.png',
      badge:   '/icons/icon-96.png',
      tag:     data.tag     || 'mcp-ia',
      vibrate: [200, 100, 200],
      data:    { url: data.url || '/' },
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then((clientList) => {
      const url = event.notification.data?.url || '/';
      for (const client of clientList) {
        if (client.url === url && 'focus' in client) return client.focus();
      }
      return clients.openWindow(url);
    })
  );
});

// ─── Background Sync ──────────────────────────
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-alerts') {
    event.waitUntil(syncAlerts());
  }
});

async function syncAlerts() {
  // Synchroniser les alertes en attente quand la connexion est rétablie
  const cache = await caches.open('mcp-ia-pending');
  const requests = await cache.keys();
  for (const req of requests) {
    try {
      await fetch(req);
      await cache.delete(req);
    } catch {}
  }
}

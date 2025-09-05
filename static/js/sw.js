// Service Worker for BBSchedule Platform - Offline Support
const CACHE_NAME = 'bbschedule-v1.0.0';
const STATIC_CACHE = 'bbschedule-static-v1';
const DYNAMIC_CACHE = 'bbschedule-dynamic-v1';

// Files to cache on install
const STATIC_FILES = [
    '/',
    '/static/css/style.css',
    '/static/css/mobile.css',
    '/static/js/app.js',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
    'https://cdn.jsdelivr.net/npm/chart.js',
    '/offline.html'
];

// Install event - cache static files
self.addEventListener('install', event => {
    console.log('Service Worker installing...');
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then(cache => {
                console.log('Caching static files');
                return cache.addAll(STATIC_FILES);
            })
            .catch(error => {
                console.error('Failed to cache static files:', error);
            })
    );
    self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
    console.log('Service Worker activating...');
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== STATIC_CACHE && cacheName !== DYNAMIC_CACHE) {
                        console.log('Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

// Fetch event - serve from cache or network
self.addEventListener('fetch', event => {
    const { request } = event;
    const url = new URL(request.url);
    
    // Handle API requests differently
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(handleApiRequest(request));
        return;
    }
    
    // Handle static assets
    if (request.destination === 'script' || 
        request.destination === 'style' || 
        request.destination === 'image') {
        event.respondWith(handleStaticRequest(request));
        return;
    }
    
    // Handle navigation requests
    if (request.mode === 'navigate') {
        event.respondWith(handleNavigationRequest(request));
        return;
    }
    
    // Default strategy: network first, then cache
    event.respondWith(
        fetch(request)
            .then(response => {
                if (response.ok) {
                    // Cache successful responses
                    const responseClone = response.clone();
                    caches.open(DYNAMIC_CACHE)
                        .then(cache => cache.put(request, responseClone));
                }
                return response;
            })
            .catch(() => {
                return caches.match(request);
            })
    );
});

// Handle API requests with offline queueing
async function handleApiRequest(request) {
    try {
        const response = await fetch(request);
        if (response.ok) {
            return response;
        }
        throw new Error('Network response was not ok');
    } catch (error) {
        // For GET requests, try to serve from cache
        if (request.method === 'GET') {
            const cachedResponse = await caches.match(request);
            if (cachedResponse) {
                return cachedResponse;
            }
        }
        
        // For POST/PUT requests, queue for later
        if (request.method === 'POST' || request.method === 'PUT') {
            await queueRequest(request);
            return new Response(JSON.stringify({
                success: true,
                message: 'Request queued for when online',
                offline: true
            }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' }
            });
        }
        
        // Return offline response
        return new Response(JSON.stringify({
            error: 'Offline - please try again when connected',
            offline: true
        }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
        });
    }
}

// Handle static assets - cache first
async function handleStaticRequest(request) {
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
        return cachedResponse;
    }
    
    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(STATIC_CACHE);
            cache.put(request, response.clone());
        }
        return response;
    } catch (error) {
        // Return a placeholder for failed assets
        if (request.destination === 'image') {
            return new Response('<svg width="200" height="200" xmlns="http://www.w3.org/2000/svg"><rect width="200" height="200" fill="#f0f0f0"/><text x="100" y="100" text-anchor="middle" fill="#999">Offline</text></svg>', {
                headers: { 'Content-Type': 'image/svg+xml' }
            });
        }
        throw error;
    }
}

// Handle navigation requests
async function handleNavigationRequest(request) {
    try {
        const response = await fetch(request);
        if (response.ok) {
            // Cache successful page loads
            const cache = await caches.open(DYNAMIC_CACHE);
            cache.put(request, response.clone());
        }
        return response;
    } catch (error) {
        // Try to serve from cache
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }
        
        // Serve offline page
        return caches.match('/offline.html');
    }
}

// Queue requests for when back online
async function queueRequest(request) {
    const requestData = {
        url: request.url,
        method: request.method,
        headers: Object.fromEntries(request.headers.entries()),
        body: await request.text(),
        timestamp: Date.now()
    };
    
    // Store in IndexedDB for persistence
    const db = await openDB();
    const transaction = db.transaction(['requests'], 'readwrite');
    const store = transaction.objectStore('requests');
    await store.add(requestData);
}

// Open IndexedDB for offline storage
function openDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('BBScheduleOffline', 1);
        
        request.onerror = () => reject(request.error);
        request.onsuccess = () => resolve(request.result);
        
        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains('requests')) {
                const store = db.createObjectStore('requests', { keyPath: 'id', autoIncrement: true });
                store.createIndex('timestamp', 'timestamp');
            }
        };
    });
}

// Process queued requests when online
self.addEventListener('online', async () => {
    console.log('Back online - processing queued requests');
    
    try {
        const db = await openDB();
        const transaction = db.transaction(['requests'], 'readwrite');
        const store = transaction.objectStore('requests');
        const requests = await store.getAll();
        
        for (const requestData of requests) {
            try {
                const response = await fetch(requestData.url, {
                    method: requestData.method,
                    headers: requestData.headers,
                    body: requestData.body
                });
                
                if (response.ok) {
                    // Remove successfully processed request
                    await store.delete(requestData.id);
                    console.log('Processed queued request:', requestData.url);
                }
            } catch (error) {
                console.error('Failed to process queued request:', error);
            }
        }
    } catch (error) {
        console.error('Error processing queued requests:', error);
    }
});

// Background sync for when page is not open
self.addEventListener('sync', event => {
    if (event.tag === 'background-sync') {
        event.waitUntil(processQueuedRequests());
    }
});

async function processQueuedRequests() {
    // Similar to online event handler but for background sync
    try {
        const db = await openDB();
        const transaction = db.transaction(['requests'], 'readwrite');
        const store = transaction.objectStore('requests');
        const requests = await store.getAll();
        
        for (const requestData of requests) {
            try {
                const response = await fetch(requestData.url, {
                    method: requestData.method,
                    headers: requestData.headers,
                    body: requestData.body
                });
                
                if (response.ok) {
                    await store.delete(requestData.id);
                }
            } catch (error) {
                // Keep request in queue for later
                break;
            }
        }
    } catch (error) {
        console.error('Background sync error:', error);
    }
}

// Push notifications for updates
self.addEventListener('push', event => {
    const options = {
        body: event.data ? event.data.text() : 'New update available',
        icon: '/static/images/icon-192.png',
        badge: '/static/images/badge-72.png',
        vibrate: [200, 100, 200],
        data: {
            url: '/'
        },
        actions: [
            {
                action: 'view',
                title: 'View Update'
            },
            {
                action: 'dismiss',
                title: 'Dismiss'
            }
        ]
    };
    
    event.waitUntil(
        self.registration.showNotification('BBSchedule Update', options)
    );
});

// Handle notification clicks
self.addEventListener('notificationclick', event => {
    event.notification.close();
    
    if (event.action === 'view') {
        event.waitUntil(
            clients.openWindow(event.notification.data.url)
        );
    }
});
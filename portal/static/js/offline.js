// WatchTheFall Portal - Offline Resilience System
// Implements all 8 patches for soft failure mode

// 1️⃣ PATCH: Cache /portal/test Offline
async function safeTestCheck() {
  try {
    const res = await fetch('/portal/test', { cache: 'no-store' });
    if (!res.ok) throw new Error('Server error');
    localStorage.setItem('portal_test_ok', '1');
    return true;
  } catch {
    return localStorage.getItem('portal_test_ok') === '1';
  }
}

// 2️⃣ PATCH: UI Loads Instantly Without Waiting on Server
// This will be implemented in dashboard.html by calling safeTestCheck().then(() => initPortal()); initPortal();

// 3️⃣ PATCH: Graceful Server Failure Handling
window.addEventListener('unhandledrejection', (e) => {
  if (e.reason?.message?.includes('Failed to fetch')) {
    showToast('Server waking up — UI still works.', 'warning');
    e.preventDefault();
  }
});

// Fetch wrapper for safe requests
async function safeFetch(url, opts = {}) {
  try {
    return await fetch(url, opts);
  } catch (err) {
    console.warn('[OFFLINE] Fetch failed for:', url, err);
    return { ok: false, offline: true, error: err.message };
  }
}

// 4️⃣ PATCH: Download Queue Works Offline
function queueDownload(url) {
  const q = JSON.parse(localStorage.getItem('download_queue') || '[]');
  q.push({ url, timestamp: Date.now() });
  localStorage.setItem('download_queue', JSON.stringify(q));
  console.log('[OFFLINE] Queued download:', url);
}

async function processQueuedDownloads() {
  const q = JSON.parse(localStorage.getItem('download_queue') || '[]');
  if (q.length === 0) return;
  
  console.log(`[OFFLINE] Processing ${q.length} queued downloads...`);
  const remaining = [];

  for (const item of q) {
    const res = await safeFetch('/api/videos/fetch', {
      method: 'POST',
      body: JSON.stringify({ urls: [item.url] }),
      headers: { 'Content-Type': 'application/json' }
    });

    if (!res.ok) {
      remaining.push(item);
      console.log('[OFFLINE] Re-queuing failed download:', item.url);
    } else {
      console.log('[OFFLINE] Successfully processed queued download:', item.url);
    }
  }

  localStorage.setItem('download_queue', JSON.stringify(remaining));
  if (remaining.length > 0) {
    console.log(`[OFFLINE] ${remaining.length} downloads still queued`);
  }
}

// 5️⃣ PATCH: Brand Selection Modal Works Offline
async function loadBrandConfig() {
  try {
    const res = await fetch('/portal/static/watermarks/brands.json');
    if (!res.ok) throw new Error();
    const data = await res.json();
    localStorage.setItem('brands', JSON.stringify(data));
    return data;
  } catch {
    return JSON.parse(localStorage.getItem('brands') || '[]');
  }
}

// 6️⃣ PATCH: Watermarker Always Works, Even Without Server
// This is already handled in the watermarking code - it's 100% client-side

// 7️⃣ PATCH: Instant "Offline Mode Activated" Banner
function showOffline() {
  document.body.classList.add('offline-mode');
  showToast('Portal is offline — continuing in local mode', 'warning');
  console.log('[OFFLINE] Portal entered offline mode');
}

function hideOffline() {
  document.body.classList.remove('offline-mode');
  console.log('[OFFLINE] Portal exited offline mode');
}

async function monitorServer() {
  const ok = await safeTestCheck();
  if (!ok) {
    showOffline();
  } else {
    hideOffline();
  }
  return ok;
}

// 8️⃣ PATCH: PWA Service Worker Guarantees Instant Load
// Service worker already exists with basic caching

// Toast notification helper
// 7️⃣ PATCH: Instant "Offline Mode Activated" Banner
function showToast(message, type = 'info') {
  // Check if toast already exists
  const existing = document.getElementById('offline-toast');
  if (existing) {
    existing.remove();
  }
  
  const toast = document.createElement('div');
  toast.id = 'offline-toast';
  const bgColors = { 
    success: '#0a0', 
    info: '#0af', 
    warning: '#fa0', 
    error: '#f55' 
  };
  
  toast.style.cssText = `
    position: fixed; 
    top: 20px; 
    right: 20px; 
    z-index: 10000; 
    background: ${bgColors[type] || '#0af'}; 
    color: #fff; 
    padding: 12px 20px; 
    border-radius: 8px; 
    box-shadow: 0 4px 12px rgba(0,0,0,0.3); 
    font-weight: 600; 
    animation: slideIn 0.3s ease-out;
    max-width: 300px;
  `;
  toast.textContent = message;
  document.body.appendChild(toast);
  
  setTimeout(() => {
    toast.style.transition = 'opacity 0.3s';
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, type === 'warning' ? 5000 : 3000);
}

// Initialize offline system
if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', () => {
    // Start monitoring server health
    setInterval(monitorServer, 5000);
    
    // Process queued downloads periodically
    setInterval(processQueuedDownloads, 8000);
    
    console.log('[OFFLINE] System initialized');
  });
}

// Export functions for global use
window.safeTestCheck = safeTestCheck;
window.safeFetch = safeFetch;
window.queueDownload = queueDownload;
window.loadBrandConfig = loadBrandConfig;
window.monitorServer = monitorServer;
window.showToast = showToast;
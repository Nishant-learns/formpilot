/**
 * Centralized API and WebSocket configuration for FormPilot.
 * Supports unified local hosting, container deployment, and Vercel cloud deployments.
 */

export const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '');

// Seamless fetch interceptor: If API_BASE is configured (e.g., hosted on Vercel connecting to Render/Railway),
// automatically prefix relative API & upload endpoints.
if (typeof window !== 'undefined' && API_BASE) {
  const originalFetch = window.fetch;
  window.fetch = function (input, init) {
    if (typeof input === 'string') {
      if (input.startsWith('/api/') || input.startsWith('/uploads/')) {
        input = `${API_BASE}${input}`;
      }
    }
    return originalFetch.call(this, input, init);
  };
}

export function apiUrl(endpoint) {
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  return `${API_BASE}${cleanEndpoint}`;
}

export function getWsUrl(path) {
  if (!path) return '';
  if (path.startsWith('ws://') || path.startsWith('wss://')) return path;

  const cleanPath = path.startsWith('/') ? path : `/${path}`;

  if (API_BASE) {
    const wsProtocol = API_BASE.startsWith('https://') ? 'wss:' : 'ws:';
    const host = API_BASE.replace(/^https?:\/\//, '');
    return `${wsProtocol}//${host}${cleanPath}`;
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}${cleanPath}`;
}

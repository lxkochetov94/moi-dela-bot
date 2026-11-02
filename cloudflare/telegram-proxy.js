/**
 * Moi Dela - private Telegram Bot API relay.
 * Keep PROXY_KEY only in Cloudflare Worker secrets and the Yandex function environment.
 * Bot token is supplied in a header, never in the Worker URL.
 * Do not add request/header/body logging: these contain personal tasks and credentials.
 */
const METHODS = new Set([
  'sendMessage', 'editMessageText', 'answerCallbackQuery', 'sendDocument'
]);

export default {
  async fetch(request, env) {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }
    if (!env.PROXY_KEY || request.headers.get('X-Moi-Dela-Proxy-Key') !== env.PROXY_KEY) {
      return new Response('Forbidden', { status: 403 });
    }
    const url = new URL(request.url);
    const method = url.pathname.slice(1);
    if (url.pathname !== `/${method}` || !METHODS.has(method) || url.search) {
      return new Response('Not Found', { status: 404 });
    }
    const token = request.headers.get('X-Moi-Dela-Bot-Token') || '';
    if (!/^\d+:[A-Za-z0-9_-]{20,}$/.test(token)) {
      return new Response('Unauthorized', { status: 401 });
    }
    const contentType = request.headers.get('Content-Type') || '';
    if (!(contentType === 'application/json' || contentType.startsWith('multipart/form-data; boundary='))) {
      return new Response('Unsupported Media Type', { status: 415 });
    }
    try {
      const upstream = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
        method: 'POST',
        headers: { 'Content-Type': contentType },
        body: request.body,
        redirect: 'manual'
      });
      return new Response(upstream.body, {
        status: upstream.status,
        headers: {
          'Content-Type': upstream.headers.get('Content-Type') || 'application/json',
          'Cache-Control': 'no-store'
        }
      });
    } catch {
      return new Response(JSON.stringify({ ok: false, description: 'Telegram upstream unavailable' }), {
        status: 502,
        headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }
      });
    }
  }
};

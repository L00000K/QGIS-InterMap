// Cloudflare Worker: a minimal CORS proxy for Cloud Optimized GeoTIFFs (COGs).
//
// Why this exists:
//   InterMap loads a remote COG in the browser using HTTP Range requests.
//   If the blob host (e.g. a public Azure blob) does not send CORS headers,
//   the browser blocks the fetch. This Worker re-fetches the COG server-side,
//   forwards the Range header (essential — COG streaming reads small byte
//   ranges, never the whole file), and adds the CORS headers the browser needs.
//
// Deploy (free):
//   1. Sign in at dash.cloudflare.com → Workers & Pages → Create → Worker
//   2. Paste this file, click Deploy. You get a URL like
//        https://cog-cors.<you>.workers.dev
//   3. In InterMap's export dialog, set "COG CORS proxy" to:
//        https://cog-cors.<you>.workers.dev/?url={url}
//
// Security note: this proxy will fetch ANY url passed to it. The ALLOW_HOSTS
// list below restricts it to the DataMapWales blob so it can't be abused as an
// open proxy. Add hosts as needed.

const ALLOW_HOSTS = [
  "dmwproductionblob.blob.core.windows.net",
];

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
  "Access-Control-Allow-Headers": "Range, Content-Type",
  "Access-Control-Expose-Headers":
    "Content-Length, Content-Range, Accept-Ranges, Content-Type",
  "Access-Control-Max-Age": "86400",
};

export default {
  async fetch(request) {
    // Preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }

    const target = new URL(request.url).searchParams.get("url");
    if (!target) {
      return new Response("Missing ?url= parameter", { status: 400, headers: CORS });
    }

    let upstream;
    try {
      upstream = new URL(target);
    } catch {
      return new Response("Invalid url", { status: 400, headers: CORS });
    }

    if (!ALLOW_HOSTS.includes(upstream.hostname)) {
      return new Response("Host not allowed", { status: 403, headers: CORS });
    }

    // Forward the request, preserving the Range header (critical for COG).
    const fwd = new Headers();
    const range = request.headers.get("Range");
    if (range) fwd.set("Range", range);

    const resp = await fetch(upstream.toString(), {
      method: request.method === "HEAD" ? "HEAD" : "GET",
      headers: fwd,
    });

    // Copy upstream response, add CORS headers, stream the body through.
    const headers = new Headers(resp.headers);
    for (const [k, v] of Object.entries(CORS)) headers.set(k, v);

    return new Response(resp.body, {
      status: resp.status, // 206 Partial Content is passed through unchanged
      statusText: resp.statusText,
      headers,
    });
  },
};

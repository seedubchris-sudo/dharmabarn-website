// Dharma Barn site: static files come from ./site. This script runs only for /media/*
// and adds HTTP byte-range replies (206), which Safari and iPhones need to play MP4 video.
//
// workers.dev copies (the production alias and the staging Worker) must stay out of search results.
// site/_headers sets "X-Robots-Tag: noindex" for *.workers.dev on static files, but _headers rules are not
// applied to replies made here, so this script sets the same header itself. dharmabarn.com never gets it.
export default {
  async fetch(request, env) {
    const noindex = isWorkersDev(request.url);
    const res = await env.ASSETS.fetch(request);
    const range = request.headers.get("Range");
    if (!range || res.status !== 200) return withRanges(res, noindex);
    const m = /^bytes=(\d*)-(\d*)$/.exec(range.trim());
    if (!m || (m[1] === "" && m[2] === "")) return withRanges(res, noindex);
    const buf = await res.arrayBuffer();
    const size = buf.byteLength;
    let start, end;
    if (m[1] === "") { start = Math.max(0, size - Number(m[2])); end = size - 1; }
    else { start = Number(m[1]); end = m[2] === "" ? size - 1 : Math.min(Number(m[2]), size - 1); }
    if (start >= size || start > end) {
      const h416 = new Headers({ "Content-Range": `bytes */${size}` });
      if (noindex) h416.set("X-Robots-Tag", "noindex");
      return new Response(null, { status: 416, headers: h416 });
    }
    const h = new Headers(res.headers);
    h.set("Accept-Ranges", "bytes");
    h.set("Content-Range", `bytes ${start}-${end}/${size}`);
    h.set("Content-Length", String(end - start + 1));
    if (noindex) h.set("X-Robots-Tag", "noindex");
    return new Response(buf.slice(start, end + 1), { status: 206, headers: h });
  },
};
function isWorkersDev(url) {
  const host = new URL(url).hostname.toLowerCase();
  return host === "workers.dev" || host.endsWith(".workers.dev");
}
function withRanges(res, noindex) {
  const h = new Headers(res.headers);
  h.set("Accept-Ranges", "bytes");
  if (noindex) h.set("X-Robots-Tag", "noindex");
  return new Response(res.body, { status: res.status, headers: h });
}

// Dharma Barn site: static files come from ./site. This script runs only for /media/*
// and adds HTTP byte-range replies (206), which Safari and iPhones need to play MP4 video.
export default {
  async fetch(request, env) {
    const res = await env.ASSETS.fetch(request);
    const range = request.headers.get("Range");
    if (!range || res.status !== 200) return withRanges(res);
    const m = /^bytes=(\d*)-(\d*)$/.exec(range.trim());
    if (!m || (m[1] === "" && m[2] === "")) return withRanges(res);
    const buf = await res.arrayBuffer();
    const size = buf.byteLength;
    let start, end;
    if (m[1] === "") { start = Math.max(0, size - Number(m[2])); end = size - 1; }
    else { start = Number(m[1]); end = m[2] === "" ? size - 1 : Math.min(Number(m[2]), size - 1); }
    if (start >= size || start > end) {
      return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${size}` } });
    }
    const h = new Headers(res.headers);
    h.set("Accept-Ranges", "bytes");
    h.set("Content-Range", `bytes ${start}-${end}/${size}`);
    h.set("Content-Length", String(end - start + 1));
    return new Response(buf.slice(start, end + 1), { status: 206, headers: h });
  },
};
function withRanges(res) {
  const h = new Headers(res.headers);
  h.set("Accept-Ranges", "bytes");
  return new Response(res.body, { status: res.status, headers: h });
}

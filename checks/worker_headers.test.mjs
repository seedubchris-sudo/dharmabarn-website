// Offline test of worker.js with a stand-in for Cloudflare's asset binding. No network, no deploy.
// Run: node checks/worker_headers.test.mjs   (site_checks.py runs it for you)
import assert from "node:assert/strict";
import worker from "../worker.js";

const BODY = new Uint8Array(1000).map((_, i) => i % 251);
const env = {
  ASSETS: {
    async fetch(req) {
      if (new URL(req.url).pathname === "/media/missing.mp4") return new Response("not found", { status: 404 });
      return new Response(BODY, { status: 200, headers: { "Content-Type": "video/mp4" } });
    },
  },
};
const get = (host, headers = {}, path = "/media/clip.mp4") =>
  worker.fetch(new Request(`https://${host}${path}`, { headers }), env);

const LIVE = ["dharmabarn.com", "www.dharmabarn.com"];
const DEV = ["dharmabarn.dharmabarn-website.workers.dev", "dharmabarn-preview.dharmabarn-website.workers.dev"];
let n = 0;

for (const host of [...LIVE, ...DEV]) {
  const want = DEV.includes(host) ? "noindex" : null;
  const full = await get(host);
  assert.equal(full.status, 200);
  assert.equal(full.headers.get("Accept-Ranges"), "bytes");
  assert.equal(full.headers.get("X-Robots-Tag"), want, `${host} full reply`);

  const part = await get(host, { Range: "bytes=100-199" });
  assert.equal(part.status, 206);
  assert.equal(part.headers.get("Content-Range"), "bytes 100-199/1000");
  assert.equal(part.headers.get("Content-Length"), "100");
  assert.deepEqual(new Uint8Array(await part.arrayBuffer()), BODY.slice(100, 200));
  assert.equal(part.headers.get("X-Robots-Tag"), want, `${host} range reply`);

  const tail = await get(host, { Range: "bytes=-50" });
  assert.equal(tail.headers.get("Content-Range"), "bytes 950-999/1000");

  const past = await get(host, { Range: "bytes=5000-" });
  assert.equal(past.status, 416);
  assert.equal(past.headers.get("X-Robots-Tag"), want, `${host} 416 reply`);

  const missing = await get(host, {}, "/media/missing.mp4");
  assert.equal(missing.status, 404);
  assert.equal(missing.headers.get("X-Robots-Tag"), want, `${host} 404 reply`);
  n += 5;
}
// A look-alike host must not be treated as workers.dev, and the real domain never gets noindex.
assert.equal((await get("workers.dev.example.com")).headers.get("X-Robots-Tag"), null);
assert.equal((await get("notworkers.dev")).headers.get("X-Robots-Tag"), null);
n += 2;
console.log(`worker.js: ${n} replies checked; noindex on workers.dev hosts only, byte ranges intact`);

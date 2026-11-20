# dharmabarn.com

Static site for Dharma Barn (recording, video, events and a Sundance 2027 page), hosted on Cloudflare (static assets; deployed with `npx wrangler deploy`). The published files are in `site/`.

Built from the reviewed preview with `build_site.py` in the Dharma Barn HQ project
(`companies/dharma-barn/projects/facility-studio-events/outputs/website-preview-2026-10/`).
Edit the preview `index.html`, then rebuild into `site/` rather than editing `index.html` here.

DNS lives at GoDaddy. Only the website records point here. Email (MX/TXT for Microsoft 365) stays unchanged.

## Checks before staging

```bash
python3 checks/site_checks.py              # checks ./site; exit code 1 on any problem
python3 checks/site_checks.py --self-test  # plants 8 faults on a temporary copy and confirms each is caught
```

Runs offline with Python 3 and node only. It checks internal links and anchors, basic HTML validity, accessibility
basics (skip link, one `h1` per page view, image alt text, names on links and buttons, field labels), the
`X-Robots-Tag: noindex` rule (workers.dev hosts only, never dharmabarn.com), the 404 page, and `worker.js`
(byte ranges and the noindex header, with a stand-in for Cloudflare's asset binding).

If `lychee`, `html-validate`, `pa11y-ci` or `lhci` are installed, the script says so; `lychee` and `html-validate`
are run. When they are missing it prints "SKIPPED" for each and the built-in checks still run. Outside links are
listed, not fetched. Speed and SEO scores are not checked without Lighthouse.

Added 2026-11-20 on branch `up/2026-11-20-site-checks` (not deployed): skip link, a real 404 page (no redirect),
and noindex for the workers.dev copies. All three come from the preview `index.html` and `build_site.py` in the
HQ project; `site/` here was rebuilt from them.

# dharmabarn.com

Static site for Dharma Barn (recording, video, events and a Sundance 2027 page), hosted on Cloudflare (static assets; deployed with `npx wrangler deploy`). The published files are in `site/`.

Built from the reviewed preview with `build_site.py` in the Dharma Barn HQ project
(`companies/dharma-barn/projects/facility-studio-events/outputs/website-preview-2026-10/`).
Edit the preview `index.html`, then rebuild into `site/` rather than editing `index.html` here.

DNS lives at GoDaddy. Only the website records point here. Email (MX/TXT for Microsoft 365) stays unchanged.

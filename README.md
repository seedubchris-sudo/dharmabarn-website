# dharmabarn.com

Static site for Dharma Barn (recording, video, events and a Sundance 2027 page), hosted on Cloudflare (static assets; deployed with `npx wrangler deploy`). The published files are in `site/`.

Built from the reviewed preview with `build_site.py` in the Dharma Barn HQ project
(`companies/dharma-barn/projects/facility-studio-events/outputs/website-preview-2026-10/`).
Edit the preview `index.html`, then rebuild into `site/` rather than editing `index.html` here.

DNS is in the Cloudflare zone `dharmabarn.com` (moved from GoDaddy on 2026-10-01; GoDaddy is still the registrar).
Email records (MX/TXT for Microsoft 365) are unchanged.

## Combined branch `up/2026-11-22-combined` (on the preview address only, not released)

This branch joins `up/2026-11-22-seo-wording` and `up/2026-11-22-listing-details`. Release needs Chris's yes.

- One block of facts for search engines per page, on Home, Recording, Video and Contact. Events and Sundance carry
  none. `build_pages.py` writes it at build time: the business facts and video entries come from
  `listing_details.py`, the service and page entries from `structured_data()` in `build_pages.py`. Nothing else
  writes a block. The build stops if a business fact is no longer in the page source.
- Business entry: plain `LocalBusiness`, name, the footer's street address, email, the three footer links and one
  phone number, (720) 878-5459, with the role the Contact page prints for it. Left out until Chris decides: the
  events phone number, a studio or venue type, "Dharma Farm" as a second name, hours, coordinates and prices.
- Video entries only where the video plays on the page: the reel on Home; the Shook Twins show and the Cactus Pals
  clip on Video. The two YouTube dates are the upload dates YouTube shows (read 2026-11-22). The Cactus Pals date
  is the day the file was added to this site (commit `fce6a99`).
- Two check groups cover the block: "Search wording and data" and "Listing details for search engines".
- Google's Rich Results Test has not been run.

## Search wording (branch `up/2026-11-22-seo-wording`)

Built on top of the separate pages below. Not released; release needs Chris's yes.

- Titles, descriptions and the main heading of Home, Recording, Video and Contact use the words people type for
  recording and filmed live sessions near Longmont. They are in the `PAGES` list in `build_pages.py`. Every
  statement is already on the site. Events and Sundance keep their wording exactly.
- Business facts for search engines (schema.org JSON-LD) are written from the `FACTS` table in `listing_details.py`:
  name, the recording and video phone number, email, street address and the three profile links, all already public
  on the site. No hours, coordinates, prices or reviews. Events and Sundance carry no facts block.
- Old GoDaddy addresses are permanent redirects (301) in `site/_redirects`, the file Cloudflare reads for static
  assets. The small forwarding pages are gone. `/#recording`-style links still forward in the browser, because the
  part after `#` never reaches the server.
- `site/favicon.ico` is the same "DB" tile the pages already use as their icon.
- Heading order: the equipment headings on Recording are `h3` and the three Sundance headings are `h2`, with a
  style rule each so the look is the same.
- The "Search wording and data" check covers title and description length, heading order, no `noindex` on a live
  page, the facts block (valid JSON, known schema.org terms, phone, email and address match the visible page),
  `favicon.ico`, `robots.txt`, the sitemap and `_redirects`. Google's Rich Results Test has not been run.
- To try it locally the way Cloudflare serves it, including the redirects:
  `npx wrangler dev -c wrangler.staging.jsonc` (local only; nothing is deployed).

## Separate pages (branch `up/2026-11-20-separate-pages`, not staged, not deployed)

The site is six real pages: `/`, `/recording/`, `/video/`, `/events/`, `/sundance/` and `/contact/`. Each has its own
title, description, canonical address and share image, the same header and footer, and a menu that marks the
current page. Photos and styles are unchanged from the one-file site (for wording, see "Search wording" above).

```bash
python3 build_pages.py   # reads src/single-page.html, writes the six pages, redirects, 404 links and sitemap into ./site
```

- `src/single-page.html` is the `index.html` that `build_site.py` writes (every section in one file, switched by
  `#hash`). To change wording or photos: edit the preview in the HQ project, run `build_site.py` into a scratch
  folder, copy its `index.html` here as `src/single-page.html` (and any new photos into `site/img/`), then run
  `build_pages.py`. It stops with a message if the source no longer has a piece it expects.
- Page titles and descriptions are in the `PAGES` list at the top of `build_pages.py`.
- Old links keep working: `/#recording` and the like forward to the new page, and the old GoDaddy addresses
  (`/dharma-barn-recording`, `/dharma-barn-video`, `/dharma-barn-events`, `/sundance-2027-packages`, `/lander`,
  and three `/ola/services/...` booking pages) redirect to the new pages. `/contact` is now the Contact page itself.
- The Video page's clip list is written into the HTML, so every page shows its full content with JavaScript off.
- This branch includes commit `c903640` (site checks, skip link, 404 page, noindex for workers.dev).

## Checks before staging

```bash
python3 checks/site_checks.py              # checks ./site; exit code 1 on any problem
python3 checks/site_checks.py --self-test  # plants 35 faults on a temporary copy and confirms each is caught
```

The "Separate pages" check confirms each page has its own title and description, the right canonical address, an
existing share image, a menu of real page links with the current page marked, and a line in `sitemap.xml`.

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

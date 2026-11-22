# dharmabarn.com

Static site for Dharma Barn (recording, video, events and a Sundance 2027 page), hosted on Cloudflare (static assets; deployed with `npx wrangler deploy`). The published files are in `site/`.

Built from the reviewed preview with `build_site.py` in the Dharma Barn HQ project
(`companies/dharma-barn/projects/facility-studio-events/outputs/website-preview-2026-10/`).
Edit the preview `index.html`, then rebuild into `site/` rather than editing `index.html` here.

DNS lives at GoDaddy. Only the website records point here. Email (MX/TXT for Microsoft 365) stays unchanged.

## Separate pages (branch `up/2026-11-20-separate-pages`, not staged, not deployed)

The site is six real pages: `/`, `/recording/`, `/video/`, `/events/`, `/sundance/` and `/contact/`. Each has its own
title, description, canonical address and share image, the same header and footer, and a menu that marks the
current page. Wording, photos and styles are unchanged from the one-file site.

```bash
python3 build_pages.py   # reads src/single-page.html, writes the six pages, redirects, 404 links and sitemap into ./site
```

- `src/single-page.html` is the `index.html` that `build_site.py` writes (every section in one file, switched by
  `#hash`). To change wording or photos: edit the preview in the HQ project, run `build_site.py` into a scratch
  folder, copy its `index.html` here as `src/single-page.html` (and any new photos into `site/img/`), then run
  `build_pages.py`. It stops with a message if the source no longer has a piece it expects.
- Page titles and descriptions are in the `PAGES` list at the top of `build_pages.py`. They reuse sentences already
  on each page.
- Old links keep working: `/#recording` and the like forward to the new page, and the old GoDaddy addresses
  (`/dharma-barn-recording`, `/dharma-barn-video`, `/dharma-barn-events`, `/sundance-2027-packages`, `/lander`)
  redirect to the new pages. `/contact` is now the Contact page itself.
- The Video page's clip list is written into the HTML, so every page shows its full content with JavaScript off.
- This branch includes commit `c903640` (site checks, skip link, 404 page, noindex for workers.dev).

## Listing details for search engines (branch `up/2026-11-22-listing-details`, not staged, not deployed)

`build_pages.py` adds one block of schema.org listing details (JSON-LD) to the head of each of the six pages. The
facts are in `listing_details.py`.

- Business entry on every page: name, address, both phone numbers with the roles the Contact page gives them,
  the email address and the three footer links. No opening hours, map coordinates, prices or ratings, because the
  site states none. The type is plain `LocalBusiness`.
- Video entries only where the video plays on the page: the reel on Home; the Shook Twins show and the Cactus Pals
  clip on Video. Clips that open on YouTube are left out (Google lists a video only on a page that plays it).
- Video dates are not printed on the pages. The two YouTube dates are the upload dates YouTube shows (read
  2026-11-22). The Cactus Pals date is the day the file was added to this site (commit `fce6a99`).
- The build stops if a business fact in `listing_details.py` is no longer in the page source. The "Listing details"
  check in `checks/site_checks.py` confirms each built page says the same thing as its listing details.
- Not done here: Google's Rich Results Test needs a public address, so it waits for the staging copy.

## Checks before staging

```bash
python3 checks/site_checks.py              # checks ./site; exit code 1 on any problem
python3 checks/site_checks.py --self-test  # plants 18 faults on a temporary copy and confirms each is caught
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

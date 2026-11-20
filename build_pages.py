#!/usr/bin/env python3
"""Split the one-file site into separate pages: Home, Recording, Video, Events, Sundance 2027 and Contact.

    python3 build_pages.py                      # reads src/single-page.html, writes ./site
    python3 build_pages.py --src X --out DIR    # other input / output (used for trial builds)

Input: src/single-page.html, which is the index.html that build_site.py (in the Dharma Barn HQ project) writes.
That file holds every section as a "view" switched by the #hash. This script writes one real page per view,
each with its own title, description, canonical address and share image, and the same header, footer, styles
and script. It changes no wording, photo or style. It also:

- turns the #hash navigation into real links and marks the current page in the menu
- writes the Video page's clip list into the HTML, so the page is complete with JavaScript off
- keeps old links working: /#recording and the like forward to the new page, and the old GoDaddy
  addresses (/dharma-barn-recording ...) redirect to the new pages
- lists all six pages in sitemap.xml and points the 404 page's links at them

It stops with a message if a piece of text it expects is missing, so a change in the source cannot pass silently.
Images, media, robots.txt and _headers in the output folder are left as they are.
"""
import html
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
ORIGIN = "https://dharmabarn.com"

# Titles follow the pattern the one-file site already set in the browser tab ("Recording · Dharma Barn").
# Descriptions reuse sentences already on each page; no new facts.
PAGES = [
    {"view": "home", "path": "/", "title": None, "og_title": None, "desc": None, "image": None},
    {"view": "recording", "path": "/recording/", "title": "Recording · Dharma Barn", "image": "console.jpg",
     "desc": "We track, mix and master at Dharma Barn in Hygiene, Colorado. Everything runs through an API 1608-II "
             "console, with a collection of vintage Neumann, Telefunken, and AKG microphones."},
    {"view": "video", "path": "/video/", "title": "Video · Dharma Barn", "image": "stage-teal.jpg",
     "desc": "Shows on the Dharma Barn stage in Hygiene, Colorado are filmed on Sony cameras from several angles "
             "under stage lights, and each performance is recorded to multitrack at the same time."},
    {"view": "events", "path": "/events/", "title": "Events · Dharma Barn", "image": "crowd.jpg",
     "desc": "Dharma Barn in Hygiene, Colorado hosts concerts, weddings, dinners, rehearsals and livestreams. "
             "The stage, lights and sound are already in place."},
    {"view": "sundance", "path": "/sundance/", "title": "Sundance 2027 · Dharma Barn", "image": "barn-dusk.jpg",
     "desc": "The Sundance Film Festival moves to Boulder for 2027, from January 21 to 31. Dharma Barn in Hygiene "
             "is offering the barn for private screenings, brand events and recorded sessions that week."},
    {"view": "contact", "path": "/contact/", "title": "Contact · Dharma Barn", "image": "barn-moon.jpg",
     "desc": "Write or call Dharma Barn. Chris Wright for recording and video, Jeremy Ragland for the barn and "
             "events. 12281 N 75th St, Longmont, CO 80503, in Hygiene, Boulder County."},
]
PATH_OF = {p["view"]: p["path"] for p in PAGES}
# Anchors that used to live in the one file and now sit on another page.
MOVED_ANCHORS = {"inventory": "/recording/#inventory", "video-reel": "/video/#video-reel"}
# Old GoDaddy addresses still in search results. (/contact is now the real Contact page.)
OLD_ADDRESSES = {"dharma-barn-recording": "/recording/", "dharma-barn-video": "/video/", "dharma-barn-events": "/events/",
                 "sundance-2027-packages": "/sundance/", "lander": "/"}


def stop(msg):
    sys.exit("build_pages: " + msg)


def swap(text, old, new, what):
    if old not in text:
        stop(f"expected text not found ({what}): {old[:80]!r}")
    return text.replace(old, new, 1)


def cut(text, start, end, what):
    """Remove from the first `start` up to (not including) the next `end`."""
    a = text.find(start)
    b = text.find(end, a + 1) if a >= 0 else -1
    if a < 0 or b < 0:
        stop(f"expected block not found ({what})")
    return text[:a] + text[b:], text[a:b]


def clip_html(js):
    """The Video page's clip list, written the same way the page script used to write it in the browser."""
    out = []
    for m in re.finditer(r"\{([^{}]*)\}", js):
        f = dict(re.findall(r'(\w+):"([^"]*)"', m.group(1)))
        t = html.escape(f["t"], quote=False)
        if "local" in f:
            out.append(f'<button class="clip clip-local" type="button" data-src="/{f["local"]}" aria-label="Play {t} here">'
                       f'<div class="th"><img src="/{f["poster"]}" alt="" loading="lazy"><span class="missing">Thumbnail unavailable</span></div>'
                       f'<strong>{t}</strong><small>{html.escape(f["s"])}</small></button>')
        else:
            small = f'<small>{html.escape(f["s"])}</small>' if f.get("s") and f["s"] != "At the barn" else ""
            out.append(f'<a class="clip" href="https://www.youtube.com/watch?v={f["id"]}" target="_blank" rel="noopener" '
                       f'aria-label="Watch {t} on YouTube">'
                       f'<div class="th"><img src="/img/yt-{f["id"]}.jpg" alt="" loading="lazy"><span class="missing">Thumbnail unavailable</span></div>'
                       f'<strong>{t}</strong>{small}</a>')
    if len(out) < 2:
        stop("the clip list could not be read from the page script")
    return "\n        ".join(out)


def build(src, out):
    s = open(src, encoding="utf-8").read()
    if s.count("data-view=") < 2 + len(PAGES) - 1 or "function route(" not in s:
        stop(f"{src} is not the one-file site (it may already be a split page)")

    # Photos, video and posters are addressed from the site root so they load from any page.
    s = re.sub(r'((?:src|poster)=")(img|media)/', r"\1/\2/", s)
    s = s.replace("url(img/", "url(/img/")
    # Hash links between views become real links.
    s, n = re.subn(r'href="#(home|recording|video|events|sundance|contact)" data-link',
                   lambda m: f'href="{PATH_OF[m.group(1)]}"', s)
    if n < 8:
        stop(f"only {n} view links found; expected the menu and the in-page links")

    # Page script: the clip list is written into the HTML, and there is no view switching any more.
    s, clips_js = cut(s, "  var CLIPS=[", "  /* Missing image state */", "clip list script")
    s = swap(s, '<div class="clips" data-clips="all" style="margin-top:clamp(32px,4vw,56px)"></div>',
             '<div class="clips" style="margin-top:clamp(32px,4vw,56px)">\n        '
             + clip_html(clips_js.split("];", 1)[0]) + "\n      </div>", "clip list holder")
    s = swap(s, "  reelFacade.addEventListener('click',function(){", "  if(reelFacade) reelFacade.addEventListener('click',function(){",
             "reel button")
    s, _ = cut(s, "  /* Router */", "  var skip=document.getElementById('skip-link')", "router")
    s = swap(s, "  var skip=document.getElementById('skip-link')",
             "  var nav=document.getElementById('nav'), mb=document.getElementById('menu-btn');\n"
             "/*MOVED*/  var skip=document.getElementById('skip-link')", "skip link script")
    s = swap(s, "\n  route();\n", "\n", "router start")
    for left in ("route(", "data-link", "stopReel();", "document.title="):
        if left in s:
            stop(f"view-switching code is still in the page: {left}")
    moved = {**{v: p for v, p in PATH_OF.items() if v != "home"}, **MOVED_ANCHORS}
    moved_js = ("  /* Old links such as /#recording go to the page that now holds that section */\n"
                "  var MOVED={" + ",".join(f"'{k}':'{v}'" for k, v in moved.items()) + "};\n"
                "  function goMoved(){ var to=MOVED[(location.hash||'').slice(1)]; if(to) location.replace(to); }\n"
                "  goMoved(); window.addEventListener('hashchange',goMoved);\n")

    main_a = s.index('<main id="content"')
    main_a = s.index(">", main_a) + 1
    main_b = s.index("</main>")
    before, views_html, after = s[:main_a], s[main_a:main_b], s[main_b:]
    views = {}
    for m in re.finditer(r'<!-- [A-Z]+ -->\n<div data-view="([a-z]+)"( hidden)?>.*?(?=\n<!-- [A-Z]+ -->\n<div data-view=|\Z)', views_html, re.S):
        views[m.group(1)] = m.group(0).rstrip().replace(f'<div data-view="{m.group(1)}" hidden>', f'<div data-view="{m.group(1)}">', 1)
    if sorted(views) != sorted(PATH_OF):
        stop(f"views found {sorted(views)}; expected {sorted(PATH_OF)}")

    home_title = re.search(r"<title>(.*?)</title>", before).group(1)
    seen_titles, seen_descs = set(), set()
    for p in PAGES:
        head = before
        if p["view"] != "home":
            url = ORIGIN + p["path"]
            desc = html.escape(p["desc"], quote=True)
            head = swap(head, f"<title>{home_title}</title>", f"<title>{p['title']}</title>", "title")
            head = swap(head, f'<link rel="canonical" href="{ORIGIN}/">', f'<link rel="canonical" href="{url}">', "canonical")
            head = swap(head, '<meta property="og:title" content="Dharma Barn">', f'<meta property="og:title" content="{p["title"]}">', "og:title")
            head = swap(head, f'<meta property="og:url" content="{ORIGIN}/">', f'<meta property="og:url" content="{url}">', "og:url")
            head = swap(head, f'<meta property="og:image" content="{ORIGIN}/img/barn-dusk.jpg">',
                        f'<meta property="og:image" content="{ORIGIN}/img/{p["image"]}">', "og:image")
            if not os.path.exists(os.path.join(out, "img", p["image"])):
                stop(f"share image missing from {out}/img: {p['image']}")
            head, n1 = re.subn(r'<meta property="og:description" content="[^"]*">', f'<meta property="og:description" content="{desc}">', head)
            head, n2 = re.subn(r'<meta name="description" content="[^"]*">', f'<meta name="description" content="{desc}">', head)
            if (n1, n2) != (1, 1):
                stop("description tags not found exactly once")
            head, n3 = re.subn(rf'(<nav class="nav".*?<a href="{re.escape(p["path"])}")', r'\1 aria-current="page"', head, count=1, flags=re.S)
            if n3 != 1:
                stop(f"menu link for {p['path']} not found")
        head = swap(head, "<body>", f'<body data-view="{p["view"]}">', "body tag")
        title = re.search(r"<title>(.*?)</title>", head).group(1)
        d = re.search(r'<meta name="description" content="([^"]*)">', head).group(1)
        if title in seen_titles or d in seen_descs:
            stop(f"title or description repeated on {p['path']}")
        seen_titles.add(title)
        seen_descs.add(d)
        tail = after.replace("/*MOVED*/", moved_js if p["view"] == "home" else "", 1)
        page = head + "\n" + views[p["view"]] + "\n" + tail
        folder = os.path.join(out, p["path"].strip("/"))
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as fh:
            fh.write(page)

    for slug, target in OLD_ADDRESSES.items():
        d = os.path.join(out, slug)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as fh:
            fh.write(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Dharma Barn</title>'
                     f'<link rel="canonical" href="{ORIGIN}{target}"><meta http-equiv="refresh" content="0; url={target}">'
                     f'<script>location.replace("{target}")</script></head><body><p><a href="{target}">Continue to Dharma Barn</a></p></body></html>\n')

    nf_path = os.path.join(out, "404.html")
    nf = open(nf_path, encoding="utf-8").read()
    for v, path in PATH_OF.items():
        if v != "home" and f'href="{path}"' not in nf:
            nf = swap(nf, f'href="/#{v}"', f'href="{path}"', "404 page link")
    with open(nf_path, "w", encoding="utf-8") as fh:
        fh.write(nf)

    with open(os.path.join(out, "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                 + "".join(f"<url><loc>{ORIGIN}{p['path']}</loc></url>\n" for p in PAGES) + "</urlset>\n")
    print(f"built {len(PAGES)} pages in {out}")


def main():
    args = sys.argv[1:]
    src = os.path.join(ROOT, "src", "single-page.html")
    out = os.path.join(ROOT, "site")
    while args:
        a = args.pop(0)
        if a == "--src" and args:
            src = args.pop(0)
        elif a == "--out" and args:
            out = args.pop(0)
        else:
            stop("usage: build_pages.py [--src single-page.html] [--out site_dir]")
    build(src, out)


main()

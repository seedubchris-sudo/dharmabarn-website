#!/usr/bin/env python3
"""Split the one-file site into separate pages: Home, Recording, Video, Events, Sundance 2027 and Contact.

    python3 build_pages.py                      # reads src/single-page.html, writes ./site
    python3 build_pages.py --src X --out DIR    # other input / output (used for trial builds)

Input: src/single-page.html, which is the index.html that build_site.py (in the Dharma Barn HQ project) writes.
That file holds every section as a "view" switched by the #hash. This script writes one real page per view,
each with its own title, description, canonical address and share image, and the same header, footer, styles
and script. It changes no photo or style. It also:

- turns the #hash navigation into real links and marks the current page in the menu
- writes the Video page's clip list into the HTML, so the page is complete with JavaScript off
- keeps old links working: /#recording and the like forward to the new page (in the browser, because the part
  after # is never sent to the server), and the old GoDaddy addresses (/dharma-barn-recording ...) get a
  permanent redirect (301) in site/_redirects, the file Cloudflare reads for static assets
- lists all six pages in sitemap.xml and points the 404 page's links at them
- sets the search wording (title, description, main heading) for Home, Recording, Video and Contact, and writes
  the business facts for search engines (schema.org JSON-LD) from the FACTS table below. Events and Sundance
  keep their wording exactly.

It stops with a message if a piece of text it expects is missing, so a change in the source cannot pass silently.
Images, media, robots.txt and _headers in the output folder are left as they are.
"""
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
ORIGIN = "https://dharmabarn.com"

# Search wording, 2026-11-22. Home, Recording, Video and Contact use the words people type for recording and
# filmed live sessions near Longmont. Every statement is already on the site; no new facts. Events and Sundance
# are unchanged on purpose (their wording waits on Chris). "h1" is (heading in the source, heading to publish).
PAGES = [
    {"view": "home", "path": "/", "image": "barn-dusk.jpg",
     "title": "Dharma Barn · Recording Studio & Live Sessions near Longmont, CO",
     "desc": "Recording studio, filmed live sessions and concert video, and a private venue, in a 1918 barn in "
             "Hygiene, between Longmont and Lyons in Boulder County, Colorado."},
    {"view": "recording", "path": "/recording/", "image": "console.jpg",
     "title": "Recording Studio near Longmont, CO · Dharma Barn",
     "h1": ("<h1>Recording</h1>", "<h1>Recording studio near Longmont</h1>"),
     "desc": "Recording studio in a 1918 barn in Hygiene, near Longmont, Colorado. Tracking, mixing and mastering "
             "on an API 1608-II console with vintage Neumann and AKG microphones."},
    {"view": "video", "path": "/video/", "image": "stage-teal.jpg",
     "title": "Live Session Video & Concert Filming, Colorado · Dharma Barn",
     "h1": ("<h1>Video</h1>", "<h1>Live session and concert video</h1>"),
     "desc": "Live session and concert video for bands, filmed from several camera angles on the barn stage near "
             "Longmont, Colorado, with multitrack audio mixed in our studio."},
    {"view": "events", "path": "/events/", "title": "Events · Dharma Barn", "image": "crowd.jpg",
     "desc": "Dharma Barn in Hygiene, Colorado hosts concerts, weddings, dinners, rehearsals and livestreams. "
             "The stage, lights and sound are already in place."},
    {"view": "sundance", "path": "/sundance/", "title": "Sundance 2027 · Dharma Barn", "image": "barn-dusk.jpg",
     "desc": "The Sundance Film Festival moves to Boulder for 2027, from January 21 to 31. Dharma Barn in Hygiene "
             "is offering the barn for private screenings, brand events and recorded sessions that week."},
    {"view": "contact", "path": "/contact/", "image": "barn-moon.jpg",
     "title": "Contact · Dharma Barn, Hygiene, near Longmont, Colorado",
     "desc": "Call or write to plan a recording or a filmed live session: Chris Wright. For the barn and events: "
             "Jeremy Ragland. 12281 N 75th St, Longmont, CO 80503, in Hygiene."},
]
PATH_OF = {p["view"]: p["path"] for p in PAGES}
# Anchors that used to live in the one file and now sit on another page.
MOVED_ANCHORS = {"inventory": "/recording/#inventory", "video-reel": "/video/#video-reel"}
# Old GoDaddy addresses still in search results. (/contact is now the real Contact page.) Written to
# site/_redirects as permanent redirects, with and without the closing slash.
OLD_ADDRESSES = {"dharma-barn-recording": "/recording/", "dharma-barn-video": "/video/", "dharma-barn-events": "/events/",
                 "sundance-2027-packages": "/sundance/", "lander": "/",
                 # the old GoDaddy booking pages (in the old site's own sitemap; Bing still lists the first)
                 "ola/services/mixing-and-mastering": "/recording/",
                 "ola/services/audio-visual-capture-of-live-event": "/video/",
                 "ola/services/video-product-screening-events": "/sundance/"}

# Business facts for search engines. Every value is already public on the site (footer, Contact page).
# One place only: the JSON-LD is written from this table, and checks/site_checks.py compares it with the visible
# page. Left out on purpose, because the site does not state them or the decision is not made: opening hours,
# map coordinates, prices, reviews, "Dharma Farm" as a second name, and the events phone number.
FACTS = {
    "name": "Dharma Barn",
    "phone": "+1-720-878-5459",  # Chris Wright, recording and video; shown on the pages as (720) 878-5459
    "email": "dharmafarm@icloud.com",
    "street": "12281 N 75th St", "city": "Longmont", "region": "CO", "postcode": "80503", "country": "US",
    "profiles": ["https://www.youtube.com/@dharma_barn", "https://www.instagram.com/dharma_farm_/",
                 "https://www.facebook.com/p/Dharma-Farm-100095685273767/"],
    "about": "Recording studio and filmed live sessions in a 1918 barn in Hygiene, Colorado, between Longmont and Lyons.",
}
BUSINESS_ID = ORIGIN + "/#business"

# In-text links between the pages (same words, now links), so each service page points at the other.
TEXT_LINKS = [
    ("recording", "Chris Wright runs the studio and the video work.",
     'Chris Wright runs the studio and the <a class="textlink" href="/video/">video work</a>.'),
    ("video", "We mix the audio in the studio first, then cut the picture to it.",
     'We mix the audio in <a class="textlink" href="/recording/">the studio</a> first, then cut the picture to it.'),
]
# Heading order: no level is skipped under the page's one main heading. Only the tag changes; the style rule
# added beside each keeps the look as it was. (view, old tag, new tag, how many are expected)
HEADING_FIXES = [
    ("recording", "<h4", "<h3", 5), ("recording", "</h4>", "</h3>", 5),
    ("sundance", "<h3>", "<h2>", 3), ("sundance", "</h3>", "</h2>", 3),
]
HEADING_CSS = [
    (".inv-grid h4{font-family:var(--f-ui);font-weight:500;font-size:12px;letter-spacing:var(--label-track);"
     "text-transform:uppercase;color:var(--tungsten);margin:0 0 10px}",
     ".inv-grid h3{font-family:var(--f-ui);font-weight:500;font-size:12px;letter-spacing:var(--label-track);"
     "text-transform:uppercase;color:var(--tungsten);margin:0 0 10px;font-variation-settings:normal;"
     "line-height:inherit;text-wrap:wrap}"),
    (".pkg h3{font-size:clamp(22px,1.8vw,26px);font-weight:400;color:var(--siding)}",
     ".pkg h2{font-size:clamp(22px,1.8vw,26px);line-height:1.18;font-weight:400;color:var(--siding)}"),
]


def business():
    f = FACTS
    return {
        "@type": "LocalBusiness", "@id": BUSINESS_ID, "name": f["name"],
        "additionalType": "https://www.wikidata.org/wiki/Q746369",  # "recording studio"; schema.org has no such type
        "description": f["about"], "url": ORIGIN + "/", "image": ORIGIN + "/img/barn-dusk.jpg",
        "telephone": f["phone"], "email": f["email"],
        "address": {"@type": "PostalAddress", "streetAddress": f["street"], "addressLocality": f["city"],
                    "addressRegion": f["region"], "postalCode": f["postcode"], "addressCountry": f["country"]},
        "contactPoint": [{"@type": "ContactPoint", "contactType": "Recording and video",
                          "telephone": f["phone"], "email": f["email"]}],
        "sameAs": f["profiles"],
    }


def crumbs(name):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": FACTS["name"], "item": ORIGIN + "/"},
        {"@type": "ListItem", "position": 2, "name": name}]}


def structured_data(view):
    """schema.org facts for one page, or None. Events and Sundance get none (their promotion waits on Chris)."""
    provider = {"@type": "LocalBusiness", "@id": BUSINESS_ID, "name": FACTS["name"], "url": ORIGIN + "/"}
    if view == "home":
        graph = [business(), {"@type": "WebSite", "@id": ORIGIN + "/#website", "name": FACTS["name"],
                              "url": ORIGIN + "/", "publisher": {"@id": BUSINESS_ID}}]
    elif view == "recording":
        graph = [{"@type": "Service", "@id": ORIGIN + "/recording/#service", "name": "Recording at Dharma Barn",
                  "serviceType": "Recording studio services", "url": ORIGIN + "/recording/",
                  "image": ORIGIN + "/img/console.jpg", "provider": provider,
                  "description": "Tracking, mixing and mastering at Dharma Barn in Hygiene, Colorado, through an "
                                 "API 1608-II console.",
                  "hasOfferCatalog": {"@type": "OfferCatalog", "name": "Recording services", "itemListElement": [
                      {"@type": "Offer", "itemOffered": {"@type": "Service", "name": n}}
                      for n in ("Tracking", "Mixing", "Mastering")]}},
                 crumbs("Recording")]
    elif view == "video":
        graph = [{"@type": "Service", "@id": ORIGIN + "/video/#service", "name": "Filmed live sessions at Dharma Barn",
                  "serviceType": "Live session and concert video production", "url": ORIGIN + "/video/",
                  "image": ORIGIN + "/img/stage-teal.jpg", "provider": provider,
                  "description": "Performances on the Dharma Barn stage are filmed from several camera angles under "
                                 "stage lights and recorded to multitrack at the same time."},
                 crumbs("Video")]
    elif view == "contact":
        graph = [{"@type": "ContactPage", "@id": ORIGIN + "/contact/#page", "name": "Contact Dharma Barn",
                  "url": ORIGIN + "/contact/", "mainEntity": {"@id": BUSINESS_ID}},
                 business(), crumbs("Contact")]
    else:
        return None
    text = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=1)
    return '<script type="application/ld+json">\n' + text.replace("</", "<\\/") + "\n</script>\n"


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

    for old, new in HEADING_CSS:  # the style follows the tag, so the page looks the same
        before = swap(before, old, old + "\n" + new, "heading style")
    for view, old, new, want in HEADING_FIXES:
        if views[view].count(old) != want:
            stop(f"heading order: expected {want} x {old!r} on the {view} page, found {views[view].count(old)}")
        views[view] = views[view].replace(old, new)
    for view, old, new in TEXT_LINKS:
        views[view] = swap(views[view], old, new, f"in-text link on the {view} page")
    for p in PAGES:
        if "h1" in p:
            views[p["view"]] = swap(views[p["view"]], p["h1"][0], p["h1"][1], f"main heading on {p['path']}")
        if views[p["view"]].count("<h1") != 1:
            stop(f"{p['path']} should have exactly one main heading (h1)")

    home_title = re.search(r"<title>(.*?)</title>", before).group(1)
    seen_titles, seen_descs = set(), set()
    for p in PAGES:
        head = before
        url = ORIGIN + p["path"]
        desc = html.escape(p["desc"], quote=True)
        head = swap(head, f"<title>{home_title}</title>", f"<title>{html.escape(p['title'], quote=False)}</title>", "title")
        head, n1 = re.subn(r'<meta property="og:description" content="[^"]*">', f'<meta property="og:description" content="{desc}">', head)
        head, n2 = re.subn(r'<meta name="description" content="[^"]*">', f'<meta name="description" content="{desc}">', head)
        if (n1, n2) != (1, 1):
            stop("description tags not found exactly once")
        if not os.path.exists(os.path.join(out, "img", p["image"])):
            stop(f"share image missing from {out}/img: {p['image']}")
        if p["view"] != "home":
            og_title = html.escape(p["title"], quote=True)
            head = swap(head, f'<link rel="canonical" href="{ORIGIN}/">', f'<link rel="canonical" href="{url}">', "canonical")
            head = swap(head, '<meta property="og:title" content="Dharma Barn">', f'<meta property="og:title" content="{og_title}">', "og:title")
            head = swap(head, f'<meta property="og:url" content="{ORIGIN}/">', f'<meta property="og:url" content="{url}">', "og:url")
            head = swap(head, f'<meta property="og:image" content="{ORIGIN}/img/barn-dusk.jpg">',
                        f'<meta property="og:image" content="{ORIGIN}/img/{p["image"]}">', "og:image")
            head, n3 = re.subn(rf'(<nav class="nav".*?<a href="{re.escape(p["path"])}")', r'\1 aria-current="page"', head, count=1, flags=re.S)
            if n3 != 1:
                stop(f"menu link for {p['path']} not found")
        ld = structured_data(p["view"])
        if ld:
            head = swap(head, "</head>", ld + "</head>", "end of head")
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

    # Permanent redirects for the old GoDaddy addresses, in the form Cloudflare reads for static assets: one rule
    # per line, "from to code". Both the bare and the closing-slash form are listed, so neither passes through a
    # temporary redirect first. They replace the small forwarding pages the earlier branch wrote.
    lines = []
    for slug, target in OLD_ADDRESSES.items():
        if os.path.exists(os.path.join(out, slug, "index.html")):
            stop(f"{out}/{slug}/ still holds an old forwarding page; remove that folder (the redirect rule replaces it)")
        lines += [f"/{slug} {target} 301", f"/{slug}/ {target} 301"]
    with open(os.path.join(out, "_redirects"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

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

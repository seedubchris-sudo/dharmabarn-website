#!/usr/bin/env python3
"""Offline checks for the built site in ./site. Run before every staging deploy:

    python3 checks/site_checks.py            # check ./site
    python3 checks/site_checks.py --self-test  # prove the checks catch planted faults (works on a temp copy)

Checks: broken internal links and anchors, basic HTML validity, accessibility basics (skip link, one h1 per
page view, image alt text, names on buttons and links, labels on fields), the workers.dev noindex rule, the 404
page, and the Worker's headers. Nothing is fetched from the network and nothing is installed. Uses only Python 3
and, for the Worker test, node. If lychee, html-validate or pa11y-ci are installed they run too; if not, that
extra check is skipped with a message and the built-in checks still run. Exit code 0 = all passed, 1 = a failure.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.dom.minidom
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
OPTIONAL_END = {"p", "li", "option", "tr", "td", "th", "dt", "dd"}
URL_ATTRS = {"href", "src", "poster", "data-src"}
REDIRECT_STUB = re.compile(r'http-equiv="refresh"', re.I)
ORIGIN = "https://dharmabarn.com"
NODE_DIRS = [Path.home() / "Library/Application Support/Indigo HQ/toolchain/node/bin", Path("/opt/homebrew/bin"), Path("/usr/local/bin")]


class Page(HTMLParser):
    """One parsed HTML file: tags in order, ids, links, and tag-balance problems."""

    def __init__(self, path, text):
        super().__init__(convert_charrefs=True)
        self.path, self.text = path, text
        self.els, self.stack, self.problems = [], [], []
        self.ids, self.urls = {}, []
        self.feed(text)
        self.close()
        for el in self.stack:
            if el["tag"] not in OPTIONAL_END | {"html", "body", "head"}:
                self.problems.append(f"<{el['tag']}> opened on line {el['line']} is never closed")

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        el = {"tag": tag, "attrs": a, "line": self.getpos()[0], "text": "", "parents": [e for e in self.stack],
              "names": []}
        self.els.append(el)
        if a.get("id") is not None:
            if a["id"] in self.ids:
                self.problems.append(f"duplicate id \"{a['id']}\" (lines {self.ids[a['id']]} and {el['line']})")
            self.ids[a["id"]] = el["line"]
        for k in URL_ATTRS:
            if a.get(k):
                self.urls.append((a[k], tag, k, el["line"]))
        if tag not in VOID:
            self.stack.append(el)
        for p in el["parents"]:  # accessible-name sources inside buttons and links
            if tag == "img" and a.get("alt"):
                p["names"].append(a["alt"])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1]["tag"] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        open_tags = [e["tag"] for e in self.stack]
        if tag not in open_tags:
            self.problems.append(f"</{tag}> on line {self.getpos()[0]} closes nothing")
            return
        while self.stack:
            el = self.stack.pop()
            if el["tag"] == tag:
                break
            if el["tag"] not in OPTIONAL_END:
                self.problems.append(f"<{el['tag']}> opened on line {el['line']} is not closed before </{tag}> on line {self.getpos()[0]}")

    def handle_data(self, data):
        if any(e["tag"] in ("script", "style") for e in self.stack):
            return
        for e in self.stack:
            e["text"] += data

    def find(self, tag):
        return [e for e in self.els if e["tag"] == tag]


def view_of(el):
    for p in reversed(el["parents"]):
        if "data-view" in p["attrs"]:
            return p["attrs"]["data-view"]
    return None


def name_of(el):
    a = el["attrs"]
    return (a.get("aria-label") or a.get("title") or " ".join(el["text"].split()) or " ".join(el["names"])).strip()


def load(site):
    pages = {}
    for p in sorted(site.rglob("*.html")):
        pages[p] = Page(p, p.read_text(encoding="utf-8"))
    return pages


def resolve(site, page_path, url):
    """Internal URL -> (file path or None, fragment). Follows the Worker's html_handling (folder -> index.html)."""
    u = urlsplit(url)
    path = unquote(u.path)
    if not path:
        return page_path, u.fragment
    base = site if path.startswith("/") else page_path.parent
    target = (base / path.lstrip("/")).resolve()
    if target.is_dir():
        target = target / "index.html"
    elif not target.exists() and target.with_suffix(".html").exists():
        target = target.with_suffix(".html")
    return (target if target.exists() else None), u.fragment


def check_links(site, pages):
    fails, external, internal = [], set(), 0
    for path, pg in pages.items():
        rel = path.relative_to(site)
        metas = [m["attrs"].get("content", "") for m in pg.find("meta") if (m["attrs"].get("http-equiv") or "").lower() == "refresh"]
        urls = list(pg.urls) + [(c.split("url=", 1)[1].strip(), "meta", "refresh", 0) for c in metas if "url=" in c]
        for url, tag, attr, line in urls:
            if url.startswith(("data:", "javascript:")):
                continue
            if url.startswith("mailto:"):
                if not re.fullmatch(r"mailto:[^@\s]+@[^@\s]+\.[a-z]{2,}(\?.*)?", url, re.I):
                    fails.append(f"{rel}:{line} malformed email link {url}")
                continue
            if url.startswith("tel:"):
                if not re.fullmatch(r"tel:\+?[0-9]{7,15}", url):
                    fails.append(f"{rel}:{line} malformed phone link {url}")
                continue
            if re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I) or url.startswith("//"):
                external.add(url)
                if url.startswith("http://"):
                    fails.append(f"{rel}:{line} insecure http link {url}")
                continue
            internal += 1
            target, frag = resolve(site, path, url)
            if target is None:
                fails.append(f"{rel}:{line} <{tag} {attr}> points to a missing file: {url}")
            elif frag and target.suffix == ".html":
                tp = pages.get(target) or Page(target, target.read_text(encoding="utf-8"))
                views = {e["attrs"]["data-view"] for e in tp.els if "data-view" in e["attrs"]}
                if frag not in tp.ids and frag not in views:
                    fails.append(f"{rel}:{line} link {url} names an anchor that does not exist (#{frag})")
    return fails, f"{internal} internal links and anchors checked; {len(external)} outside links listed, not fetched (offline)"


def check_html(site, pages):
    fails = []
    for path, pg in pages.items():
        rel = path.relative_to(site)
        t = pg.text
        fails += [f"{rel}: {p}" for p in pg.problems]
        if not t.lstrip().lower().startswith("<!doctype html>"):
            fails.append(f"{rel}: does not start with <!doctype html>")
        html = pg.find("html")
        if len(html) != 1 or not html[0]["attrs"].get("lang"):
            fails.append(f"{rel}: needs exactly one <html> with a lang attribute")
        if not any(m["attrs"].get("charset", "").lower() == "utf-8" for m in pg.find("meta")):
            fails.append(f"{rel}: no <meta charset=\"utf-8\">")
        titles = pg.find("title")
        if len(titles) != 1 or not titles[0]["text"].strip():
            fails.append(f"{rel}: needs exactly one non-empty <title>")
        for tag in ("head", "body"):
            if len(pg.find(tag)) != 1:
                fails.append(f"{rel}: needs exactly one <{tag}>")
        for e in pg.els:
            if e["tag"] == "img" and not e["attrs"].get("src"):
                fails.append(f"{rel}:{e['line']} <img> without src")
            if e["tag"] == "a" and "href" not in e["attrs"]:
                fails.append(f"{rel}:{e['line']} <a> without href")
    for name in ("sitemap.xml",):
        p = site / name
        if not p.exists():
            fails.append(f"{name} is missing")
            continue
        try:
            xml.dom.minidom.parse(str(p))
        except Exception as exc:  # noqa: BLE001
            fails.append(f"{name} is not well-formed XML: {exc}")
    if not (site / "robots.txt").exists():
        fails.append("robots.txt is missing")
    return fails, f"{len(pages)} HTML files, sitemap.xml and robots.txt checked"


def check_a11y(site, pages):
    fails, full = [], 0
    for path, pg in pages.items():
        rel = path.relative_to(site)
        if REDIRECT_STUB.search(pg.text):  # old-address redirect stubs: need only a visible link for no-script visitors
            if not any(name_of(a) for a in pg.find("a")):
                fails.append(f"{rel}: redirect page has no visible link")
            continue
        full += 1
        h1s = pg.find("h1")
        views = [e["attrs"]["data-view"] for e in pg.els if "data-view" in e["attrs"] and e["tag"] != "body"]
        if views:
            per = {v: 0 for v in views}
            for h in h1s:
                v = view_of(h)
                if v is None:
                    fails.append(f"{rel}:{h['line']} <h1> outside any page view")
                else:
                    per[v] += 1
            fails += [f"{rel}: page view \"{v}\" has {n} <h1> (needs exactly 1)" for v, n in per.items() if n != 1]
        elif len(h1s) != 1:
            fails.append(f"{rel}: has {len(h1s)} <h1> (needs exactly 1)")
        if len(pg.find("main")) != 1:
            fails.append(f"{rel}: needs exactly one <main>")
        body_els = [e for e in pg.els if any(p["tag"] == "body" for p in e["parents"])]
        focusable = [e for e in body_els if e["tag"] in ("a", "button", "input", "select", "textarea", "summary")]
        if views:  # the full site page: a skip link must be the first thing a keyboard reaches
            first = focusable[0] if focusable else None
            href = (first or {"attrs": {}})["attrs"].get("href", "")
            if not first or first["tag"] != "a" or not href.startswith("#") or "skip" not in name_of(first).lower():
                fails.append(f"{rel}: the first focusable element is not a \"Skip to content\" link")
            elif href[1:] not in pg.ids:
                fails.append(f"{rel}: the skip link points to #{href[1:]}, which does not exist")
            else:
                tgt = next(e for e in pg.els if e["attrs"].get("id") == href[1:])
                if tgt["tag"] != "main":
                    fails.append(f"{rel}: the skip link should land on <main>, not <{tgt['tag']}>")
        for e in body_els:
            a = e["attrs"]
            if e["tag"] == "img" and "alt" not in a:
                fails.append(f"{rel}:{e['line']} image without alt text: {a.get('src')}")
            if e["tag"] in ("a", "button") and not name_of(e) and a.get("aria-hidden") != "true":
                fails.append(f"{rel}:{e['line']} <{e['tag']}> has no text or aria-label")
            if e["tag"] == "iframe" and not a.get("title"):
                fails.append(f"{rel}:{e['line']} <iframe> without a title")
            if e["tag"] in ("input", "select", "textarea") and a.get("type") not in ("hidden", "submit", "button"):
                labelled = a.get("aria-label") or a.get("aria-labelledby") or any(p["tag"] == "label" for p in e["parents"]) \
                    or any(l["attrs"].get("for") == a.get("id") for l in pg.find("label") if a.get("id"))
                if not labelled:
                    fails.append(f"{rel}:{e['line']} form field without a label")
            if e["tag"] == "nav" and len(pg.find("nav")) > 1 and not a.get("aria-label"):
                fails.append(f"{rel}:{e['line']} more than one <nav>: each needs an aria-label")
            if a.get("tabindex") not in (None, "0", "-1"):
                fails.append(f"{rel}:{e['line']} positive tabindex changes the keyboard order")
        vp = next((m["attrs"].get("content", "") for m in pg.find("meta") if m["attrs"].get("name") == "viewport"), None)
        if vp is None:
            fails.append(f"{rel}: no viewport meta tag")
        elif "user-scalable=no" in vp or "maximum-scale=1" in vp:
            fails.append(f"{rel}: the viewport blocks zoom")
    return fails, f"{full} full pages checked (redirect pages need only a visible link)"


def check_headers_and_404(site, pages):
    fails = []
    hp = site / "_headers"
    rules, cur = {}, None
    for line in (hp.read_text() if hp.exists() else "").splitlines():
        if line.strip() and not line.startswith((" ", "\t")):
            cur = line.strip()
            rules[cur] = []
        elif line.strip() and cur:
            rules[cur].append(line.strip())
    robots = {pat for pat, hs in rules.items() if any(h.lower().startswith("x-robots-tag") for h in hs)}
    if not any(re.fullmatch(r"https://[^/]*\.workers\.dev/\*", p) and "X-Robots-Tag: noindex" in rules[p] for p in robots):
        fails.append("_headers: no \"X-Robots-Tag: noindex\" rule for the workers.dev hosts")
    for p in robots:
        if not re.fullmatch(r"https://[^/]*\.workers\.dev/\*", p):
            fails.append(f"_headers: X-Robots-Tag under \"{p}\" would also hide dharmabarn.com from search engines")
    idx = pages.get(site / "index.html")
    if idx and any(m["attrs"].get("name") == "robots" and "noindex" in m["attrs"].get("content", "") for m in idx.find("meta")):
        fails.append("index.html carries a robots noindex tag")
    nf = pages.get(site / "404.html")
    if not nf:
        fails.append("404.html is missing")
    else:
        if REDIRECT_STUB.search(nf.text) or "location.replace" in nf.text:
            fails.append("404.html redirects instead of saying the page was not found")
        if "not found" not in " ".join(h["text"] for h in nf.find("h1")).lower():
            fails.append("404.html has no \"not found\" heading")
        if not any(a["attrs"].get("href") == "/" for a in nf.find("a")):
            fails.append("404.html has no link to the home page")
        if not any(m["attrs"].get("name") == "robots" and "noindex" in m["attrs"].get("content", "") for m in nf.find("meta")):
            fails.append("404.html should carry a robots noindex tag")
    return fails, "_headers noindex rule limited to workers.dev; 404 page says so and links home"


def check_pages(site, pages):
    """Separate pages: each has its own title, description and canonical address, a menu of real links that marks
    the current page, a share image that exists, and a line in sitemap.xml."""
    fails, titles, descs, canon = [], {}, {}, set()
    for path, pg in pages.items():
        rel = path.relative_to(site).as_posix()
        if REDIRECT_STUB.search(pg.text) or rel == "404.html":
            continue
        own = "/" if rel == "index.html" else "/" + rel[:-len("index.html")]
        metas = {m["attrs"].get("name") or m["attrs"].get("property"): m["attrs"].get("content", "") for m in pg.find("meta")}
        title = " ".join((pg.find("title") or [{"text": ""}])[0]["text"].split())
        desc = metas.get("description", "").strip()
        if not desc:
            fails.append(f"{rel}: no meta description")
        for kind, seen, val in (("title", titles, title), ("description", descs, desc)):
            if val and val in seen:
                fails.append(f"{rel}: has the same {kind} as {seen[val]}")
            seen.setdefault(val, rel)
        links = [l["attrs"].get("href") for l in pg.find("link") if l["attrs"].get("rel") == "canonical"]
        if links != [ORIGIN + own]:
            fails.append(f"{rel}: canonical address should be {ORIGIN + own}, found {links}")
        canon.add(ORIGIN + own)
        if metas.get("og:url") != ORIGIN + own:
            fails.append(f"{rel}: og:url should be {ORIGIN + own}")
        img = metas.get("og:image", "")
        if not img.startswith(ORIGIN + "/") or not (site / img[len(ORIGIN) + 1:]).exists():
            fails.append(f"{rel}: share image is missing from the site: {img}")
        menu = [a for a in pg.find("a") if any(p["tag"] == "nav" for p in a["parents"])]
        if len(menu) < 5:
            fails.append(f"{rel}: the menu has {len(menu)} links (needs Recording, Video, Events, Sundance and Contact)")
        for a in menu:
            if not a["attrs"].get("href", "").startswith("/"):
                fails.append(f"{rel}:{a['line']} menu link is not a page address: {a['attrs'].get('href')}")
        current = [a["attrs"].get("href") for a in menu if a["attrs"].get("aria-current") == "page"]
        if current != ([] if own == "/" else [own]):
            fails.append(f"{rel}: the menu should mark {own if own != '/' else 'no page'} as the current page, found {current}")
        if 'data-view="' + rel.split("/")[0] + '"' not in pg.text and own != "/":
            fails.append(f"{rel}: does not hold the \"{rel.split('/')[0]}\" section")
        if len([e for e in pg.els if "data-view" in e["attrs"] and e["tag"] != "body"]) != 1:
            fails.append(f"{rel}: should hold exactly one section of the site")
    sm = site / "sitemap.xml"
    listed = set(re.findall(r"<loc>([^<]+)</loc>", sm.read_text())) if sm.exists() else set()
    for u in sorted(canon - listed):
        fails.append(f"sitemap.xml does not list {u}")
    for u in sorted(listed - canon):
        fails.append(f"sitemap.xml lists {u}, which is not a page of the site")
    return fails, f"{len(canon)} pages, each with its own title, description, canonical address and sitemap line"


# schema.org terms the site may use: each type with the properties allowed on it here. Checked against
# schema.org's published vocabulary on 2026-11-22. A type or property that is not listed fails the check, so a
# new one has to be looked up and added on purpose.
VOCAB = {
    "LocalBusiness": {"name", "additionalType", "description", "url", "image", "telephone", "email", "address",
                      "contactPoint", "sameAs"},
    "PostalAddress": {"streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry"},
    "ContactPoint": {"contactType", "telephone", "email"},
    "WebSite": {"name", "url", "publisher"},
    "Service": {"name", "serviceType", "url", "image", "provider", "description", "hasOfferCatalog"},
    "OfferCatalog": {"name", "itemListElement"},
    "Offer": {"itemOffered"},
    "BreadcrumbList": {"itemListElement"},
    "ListItem": {"position", "name", "item"},
    "ContactPage": {"name", "url", "mainEntity"},
}
LD_BLOCK = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
# Events and Sundance keep their wording until Chris decides: no facts block, and a short title is reported, not failed.
FROZEN_PAGES = {"events/index.html", "sundance/index.html"}
TITLE_LEN, DESC_LEN = (25, 70), (70, 200)


def ld_nodes(obj):
    """Every {...} inside a JSON-LD block, outermost first."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from ld_nodes(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from ld_nodes(v)


def check_search(site, pages):
    """Search wording and data: title and description length, heading order, no noindex, business facts (JSON-LD)
    that parse, use known schema.org terms and match the visible page, favicon, robots.txt, sitemap and redirects."""
    import json
    fails, blocks, defined, referenced, kept = [], 0, set(), set(), []
    for path, pg in pages.items():
        rel = path.relative_to(site).as_posix()
        if REDIRECT_STUB.search(pg.text):
            fails.append(f"{rel}: forwards with a meta refresh; old addresses belong in _redirects as 301 lines")
            continue
        if rel == "404.html":
            continue
        metas = {m["attrs"].get("name") or m["attrs"].get("property"): m["attrs"].get("content", "") for m in pg.find("meta")}
        title = " ".join((pg.find("title") or [{"text": ""}])[0]["text"].split())
        desc = metas.get("description", "").strip()
        if rel in FROZEN_PAGES and len(title) < TITLE_LEN[0]:
            kept.append(f"{rel.split('/')[0]} title is short ({len(title)} characters) and is left as it is")
        elif not TITLE_LEN[0] <= len(title) <= TITLE_LEN[1]:
            fails.append(f"{rel}: title is {len(title)} characters (aim for {TITLE_LEN[0]} to {TITLE_LEN[1]})")
        if not DESC_LEN[0] <= len(desc) <= DESC_LEN[1]:
            fails.append(f"{rel}: description is {len(desc)} characters (aim for {DESC_LEN[0]} to {DESC_LEN[1]})")
        if "noindex" in metas.get("robots", ""):
            fails.append(f"{rel}: carries a robots noindex tag, which would hide the page from search engines")
        last = 0
        for e in pg.els:
            if re.fullmatch(r"h[1-6]", e["tag"]):
                level = int(e["tag"][1])
                if level > last + 1:
                    fails.append(f"{rel}:{e['line']} heading order: <{e['tag']}> follows "
                                 + (f"<h{last}>" if last else "no heading") + " (a level is skipped)")
                last = level
        body_text = " ".join(((pg.find("body") or [{"text": ""}])[0]["text"]).split())
        tel_digits = {re.sub(r"\D", "", u) for u, *_ in pg.urls if u.startswith("tel:")}
        found = LD_BLOCK.findall(pg.text)
        if rel in FROZEN_PAGES and found:
            fails.append(f"{rel}: has a search-engine facts block; this page is to stay as it is until Chris decides")
        if rel == "index.html" and not found:
            fails.append("index.html: the business facts block (JSON-LD) is missing")
        for raw in found:
            blocks += 1
            try:
                data = json.loads(raw)
            except ValueError as exc:
                fails.append(f"{rel}: a JSON-LD block is not valid JSON: {exc}")
                continue
            if data.get("@context") != "https://schema.org":
                fails.append(f"{rel}: JSON-LD @context should be https://schema.org")
            if re.search(r"TODO|PHONE_|EMAIL\b|example\.com", raw):
                fails.append(f"{rel}: a JSON-LD block still holds a placeholder")
            for node in ld_nodes(data):
                kind = node.get("@type")
                keys = {k for k in node if not k.startswith("@")}
                if kind is None:
                    if keys:
                        fails.append(f"{rel}: JSON-LD item without @type: {sorted(keys)}")
                    elif "@id" in node:
                        referenced.add(node["@id"])
                    continue
                if kind not in VOCAB:
                    fails.append(f"{rel}: JSON-LD type \"{kind}\" is not in the checked schema.org list")
                    continue
                for k in sorted(keys - VOCAB[kind]):
                    fails.append(f"{rel}: JSON-LD property \"{k}\" is not in the checked list for {kind}")
                if "@id" in node and keys - {"name", "url"}:
                    defined.add(node["@id"])
                if "telephone" in node and re.sub(r"\D", "", node["telephone"]) not in tel_digits:
                    fails.append(f"{rel}: JSON-LD phone {node['telephone']} is not a phone link on the page")
                if "email" in node and "mailto:" + node["email"] not in {u for u, *_ in pg.urls}:
                    fails.append(f"{rel}: JSON-LD email {node['email']} is not an email link on the page")
                if kind == "PostalAddress":
                    for k in ("streetAddress", "addressLocality", "postalCode"):
                        if node.get(k, "") not in body_text:
                            fails.append(f"{rel}: JSON-LD {k} \"{node.get(k)}\" is not in the page's visible text")
                for k in ("url", "image", "item"):
                    v = node.get(k)
                    if isinstance(v, str):
                        if not v.startswith(ORIGIN + "/"):
                            fails.append(f"{rel}: JSON-LD {k} is not a dharmabarn.com address: {v}")
                        elif resolve(site, path, v[len(ORIGIN):])[0] is None:
                            fails.append(f"{rel}: JSON-LD {k} points to something not on the site: {v}")
                for v in node.get("sameAs", []):
                    if v not in {u for u, *_ in pg.urls}:
                        fails.append(f"{rel}: JSON-LD profile link {v} is not a link on the page")
    for ref in sorted(referenced - defined):
        fails.append(f"JSON-LD points to {ref}, which no page defines")

    ico = site / "favicon.ico"
    if not ico.exists() or ico.read_bytes()[:4] != b"\x00\x00\x01\x00":
        fails.append("favicon.ico is missing or is not an icon file")
    robots = (site / "robots.txt").read_text() if (site / "robots.txt").exists() else ""
    lines = [l.strip() for l in robots.splitlines()]
    if f"Sitemap: {ORIGIN}/sitemap.xml" not in lines:
        fails.append(f"robots.txt does not point at {ORIGIN}/sitemap.xml")
    if any(re.fullmatch(r"disallow:\s*/", l, re.I) for l in lines):
        fails.append("robots.txt blocks the whole site (Disallow: /)")
    sm = site / "sitemap.xml"
    for u in re.findall(r"<loc>([^<]+)</loc>", sm.read_text() if sm.exists() else ""):
        if not u.startswith(ORIGIN + "/") or not u.endswith("/"):
            fails.append(f"sitemap.xml: {u} should be an https://dharmabarn.com address ending in /")

    rp, rules = site / "_redirects", []
    if not rp.exists():
        fails.append("_redirects is missing (permanent redirects for the old GoDaddy addresses)")
    for n, line in enumerate(rp.read_text().splitlines() if rp.exists() else [], 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 3 or not parts[0].startswith("/") or not parts[1].startswith("/"):
            fails.append(f"_redirects:{n} should read \"/old-address /new-address/ 301\": {line}")
            continue
        src, dst, code = parts
        if code != "301":
            fails.append(f"_redirects:{n} uses {code}; old addresses need a permanent redirect (301)")
        if src in [r[0] for r in rules]:
            fails.append(f"_redirects:{n} repeats {src}")
        if "*" not in src and ":" not in src and resolve(site, site / "index.html", src)[0] is not None:
            fails.append(f"_redirects:{n} {src} is a real page or file on the site and would be hidden by the redirect")
        if resolve(site, site / "index.html", dst)[0] is None:
            fails.append(f"_redirects:{n} sends {src} to {dst}, which is not on the site")
        elif not dst.endswith("/"):
            fails.append(f"_redirects:{n} target {dst} should end in / (the form the pages are served at)")
        rules.append((src, dst))
    if rp.exists() and len(rules) > 2000:
        fails.append("_redirects has more than Cloudflare's 2,000 rules")
    return fails, (f"titles and descriptions within length, heading order, {blocks} JSON-LD blocks against {len(VOCAB)} "
                   f"schema.org types, favicon, robots.txt, sitemap, {len(rules)} permanent redirects"
                   + "".join(f"; {k}" for k in kept))


def find_tool(name):
    hit = shutil.which(name)
    if hit:
        return hit
    for d in NODE_DIRS:
        if (d / name).exists():
            return str(d / name)
    return None


def check_worker(site):
    node = find_tool("node")
    if not node:
        return None, "SKIPPED: node is not installed, so worker.js was not exercised"
    r = subprocess.run([node, str(ROOT / "checks" / "worker_headers.test.mjs")], capture_output=True, text=True, cwd=ROOT)
    out = (r.stdout + r.stderr).strip()
    return ([out or "worker test failed"] if r.returncode else []), out.splitlines()[-1] if out else ""


def optional_tools(site):
    """Run lychee / html-validate / pa11y-ci when they are already installed. Never installs anything."""
    notes, fails = [], []
    cmds = {"lychee": ["--offline", "--no-progress", "--root-dir", str(site), str(site)],
            "html-validate": [str(site)]}
    for tool, args in cmds.items():
        exe = find_tool(tool)
        if not exe:
            notes.append(f"SKIPPED {tool}: not installed on this Mac (the built-in check above still ran)")
            continue
        r = subprocess.run([exe] + args, capture_output=True, text=True)
        notes.append(f"{tool}: {'passed' if r.returncode == 0 else 'FAILED'}")
        if r.returncode:
            fails.append(f"{tool}:\n{(r.stdout + r.stderr)[-2000:]}")
    for tool in ("pa11y-ci", "lhci"):
        if not find_tool(tool):
            notes.append(f"SKIPPED {tool}: not installed on this Mac"
                         + (" (the built-in accessibility check above still ran)" if tool == "pa11y-ci" else " (no speed or SEO score budget is checked)"))
        else:
            notes.append(f"{tool} is installed but needs a local web server and a browser; run it by hand against staging")
    return fails, notes


def run(site, quiet=False):
    say = (lambda *a: None) if quiet else print
    pages = load(site)
    total = []
    for title, fn in (("Links", check_links), ("HTML validity (basic)", check_html), ("Accessibility (basic)", check_a11y),
                      ("Separate pages", check_pages), ("Search wording and data", check_search),
                      ("Search-engine headers and 404 page", check_headers_and_404)):
        fails, note = fn(site, pages)
        say(f"{'FAIL' if fails else 'ok  '}  {title}: {note}")
        for f in fails:
            say(f"        - {f}")
        total += fails
    fails, note = check_worker(site)
    say(f"{'SKIP' if fails is None else 'FAIL' if fails else 'ok  '}  Worker headers: {note}")
    for f in fails or []:
        say(f"        - {f}")
    total += fails or []
    fails, notes = optional_tools(site)
    for n in notes:
        say(f"      {n}")
    total += fails
    say(f"\n{'FAILED: ' + str(len(total)) + ' problem(s)' if total else 'ALL CHECKS PASSED'} ({site})")
    return total


PLANTS = [
    ("a broken internal link", "index.html", "</main>", '<a href="/no-such-page/">x</a></main>', "/no-such-page/"),
    ("a broken anchor", "index.html", "</main>", '<a href="#no-such-anchor">x</a></main>', "anchor that does not exist"),
    ("a second h1 in one view", "index.html", "</h1>", "</h1><h1>Again</h1>", "needs exactly 1"),
    ("an image without alt text", "index.html", "</main>", '<img src="img/barn-dusk.jpg"></main>', "without alt text"),
    ("a removed skip link", "index.html", 'id="skip-link"', 'id="skip-link" hidden-x', None),
    ("an unclosed tag", "404.html", "</main>", "<div></main>", "not closed"),
    ("noindex on every host", "_headers", "https://:version.:subdomain.workers.dev/*", "/*", "workers.dev"),
    ("a 404 page that redirects", "404.html", "<title>", '<meta http-equiv="refresh" content="0; url=/"><title>', "redirects"),
    ("a page with another page's title", "recording/index.html", "<title>Recording Studio near Longmont, CO · Dharma Barn</title>",
     "<title>Events · Dharma Barn</title>", "same title"),
    ("a title that is too short", "video/index.html", "<title>Live Session Video &amp; Concert Filming, Colorado · Dharma Barn</title>",
     "<title>Video</title>", "title is 5 characters"),
    ("a skipped heading level", "recording/index.html", "<h2>Equipment</h2>", "<h4>Equipment</h4>", "heading order"),
    ("noindex on a live page", "recording/index.html", "<title>", '<meta name="robots" content="noindex"><title>', "robots noindex tag"),
    ("broken JSON in the facts block", "index.html", '"@context": "https://schema.org",', '"@context": "https://schema.org"', "not valid JSON"),
    ("an invented schema.org type", "index.html", '"@type": "LocalBusiness"', '"@type": "RecordingStudio"', "not in the checked schema.org list"),
    ("an invented fact (opening hours)", "index.html", '"sameAs": [', '"openingHours": "Mo-Su", "sameAs": [', "not in the checked list for LocalBusiness"),
    ("a phone number that is not on the page", "index.html", '"telephone": "+1-720-878-5459"', '"telephone": "+1-720-555-0100"', "is not a phone link on the page"),
    ("a facts block on the Events page", "events/index.html", "</head>",
     '<script type="application/ld+json">{"@context": "https://schema.org", "@type": "LocalBusiness", "name": "Dharma Barn"}</script></head>',
     "stay as it is until Chris decides"),
    ("a missing favicon", "favicon.ico", None, None, "favicon.ico is missing"),
    ("robots.txt that blocks the site", "robots.txt", "Allow: /", "Disallow: /", "blocks the whole site"),
    ("a temporary redirect", "_redirects", "/lander / 301", "/lander / 302", "permanent redirect (301)"),
    ("a redirect to a page that does not exist", "_redirects", "/lander/ / 301", "/lander/ /nowhere/ 301", "which is not on the site"),
    ("an old forwarding page left in place", "contact/index.html", "<title>", '<meta http-equiv="refresh" content="0; url=/"><title>', "meta refresh"),
    ("a page left out of the sitemap", "sitemap.xml", "<url><loc>https://dharmabarn.com/events/</loc></url>\n", "", "sitemap.xml does not list"),
    ("a menu link back to a #hash view", "video/index.html", '<a href="/contact/">Contact</a>', '<a href="#contact">Contact</a>',
     "not a page address"),
]


def self_test(site):
    """Each planted fault must be caught on a temporary copy; the real ./site is never changed."""
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for what, fname, old, new, expect in PLANTS:
            copy = Path(tmp) / what.replace(" ", "-")
            shutil.copytree(site, copy, ignore=shutil.ignore_patterns("media"))
            if (site / "media").exists():
                os.symlink(site / "media", copy / "media")  # the video files are large; point at them instead of copying
            p = copy / fname
            if old is None and new is None:  # plant: the file is gone
                p.unlink()
                fails = run(copy, quiet=True)
                hit = [f for f in fails if expect in f]
                print(f"{'ok  ' if hit else 'FAIL'}  planted {what}: {'caught — ' + hit[0][:110] if hit else 'NOT caught'}")
                bad += 0 if hit else 1
                continue
            text = p.read_text(encoding="utf-8")
            if what == "a removed skip link":
                text = re.sub(r'<a class="skip"[^>]*>.*?</a>\n?', "", text, count=1)
            elif old not in text:
                print(f"FAIL  self-test could not plant {what}: marker not found in {fname}")
                bad += 1
                continue
            else:
                text = text.replace(old, new, 1)
            p.write_text(text, encoding="utf-8")
            fails = run(copy, quiet=True)
            hit = [f for f in fails if (expect or "Skip to content") in f]
            print(f"{'ok  ' if hit else 'FAIL'}  planted {what}: {'caught — ' + hit[0][:110] if hit else 'NOT caught'}")
            bad += 0 if hit else 1
    print(f"\n{'SELF-TEST FAILED' if bad else 'SELF-TEST PASSED'}: {len(PLANTS) - bad} of {len(PLANTS)} planted faults caught")
    return bad


if __name__ == "__main__":
    site_dir = ROOT / "site"
    if "--self-test" in sys.argv:
        sys.exit(1 if self_test(site_dir) else 0)
    sys.exit(1 if run(site_dir) else 0)

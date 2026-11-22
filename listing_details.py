"""Business and video listing details for search engines (schema.org JSON-LD), added to each page by build_pages.py.

Rule: nothing here may say something the page does not already say. `block()` stops the build if a business fact
below is not in the page source, so a change of address, phone or email on the site cannot leave an old one here.

Two kinds of entry:
- The business (one per page, the same on all six): name, address, the two phone numbers with the roles the
  Contact page gives them, email, and the three social links from the footer. No opening hours, map coordinates,
  prices or ratings: the site states none.
- Videos, only where the video plays on that page (Google's rule for video listings): the reel on Home, and the
  featured show and the Cactus Pals clip on Video. The clips that open on YouTube are left out for that reason.

Where each video date comes from (the pages do not print them):
- s7iopa9lM4o and mR_TFoWGO_8: the upload date YouTube shows for the video, read 2026-11-22.
- Cactus Pals: the day the file was added to this site (commit fce6a99, 2026-10-01).
"""
import json
import re

ORIGIN = "https://dharmabarn.com"
BUSINESS_ID = ORIGIN + "/#business"

BUSINESS = {
    "name": "Dharma Barn",
    "street": "12281 N 75th St",
    "city": "Longmont",
    "region": "CO",
    "postcode": "80503",
    "email": "dharmafarm@icloud.com",
    # (number as dialled, number as printed on the page, role as printed on the Contact page)
    "phones": [("+17208785459", "(720) 878-5459", "Recording and video"),
               ("+13038081091", "(303) 808-1091", "The barn and events")],
    "same_as": ["https://www.youtube.com/@dharma_barn", "https://www.instagram.com/dharma_farm_/",
                "https://www.facebook.com/p/Dharma-Farm-100095685273767/"],
    "image": "barn-dusk.jpg",
}

# view -> videos that play on that page. `marker` is text that must be in that page's source.
VIDEOS = {
    "home": [
        {"name": "Dharma Barn Sizzle Reel", "marker": "embed/s7iopa9lM4o", "thumb": "reel-poster.jpg",
         "uploaded": "2025-10-06T11:12:14-07:00", "embed": "https://www.youtube-nocookie.com/embed/s7iopa9lM4o"},
    ],
    "video": [
        {"name": "Shook Twins at Dharma Barn", "marker": 'data-yt="mR_TFoWGO_8"', "thumb": "shook-twins-poster.jpg",
         "uploaded": "2025-10-06T16:25:48-07:00", "embed": "https://www.youtube-nocookie.com/embed/mR_TFoWGO_8",
         "description": "Shook Twins, live at the barn."},
        {"name": "Cactus Pals", "marker": "media/cactus-pals-clip.mp4", "thumb": "cactus-pals-poster.jpg",
         "uploaded": "2026-10-01T18:35:21-06:00", "content": "/media/cactus-pals-clip.mp4", "duration": "PT2M42S",
         "duration_marker": "2:42"},
    ],
}


def _need(source, text, what, stop):
    if text not in source:
        stop(f"listing details: {what} is no longer on the page: {text!r}")


def block(view, source, description, stop):
    """The <script type="application/ld+json"> block for one page. `source` is the one-file site's HTML."""
    b = BUSINESS
    _need(source, f"{b['name']} · {b['street']}, {b['city']}, {b['region']} {b['postcode']}", "the footer address", stop)
    _need(source, f"mailto:{b['email']}\"", "the email address", stop)
    for dial, shown, role in b["phones"]:
        _need(source, f'href="tel:{dial}">{shown}<', f"the phone number {shown}", stop)
        _need(source, f'<span class="role">{role}</span>', f"the role \"{role}\"", stop)
    for url in b["same_as"]:
        _need(source, f'href="{url}"', "a footer link", stop)
    business = {
        "@type": "LocalBusiness",
        "@id": BUSINESS_ID,
        "name": b["name"],
        "url": ORIGIN + "/",
        "description": description,
        "image": f"{ORIGIN}/img/{b['image']}",
        "email": b["email"],
        "address": {"@type": "PostalAddress", "streetAddress": b["street"], "addressLocality": b["city"],
                    "addressRegion": b["region"], "postalCode": b["postcode"], "addressCountry": "US"},
        "contactPoint": [{"@type": "ContactPoint", "telephone": dial, "contactType": role} for dial, _, role in b["phones"]],
        "sameAs": b["same_as"],
    }
    graph = [business]
    for v in VIDEOS.get(view, []):
        _need(source, v["marker"], f"the video \"{v['name']}\"", stop)
        _need(source, v["name"], f"the video name \"{v['name']}\"", stop)
        if "duration_marker" in v:
            _need(source, v["duration_marker"], f"the length of \"{v['name']}\"", stop)
        if "description" in v and v["description"] not in re.sub(r"<[^>]+>", "", source):
            stop(f"listing details: the caption for \"{v['name']}\" is no longer on the page")
        entry = {"@type": "VideoObject", "name": v["name"], "thumbnailUrl": f"{ORIGIN}/img/{v['thumb']}",
                 "uploadDate": v["uploaded"], "publisher": {"@id": BUSINESS_ID}}
        if "description" in v:
            entry["description"] = v["description"]
        if "embed" in v:
            entry["embedUrl"] = v["embed"]
        if "content" in v:
            entry["contentUrl"] = ORIGIN + v["content"]
        if "duration" in v:
            entry["duration"] = v["duration"]
        graph.append(entry)
    data = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=1)
    return '<script type="application/ld+json">\n' + data.replace("</", "<\\/") + "\n</script>\n"

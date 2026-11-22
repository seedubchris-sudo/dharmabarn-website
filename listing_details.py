"""Business facts and video entries for search engines (schema.org JSON-LD). build_pages.py writes one block per
page from this file; nothing else in the repo writes one.

Rule: nothing here may say something the page does not already say. `verify()` stops the build if a business fact
below is not in the page source, so a change of address, phone or email on the site cannot leave an old one here.

Two kinds of entry come from this file:
- The business: name, street address as the footer shows it, the recording and video phone number, email, and the
  three profile links from the footer. Left out on purpose, because the site does not state them or the decision
  is not made: opening hours, map coordinates, prices, reviews, "Dharma Farm" as a second name, a studio or venue
  business type, and the events phone number.
- Videos, only where the video plays on that page (Google's rule for video listings): the reel on Home, and the
  featured show and the Cactus Pals clip on Video. The clips that open on YouTube are left out for that reason.

Where each video date comes from (the pages do not print them):
- s7iopa9lM4o and mR_TFoWGO_8: the upload date YouTube shows for the video, read 2026-11-22.
- Cactus Pals: the day the file was added to this site (commit fce6a99, 2026-10-01).
"""
import re

ORIGIN = "https://dharmabarn.com"
BUSINESS_ID = ORIGIN + "/#business"

FACTS = {
    "name": "Dharma Barn",
    # Chris Wright's number. (as written in the block, as dialled in the page's link, as printed, role as printed
    # on the Contact page)
    "phone": "+1-720-878-5459", "phone_link": "+17208785459", "phone_shown": "(720) 878-5459",
    "phone_role": "Recording and video",
    "email": "dharmafarm@icloud.com",
    "street": "12281 N 75th St", "city": "Longmont", "region": "CO", "postcode": "80503", "country": "US",
    "profiles": ["https://www.youtube.com/@dharma_barn", "https://www.instagram.com/dharma_farm_/",
                 "https://www.facebook.com/p/Dharma-Farm-100095685273767/"],
    "about": "Recording studio and filmed live sessions in a 1918 barn in Hygiene, Colorado, between Longmont and Lyons.",
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


def verify(source, stop):
    """Stop the build unless every business fact above is in the one-file site's HTML (`source`)."""
    f = FACTS
    _need(source, f"{f['name']} · {f['street']}, {f['city']}, {f['region']} {f['postcode']}", "the footer address", stop)
    _need(source, f"mailto:{f['email']}\"", "the email address", stop)
    if re.sub(r"\D", "", f["phone"]) != re.sub(r"\D", "", f["phone_link"]):
        stop("listing details: the phone number is written two different ways in FACTS")
    _need(source, f'href="tel:{f["phone_link"]}">{f["phone_shown"]}<', f"the phone number {f['phone_shown']}", stop)
    _need(source, f'<span class="role">{f["phone_role"]}</span>', f"the role \"{f['phone_role']}\"", stop)
    for url in f["profiles"]:
        _need(source, f'href="{url}"', "a footer link", stop)


def business():
    """The one full business entry (plain LocalBusiness). Home and Contact carry it; other pages point at it."""
    f = FACTS
    return {
        "@type": "LocalBusiness", "@id": BUSINESS_ID, "name": f["name"],
        "description": f["about"], "url": ORIGIN + "/", "image": f"{ORIGIN}/img/{f['image']}",
        "telephone": f["phone"], "email": f["email"],
        "address": {"@type": "PostalAddress", "streetAddress": f["street"], "addressLocality": f["city"],
                    "addressRegion": f["region"], "postalCode": f["postcode"], "addressCountry": f["country"]},
        "contactPoint": [{"@type": "ContactPoint", "contactType": f["phone_role"],
                          "telephone": f["phone"], "email": f["email"]}],
        "sameAs": f["profiles"],
    }


def videos(view, source, stop):
    """VideoObject entries for the videos that play on this page (an empty list for most pages)."""
    out = []
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
        out.append(entry)
    return out

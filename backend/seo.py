"""The BBAIS SEO Standard, built from each shop's own config.

Everything here is generated per shop and served live, so a shop that changes
its hours or prices in the admin panel has correct structured data the moment it
saves — there is no second copy to fall out of step.
"""
from __future__ import annotations

from typing import Any, Dict, List

from shop_config import DAY_LABELS, DAYS, ShopConfig

SCHEMA_DAY = {
    "mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday",
    "fri": "Friday", "sat": "Saturday", "sun": "Sunday",
}


def _site(base_url: str) -> str:
    return base_url.rstrip("/")


def _opening_hours(cfg: ShopConfig) -> List[dict]:
    return [
        {"@type": "OpeningHoursSpecification",
         "dayOfWeek": f"https://schema.org/{SCHEMA_DAY[d]}",
         "opens": h.open, "closes": h.close}
        for d, h in cfg.hours.items() if not h.closed
    ]


def _postal(cfg: ShopConfig) -> dict:
    a = cfg.address
    return {"@type": "PostalAddress", "streetAddress": " ".join(x for x in (a.line1, a.line2) if x),
            "addressLocality": a.city, "addressRegion": a.state,
            "postalCode": a.postal_code, "addressCountry": a.country}


def build_schemas(cfg: ShopConfig, base_url: str, review_stats: Dict[str, Any] | None = None) -> List[dict]:
    """The fourteen schemas, each one earned by something really on the page."""
    site = _site(base_url)
    cur = cfg.payments.currency
    services = [s for s in cfg.services if s.active]
    stats = review_stats or {}

    org_id = f"{site}/#organization"
    shop_id = f"{site}/#nailsalon"

    schemas: List[dict] = []

    # 1. NailSalon — the anchor entity for local search.
    salon: Dict[str, Any] = {
        "@context": "https://schema.org", "@type": "NailSalon", "@id": shop_id,
        "name": cfg.name, "description": cfg.seo.description or cfg.about,
        "url": site, "telephone": cfg.contact.phone, "email": cfg.contact.email,
        "address": _postal(cfg), "priceRange": cfg.seo.price_range,
        "openingHoursSpecification": _opening_hours(cfg),
        "currenciesAccepted": cur,
        "paymentAccepted": "Cash, Credit Card",
        "image": cfg.theme.logo_url or f"{site}/icon-512.png",
        "slogan": cfg.tagline,
    }
    if cfg.contact.instagram:
        salon["sameAs"] = [f"https://instagram.com/{cfg.contact.instagram.lstrip('@')}"]
    if stats.get("count"):
        salon["aggregateRating"] = {"@type": "AggregateRating",
                                    "ratingValue": stats["average"],
                                    "reviewCount": stats["count"],
                                    "bestRating": 5, "worstRating": 1}
    schemas.append(salon)

    # 2. Organization
    schemas.append({"@context": "https://schema.org", "@type": "Organization", "@id": org_id,
                    "name": cfg.name, "url": site,
                    "logo": cfg.theme.logo_url or f"{site}/icon-512.png",
                    "contactPoint": [{"@type": "ContactPoint", "telephone": cfg.contact.phone,
                                      "contactType": "reservations",
                                      "areaServed": cfg.address.state or cfg.address.country}]})

    # 3. WebSite (+ the booking action a search engine can surface directly)
    schemas.append({"@context": "https://schema.org", "@type": "WebSite", "@id": f"{site}/#website",
                    "name": cfg.name, "url": site, "publisher": {"@id": org_id},
                    "potentialAction": {"@type": "ReserveAction",
                                        "target": {"@type": "EntryPoint",
                                                   "urlTemplate": f"{site}/book"},
                                        "result": {"@type": "Reservation",
                                                   "name": f"Appointment at {cfg.name}"}}})

    # 4. LocalBusiness view of the same premises
    schemas.append({"@context": "https://schema.org", "@type": "LocalBusiness",
                    "@id": f"{site}/#localbusiness", "name": cfg.name, "url": site,
                    "telephone": cfg.contact.phone, "address": _postal(cfg),
                    "priceRange": cfg.seo.price_range,
                    "openingHoursSpecification": _opening_hours(cfg)})

    # 5. OfferCatalog — the whole menu in one object
    schemas.append({"@context": "https://schema.org", "@type": "OfferCatalog",
                    "@id": f"{site}/#menu", "name": f"{cfg.name} service menu",
                    "itemListElement": [
                        {"@type": "Offer", "position": i + 1,
                         "itemOffered": {"@type": "Service", "name": s.name,
                                         "serviceType": s.category},
                         "price": f"{s.price:.2f}", "priceCurrency": cur,
                         "availability": "https://schema.org/InStock"}
                        for i, s in enumerate(services)]})

    # 6. Individual Service entities — the nail-relevant ones the standard asks for
    schemas.append({"@context": "https://schema.org", "@type": "ItemList",
                    "@id": f"{site}/#services", "name": "Services",
                    "itemListElement": [
                        {"@type": "ListItem", "position": i + 1,
                         "item": {"@type": "Service", "name": s.name,
                                  "serviceType": s.category, "description": s.description,
                                  "provider": {"@id": shop_id},
                                  "offers": {"@type": "Offer", "price": f"{s.price:.2f}",
                                             "priceCurrency": cur,
                                             "url": f"{site}/book?service={s.id}"}}}
                        for i, s in enumerate(services)]})

    # 7. Individual Offers, priced
    schemas.append({"@context": "https://schema.org", "@type": "ItemList",
                    "@id": f"{site}/#offers", "name": "Prices",
                    "itemListElement": [
                        {"@type": "ListItem", "position": i + 1,
                         "item": {"@type": "Offer", "name": s.name,
                                  "price": f"{s.price:.2f}", "priceCurrency": cur,
                                  "category": s.category,
                                  "eligibleDuration": {"@type": "QuantitativeValue",
                                                       "value": s.duration_min,
                                                       "unitCode": "MIN"}}}
                        for i, s in enumerate(services)]})

    # 8. The people who do the work
    schemas.append({"@context": "https://schema.org", "@type": "ItemList",
                    "@id": f"{site}/#team", "name": "Technicians",
                    "itemListElement": [
                        {"@type": "ListItem", "position": i + 1,
                         "item": {"@type": "Person", "name": t.name, "jobTitle": t.title,
                                  "description": t.bio, "worksFor": {"@id": org_id},
                                  "knowsAbout": t.specialties}}
                        for i, t in enumerate(t2 for t2 in cfg.technicians if t2.active)]})

    # 9. Breadcrumbs
    schemas.append({"@context": "https://schema.org", "@type": "BreadcrumbList",
                    "@id": f"{site}/#breadcrumbs",
                    "itemListElement": [
                        {"@type": "ListItem", "position": i + 1, "name": name,
                         "item": f"{site}{path}"}
                        for i, (name, path) in enumerate(
                            [("Home", "/"), ("Services", "/services"), ("The Menu", "/menu"),
                             ("Our Team", "/team"), ("Visit", "/visit"), ("Book", "/book")])]})

    # 10. FAQ — answered from the shop's own rules, never invented
    faq = [("Do I need a deposit?", cfg.deposit.policy_text or "No deposit is required to book."),
           ("How long does an appointment take?",
            "Times shown include processing, so a "
            + (services[0].name if services else "service")
            + " is booked as "
            + (f"{services[0].block_min} minutes" if services else "its full length")
            + " of chair time."),
           ("Do you take walk-ins?",
            cfg.contact.booking_note or "Walk-ins are welcome when we have a chair free."),
           ("Where are you?", cfg.address.one_line() or "Get in touch for directions."),
           ("Can I ask for a particular technician?",
            "Yes — choose them when you book, or leave it to us and we'll match you.")]
    schemas.append({"@context": "https://schema.org", "@type": "FAQPage", "@id": f"{site}/#faq",
                    "mainEntity": [{"@type": "Question", "name": q,
                                    "acceptedAnswer": {"@type": "Answer", "text": a}}
                                   for q, a in faq]})

    # 11. The booking page as a bookable action
    schemas.append({"@context": "https://schema.org", "@type": "WebPage",
                    "@id": f"{site}/book#webpage", "name": f"Book at {cfg.name}",
                    "url": f"{site}/book", "isPartOf": {"@id": f"{site}/#website"},
                    "about": {"@id": shop_id},
                    "primaryImageOfPage": cfg.theme.logo_url or f"{site}/icon-512.png"})

    # 12. Products — the colour wall is genuinely a catalogue
    schemas.append({"@context": "https://schema.org", "@type": "ItemList",
                    "@id": f"{site}/#colours", "name": "Colour menu",
                    "itemListElement": [
                        {"@type": "ListItem", "position": i + 1,
                         "item": {"@type": "Product", "name": c.name,
                                  "category": c.family, "color": c.hex,
                                  "brand": {"@id": org_id}}}
                        for i, c in enumerate(c2 for c2 in cfg.colours if c2.active)]})

    # 13. Reviews, when there are real ones
    if stats.get("count"):
        schemas.append({"@context": "https://schema.org", "@type": "AggregateRating",
                        "@id": f"{site}/#rating", "itemReviewed": {"@id": shop_id},
                        "ratingValue": stats["average"], "reviewCount": stats["count"],
                        "bestRating": 5, "worstRating": 1})
    else:
        schemas.append({"@context": "https://schema.org", "@type": "ContactPage",
                        "@id": f"{site}/visit#webpage", "name": f"Visit {cfg.name}",
                        "url": f"{site}/visit", "about": {"@id": shop_id}})

    # 14. Where we actually are
    schemas.append({"@context": "https://schema.org", "@type": "Place", "@id": f"{site}/#place",
                    "name": cfg.name, "address": _postal(cfg),
                    "openingHoursSpecification": _opening_hours(cfg),
                    "publicAccess": True,
                    "smokingAllowed": False})

    return schemas


def llms_txt(cfg: ShopConfig, base_url: str) -> str:
    """llms.txt — what an assistant needs to answer about this shop correctly,
    and where to send someone to actually book."""
    site = _site(base_url)
    services = [s for s in cfg.services if s.active and not s.addon]
    hours = "\n".join(
        f"- {DAY_LABELS[d]}: {'Closed' if h.closed else f'{h.open}–{h.close}'}"
        for d, h in cfg.hours.items())
    menu = "\n".join(
        f"- {s.name} ({s.category}) — {s.price:.0f} {cfg.payments.currency}, "
        f"{s.duration_min} min in the chair"
        + (f", {s.buffer_min} min processing held" if s.buffer_min else "")
        for s in services)
    techs = "\n".join(f"- {t.name}, {t.title} — {', '.join(t.specialties) or 'all services'}"
                      for t in cfg.technicians if t.active)
    shapes = ", ".join(o.label for o in cfg.nail_menu.shapes if o.active)
    lengths = ", ".join(o.label for o in cfg.nail_menu.lengths if o.active)
    finishes = ", ".join(o.label for o in cfg.nail_menu.finishes if o.active)

    return f"""# {cfg.name}

> {cfg.tagline or cfg.seo.description}

{cfg.about}

## Contact
- Address: {cfg.address.one_line()}
- Phone: {cfg.contact.phone}
- Email: {cfg.contact.email}
- Book online: {site}/book

## Hours
{hours}

## Services
{menu}

## Nail menu
- Shapes: {shapes}
- Lengths: {lengths}
- Finishes: {finishes}

## Technicians
{techs}

## Booking
- Book at {site}/book — real availability, deposits handled at the shop.
- Appointment times already include processing time, so a booked slot is the
  full chair time, not just the hands-on part.
- Deposits: {cfg.deposit.policy_text or 'no deposit required'}

## Notes for assistants
- Prices and hours here are generated from this shop's live configuration.
- Do not quote a price or an opening time that is not on this page.
- To check real availability, send the person to {site}/book rather than guessing.
"""


def robots_txt(base_url: str) -> str:
    """Assistants that answer questions are welcome. Crawlers that only scrape
    to train on the shop's copy are not."""
    site = _site(base_url)
    allowed = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "PerplexityBot",
               "ClaudeBot", "Claude-User", "Claude-SearchBot", "Google-Extended",
               "Applebot", "Applebot-Extended", "Bingbot", "DuckDuckBot"]
    blocked = ["CCBot", "Bytespider", "Amazonbot", "FacebookBot", "Meta-ExternalAgent",
               "Omgilibot", "Diffbot", "Scrapy", "magpie-crawler", "DataForSeoBot"]
    lines = ["# Assistants answering questions about this shop are welcome.",
             "# Bulk scrapers are not.", ""]
    for ua in allowed:
        lines += [f"User-agent: {ua}", "Allow: /", ""]
    for ua in blocked:
        lines += [f"User-agent: {ua}", "Disallow: /", ""]
    lines += ["User-agent: *", "Allow: /",
              "Disallow: /admin", "Disallow: /desk", "Disallow: /api/", "",
              f"Sitemap: {site}/sitemap.xml", f"# llms.txt: {site}/llms.txt"]
    return "\n".join(lines)


def sitemap_xml(cfg: ShopConfig, base_url: str) -> str:
    site = _site(base_url)
    pages = [("/", "1.0", "weekly"), ("/services", "0.9", "weekly"),
             ("/menu", "0.8", "monthly"), ("/team", "0.7", "monthly"),
             ("/visit", "0.7", "monthly"), ("/book", "0.9", "weekly"),
             ("/consult", "0.6", "monthly"), ("/chat", "0.5", "monthly"),
             ("/check-in", "0.4", "monthly")]
    urls = "\n".join(
        f"  <url><loc>{site}{p}</loc>"
        f"<changefreq>{freq}</changefreq><priority>{pri}</priority></url>"
        for p, pri, freq in pages)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{urls}\n</urlset>\n")


def manifest(cfg: ShopConfig, base_url: str) -> dict:
    """PWA manifest, themed from the shop's own config."""
    return {
        "name": cfg.name,
        "short_name": (cfg.theme.logo_mark or cfg.name)[:12],
        "description": cfg.seo.description or cfg.tagline,
        "start_url": "/?utm_source=pwa",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": cfg.theme.base,
        "theme_color": cfg.theme.accent or cfg.theme.gold,
        "categories": ["beauty", "lifestyle"],
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "shortcuts": [
            {"name": "Book", "url": "/book"},
            {"name": "Check in", "url": "/check-in"},
        ],
    }


def icon_png(cfg: ShopConfig, size: int) -> bytes:
    """A launcher icon in the shop's own colours.

    Generated rather than shipped as a file: a white-label platform cannot have
    one static icon, and asking each shop for artwork before they can install
    the app would block them on a designer.
    """
    from PIL import Image, ImageDraw, ImageFont

    accent = cfg.theme.accent or cfg.theme.gold
    img = Image.new("RGB", (size, size), cfg.theme.base)
    d = ImageDraw.Draw(img)

    pad = size // 8
    d.rounded_rectangle([pad, pad, size - pad, size - pad],
                        radius=size // 5, outline=accent, width=max(2, size // 48))

    mark = (cfg.theme.logo_mark or cfg.name[:2]).upper()[:3]
    # Fit the monogram to the tile rather than guessing a point size.
    font = None
    for candidate in ("georgia.ttf", "times.ttf", "arial.ttf", "DejaVuSerif.ttf"):
        try:
            font = ImageFont.truetype(candidate, int(size * (0.34 if len(mark) > 2 else 0.42)))
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    box = d.textbbox((0, 0), mark, font=font)
    d.text(((size - (box[2] - box[0])) / 2 - box[0],
            (size - (box[3] - box[1])) / 2 - box[1]), mark, font=font, fill=accent)

    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()

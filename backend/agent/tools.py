"""What the front-desk agent can actually DO.

Every tool here calls the SAME function the field-based flow calls. The agent
does not have a private path to the database, its own pricing, or its own idea
of what is free — so a booking made by talking is identical to one made by
clicking, and the two can never drift into separate sources of truth.

Prices, times and availability are always returned BY these tools. The model is
never asked to work them out, so it cannot invent a price.
"""
from __future__ import annotations

from datetime import date as Date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import bookings
import scheduling
import walkins
from scheduling import QuoteError, build_quote
from shop_config import ShopConfig


class ToolError(Exception):
    """A failure the agent should tell the client about, in the shop's voice."""


# --------------------------------------------------------------- schemas ----
def tool_schemas(cfg: ShopConfig) -> List[dict]:
    """OpenAI-style tool definitions, built from THIS shop's config so the model
    can only ever choose ids the shop actually offers."""
    service_ids = [s.id for s in cfg.services if s.active]
    tech_ids = [t.id for t in cfg.technicians if t.active]
    shapes = [o.id for o in cfg.nail_menu.shapes if o.active]
    lengths = [o.id for o in cfg.nail_menu.lengths if o.active]
    finishes = [o.id for o in cfg.nail_menu.finishes if o.active]
    colours = [c.id for c in cfg.colours if c.active]

    look = {
        "shape": {"type": "string", "enum": shapes, "description": "Nail shape"},
        "length": {"type": "string", "enum": lengths, "description": "Nail length"},
        "finish": {"type": "string", "enum": finishes, "description": "Finish over the colour"},
    }

    return [
        {"type": "function", "function": {
            "name": "list_services",
            "description": "The shop's service menu with real prices and how long each takes.",
            "parameters": {"type": "object", "properties": {}},
        }},
        {"type": "function", "function": {
            "name": "shop_info",
            "description": "Opening hours, address, phone, deposit policy and the colour menu.",
            "parameters": {"type": "object", "properties": {}},
        }},
        {"type": "function", "function": {
            "name": "get_quote",
            "description": "The real price and chair time for a service with a chosen look. "
                           "Always call this before quoting any price.",
            "parameters": {"type": "object", "properties": {
                "service": {"type": "string", "enum": service_ids},
                **look,
                "colour": {"type": "string", "enum": colours},
            }, "required": ["service"]},
        }},
        {"type": "function", "function": {
            "name": "check_availability",
            "description": "Real open start times for a service on a date. Use YYYY-MM-DD. "
                           "Never guess times; only offer what this returns.",
            "parameters": {"type": "object", "properties": {
                "service": {"type": "string", "enum": service_ids},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                **look,
                "technician": {"type": "string", "enum": tech_ids,
                               "description": "Omit for no preference"},
            }, "required": ["service", "date"]},
        }},
        {"type": "function", "function": {
            "name": "find_next_days",
            "description": "Which of the coming days have any opening for a service. "
                           "Use this when the client has no particular day in mind.",
            "parameters": {"type": "object", "properties": {
                "service": {"type": "string", "enum": service_ids},
                "days": {"type": "integer", "description": "How many days ahead to scan, max 14"},
                **look,
                "technician": {"type": "string", "enum": tech_ids},
            }, "required": ["service"]},
        }},
        {"type": "function", "function": {
            "name": "create_booking",
            "description": "Confirm a booking. Only call once the client has given a name and "
                           "phone number AND agreed to a specific date and time you offered.",
            "parameters": {"type": "object", "properties": {
                "service": {"type": "string", "enum": service_ids},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "start": {"type": "string", "description": "24h HH:MM, exactly as offered"},
                **look,
                "colour": {"type": "string", "enum": colours},
                "technician": {"type": "string", "enum": tech_ids},
                "name": {"type": "string"},
                "phone": {"type": "string"},
                "notes": {"type": "string"},
            }, "required": ["service", "date", "start", "name", "phone"]},
        }},
        {"type": "function", "function": {
            "name": "lookup_booking",
            "description": "Look up an existing booking by its reference.",
            "parameters": {"type": "object", "properties": {
                "reference": {"type": "string"}}, "required": ["reference"]},
        }},
        {"type": "function", "function": {
            "name": "check_in",
            "description": "Check a client in for an appointment they already have.",
            "parameters": {"type": "object", "properties": {
                "reference": {"type": "string"}}, "required": ["reference"]},
        }},
        {"type": "function", "function": {
            "name": "join_queue",
            "description": "Put a walk-in in today's line and report their position and wait.",
            "parameters": {"type": "object", "properties": {
                "service": {"type": "string", "enum": service_ids},
                "name": {"type": "string"},
                "phone": {"type": "string"},
                "technician": {"type": "string", "enum": tech_ids},
            }, "required": ["service", "name", "phone"]},
        }},
        {"type": "function", "function": {
            "name": "queue_status",
            "description": "How many people are waiting right now and how long the wait is.",
            "parameters": {"type": "object", "properties": {}},
        }},
    ]


# ------------------------------------------------------------- execution ----
async def run_tool(cfg: ShopConfig, name: str, args: Dict[str, Any], *,
                   today: Date, now) -> dict:
    """Execute one tool against the real platform. Errors come back as data so
    the agent can explain them, rather than as exceptions that kill the turn."""
    slug = cfg.slug

    def look(a):
        return {k: a.get(k) for k in ("shape", "length", "finish")}

    try:
        if name == "list_services":
            return {"services": [
                {"id": s.id, "name": s.name, "category": s.category, "price": s.price,
                 "minutes_in_chair": s.duration_min, "processing_held": s.buffer_min,
                 "is_fill": s.is_fill, "add_on": s.addon}
                for s in cfg.services if s.active]}

        if name == "shop_info":
            return {
                "name": cfg.name,
                "address": cfg.address.one_line(),
                "phone": cfg.contact.phone,
                "hours": {d: ("closed" if h.closed else f"{h.open}-{h.close}")
                          for d, h in cfg.hours.items()},
                "today": today.isoformat(),
                "today_is": scheduling.day_key(today),
                "deposit_policy": cfg.deposit.policy_text,
                "technicians": [{"id": t.id, "name": t.name, "specialties": t.specialties}
                                for t in cfg.technicians if t.active],
                "colours": [{"id": c.id, "name": c.name, "family": c.family}
                            for c in cfg.colours if c.active],
                "shapes": [{"id": o.id, "label": o.label, "extra_cost": o.surcharge}
                           for o in cfg.nail_menu.shapes if o.active],
                "lengths": [{"id": o.id, "label": o.label, "extra_cost": o.surcharge}
                            for o in cfg.nail_menu.lengths if o.active],
                "finishes": [{"id": o.id, "label": o.label, "extra_cost": o.surcharge}
                             for o in cfg.nail_menu.finishes if o.active],
            }

        if name == "get_quote":
            q = build_quote(cfg, args["service"], **look(args), colour=args.get("colour"))
            return {"price": q.price, "minutes_in_chair": q.duration_min,
                    "processing_held": q.buffer_min, "booked_as_minutes": q.block_min,
                    "deposit_due": q.deposit_due, "service": q.service_name,
                    "breakdown": [{"item": l.label, "amount": l.amount} for l in q.lines]}

        if name == "check_availability":
            d = Date.fromisoformat(args["date"])
            q = build_quote(cfg, args["service"], **look(args))
            busy = scheduling.busy_from_bookings(await bookings.for_day(slug, d))
            by_tech = scheduling.availability(cfg, d, q.block_min, busy,
                                              tech_id=args.get("technician"), now=now)
            slots = scheduling.merge_slots(by_tech)
            return {"date": d.isoformat(), "open_times": slots,
                    "by_technician": by_tech,
                    "note": "" if slots else "Nothing open that day."}

        if name == "find_next_days":
            q = build_quote(cfg, args["service"], **look(args))
            out = []
            for i in range(min(int(args.get("days") or 7), 14)):
                d = today + timedelta(days=i)
                busy = scheduling.busy_from_bookings(await bookings.for_day(slug, d))
                by_tech = scheduling.availability(cfg, d, q.block_min, busy,
                                                  tech_id=args.get("technician"), now=now)
                slots = scheduling.merge_slots(by_tech)
                out.append({"date": d.isoformat(), "day": scheduling.day_key(d),
                            "open_count": len(slots), "first_open": slots[0] if slots else None})
            return {"days": out}

        if name == "create_booking":
            d = Date.fromisoformat(args["date"])
            q = build_quote(cfg, args["service"], **look(args), colour=args.get("colour"))
            busy = scheduling.busy_from_bookings(await bookings.for_day(slug, d))
            by_tech = scheduling.availability(cfg, d, q.block_min, busy,
                                              tech_id=args.get("technician"), now=now)
            start = args["start"]
            candidates = [t for t, sl in by_tech.items() if start in sl]
            if not candidates:
                return {"error": f"{start} is not available on {d.isoformat()}",
                        "open_times": scheduling.merge_slots(by_tech)}
            tech_id = args.get("technician") or candidates[0]
            start_min = scheduling.to_min(start)
            if await bookings.overlapping(slug, d, tech_id, start_min, q.block_min):
                return {"error": "that slot was just taken"}
            tech = cfg.technician(tech_id)
            b = await bookings.create({
                "shop_slug": slug, "reference": bookings.new_reference(), "status": "booked",
                "date": d.isoformat(), "start": start,
                "end": scheduling.to_hhmm(start_min + q.block_min),
                "technician_id": tech_id, "technician_name": tech.name if tech else tech_id,
                "tech_was_chosen": bool(args.get("technician")),
                "client": {"name": str(args["name"]).strip(), "phone": str(args["phone"]).strip(),
                           "email": "", "notes": str(args.get("notes") or "").strip()},
                "quote": q.as_dict(), "duration_min": q.duration_min, "buffer_min": q.buffer_min,
                "block_min": q.block_min, "price": round(q.price, 2),
                "deposit": {"due": q.deposit_due, "reason": q.deposit_reason,
                            "status": "owed" if q.deposit_due else "not_required",
                            "refundable_until_hours": cfg.deposit.refundable_until_hours},
                "remind_at": scheduling.reminder_at(cfg, d, start, q.block_min),
                "source": "agent",
            })
            return {"booked": True, "reference": b["reference"], "date": b["date"],
                    "start": b["start"], "technician": b["technician_name"],
                    "price": b["price"], "deposit_due": b["deposit"]["due"]}

        if name == "lookup_booking":
            b = await bookings.get(slug, str(args["reference"]))
            if b is None:
                return {"error": "no booking with that reference"}
            return {"reference": b["reference"], "status": b["status"], "date": b["date"],
                    "start": b["start"], "technician": b["technician_name"],
                    "service": (b.get("quote") or {}).get("service_name", ""),
                    "client": (b.get("client") or {}).get("name", "")}

        if name == "check_in":
            ref = str(args["reference"])
            b = await bookings.get(slug, ref)
            if b is None:
                return {"error": "no booking with that reference"}
            if b["status"] == "checked_in":
                return {"checked_in": True, "already": True, "technician": b["technician_name"],
                        "start": b["start"]}
            if b["status"] != "booked":
                return {"error": f"that booking is {b['status']}"}
            b = await bookings.set_status(slug, ref, "checked_in")
            return {"checked_in": True, "reference": b["reference"],
                    "technician": b["technician_name"], "start": b["start"]}

        if name == "join_queue":
            svc = cfg.service(args["service"])
            if svc is None:
                return {"error": "that isn't a service here"}
            if not cfg.is_open_on(scheduling.day_key(today)):
                return {"error": "the shop is closed today"}
            ahead = await walkins.waiting(slug, today)
            on_floor = sum(1 for t in cfg.technicians if t.works_on(scheduling.day_key(today)))
            entry = await walkins.add({
                "shop_slug": slug, "reference": bookings.new_reference(),
                "status": walkins.WAITING, "date": today.isoformat(),
                "service_id": svc.id, "service_name": svc.name,
                "technician_id": args.get("technician"),
                "client": {"name": str(args["name"]).strip(),
                           "phone": str(args["phone"]).strip(), "notes": ""},
            })
            return {"joined": True, "reference": entry["reference"],
                    "position": len(ahead) + 1,
                    "estimated_wait_min": walkins.estimate_wait(cfg, ahead, on_floor)}

        if name == "queue_status":
            line = await walkins.waiting(slug, today)
            on_floor = sum(1 for t in cfg.technicians if t.works_on(scheduling.day_key(today)))
            return {"waiting": len(line), "technicians_on_floor": on_floor,
                    "estimated_wait_min": walkins.estimate_wait(cfg, line, on_floor)}

        return {"error": f"unknown tool {name}"}

    except QuoteError as e:
        return {"error": str(e)}
    except (KeyError, ValueError) as e:
        return {"error": f"bad arguments for {name}: {e}"}


TOOL_NAMES = {
    "list_services", "shop_info", "get_quote", "check_availability", "find_next_days",
    "create_booking", "lookup_booking", "check_in", "join_queue", "queue_status",
}

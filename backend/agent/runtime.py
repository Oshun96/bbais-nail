"""The front-desk agent's turn loop.

The agent is not a chatbot bolted beside the platform — it operates it. It asks
for real prices, real openings and real queue positions through tools, and when
it books someone that booking is created by the same function the form calls.

Whatever the model does internally, the client sees ONE reply in the shop's
voice. Tool traffic never reaches them, and no engine is ever named.
"""
from __future__ import annotations

import json
import re
from datetime import date as Date, datetime
from typing import Any, Dict, List, Tuple

from shop_config import DAY_LABELS, ShopConfig

from . import model
from .tools import TOOL_NAMES, run_tool, tool_schemas

MAX_TOOL_ROUNDS = 5          # generous enough to quote, check, then book

# Language that tells a client their appointment EXISTS. If a reply talks like
# this without create_booking having actually run, the client has been told a
# lie — the single worst thing a booking agent can do. Detected in code and
# corrected, because a prompt instruction is a request, not a guarantee.
_CLAIMS_BOOKED = re.compile(
    r"((you'?re|you are|you'?re) (all )?(set|booked|confirmed|down)"
    r"|here'?s your confirmation"
    r"|i'?ve (booked|reserved|got you (down|in))"
    r"|i have (booked|got you (down|in))"
    r"|booked you (in|for)"
    r"|your (booking|appointment|spot) is (now )?(confirmed|booked|set|held)"
    r"|all (booked|set)"
    r"|confirmation:"
    r"|see you (then|on|at)\b)",
    re.IGNORECASE,
)

_NUDGE = (
    "STOP. Nothing has been booked — no appointment exists and the client has no "
    "reference. Never describe a booking as confirmed before create_booking has "
    "returned a reference. If you have the service, date, time, name and phone, "
    "call create_booking now. If something is genuinely missing, ask for only "
    "that, and do not imply anything is confirmed."
)


def system_prompt(cfg: ShopConfig, today: Date, now: datetime) -> str:
    """The shop's own voice, assembled from its config."""
    a = cfg.agent
    hours = "; ".join(
        f"{DAY_LABELS[d]}: {'closed' if h.closed else f'{h.open}–{h.close}'}"
        for d, h in cfg.hours.items()
    )
    persona = a.persona or f"You are the front desk at {cfg.name}."
    return f"""{persona}

You ARE {cfg.name}'s front desk. You speak as the shop — "we", "us", "our".
Your tone: {a.tone}.

Today is {DAY_LABELS[_day_key(today)]} {today.isoformat()} and the time is {now.strftime('%H:%M')}.
Opening hours — {hours}.
{('Deposit policy: ' + cfg.deposit.policy_text) if cfg.deposit.policy_text else ''}

How you work:
- You can actually book, check people in, and put walk-ins in the line. Use your
  tools to do it; do not tell someone to call or use the website instead.
- NEVER state a price, a duration or an open time you have not just got from a
  tool. If you have not checked, check.
- Offer only the times a tool returned. Never round, invent or approximate one.
- CARRY THE CONVERSATION. If the client already told you the service, shape,
  length or colour earlier, use it. Never ask again for something they've said.
- A technician is OPTIONAL. Default to no preference and let us assign someone;
  only ask if they bring it up.
- To book you need four things: the service, a date and time, a name, and a
  phone number. Ask only for what is genuinely missing, one or two things at a
  time — do not interrogate.
- BE DECISIVE. The moment you have those four, book it in the SAME reply: call
  check_availability, then call create_booking with a time it returned. Do not
  ask the client to confirm something they have already asked you to do. You may
  call several tools in one turn.
- "Soonest", "next available", "whenever", "first thing" or "asap" IS an answer
  about the date. Call find_next_days, take the first day with an opening, then
  check_availability on it and book the earliest time. Do not ask which day.
- NEVER say a booking is confirmed, set, or done before create_booking has
  returned you a reference. Describing an appointment that does not exist is
  the worst mistake you can make here.
- After booking, give the reference back clearly and mention any deposit.
- Do NOT work out deposits yourself. get_quote returns the exact deposit due;
  quote that figure or say nothing about it.
- If a tool returns an error, say plainly what went wrong and offer the next
  best option.
- Keep replies short and warm. This is a conversation at a front desk, not a
  brochure. No bullet lists unless you are laying out times or a menu.
- Never mention tools, functions, systems, or how you work. You are the desk.
{('Greeting style: ' + a.greeting) if a.greeting else ''}
"""


def _day_key(d: Date) -> str:
    from scheduling import day_key
    return day_key(d)


def _tool_calls_of(msg: Dict[str, Any]) -> List[dict]:
    return [c for c in (msg.get("tool_calls") or []) if isinstance(c, dict)]


async def respond(
    cfg: ShopConfig,
    history: List[Dict[str, str]],
    user_text: str,
    *,
    today: Date,
    now: datetime,
) -> Tuple[str, List[str]]:
    """Run one turn. Returns (reply for the client, names of actions taken).

    `history` is the visible conversation only — user and assistant text. Tool
    traffic lives and dies inside this function, so a resumed conversation never
    replays stale tool output.
    """
    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt(cfg, today, now)}]
    for m in history[-20:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_text})

    tools = tool_schemas(cfg)
    actions: List[str] = []
    corrected = False

    for _ in range(MAX_TOOL_ROUNDS):
        msg = await model.complete(messages, tools=tools)
        calls = _tool_calls_of(msg)

        if not calls:
            text = (msg.get("content") or "").strip()
            if not text:
                text = "Sorry — could you say that again?"

            # A reply that claims the appointment exists, when it does not.
            if _CLAIMS_BOOKED.search(text) and "create_booking" not in actions:
                if not corrected:
                    corrected = True
                    messages.append({"role": "assistant", "content": text})
                    messages.append({"role": "user", "content": _NUDGE})
                    continue
                # It would not correct itself: never pass the false claim on.
                return (
                    "Before I confirm anything — I haven't actually put that in the "
                    "book yet. Tell me the day and time you'd like from the ones I "
                    "listed, plus a name and number, and I'll book it properly.",
                    actions,
                )

            return model.scrub(text, cfg.name), actions

        messages.append({
            "role": "assistant",
            "content": msg.get("content") or "",
            "tool_calls": calls,
        })

        for call in calls:
            fn = (call.get("function") or {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}

            if name not in TOOL_NAMES:
                result: Dict[str, Any] = {"error": f"unknown action {name}"}
            else:
                result = await run_tool(cfg, name, args, today=today, now=now)
                if not result.get("error"):
                    actions.append(name)

            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "name": name,
                "content": json.dumps(result, default=str),
            })

    # Out of rounds: ask for a plain answer rather than looping on the client's time.
    messages.append({"role": "user", "content":
                     "Answer now in one or two sentences using what you already have."})
    final = await model.complete(messages, tools=None)
    return model.scrub((final.get("content") or "").strip() or
                       "Sorry — could you say that again?", cfg.name), actions

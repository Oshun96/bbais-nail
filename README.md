# BBAIS Nail Platform

One platform, white-labeled per shop. Everything a nail shop differs on — brand,
services, technicians, nail menus, colour wall, hours, deposit rules, payment
processor, front-desk agent voice — lives in **one config per shop**. A new shop
is a config entry, not a build.

## Status

**Phase 1 complete and verified live.** Foundation + the per-shop config engine.

Later phases (booking, check-in/checkout, payments, admin, the front-desk agent,
photo consultation, hardening, try-on) are not built yet. There are deliberately
no booking buttons in the UI until Phase 2 — nothing in this repo is a
placeholder or a stub.

## Running it

```bash
# backend
cd backend
cp .env.example .env          # then fill it in — never commit .env
pip install -r requirements.txt
python -m uvicorn server:app --reload --port 8080

# frontend
cd frontend
npm install
npm run dev                   # http://localhost:5173, /api proxied to :8080
```

Seed configs in `backend/shops/*.json` are upserted into Mongo on boot. A shop
edited through the admin API is marked `_edited` and is never overwritten by a
later re-seed.

## The white-label engine

`backend/shop_config.py` is the schema and the contract. `GET /api/shops/{slug}/config`
returns the whole payload; the front end themes and populates itself from that one
response via CSS custom properties (`frontend/src/theme.js`), so a different config
repaints the entire platform with no code change.

Two shops ship as proof:

| | `lacquer-and-lume` | `maison-ruby` |
|---|---|---|
| Accent | `#D4AF37` gold | `#B76E79` rose gold |
| Fonts | Cormorant Garamond / DM Sans | Playfair Display / Inter |
| Services | 14 | 15 |
| Technicians | 3 | 4 |
| Colour wall | 14 shades | 16 shades |
| Closed | Mondays | Sundays |
| Deposit | 25% over 60 min | flat $20 over 45 min |
| Processor | PayPal | Stripe |

Append `?shop=<slug>` to any URL to swap configs live. The switcher only appears
when the API reports more than one shop; a single-shop deployment sets
`DEFAULT_SHOP_SLUG` and never shows it.

### Things the schema enforces, not just documents

- **No white backgrounds, ever.** `Theme.base`/`surface` reject any colour above a
  luminance threshold, so a shop config physically cannot ship a light base.
- **Hours are total.** A missing day is a closed day; all seven always come back
  in order.
- **Buffer time is first-class.** Every service carries `buffer_min` (cure, dry,
  station reset) and exposes `block_min` = duration + buffer. That is the number
  the calendar reserves, which is why a fill is genuinely shorter than a full set.
- **Add-ons are flagged, not inferred.** `addon: true` keeps a $12 nail repair out
  of "services from", instead of guessing from a category name.
- **Specialty work costs more *and* takes longer.** Shapes, lengths and finishes
  each carry `surcharge` and `extra_min`.

## Security

Applied from Phase 1, completed in Phase 7.

- **VULN-CRED-01** — no credential is hardcoded, defaulted, logged or returned.
  `security.require_env` is the only path to a secret; `.env` is gitignored.
- **VULN-AUTH-01** — admin endpoints go through `require_admin`: constant-time
  comparison, and an unset `ADMIN_API_KEY` **fails closed** (503), never open.
- **Emergent** — CORS is an explicit allowlist that rejects `*` at boot; security
  headers on every response; request bodies size-capped before parsing.

## Models

The front-desk agent (Phase 5) and photo consultation (Phase 6) run on the
bskdesigner Modal account. Endpoint URLs come from the environment, never source.

Cold start is disclosed honestly rather than engineered away: the field-based
booking flow is always the instant path, and the agent is the conversational
layer on top. No keep-warm.

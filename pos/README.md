# DineFlow POS (milestone 1)

A separate Expo/React Native app — not part of the Nuxt `frontend/` — for the staff-facing till that
runs on a restaurant's own iPad. See `/backend`'s `pos.py`/`admin_devices.py`/`pos_service.py` for the
API this talks to.

**This milestone is cash-only.** No Stripe Terminal card payment yet (needs physical reader hardware to
build against — a separate milestone), no shifts/cash-reconciliation/Z-report, no offline queue, no
receipt printing. The goal is proving the whole pipeline end to end: pair a device, PIN in, take an
order, watch it hit the kitchen screen, mark it paid in cash.

## Running it

```sh
cd pos
npm install
npm run ios      # or: npx expo start, then press i / scan the QR with Expo Go on a real iPad
```

By default it talks to `http://localhost:8000` (the dev backend on your own machine). On a real iPad
(not a simulator), `localhost` means the iPad itself — point it at your Mac's LAN IP instead:

```sh
EXPO_PUBLIC_API_URL=http://192.168.1.23:8000 npx expo start
```

## First-time setup (once the backend's running)

1. Make sure the restaurant's `pos` feature flag is on (`/platform/features` or the CLI —
   see `docs/OPERATIONS.md`'s Feature flags section).
2. Pair the device: `POST /api/v1/admin/devices` as a restaurant admin (there's no admin-side UI for
   this yet — curl it, or build the screen in `frontend/app/pages/admin/` as a follow-up). Copy the
   `device_token` from the response.
3. Open the app, paste that token into the Pairing screen.
4. Set a staff member's PIN: `POST /api/v1/admin/devices/staff/{membership_id}/pin`.
5. PIN in on the app, take an order, send it, watch it land on `/admin/kitchen` in the web app.

## What's here

```
src/
  config.ts              # API_URL (EXPO_PUBLIC_API_URL override)
  api/
    client.ts             # fetch wrapper, Authorization header, error shaping
    jwt.ts                 # reads a JWT's own payload client-side (restaurant_id, never verifies — the
                            #   backend already did that) — needed since the public menu endpoints take
                            #   restaurant_id as a query param, not derived from auth
    pos.ts                  # the actual endpoint calls
    types.ts                 # response shapes, hand-kept in sync with backend/app/schemas/pos.py
  state/store.ts            # zustand: device token (SecureStore-persisted), PIN session (memory-only,
                              #   by design — re-entering a PIN after a restart is the point), cart
  screens/
    PairingScreen.tsx         # text-entry pairing code (no QR scan yet — trivial polish for later)
    PinEntryScreen.tsx          # numeric pad -> pos_session token
    OrderScreen.tsx               # counter vs. table toggle, menu, cart, "Send to Kitchen"
    CashTenderScreen.tsx           # total due, "Mark Paid (Cash)"
  navigation/RootNavigator.tsx      # Pairing -> PinEntry -> Order (-> CashTender), gated on token presence
```

No offline queue, no receipt printing, no shift concept — correctly out of scope for this milestone.

# DineFlow POS (milestone 2)

A separate Expo/React Native app — not part of the Nuxt `frontend/` — for the staff-facing till that
runs on a restaurant's own iPad. See `/backend`'s `pos.py`/`admin_devices.py`/`pos_service.py`/
`table_session_service.py` for the API this talks to.

**Milestone 1** (cash-only counter + dine-in orders) is done. **Milestone 2** adds Stripe Terminal card
payments via a simulated reader — no physical hardware needed to test, but real card hardware is still a
future step (needs a Stripe Terminal `Location` on the connected account once a physical reader shows up).
Still not built: shifts/cash-reconciliation/Z-report, offline queue, receipt printing.

## Running it

**`@stripe/stripe-terminal-react-native` has native code and cannot run inside Expo Go.** Testing this
app now requires a native "development build", not `expo start` + scanning a QR code with Expo Go:

```sh
cd pos
npm install
npx eas-cli@latest login                                    # once
npx eas-cli@latest build --profile development --platform ios
# open the install link it gives you on the test iPad, then:
npx expo start --dev-client
```

Re-pairing is required the first time you move to a dev build: its SecureStore is a fresh keychain
group, separate from the old Expo Go app's, so the previously-paired device token won't carry over.

By default it talks to `http://localhost:8000` (the dev backend on your own machine). On a real iPad
(not a simulator), `localhost` means the iPad itself — point it at your Mac's LAN IP instead:

```sh
EXPO_PUBLIC_API_URL=http://192.168.1.23:8000 npx expo start --dev-client
```

Card payments only work end to end against the real Stripe test-mode provider (`PAYMENT_PROVIDER=stripe`
on the backend) — the mock provider settles instantly server-side with nothing for the Terminal SDK to
actually do, which is fine for the backend's own automated tests but means the RN app's card flow can
only be manually verified under `PAYMENT_PROVIDER=stripe`.

## First-time setup (once the backend's running)

1. Make sure the restaurant's `pos` feature flag is on (`/platform/features` or the CLI —
   see `docs/OPERATIONS.md`'s Feature flags section).
2. Pair the device: `POST /api/v1/admin/devices` as a restaurant admin (there's no admin-side UI for
   this yet — curl it, or build the screen in `frontend/app/pages/admin/` as a follow-up). Copy the
   `device_token` from the response.
3. Open the app, paste that token into the Pairing screen.
4. Set a staff member's PIN: `POST /api/v1/admin/devices/staff/{membership_id}/pin`.
5. PIN in on the app, take an order, send it, watch it land on `/admin/kitchen` in the web app.
6. For card payments: the test restaurant needs `stripe_account_id` set (complete Stripe Connect
   onboarding first if not), and the backend needs `PAYMENT_PROVIDER=stripe`. "Pay by card" from the
   cash-tender screen connects to Stripe's simulated reader automatically — no physical hardware needed.

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
    CashTenderScreen.tsx           # total due, "Mark Paid (Cash)" / "Pay by card"
    CardTenderScreen.tsx            # connects to the Terminal simulated reader and processes the card
  navigation/RootNavigator.tsx      # Pairing -> PinEntry -> Order -> CashTender/CardTender, gated on token presence
App.tsx                               # mounts StripeTerminalProvider at the root (tokenProvider hits
                                      #   /pos/terminal/connection-token)
eas.json                               # EAS "development" build profile
```

No offline queue, no receipt printing, no shift concept, no real (non-simulated) card reader yet —
correctly out of scope for this milestone.

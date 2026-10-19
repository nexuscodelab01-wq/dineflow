# DineFlow POS (milestone 3)

A separate Expo/React Native app — not part of the Nuxt `frontend/` — for the staff-facing till that
runs on a restaurant's own iPad. See `/backend`'s `pos.py`/`admin_devices.py`/`admin_shifts.py`/
`pos_service.py`/`shift_service.py`/`table_session_service.py` for the API this talks to.

**Milestone 1** (cash-only counter + dine-in orders) and **Milestone 2** (Stripe Terminal card payments,
simulated reader) are done. **Milestone 3** adds shifts/cash reconciliation (Z-report): opening a shift
with a starting float is now **mandatory** before taking orders, closing one shows expected cash vs.
counted cash and the variance, and cash-in/out can be recorded mid-shift (a float top-up, a cash tip paid
out, etc). Still not built: offline queue, receipt printing, a real (non-simulated) card reader.

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
5. PIN in on the app — you'll land on "Open the till" first. Enter a starting float, then take an
   order, send it, watch it land on `/admin/kitchen` in the web app.
6. For card payments: the test restaurant needs `stripe_account_id` set (complete Stripe Connect
   onboarding first if not), and the backend needs `PAYMENT_PROVIDER=stripe`. "Pay by card" from the
   cash-tender screen connects to Stripe's simulated reader automatically — no physical hardware needed.
7. "End shift" (in the Order screen's header) counts the drawer and shows the variance. Admins can see
   every past shift's Z-report at `GET /admin/shifts`.

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
                              #   by design — re-entering a PIN after a restart is the point), cart,
                              #   shift (device-scoped, always re-fetched fresh, never persisted)
  screens/
    PairingScreen.tsx         # text-entry pairing code (no QR scan yet — trivial polish for later)
    PinEntryScreen.tsx          # numeric pad -> pos_session token
    OpenShiftScreen.tsx           # starting-float entry -> mandatory before reaching Order
    OrderScreen.tsx                 # counter vs. table toggle, menu, cart, "Send to Kitchen"
    CashTenderScreen.tsx             # total due, "Mark Paid (Cash)" / "Pay by card"
    CardTenderScreen.tsx              # connects to the Terminal simulated reader and processes the card
    CloseShiftScreen.tsx               # counted-cash entry -> expected/counted/variance recap
    CashMovementScreen.tsx              # mid-shift cash in/out with a reason
  navigation/RootNavigator.tsx      # Pairing -> PinEntry -> OpenShift -> Order -> CashTender/CardTender/CloseShift/CashMovement
App.tsx                               # mounts StripeTerminalProvider at the root (tokenProvider hits
                                      #   /pos/terminal/connection-token)
eas.json                               # EAS "development" build profile
```

No offline queue, no receipt printing, no real (non-simulated) card reader yet, and refunds aren't
reflected in a shift's variance math (known limitation — see shift_service.py's module docstring) —
correctly out of scope for this milestone.

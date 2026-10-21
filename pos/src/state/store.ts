import { create } from 'zustand';
import * as SecureStore from 'expo-secure-store';
import { fetchCurrentShift, fetchCurrentTimeEntry } from '../api/pos';
import type { DeviceKind, ShiftRead, TimeEntryRead } from '../api/types';

const DEVICE_TOKEN_KEY = 'dineflow_pos_device_token';

export type CartLine = {
  // Identifies this specific line, not the menu item — two lines for the same item with different
  // notes must stay separate (see addToCart), so menuItemId alone can no longer be a unique key.
  lineId: string;
  menuItemId: number;
  name: string;
  price: number;
  quantity: number;
  note?: string;
  // Chosen modifier options (price already includes their adjustments). Part of what makes a line unique.
  modifierOptionIds?: number[];
  modifierLabels?: string[];
};

type PosState = {
  // The iPad's own long-lived credential — survives restarts, loaded from SecureStore on launch.
  deviceToken: string | null;
  deviceReady: boolean; // false until the initial SecureStore read completes
  // Short-lived, in-memory only — never persisted. Re-entering a PIN after an app restart is the point.
  posSessionToken: string | null;
  staffName: string | null;
  // Device-level, learned at PIN login (the backend knows, the device token doesn't carry it). Survives a
  // staff switch like `shift` does; only matters after login, which is when every gate that reads it runs.
  deviceKind: DeviceKind | null;
  // The restaurant's currency/country, learned at PIN login for the same reason. Defaults until then.
  currency: string;
  country: string;
  // Whether the card reader should show its tip screen (learned at PIN login).
  tipsEnabled: boolean;
  // Whether voids / comps / discounts / refunds are switched on for this restaurant.
  controlsEnabled: boolean;
  cart: CartLine[];
  // A shift is scoped to this device, not the current PIN session — it survives a staff switch, so it's
  // always re-fetched fresh from the backend rather than inferred client-side (avoids staleness if the
  // app was killed mid-shift).
  shift: ShiftRead | null;
  shiftChecked: boolean;
  // Unlike `shift` (device-scoped, survives a PIN switch), a clock-in is about the specific person
  // logged in right now — it must be re-checked fresh every time posSessionToken changes, and cleared
  // on logoutPin so the next staff member doesn't inherit whoever was clocked in before them.
  timeEntry: TimeEntryRead | null;
  timeEntryChecked: boolean;

  loadDevice: () => Promise<void>;
  pair: (token: string) => Promise<void>;
  unpair: () => Promise<void>;
  loginWithPin: (token: string, staffName: string, deviceKind: DeviceKind, currency: string, country: string, tipsEnabled: boolean, controlsEnabled: boolean) => void;
  logoutPin: () => void;
  loadShift: () => Promise<void>;
  setShift: (shift: ShiftRead | null) => void;
  loadTimeEntry: () => Promise<void>;
  setTimeEntry: (entry: TimeEntryRead | null) => void;
  addToCart: (line: Omit<CartLine, 'quantity' | 'lineId'>, quantity?: number) => void;
  removeFromCart: (lineId: string) => void;
  decrementCartLine: (lineId: string) => void;
  setCartLineNote: (lineId: string, note: string) => void;
  clearCart: () => void;
};

export const usePosStore = create<PosState>((set, get) => ({
  deviceToken: null,
  deviceReady: false,
  posSessionToken: null,
  staffName: null,
  deviceKind: null,
  currency: 'usd',
  country: 'US',
  tipsEnabled: false,
  controlsEnabled: false,
  cart: [],
  shift: null,
  shiftChecked: false,
  timeEntry: null,
  timeEntryChecked: false,

  loadDevice: async () => {
    const token = await SecureStore.getItemAsync(DEVICE_TOKEN_KEY);
    set({ deviceToken: token, deviceReady: true });
  },

  pair: async (token: string) => {
    await SecureStore.setItemAsync(DEVICE_TOKEN_KEY, token);
    set({ deviceToken: token });
  },

  unpair: async () => {
    await SecureStore.deleteItemAsync(DEVICE_TOKEN_KEY);
    set({
      deviceToken: null, posSessionToken: null, staffName: null, deviceKind: null, cart: [],
      shift: null, shiftChecked: false, timeEntry: null, timeEntryChecked: false,
    });
  },

  loginWithPin: (token, staffName, deviceKind, currency, country, tipsEnabled, controlsEnabled) => set({ posSessionToken: token, staffName, deviceKind, currency, country, tipsEnabled, controlsEnabled }),

  // Switching staff: just drop the old session token client-side. It's short-lived and stateless
  // server-side, so there's nothing to "log out" on the backend — see pos_service.py's design notes.
  // The shift is device-scoped, not session-scoped, so it's deliberately NOT cleared here.
  logoutPin: () => set({ posSessionToken: null, staffName: null, cart: [], timeEntry: null, timeEntryChecked: false }),

  loadShift: async () => {
    const token = get().deviceToken;
    if (!token) return;
    try {
      const shift = await fetchCurrentShift(token);
      set({ shift, shiftChecked: true });
    } catch {
      set({ shift: null, shiftChecked: true });
    }
  },

  setShift: (shift) => set({ shift }),

  loadTimeEntry: async () => {
    const token = get().posSessionToken;
    if (!token) return;
    try {
      const entry = await fetchCurrentTimeEntry(token);
      set({ timeEntry: entry, timeEntryChecked: true });
    } catch {
      set({ timeEntry: null, timeEntryChecked: true });
    }
  },

  setTimeEntry: (entry) => set({ timeEntry: entry }),

  addToCart: (line, quantity = 1) =>
    set((state) => {
      // Two lines for the same item with different notes must stay separate — matched on
      // (menuItemId, note), not menuItemId alone.
      const sig = (ids?: number[]) => [...(ids ?? [])].sort((a, b) => a - b).join(',');
      const existing = state.cart.find(
        (l) => l.menuItemId === line.menuItemId && l.note === line.note && sig(l.modifierOptionIds) === sig(line.modifierOptionIds),
      );
      if (existing) {
        return {
          cart: state.cart.map((l) =>
            l.lineId === existing.lineId ? { ...l, quantity: l.quantity + quantity } : l,
          ),
        };
      }
      const lineId = `${line.menuItemId}:${Date.now()}:${Math.random().toString(36).slice(2)}`;
      return { cart: [...state.cart, { ...line, lineId, quantity }] };
    }),

  removeFromCart: (lineId) =>
    set((state) => ({ cart: state.cart.filter((l) => l.lineId !== lineId) })),

  decrementCartLine: (lineId) =>
    set((state) => ({
      cart: state.cart
        .map((l) => (l.lineId === lineId ? { ...l, quantity: l.quantity - 1 } : l))
        .filter((l) => l.quantity > 0),
    })),

  // Editing an existing line's note does not re-merge it with another line that happens to end up with
  // the same note — a deliberate simplification, not a bug: avoids silently combining two things staff
  // kept separate on purpose.
  setCartLineNote: (lineId, note) =>
    set((state) => ({
      cart: state.cart.map((l) => (l.lineId === lineId ? { ...l, note: note || undefined } : l)),
    })),

  clearCart: () => set({ cart: [] }),
}));

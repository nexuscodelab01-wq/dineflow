import { create } from 'zustand';
import * as SecureStore from 'expo-secure-store';
import { fetchCurrentShift, fetchCurrentTimeEntry } from '../api/pos';
import type { ShiftRead, TimeEntryRead } from '../api/types';

const DEVICE_TOKEN_KEY = 'dineflow_pos_device_token';

export type CartLine = {
  menuItemId: number;
  name: string;
  price: number;
  quantity: number;
};

type PosState = {
  // The iPad's own long-lived credential — survives restarts, loaded from SecureStore on launch.
  deviceToken: string | null;
  deviceReady: boolean; // false until the initial SecureStore read completes
  // Short-lived, in-memory only — never persisted. Re-entering a PIN after an app restart is the point.
  posSessionToken: string | null;
  staffName: string | null;
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
  loginWithPin: (token: string, staffName: string) => void;
  logoutPin: () => void;
  loadShift: () => Promise<void>;
  setShift: (shift: ShiftRead | null) => void;
  loadTimeEntry: () => Promise<void>;
  setTimeEntry: (entry: TimeEntryRead | null) => void;
  addToCart: (line: Omit<CartLine, 'quantity'>, quantity?: number) => void;
  removeFromCart: (menuItemId: number) => void;
  decrementCartLine: (menuItemId: number) => void;
  clearCart: () => void;
};

export const usePosStore = create<PosState>((set, get) => ({
  deviceToken: null,
  deviceReady: false,
  posSessionToken: null,
  staffName: null,
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
      deviceToken: null, posSessionToken: null, staffName: null, cart: [],
      shift: null, shiftChecked: false, timeEntry: null, timeEntryChecked: false,
    });
  },

  loginWithPin: (token: string, staffName: string) => set({ posSessionToken: token, staffName }),

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
      const existing = state.cart.find((l) => l.menuItemId === line.menuItemId);
      if (existing) {
        return {
          cart: state.cart.map((l) =>
            l.menuItemId === line.menuItemId ? { ...l, quantity: l.quantity + quantity } : l,
          ),
        };
      }
      return { cart: [...state.cart, { ...line, quantity }] };
    }),

  removeFromCart: (menuItemId) =>
    set((state) => ({ cart: state.cart.filter((l) => l.menuItemId !== menuItemId) })),

  decrementCartLine: (menuItemId) =>
    set((state) => ({
      cart: state.cart
        .map((l) => (l.menuItemId === menuItemId ? { ...l, quantity: l.quantity - 1 } : l))
        .filter((l) => l.quantity > 0),
    })),

  clearCart: () => set({ cart: [] }),
}));

import { create } from 'zustand';
import * as SecureStore from 'expo-secure-store';

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

  loadDevice: () => Promise<void>;
  pair: (token: string) => Promise<void>;
  unpair: () => Promise<void>;
  loginWithPin: (token: string, staffName: string) => void;
  logoutPin: () => void;
  addToCart: (line: Omit<CartLine, 'quantity'>, quantity?: number) => void;
  removeFromCart: (menuItemId: number) => void;
  decrementCartLine: (menuItemId: number) => void;
  clearCart: () => void;
};

export const usePosStore = create<PosState>((set) => ({
  deviceToken: null,
  deviceReady: false,
  posSessionToken: null,
  staffName: null,
  cart: [],

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
    set({ deviceToken: null, posSessionToken: null, staffName: null, cart: [] });
  },

  loginWithPin: (token: string, staffName: string) => set({ posSessionToken: token, staffName }),

  // Switching staff: just drop the old session token client-side. It's short-lived and stateless
  // server-side, so there's nothing to "log out" on the backend — see pos_service.py's design notes.
  logoutPin: () => set({ posSessionToken: null, staffName: null, cart: [] }),

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

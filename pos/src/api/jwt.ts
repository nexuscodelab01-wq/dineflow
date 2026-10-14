// Reads a JWT's own payload client-side — never verifies the signature (the backend already did
// that when it issued the token; this is purely for the app to know its own restaurant_id so it can
// call the public menu/categories endpoints, which take restaurant_id as a query param rather than
// deriving it from auth).
export function decodeJwtPayload<T = Record<string, unknown>>(token: string): T {
  const [, payload] = token.split('.');
  if (!payload) throw new Error('Not a JWT');
  const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
  const padded = normalized + '='.repeat((4 - (normalized.length % 4)) % 4);
  const json = atob(padded);
  return JSON.parse(json) as T;
}

// Set with EXPO_PUBLIC_API_URL for a real device/simulator pointed at something other than localhost
// (e.g. the Docker host's LAN IP). Expo only exposes env vars prefixed EXPO_PUBLIC_ to app code.
export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';
export const API_BASE = `${API_URL}/api/v1`;

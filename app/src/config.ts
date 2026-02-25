/**
 * Elora app configuration.
 *
 * The backend URL is the only value that changes between environments.
 * Override EXPO_PUBLIC_ELORA_BACKEND at build time to point at a
 * different server (e.g. a local dev instance).
 *
 * Expo exposes EXPO_PUBLIC_* vars to the JS bundle at build time.
 * See: https://docs.expo.dev/guides/environment-variables/
 */

const BACKEND_BASE =
  process.env.EXPO_PUBLIC_ELORA_BACKEND ||
  "https://elora-backend-453139277365.us-central1.run.app";

export const BACKEND_URL = BACKEND_BASE;
export const WS_URL = BACKEND_BASE.replace(/^http/, "ws") + "/ws";
export const LIVE_WS_URL = BACKEND_BASE.replace(/^http/, "ws") + "/ws/live";
export const WAKE_WS_URL = BACKEND_BASE.replace(/^http/, "ws") + "/ws/wake";
export const LIVEKIT_TOKEN_URL = BACKEND_BASE + "/livekit/token";

/**
 * Build a WebSocket URL with an optional Firebase ID token appended as ?token=
 * Falls back to the base URL if no token provided (demo mode).
 */
export function wsUrl(base: string, userId: string, token?: string | null): string {
  const url = `${base}/${userId}`;
  return token ? `${url}?token=${encodeURIComponent(token)}` : url;
}


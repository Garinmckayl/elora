/**
 * useFirebaseAuth -- Firebase anonymous authentication for Elora
 *
 * Signs the user in anonymously on first launch (no email/password needed).
 * Persists the uid across app restarts via Firebase's built-in persistence.
 *
 * Returns:
 *   uid        -- stable Firebase user ID (used as user_id throughout the app)
 *   idToken    -- short-lived ID token to pass on WebSocket connect for verification
 *   loading    -- true while signing in
 *   refreshToken -- call this to get a fresh idToken before connecting
 */

import { useState, useEffect, useCallback } from "react";
import { initializeApp, getApps, getApp } from "firebase/app";
import {
  getAuth,
  signInAnonymously,
  onAuthStateChanged,
  User,
} from "firebase/auth";

// ---------------------------------------------------------------------------
// Firebase config -- values are public (they are client-side config, not secrets)
// The security is enforced by Firebase Security Rules + backend token verification.
// Override at build time via EXPO_PUBLIC_* vars.
// ---------------------------------------------------------------------------
const firebaseConfig = {
  apiKey: process.env.EXPO_PUBLIC_FIREBASE_API_KEY || "",
  authDomain: process.env.EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN || "",
  projectId: process.env.EXPO_PUBLIC_FIREBASE_PROJECT_ID || "",
  storageBucket: process.env.EXPO_PUBLIC_FIREBASE_STORAGE_BUCKET || "",
  messagingSenderId: process.env.EXPO_PUBLIC_FIREBASE_MESSAGING_SENDER_ID || "",
  appId: process.env.EXPO_PUBLIC_FIREBASE_APP_ID || "",
};

// Initialise Firebase once (guard against hot-reload double-init)
function getFirebaseApp() {
  if (getApps().length > 0) return getApp();
  return initializeApp(firebaseConfig);
}

export interface FirebaseAuthState {
  uid: string | null;
  idToken: string | null;
  loading: boolean;
  refreshToken: () => Promise<string | null>;
}

export function useFirebaseAuth(): FirebaseAuthState {
  const [user, setUser] = useState<User | null>(null);
  const [idToken, setIdToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Firebase config may be empty in dev (no .env) -- gracefully degrade
    if (!firebaseConfig.apiKey) {
      console.warn(
        "[Auth] Firebase config not set. Running in unauthenticated demo mode. " +
        "Set EXPO_PUBLIC_FIREBASE_* env vars to enable real auth."
      );
      setLoading(false);
      return;
    }

    let app: ReturnType<typeof initializeApp>;
    try {
      app = getFirebaseApp();
    } catch (e) {
      console.warn("[Auth] Firebase init failed:", e);
      setLoading(false);
      return;
    }

    const auth = getAuth(app);

    // Listen for auth state -- fires immediately with cached user or null
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      if (firebaseUser) {
        setUser(firebaseUser);
        try {
          const token = await firebaseUser.getIdToken();
          setIdToken(token);
        } catch (e) {
          console.warn("[Auth] getIdToken failed:", e);
        }
        setLoading(false);
      } else {
        // No user -- sign in anonymously (silent, instant, no UI)
        try {
          await signInAnonymously(auth);
          // onAuthStateChanged will fire again with the new user
        } catch (e) {
          console.warn("[Auth] Anonymous sign-in failed:", e);
          setLoading(false);
        }
      }
    });

    return unsubscribe;
  }, []);

  const refreshToken = useCallback(async (): Promise<string | null> => {
    if (!user) return null;
    try {
      const token = await user.getIdToken(/* forceRefresh */ true);
      setIdToken(token);
      return token;
    } catch (e) {
      console.warn("[Auth] Token refresh failed:", e);
      return null;
    }
  }, [user]);

  return {
    uid: user?.uid ?? null,
    idToken,
    loading,
    refreshToken,
  };
}

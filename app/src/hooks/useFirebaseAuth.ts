/**
 * useFirebaseAuth -- Firebase Google Sign-In for Elora
 *
 * Uses expo-auth-session to launch Google OAuth, then signs into Firebase
 * with the Google credential. Falls back gracefully if Firebase config
 * is missing or if native modules aren't available (Expo Go).
 *
 * Returns:
 *   uid        -- stable Firebase user ID
 *   idToken    -- short-lived ID token for backend verification
 *   loading    -- true while auth state is resolving
 *   user       -- Firebase user object (has displayName, email, photoURL)
 *   signIn     -- trigger the Google Sign-In flow
 *   signOut    -- sign out
 *   refreshToken -- force-refresh the idToken
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { initializeApp, getApps, getApp, FirebaseApp } from "firebase/app";
import {
  getAuth,
  signInAnonymously,
  signInWithCredential,
  GoogleAuthProvider,
  onAuthStateChanged,
  signOut as firebaseSignOut,
  User,
  Auth,
} from "firebase/auth";

// ---------------------------------------------------------------------------
// Firebase config
// ---------------------------------------------------------------------------
const firebaseConfig = {
  apiKey: process.env.EXPO_PUBLIC_FIREBASE_API_KEY || "",
  authDomain: process.env.EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN || "",
  projectId: process.env.EXPO_PUBLIC_FIREBASE_PROJECT_ID || "",
  storageBucket: process.env.EXPO_PUBLIC_FIREBASE_STORAGE_BUCKET || "",
  messagingSenderId: process.env.EXPO_PUBLIC_FIREBASE_MESSAGING_SENDER_ID || "",
  appId: process.env.EXPO_PUBLIC_FIREBASE_APP_ID || "",
};

// Google OAuth client IDs
const GOOGLE_WEB_CLIENT_ID = process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID || "";

function getFirebaseApp(): FirebaseApp {
  if (getApps().length > 0) return getApp();
  return initializeApp(firebaseConfig);
}

export interface FirebaseAuthState {
  uid: string | null;
  idToken: string | null;
  loading: boolean;
  user: User | null;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
  refreshToken: () => Promise<string | null>;
}

export function useFirebaseAuth(): FirebaseAuthState {
  const [user, setUser] = useState<User | null>(null);
  const [idToken, setIdToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const authRef = useRef<Auth | null>(null);

  useEffect(() => {
    // Firebase config may be empty in dev -- gracefully degrade
    if (!firebaseConfig.apiKey) {
      console.warn(
        "[Auth] Firebase config not set. Running in unauthenticated demo mode. " +
        "Set EXPO_PUBLIC_FIREBASE_* env vars to enable real auth."
      );
      setLoading(false);
      return;
    }

    let app: FirebaseApp;
    try {
      app = getFirebaseApp();
    } catch (e) {
      console.warn("[Auth] Firebase init failed:", e);
      setLoading(false);
      return;
    }

    const auth = getAuth(app);
    authRef.current = auth;

    // Listen for auth state changes
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      if (firebaseUser) {
        setUser(firebaseUser);
        try {
          const token = await firebaseUser.getIdToken();
          setIdToken(token);
        } catch (e) {
          console.warn("[Auth] getIdToken failed:", e);
        }
      } else {
        setUser(null);
        setIdToken(null);
      }
      setLoading(false);
    });

    return unsubscribe;
  }, []);

  /**
   * Launch Google Sign-In flow.
   * Tries expo-auth-session if available, otherwise falls back to anonymous.
   */
  const signIn = useCallback(async () => {
    const auth = authRef.current;
    if (!auth) {
      console.warn("[Auth] Firebase not initialized, cannot sign in");
      return;
    }

    // Try to load expo-auth-session dynamically
    let AuthSessionMod: any = null;
    try {
      AuthSessionMod = require("expo-auth-session");
    } catch {
      console.warn("[Auth] expo-auth-session not available. Falling back to anonymous.");
      try { await signInAnonymously(auth); } catch (e) { console.warn("[Auth] Anonymous sign-in failed:", e); }
      return;
    }

    if (!GOOGLE_WEB_CLIENT_ID) {
      console.warn("[Auth] No Google client ID configured. Falling back to anonymous auth.");
      try { await signInAnonymously(auth); } catch (e) { console.warn("[Auth] Anonymous sign-in failed:", e); }
      return;
    }

    try {
      const redirectUri = AuthSessionMod.makeRedirectUri({ scheme: "elora" });
      const discovery = {
        authorizationEndpoint: "https://accounts.google.com/o/oauth2/v2/auth",
        tokenEndpoint: "https://oauth2.googleapis.com/token",
      };

      const request = new AuthSessionMod.AuthRequest({
        clientId: GOOGLE_WEB_CLIENT_ID,
        redirectUri,
        scopes: ["openid", "profile", "email"],
        responseType: AuthSessionMod.ResponseType.IdToken,
        extraParams: {
          nonce: Math.random().toString(36).substring(2),
        },
      });

      const result = await request.promptAsync(discovery);

      if (result.type === "success" && result.params?.id_token) {
        const credential = GoogleAuthProvider.credential(result.params.id_token);
        const userCredential = await signInWithCredential(auth, credential);
        console.log("[Auth] Google sign-in success:", userCredential.user.displayName);
      } else if (result.type === "cancel") {
        console.log("[Auth] Sign-in cancelled by user");
      } else {
        console.warn("[Auth] Sign-in result:", result.type);
      }
    } catch (e) {
      console.error("[Auth] Google sign-in error:", e);
      // Fall back to anonymous
      try { await signInAnonymously(auth); } catch (e2) { console.warn("[Auth] Anonymous fallback failed:", e2); }
    }
  }, []);

  /**
   * Sign out of Firebase
   */
  const signOut = useCallback(async () => {
    const auth = authRef.current;
    if (!auth) return;
    try {
      await firebaseSignOut(auth);
      setUser(null);
      setIdToken(null);
    } catch (e) {
      console.warn("[Auth] Sign-out failed:", e);
    }
  }, []);

  /**
   * Force-refresh the ID token
   */
  const refreshToken = useCallback(async (): Promise<string | null> => {
    if (!user) return null;
    try {
      const token = await user.getIdToken(true);
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
    user,
    signIn,
    signOut,
    refreshToken,
  };
}

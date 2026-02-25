/**
 * useExpoPush -- registers the device's Expo push token with the backend
 * so Elora can send proactive notifications (reminders, email alerts, etc.)
 *
 * Call this once on app startup with the Firebase user ID + token.
 * It requests notification permissions, gets the Expo push token,
 * and POSTs it to POST /push/register on the backend.
 *
 * Also listens for notification taps and calls onNotificationTap so the
 * app can navigate to the right state (e.g., open conversation).
 */

import { useEffect } from "react";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { BACKEND_URL } from "../config";

// Configure how notifications are shown while app is foregrounded
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

interface UseExpoPushOptions {
  userId?: string;
  token?: string | null;    // Firebase ID token
  enabled?: boolean;
  /** Called when the user taps a notification. Receives the notification data payload. */
  onNotificationTap?: (data: Record<string, any>) => void;
}

export function useExpoPush({ userId, token, enabled = true, onNotificationTap }: UseExpoPushOptions) {
  // Register token with backend
  useEffect(() => {
    if (!enabled || !userId || userId === "anonymous") return;

    let cancelled = false;

    (async () => {
      try {
        // Request permission
        const { status: existingStatus } = await Notifications.getPermissionsAsync();
        let finalStatus = existingStatus;
        if (existingStatus !== "granted") {
          const { status } = await Notifications.requestPermissionsAsync();
          finalStatus = status;
        }
        if (finalStatus !== "granted") {
          console.log("[Push] Notification permission denied");
          return;
        }

        // Android notification channel
        if (Platform.OS === "android") {
          await Notifications.setNotificationChannelAsync("default", {
            name: "Elora",
            importance: Notifications.AndroidImportance.HIGH,
            vibrationPattern: [0, 250, 250, 250],
            lightColor: "#D4A853",
          });
        }

        // Get Expo push token
        const { data: expoPushToken } = await Notifications.getExpoPushTokenAsync();
        if (cancelled || !expoPushToken) return;

        console.log("[Push] Expo token:", expoPushToken);

        // Register with backend
        const resp = await fetch(`${BACKEND_URL}/push/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: userId,
            expo_token: expoPushToken,
            token: token ?? "",
          }),
        });
        if (resp.ok) {
          console.log("[Push] Token registered with backend");
        } else {
          console.warn("[Push] Backend registration failed:", resp.status);
        }
      } catch (err) {
        console.warn("[Push] Setup error:", err);
      }
    })();

    return () => { cancelled = true; };
  }, [userId, token, enabled]);

  // Handle notification taps (works both when app is in foreground and when launched from background)
  useEffect(() => {
    if (!onNotificationTap) return;

    // Fired when user taps a notification while app is running
    const tapSub = Notifications.addNotificationResponseReceivedListener((response) => {
      const data = (response.notification.request.content.data ?? {}) as Record<string, any>;
      console.log("[Push] Notification tapped:", data);
      onNotificationTap(data);
    });

    // Also check if the app was launched from a notification tap
    Notifications.getLastNotificationResponseAsync().then((response) => {
      if (response) {
        const data = (response.notification.request.content.data ?? {}) as Record<string, any>;
        console.log("[Push] App launched from notification:", data);
        onNotificationTap(data);
      }
    });

    return () => {
      tapSub.remove();
    };
  }, [onNotificationTap]);
}


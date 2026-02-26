/**
 * SettingsScreen -- Account connections, preferences, about
 * Premium Warm/Elegant design
 */

import React, { useState, useEffect, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Alert,
  Linking,
  ActivityIndicator,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, borderRadius, shadows } from "../theme";
import { BACKEND_URL } from "../config";

interface SettingsScreenProps {
  onClose: () => void;
  userId: string;
}

export default function SettingsScreen({ onClose, userId }: SettingsScreenProps) {
  const [isGmailConnected, setIsGmailConnected] = useState(false);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const linkingSubscription = useRef<ReturnType<typeof Linking.addEventListener> | null>(null);

  useEffect(() => {
    checkAuthStatus();

    // Listen for the OAuth deep-link callback: elora://auth/success?user_id=...
    linkingSubscription.current = Linking.addEventListener("url", ({ url }) => {
      if (url.startsWith("elora://auth/success")) {
        setIsGmailConnected(true);
        Alert.alert("Connected!", "Your Google account is now linked to Elora.");
      } else if (url.startsWith("elora://auth/error")) {
        const msg = new URL(url).searchParams.get("message") || "Unknown error";
        Alert.alert("Connection Failed", msg);
      }
    });

    return () => {
      linkingSubscription.current?.remove();
    };
  }, []);

  const checkAuthStatus = async () => {
    try {
      const resp = await fetch(`${BACKEND_URL}/auth/status/${userId}`);
      const data = await resp.json();
      setIsGmailConnected(data.connected);
    } catch (e) {
      console.error("[Settings] Auth check failed:", e);
    } finally {
      setCheckingAuth(false);
    }
  };

  const handleConnectGoogle = async () => {
    try {
      const resp = await fetch(`${BACKEND_URL}/auth/login/${userId}`);
      const data = await resp.json();
      if (data.auth_url) {
        await Linking.openURL(data.auth_url);
      } else {
        Alert.alert("Error", "Could not generate auth URL");
      }
    } catch (e) {
      Alert.alert("Error", "Failed to connect. Check your connection.");
    }
  };

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={onClose} style={styles.backButton}>
          <Ionicons name="chevron-back" size={24} color={colors.textPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Settings</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        {/* Profile section */}
        <View style={styles.profileSection}>
          <LinearGradient
            colors={colors.gradientGold as [string, string]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.profileAvatar}
          >
            <Ionicons name="person" size={32} color={colors.background} />
          </LinearGradient>
          <Text style={styles.profileName}>User</Text>
          <Text style={styles.profileSub}>Personal AI Agent</Text>
        </View>

        {/* Connected Accounts */}
        <Text style={styles.sectionLabel}>CONNECTED ACCOUNTS</Text>
        <View style={styles.card}>
          <SettingsRow
            icon="mail-outline"
            label="Gmail"
            description={isGmailConnected ? "Connected" : "Send & read emails"}
            status={checkingAuth ? "loading" : isGmailConnected ? "connected" : "disconnected"}
            onPress={isGmailConnected ? undefined : handleConnectGoogle}
          />
          <View style={styles.divider} />
          <SettingsRow
            icon="calendar-outline"
            label="Google Calendar"
            description={isGmailConnected ? "Connected" : "Create & view events"}
            status={checkingAuth ? "loading" : isGmailConnected ? "connected" : "disconnected"}
            onPress={isGmailConnected ? undefined : handleConnectGoogle}
          />
        </View>

        {/* Capabilities */}
        <Text style={styles.sectionLabel}>CAPABILITIES</Text>
        <View style={styles.card}>
          <SettingsRow
            icon="mic-outline"
            label="Voice"
            description="Push-to-talk & call mode"
            status="connected"
          />
          <View style={styles.divider} />
          <SettingsRow
            icon="eye-outline"
            label="Vision"
            description="Camera analysis"
            status="connected"
          />
          <View style={styles.divider} />
          <SettingsRow
            icon="search-outline"
            label="Web Search"
            description="Real-time information"
            status="connected"
          />
          <View style={styles.divider} />
          <SettingsRow
            icon="hardware-chip-outline"
            label="Memory"
            description="Remembers your preferences"
            status="connected"
          />
        </View>

        {/* About */}
        <Text style={styles.sectionLabel}>ABOUT</Text>
        <View style={styles.card}>
          <SettingsRow
            icon="sparkles"
            label="Elora"
            description="v1.0.0 -- Personal AGI"
          />
          <View style={styles.divider} />
          <SettingsRow
            icon="globe-outline"
            label="Built from"
            description="Addis Ababa, Ethiopia"
          />
          <View style={styles.divider} />
          <SettingsRow
            icon="code-slash-outline"
            label="Powered by"
            description="Gemini + Google ADK"
          />
        </View>

        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

// -- SettingsRow component --

interface SettingsRowProps {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  description: string;
  status?: "connected" | "disconnected" | "loading";
  onPress?: () => void;
}

function SettingsRow({ icon, label, description, status, onPress }: SettingsRowProps) {
  const content = (
    <View style={styles.row}>
      <View style={styles.rowIcon}>
        <Ionicons name={icon} size={20} color={colors.gold} />
      </View>
      <View style={styles.rowContent}>
        <Text style={styles.rowLabel}>{label}</Text>
        <Text style={styles.rowDescription}>{description}</Text>
      </View>
      {status === "loading" && (
        <ActivityIndicator size="small" color={colors.gold} />
      )}
      {status === "connected" && (
        <View style={styles.connectedBadge}>
          <Ionicons name="checkmark-circle" size={20} color={colors.success} />
        </View>
      )}
      {status === "disconnected" && (
        <View style={styles.connectButton}>
          <Text style={styles.connectButtonText}>Connect</Text>
        </View>
      )}
      {!status && (
        <Ionicons name="chevron-forward" size={18} color={colors.textTertiary} />
      )}
    </View>
  );

  if (onPress) {
    return (
      <TouchableOpacity onPress={onPress} activeOpacity={0.7}>
        {content}
      </TouchableOpacity>
    );
  }

  return content;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingTop: 60,
    paddingBottom: 16,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  backButton: {
    width: 40,
    height: 40,
    alignItems: "center",
    justifyContent: "center",
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: colors.textPrimary,
  },
  content: {
    flex: 1,
    paddingHorizontal: 16,
  },
  profileSection: {
    alignItems: "center",
    paddingVertical: 28,
  },
  profileAvatar: {
    width: 72,
    height: 72,
    borderRadius: 36,
    alignItems: "center",
    justifyContent: "center",
    ...shadows.gold,
  },
  profileName: {
    fontSize: 22,
    fontWeight: "700",
    color: colors.textPrimary,
    marginTop: 14,
  },
  profileSub: {
    fontSize: 14,
    color: colors.textSecondary,
    marginTop: 4,
  },
  sectionLabel: {
    fontSize: 12,
    fontWeight: "700",
    color: colors.textTertiary,
    letterSpacing: 1,
    marginTop: 24,
    marginBottom: 10,
    marginLeft: 4,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: "hidden",
  },
  divider: {
    height: 1,
    backgroundColor: colors.border,
    marginLeft: 56,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 14,
    paddingHorizontal: 16,
    gap: 12,
  },
  rowIcon: {
    width: 28,
    height: 28,
    borderRadius: 8,
    backgroundColor: colors.goldMuted,
    alignItems: "center",
    justifyContent: "center",
  },
  rowContent: {
    flex: 1,
  },
  rowLabel: {
    fontSize: 16,
    fontWeight: "600",
    color: colors.textPrimary,
  },
  rowDescription: {
    fontSize: 13,
    color: colors.textSecondary,
    marginTop: 1,
  },
  connectedBadge: {
    padding: 4,
  },
  connectButton: {
    backgroundColor: colors.goldMuted,
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: borderRadius.full,
    borderWidth: 1,
    borderColor: colors.gold,
  },
  connectButtonText: {
    color: colors.gold,
    fontSize: 13,
    fontWeight: "600",
  },
});

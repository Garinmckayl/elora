/**
 * SettingsScreen -- Account connections, preferences, about
 * Premium Warm/Elegant design
 */

import React, { useState, useEffect, useRef, useMemo } from "react";
import {
  View,
  Text,
  Image,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Alert,
  Linking,
  ActivityIndicator,
  Animated,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { spacing, borderRadius, useTheme } from "../theme";
import { BACKEND_URL } from "../config";

import { User } from "firebase/auth";

interface SettingsScreenProps {
  onClose: () => void;
  userId: string;
  user?: User | null;
  onSignIn?: () => Promise<void>;
  onSignOut?: () => Promise<void>;
}

export default function SettingsScreen({ onClose, userId, user, onSignIn, onSignOut }: SettingsScreenProps) {
  const [isGmailConnected, setIsGmailConnected] = useState(false);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const linkingSubscription = useRef<ReturnType<typeof Linking.addEventListener> | null>(null);
  const { mode, toggleTheme, isDark, colors, shadows } = useTheme();
  const insets = useSafeAreaInsets();
  const toggleAnim = useRef(new Animated.Value(isDark ? 1 : 0)).current;
  const styles = useMemo(() => createStyles(colors, shadows), [colors, shadows]);

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
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <TouchableOpacity onPress={onClose} style={styles.backButton}>
          <Ionicons name="chevron-back" size={24} color={colors.textPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Settings</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView style={styles.content} showsVerticalScrollIndicator={false} nestedScrollEnabled={true}>
        {/* Profile section */}
        <View style={styles.profileSection}>
          <LinearGradient
            colors={colors.gradientGold as [string, string]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.profileAvatar}
          >
            {user?.photoURL ? (
              <Image
                source={{ uri: user.photoURL }}
                style={{ width: 72, height: 72, borderRadius: 36 }}
              />
            ) : (
              <Ionicons name="person" size={32} color={colors.background} />
            )}
          </LinearGradient>
          <Text style={styles.profileName}>{user?.displayName || "User"}</Text>
          <Text style={styles.profileSub}>{user?.email || "Personal AI Agent"}</Text>
          {user && onSignOut && (
            <TouchableOpacity
              onPress={onSignOut}
              style={{
                marginTop: 12,
                paddingHorizontal: 20,
                paddingVertical: 8,
                borderRadius: borderRadius.full,
                borderWidth: 1,
                borderColor: colors.error,
                backgroundColor: "rgba(229, 62, 62, 0.1)",
              }}
            >
              <Text style={{ color: colors.error, fontSize: 14, fontWeight: "600" }}>Sign Out</Text>
            </TouchableOpacity>
          )}
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

        {/* Appearance */}
        <Text style={styles.sectionLabel}>APPEARANCE</Text>
        <View style={styles.card}>
          <TouchableOpacity onPress={() => {
            Animated.spring(toggleAnim, {
              toValue: isDark ? 0 : 1,
              useNativeDriver: false,
              friction: 7,
              tension: 40,
            }).start();
            toggleTheme();
          }} activeOpacity={0.7}>
            <View style={styles.row}>
              <View style={styles.rowIcon}>
                <Ionicons name={isDark ? "moon-outline" : "sunny-outline"} size={20} color={colors.gold} />
              </View>
              <View style={styles.rowContent}>
                <Text style={styles.rowLabel}>Theme</Text>
                <Text style={styles.rowDescription}>{isDark ? "Dark mode" : "Light mode"}</Text>
              </View>
              <Animated.View style={{
                width: 50,
                height: 28,
                borderRadius: 14,
                backgroundColor: toggleAnim.interpolate({
                  inputRange: [0, 1],
                  outputRange: ["rgba(0,0,0,0.1)", colors.gold],
                }),
                justifyContent: "center",
                paddingHorizontal: 2,
              }}>
                <Animated.View style={{
                  width: 24,
                  height: 24,
                  borderRadius: 12,
                  backgroundColor: "#FFFFFF",
                  transform: [{
                    translateX: toggleAnim.interpolate({
                      inputRange: [0, 1],
                      outputRange: [0, 22],
                    }),
                  }],
                  shadowColor: "#000",
                  shadowOffset: { width: 0, height: 1 },
                  shadowOpacity: 0.2,
                  shadowRadius: 2,
                  elevation: 2,
                }} />
              </Animated.View>
            </View>
          </TouchableOpacity>
        </View>

        {/* About */}
        <Text style={styles.sectionLabel}>ABOUT</Text>
        <View style={styles.card}>
          <SettingsRow
            icon="sparkles"
            label="Elora"
            description="v1.0.0 -- Personal AI Computer"
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
  const { colors } = useTheme();
  const content = (
    <View style={rowStyles.row}>
      <View style={[rowStyles.rowIcon, { backgroundColor: colors.goldMuted }]}>
        <Ionicons name={icon} size={20} color={colors.gold} />
      </View>
      <View style={rowStyles.rowContent}>
        <Text style={[rowStyles.rowLabel, { color: colors.textPrimary }]}>{label}</Text>
        <Text style={[rowStyles.rowDescription, { color: colors.textSecondary }]}>{description}</Text>
      </View>
      {status === "loading" && (
        <ActivityIndicator size="small" color={colors.gold} />
      )}
      {status === "connected" && (
        <View style={rowStyles.connectedBadge}>
          <Ionicons name="checkmark-circle" size={20} color={colors.success} />
        </View>
      )}
      {status === "disconnected" && (
        <View style={[rowStyles.connectButton, { backgroundColor: colors.goldMuted, borderColor: colors.gold }]}>
          <Text style={[rowStyles.connectButtonText, { color: colors.gold }]}>Connect</Text>
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

const rowStyles = StyleSheet.create({
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
    alignItems: "center",
    justifyContent: "center",
  },
  rowContent: {
    flex: 1,
  },
  rowLabel: {
    fontSize: 16,
    fontWeight: "600",
  },
  rowDescription: {
    fontSize: 13,
    marginTop: 1,
  },
  connectedBadge: {
    padding: 4,
  },
  connectButton: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: borderRadius.full,
    borderWidth: 1,
  },
  connectButtonText: {
    fontSize: 13,
    fontWeight: "600",
  },
});

function createStyles(colors: any, shadows: any) {
  return StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
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
    ...shadows.glow,
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
});
}

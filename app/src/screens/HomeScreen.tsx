/**
 * HomeScreen -- Alive, Warm, Intent-Based
 *
 * Design: Duolingo-level friendly + "Her" level intimate.
 * Blank canvas. Soft gradient. Elora character alive at center.
 * Tap anywhere on the canvas to open chat (type or speak).
 * Dedicated voice call button for live calls.
 *
 * NO clutter. NO traditional nav. NO mock widgets.
 * Just Elora, waiting warmly.
 */

import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Animated,
  Dimensions,
  Platform,
  StatusBar,
  Pressable,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { useTheme, borderRadius, spacing } from "../theme";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import EloraAvatar from "../../components/EloraAvatar";
import { BACKEND_URL } from "../config";

const { width: SCREEN_WIDTH } = Dimensions.get("window");

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface HomeScreenProps {
  userName?: string;
  userId?: string;
  idToken?: string | null;
  onOpenChat: () => void;
  onOpenVoice: () => void;
  onOpenCamera: () => void;
  onOpenSettings: () => void;
  onOpenJourney?: () => void;
  onOpenSkills?: () => void;
}

interface HomeContext {
  lastSummary: string | null;
  lastActive: string | null;
  memoryCount: number;
  peopleCount: number;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function HomeScreen({
  userName,
  userId,
  idToken,
  onOpenChat,
  onOpenVoice,
  onOpenCamera,
  onOpenSettings,
  onOpenJourney,
  onOpenSkills,
}: HomeScreenProps) {
  const { colors, shadows, mode } = useTheme();
  const insets = useSafeAreaInsets();
  const [currentTime, setCurrentTime] = useState<Date>(new Date());
  const [context, setContext] = useState<HomeContext>({
    lastSummary: null,
    lastActive: null,
    memoryCount: 0,
    peopleCount: 0,
  });

  // Animations
  const fadeIn = useRef(new Animated.Value(0)).current;
  const slideUp = useRef(new Animated.Value(30)).current;
  const avatarScale = useRef(new Animated.Value(0.8)).current;
  const avatarFloat = useRef(new Animated.Value(0)).current;
  const glowPulse = useRef(new Animated.Value(0.3)).current;
  const gradientShift = useRef(new Animated.Value(0)).current;
  const buttonPulse = useRef(new Animated.Value(1)).current;
  const buttonGlow = useRef(new Animated.Value(0.15)).current;

  // Update time every minute
  useEffect(() => {
    const interval = setInterval(() => setCurrentTime(new Date()), 60000);
    return () => clearInterval(interval);
  }, []);

  // Fetch real context from backend
  useEffect(() => {
    if (!userId) return;
    const fetchContext = async () => {
      try {
        const params = new URLSearchParams({ user_id: userId });
        if (idToken) params.set("token", idToken);
        const res = await fetch(`${BACKEND_URL}/user/context?${params}`);
        const data = await res.json();
        if (data.status === "ok" && data.context) {
          setContext({
            lastSummary: data.context.last_summary || null,
            lastActive: data.context.last_active || null,
            memoryCount: data.context.memory_count || 0,
            peopleCount: data.context.people_count || 0,
          });
        }
      } catch {
        // Silently fail -- fallback to time-based context
      }
    };
    fetchContext();
  }, [userId, idToken]);

    // Entry animation
    useEffect(() => {
      Animated.parallel([
        Animated.timing(fadeIn, {
          toValue: 1,
          duration: 800,
          useNativeDriver: true,
        }),
        Animated.timing(slideUp, {
          toValue: 0,
          duration: 800,
          useNativeDriver: true,
        }),
        Animated.spring(avatarScale, {
          toValue: 1,
          friction: 6,
          tension: 40,
          useNativeDriver: true,
        }),
      ]).start();

      // Continuous floating animation for avatar -- slower, smoother
      Animated.loop(
        Animated.sequence([
          Animated.timing(avatarFloat, {
            toValue: -6,
            duration: 3000,
            useNativeDriver: true,
          }),
          Animated.timing(avatarFloat, {
            toValue: 6,
            duration: 3000,
            useNativeDriver: true,
          }),
        ])
      ).start();

      // Subtle glow pulse -- softer
      Animated.loop(
        Animated.sequence([
          Animated.timing(glowPulse, {
            toValue: 0.4,
            duration: 3000,
            useNativeDriver: true,
          }),
          Animated.timing(glowPulse, {
            toValue: 0.2,
            duration: 3000,
            useNativeDriver: true,
          }),
        ])
      ).start();

      // Gradient shift animation -- slow subtle breathe
      Animated.loop(
        Animated.sequence([
          Animated.timing(gradientShift, {
            toValue: 1,
            duration: 8000,
            useNativeDriver: true,
          }),
          Animated.timing(gradientShift, {
            toValue: 0,
            duration: 8000,
            useNativeDriver: true,
          }),
        ])
      ).start();

      // Live Call button pulse animation -- subtle
      Animated.loop(
        Animated.sequence([
          Animated.timing(buttonPulse, {
            toValue: 1.06,
            duration: 2000,
            useNativeDriver: true,
          }),
          Animated.timing(buttonPulse, {
            toValue: 1,
            duration: 2000,
            useNativeDriver: true,
          }),
        ])
      ).start();

      // Live Call button glow pulse -- subtle
      Animated.loop(
        Animated.sequence([
          Animated.timing(buttonGlow, {
            toValue: 0.35,
            duration: 2000,
            useNativeDriver: true,
          }),
          Animated.timing(buttonGlow, {
            toValue: 0.15,
            duration: 2000,
            useNativeDriver: true,
          }),
        ])
      ).start();
    }, []);

  // Handle tap anywhere on canvas -> open chat
  const handleCanvasTap = useCallback(() => {
    if (Platform.OS !== "web") {
      import("expo-haptics").then((Haptics) =>
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light)
      ).catch(() => {});
    }
    onOpenChat();
  }, [onOpenChat]);

  // Handle voice call button
  const handleVoiceCall = useCallback(() => {
    if (Platform.OS !== "web") {
      import("expo-haptics").then((Haptics) =>
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium)
      ).catch(() => {});
    }
    onOpenVoice();
  }, [onOpenVoice]);

  // Greeting based on time
  const getGreeting = () => {
    const hour = currentTime.getHours();
    if (hour < 12) return "Good Morning";
    if (hour < 17) return "Good Afternoon";
    if (hour < 21) return "Good Evening";
    return "Good Night";
  };

  // Context line -- prefer real data, fallback to time-based
  const getContextLine = () => {
    // If we have a real last session summary, derive something from it
    if (context.lastSummary) {
      // Truncate the summary to a short, friendly line
      const summary = context.lastSummary;
      if (summary.length > 60) {
        return summary.slice(0, 57).trimEnd() + "...";
      }
      return summary;
    }

    // If we have stats, mention them
    if (context.memoryCount > 0 && context.peopleCount > 0) {
      return `I remember ${context.memoryCount} things about you`;
    }
    if (context.memoryCount > 0) {
      return `${context.memoryCount} memories and counting`;
    }

    // Fallback: time-based
    const hour = currentTime.getHours();
    if (hour < 9) return "Ready to plan your day";
    if (hour < 12) return "Here whenever you need me";
    if (hour < 14) return "How's your day going?";
    if (hour < 17) return "Keeping an eye on things for you";
    if (hour < 20) return "Winding down with you";
    return "Still here if you need anything";
  };

  const greeting = getGreeting();
  const displayName = userName ? userName.split(" ")[0] : "";
  const contextLine = getContextLine();

  return (
    <View style={styles.container}>
      <StatusBar barStyle={mode === "dark" ? "light-content" : "dark-content"} />

      {/* Background Gradient -- subtle, warm, breathing */}
      <LinearGradient
        colors={colors.backgroundGradient as [string, string, string]}
        style={StyleSheet.absoluteFillObject}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
      />
      
      {/* Subtle warm overlay -- slow opacity breathe */}
      <Animated.View
        style={[
          StyleSheet.absoluteFillObject,
          {
            opacity: gradientShift.interpolate({ inputRange: [0, 1], outputRange: [0.3, 0.5] }),
          },
        ]}
        pointerEvents="none"
      >
        <LinearGradient
          colors={colors.gradientWarm as [string, string]}
          style={StyleSheet.absoluteFillObject}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
        />
      </Animated.View>

      {/* Top -- Settings only, ultra minimal */}
      <Animated.View
        style={[
          styles.topBar,
          { paddingTop: insets.top + 12, opacity: fadeIn },
        ]}
      >
        <View style={styles.topLeft}>
          <View style={[styles.statusPill, { backgroundColor: colors.goldMuted }]}>
            <View style={[styles.liveDot, { backgroundColor: colors.connected }]} />
            <Text style={[styles.statusPillText, { color: colors.textSecondary }]} numberOfLines={1}>
              {contextLine}
            </Text>
          </View>
        </View>
        <View style={styles.topRight}>
          {onOpenSkills && (
            <TouchableOpacity
              onPress={onOpenSkills}
              style={[styles.settingsBtn, { backgroundColor: `${colors.surface}80` }]}
              hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
            >
              <Ionicons name="flash-outline" size={20} color={colors.textTertiary} />
            </TouchableOpacity>
          )}
          {onOpenJourney && (
            <TouchableOpacity
              onPress={onOpenJourney}
              style={[styles.settingsBtn, { backgroundColor: `${colors.surface}80` }]}
              hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
            >
              <Ionicons name="map-outline" size={20} color={colors.textTertiary} />
            </TouchableOpacity>
          )}
          <TouchableOpacity
            onPress={onOpenSettings}
            style={[styles.settingsBtn, { backgroundColor: `${colors.surface}80` }]}
            hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
          >
            <Ionicons name="settings-outline" size={20} color={colors.textTertiary} />
          </TouchableOpacity>
        </View>
      </Animated.View>

      {/* Main Canvas -- tap anywhere to type/speak */}
      <Pressable
        style={styles.canvasArea}
        onPress={handleCanvasTap}
      >
        <Animated.View
          style={[
            styles.centerSection,
            {
              opacity: fadeIn,
              transform: [{ translateY: slideUp }],
            },
          ]}
        >
          {/* Greeting */}
          {displayName ? (
            <>
              <Text style={[styles.greetingLabel, { color: colors.textSecondary }]}>
                {greeting},
              </Text>
              <Text style={[styles.nameLabel, { color: colors.textPrimary }]}>
                {displayName}
              </Text>
            </>
          ) : (
            <Text style={[styles.nameLabel, { color: colors.textGold }]}>
              {greeting}
            </Text>
          )}

          {/* Elora Avatar -- alive, floating */}
          <Animated.View
            style={[
              styles.avatarWrapper,
              {
                transform: [
                  { scale: avatarScale },
                  { translateY: avatarFloat },
                ],
              },
            ]}
          >
            {/* Soft glow behind avatar */}
            <Animated.View
              style={[
                styles.avatarGlow,
                {
                  backgroundColor: colors.gold,
                  opacity: glowPulse,
                },
              ]}
            />
            <EloraAvatar state="happy" size="large" animated />
          </Animated.View>

          {/* Tap hint */}
          <Text style={[styles.tapHint, { color: colors.textTertiary }]}>
            Tap anywhere to talk to Elora
          </Text>
        </Animated.View>
      </Pressable>

      {/* Bottom -- Voice call button + camera */}
      <Animated.View
        style={[
          styles.bottomSection,
          {
            paddingBottom: insets.bottom + 16,
            opacity: fadeIn,
          },
        ]}
      >
        {/* Action row */}
        <View style={styles.actionRow}>
          {/* Camera button */}
          <TouchableOpacity
            style={[
              styles.secondaryBtn,
              { 
                backgroundColor: `${colors.surfaceLight}CC`,
                borderColor: colors.goldMuted,
                borderWidth: 1.5,
              },
            ]}
            onPress={() => {
              if (Platform.OS !== "web") {
                import("expo-haptics").then((Haptics) =>
                  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light)
                ).catch(() => {});
              }
              onOpenCamera();
            }}
            activeOpacity={0.7}
          >
            <Ionicons name="camera-outline" size={22} color={colors.gold} />
          </TouchableOpacity>

          {/* Voice call button -- primary CTA with animated gradient */}
          <TouchableOpacity
            style={[styles.voiceCallBtn, shadows.glow]}
            onPress={handleVoiceCall}
            activeOpacity={0.8}
          >
            <Animated.View
              style={[
                styles.voiceCallGradient,
                {
                  transform: [{ scale: buttonPulse }],
                  shadowOpacity: buttonGlow,
                },
              ]}
            >
              <LinearGradient
                colors={colors.gradientGold as [string, string]}
                style={StyleSheet.absoluteFillObject}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 1 }}
              />
              <View style={styles.voiceCallContent}>
                <Ionicons name="call" size={26} color="#FFF" />
                <Text style={styles.voiceCallText}>Live Call</Text>
              </View>
            </Animated.View>
          </TouchableOpacity>

          {/* Chat button */}
          <TouchableOpacity
            style={[
              styles.secondaryBtn,
              { 
                backgroundColor: `${colors.surfaceLight}CC`,
                borderColor: colors.goldMuted,
                borderWidth: 1.5,
              },
            ]}
            onPress={handleCanvasTap}
            activeOpacity={0.7}
          >
            <Ionicons name="chatbubble-outline" size={22} color={colors.gold} />
          </TouchableOpacity>
        </View>
      </Animated.View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },

  // Top bar
  topBar: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 20,
    zIndex: 10,
  },
  topLeft: {
    flex: 1,
    marginRight: 12,
  },
  statusPill: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
    gap: 8,
    maxWidth: "100%",
  },
  liveDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    flexShrink: 0,
  },
  statusPillText: {
    fontSize: 13,
    fontWeight: "500",
    flexShrink: 1,
  },
  settingsBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  topRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },

  // Canvas (tappable area)
  canvasArea: {
    flex: 1,
  },

  // Center
  centerSection: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 32,
  },
  greetingLabel: {
    fontSize: 18,
    fontWeight: "400",
    marginBottom: 4,
  },
  nameLabel: {
    fontSize: 38,
    fontWeight: "700",
    letterSpacing: -1,
    marginBottom: 40,
  },
  avatarWrapper: {
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 24,
  },
  avatarGlow: {
    position: "absolute",
    width: 180,
    height: 180,
    borderRadius: 90,
  },
  tapHint: {
    fontSize: 14,
    fontWeight: "400",
    marginTop: 8,
  },

  // Bottom
  bottomSection: {
    paddingHorizontal: 20,
  },
  actionRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 16,
  },
  secondaryBtn: {
    width: 52,
    height: 52,
    borderRadius: 26,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  voiceCallBtn: {
    borderRadius: 28,
    overflow: "hidden",
  },
  voiceCallGradient: {
    borderRadius: 28,
    overflow: "hidden",
  },
  voiceCallContent: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 16,
    paddingHorizontal: 32,
    gap: 10,
  },
  voiceCallText: {
    color: "#FFF",
    fontSize: 17,
    fontWeight: "700",
  },
});

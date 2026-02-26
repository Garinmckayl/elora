/**
 * LiveCallScreen -- Immersive full-screen live call experience
 *
 * Full camera feed background with floating UI elements:
 * - Top: ELORA pill badge + three-dot menu
 * - Center-right: Rotating AI scanning indicator
 * - Bottom: Text input, action buttons, audio waveform
 * - Gradient overlays for legibility
 */

import React, { useEffect, useRef, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Animated,
  Easing,
  Dimensions,
  TextInput,
  Platform,
  KeyboardAvoidingView,
  ScrollView,
} from "react-native";
import { CameraView } from "expo-camera";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { colors, borderRadius, shadows } from "../theme";

/** Minimal message shape — matches useElora.Message */
interface CallMessage {
  id: string;
  role: "user" | "elora";
  content: string;
  toolName?: string;
  isThinking?: boolean;
}

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get("window");

interface LiveCallScreenProps {
  cameraRef: React.RefObject<CameraView | null>;
  isListening: boolean;
  isSpeaking: boolean;
  isThinking: boolean;
  isScanning: boolean;        // AI is actively processing a frame
  liveCamera: boolean;
  isMuted?: boolean;          // Whether audio streaming is muted
  transcript?: string;        // Last user transcript or text input
  eloraText?: string;         // Last Elora response (live captions)
  userTranscript?: string;    // What the user said (shown for debugging)
  messages?: CallMessage[];   // Real-time message log for the call
  onEndCall: () => void;
  onToggleCamera: () => void;
  onPressIn: () => void;      // Hold mic to talk (fallback)
  onPressOut: () => void;
  onSendText: (text: string) => void;
  onToggleMute?: () => void;
  cameraFacing?: "front" | "back";
  onFlipCamera?: () => void;
}

export default function LiveCallScreen({
  cameraRef,
  isListening,
  isSpeaking,
  isThinking,
  isScanning,
  liveCamera,
  isMuted = false,
  transcript,
  eloraText,
  userTranscript,
  messages = [],
  onEndCall,
  onToggleCamera,
  onPressIn,
  onPressOut,
  onSendText,
  onToggleMute,
  cameraFacing = "back",
  onFlipCamera,
}: LiveCallScreenProps) {
  const [textInput, setTextInput] = useState("");
  const [showLog, setShowLog] = useState(true);
  const scrollRef = useRef<ScrollView>(null);

  // -- Animations --

  // Scanning icon rotation
  const scanRotation = useRef(new Animated.Value(0)).current;
  const scanOpacity = useRef(new Animated.Value(0)).current;

  // Waveform bars
  const wave1 = useRef(new Animated.Value(0.3)).current;
  const wave2 = useRef(new Animated.Value(0.5)).current;
  const wave3 = useRef(new Animated.Value(0.4)).current;

  // Elora badge pulse
  const badgePulse = useRef(new Animated.Value(1)).current;

  // Caption fade
  const captionOpacity = useRef(new Animated.Value(0)).current;

  // Orb animation layers (no-camera mode)
  const orbScale1 = useRef(new Animated.Value(1)).current;
  const orbScale2 = useRef(new Animated.Value(0.85)).current;
  const orbScale3 = useRef(new Animated.Value(0.7)).current;
  const orbOpacity1 = useRef(new Animated.Value(0.15)).current;
  const orbOpacity2 = useRef(new Animated.Value(0.1)).current;
  const orbOpacity3 = useRef(new Animated.Value(0.05)).current;
  const orbRotation = useRef(new Animated.Value(0)).current;

  // Scanning rotation
  useEffect(() => {
    if (isScanning || liveCamera) {
      Animated.timing(scanOpacity, {
        toValue: 1,
        duration: 300,
        useNativeDriver: true,
      }).start();

      Animated.loop(
        Animated.timing(scanRotation, {
          toValue: 1,
          duration: 2000,
          easing: Easing.linear,
          useNativeDriver: true,
        })
      ).start();
    } else {
      Animated.timing(scanOpacity, {
        toValue: 0,
        duration: 300,
        useNativeDriver: true,
      }).start();
    }
  }, [isScanning, liveCamera]);

  // Waveform animation (active when speaking or listening)
  useEffect(() => {
    const active = isSpeaking || isListening;
    if (active) {
      const animateBar = (bar: Animated.Value, minH: number, maxH: number, dur: number) =>
        Animated.loop(
          Animated.sequence([
            Animated.timing(bar, {
              toValue: maxH,
              duration: dur,
              easing: Easing.inOut(Easing.sin),
              useNativeDriver: false,
            }),
            Animated.timing(bar, {
              toValue: minH,
              duration: dur,
              easing: Easing.inOut(Easing.sin),
              useNativeDriver: false,
            }),
          ])
        );

      const a1 = animateBar(wave1, 0.2, 1.0, isSpeaking ? 400 : 300);
      const a2 = animateBar(wave2, 0.3, 0.9, isSpeaking ? 550 : 250);
      const a3 = animateBar(wave3, 0.15, 1.0, isSpeaking ? 350 : 350);
      a1.start();
      a2.start();
      a3.start();

      return () => {
        a1.stop();
        a2.stop();
        a3.stop();
      };
    } else {
      // Settle bars
      Animated.parallel([
        Animated.timing(wave1, { toValue: 0.3, duration: 300, useNativeDriver: false }),
        Animated.timing(wave2, { toValue: 0.5, duration: 300, useNativeDriver: false }),
        Animated.timing(wave3, { toValue: 0.4, duration: 300, useNativeDriver: false }),
      ]).start();
    }
  }, [isSpeaking, isListening]);

  // Badge pulse when Elora is speaking
  useEffect(() => {
    if (isSpeaking) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(badgePulse, {
            toValue: 1.1,
            duration: 600,
            useNativeDriver: true,
          }),
          Animated.timing(badgePulse, {
            toValue: 1,
            duration: 600,
            useNativeDriver: true,
          }),
        ])
      ).start();
    } else {
      badgePulse.stopAnimation();
      Animated.timing(badgePulse, {
        toValue: 1,
        duration: 200,
        useNativeDriver: true,
      }).start();
    }
  }, [isSpeaking]);

  // Orb breathing animation (no-camera mode) -- reacts to voice state
  useEffect(() => {
    // Slow rotation always running
    Animated.loop(
      Animated.timing(orbRotation, {
        toValue: 1,
        duration: 12000,
        easing: Easing.linear,
        useNativeDriver: true,
      })
    ).start();

    // Breathing layers
    const breathe = (val: Animated.Value, min: number, max: number, dur: number) =>
      Animated.loop(
        Animated.sequence([
          Animated.timing(val, { toValue: max, duration: dur, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
          Animated.timing(val, { toValue: min, duration: dur, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
        ])
      );

    if (isSpeaking) {
      // Energetic pulsing when Elora speaks
      breathe(orbScale1, 0.95, 1.2, 500).start();
      breathe(orbScale2, 0.8, 1.15, 650).start();
      breathe(orbScale3, 0.65, 1.1, 400).start();
      Animated.timing(orbOpacity1, { toValue: 0.4, duration: 300, useNativeDriver: true }).start();
      Animated.timing(orbOpacity2, { toValue: 0.25, duration: 300, useNativeDriver: true }).start();
      Animated.timing(orbOpacity3, { toValue: 0.15, duration: 300, useNativeDriver: true }).start();
    } else if (isListening) {
      // Subtle expansion when listening
      breathe(orbScale1, 1.0, 1.08, 800).start();
      breathe(orbScale2, 0.85, 0.95, 1000).start();
      breathe(orbScale3, 0.7, 0.8, 700).start();
      Animated.timing(orbOpacity1, { toValue: 0.3, duration: 300, useNativeDriver: true }).start();
      Animated.timing(orbOpacity2, { toValue: 0.18, duration: 300, useNativeDriver: true }).start();
      Animated.timing(orbOpacity3, { toValue: 0.1, duration: 300, useNativeDriver: true }).start();
    } else if (isThinking) {
      // Tight pulse when thinking
      breathe(orbScale1, 0.98, 1.05, 600).start();
      breathe(orbScale2, 0.82, 0.92, 800).start();
      breathe(orbScale3, 0.68, 0.78, 500).start();
      Animated.timing(orbOpacity1, { toValue: 0.25, duration: 300, useNativeDriver: true }).start();
      Animated.timing(orbOpacity2, { toValue: 0.15, duration: 300, useNativeDriver: true }).start();
      Animated.timing(orbOpacity3, { toValue: 0.08, duration: 300, useNativeDriver: true }).start();
    } else {
      // Idle: gentle breathing
      breathe(orbScale1, 0.97, 1.03, 3000).start();
      breathe(orbScale2, 0.83, 0.88, 3500).start();
      breathe(orbScale3, 0.68, 0.73, 4000).start();
      Animated.timing(orbOpacity1, { toValue: 0.15, duration: 500, useNativeDriver: true }).start();
      Animated.timing(orbOpacity2, { toValue: 0.1, duration: 500, useNativeDriver: true }).start();
      Animated.timing(orbOpacity3, { toValue: 0.05, duration: 500, useNativeDriver: true }).start();
    }
  }, [isSpeaking, isListening, isThinking]);

  // Caption text fade-in
  useEffect(() => {
    if (eloraText) {
      Animated.timing(captionOpacity, {
        toValue: 1,
        duration: 250,
        useNativeDriver: true,
      }).start();
    }
  }, [eloraText]);

  // Auto-scroll message log when new messages arrive
  useEffect(() => {
    if (messages.length > 0 && showLog) {
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 80);
    }
  }, [messages.length, showLog]);

  const scanSpin = scanRotation.interpolate({
    inputRange: [0, 1],
    outputRange: ["0deg", "360deg"],
  });

  const handleSend = () => {
    if (textInput.trim()) {
      onSendText(textInput.trim());
      setTextInput("");
    }
  };

  const handleEndCall = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
    onEndCall();
  };

  const maxBarHeight = 28;

  return (
    <View style={styles.container}>
      {/* Full-screen camera feed */}
      {liveCamera ? (
        <CameraView
          ref={cameraRef}
          style={StyleSheet.absoluteFillObject}
          facing={cameraFacing}
          active={true}
          flash="off"
          animateShutter={false}
        />
      ) : (
        <View style={[StyleSheet.absoluteFillObject, styles.noCameraBg]}>
          <LinearGradient
            colors={["#0A0E1A", "#121829", "#1A2238"]}
            style={StyleSheet.absoluteFillObject}
          />
          {/* Elora orb -- multi-layered breathing visualization */}
          <View style={styles.orbContainer}>
            {/* Outer ring -- slowest, largest */}
            <Animated.View style={[styles.orbRing, styles.orbRing3, {
              transform: [
                { scale: orbScale3 },
                { rotate: orbRotation.interpolate({ inputRange: [0, 1], outputRange: ["0deg", "-360deg"] }) },
              ],
              opacity: orbOpacity3,
            }]} />
            {/* Middle ring */}
            <Animated.View style={[styles.orbRing, styles.orbRing2, {
              transform: [
                { scale: orbScale2 },
                { rotate: orbRotation.interpolate({ inputRange: [0, 1], outputRange: ["0deg", "360deg"] }) },
              ],
              opacity: orbOpacity2,
            }]} />
            {/* Inner core -- brightest */}
            <Animated.View style={[styles.orbRing, styles.orbRing1, {
              transform: [{ scale: orbScale1 }],
              opacity: orbOpacity1,
            }]} />
            {/* Center dot -- always visible */}
            <View style={styles.orbCenter} />
            {/* State label */}
            <Text style={styles.orbLabel}>
              {isSpeaking ? "Speaking" : isListening ? "Listening" : isThinking ? "Thinking" : "Elora"}
            </Text>
          </View>
        </View>
      )}

      {/* Top gradient overlay */}
      <LinearGradient
        colors={["rgba(0,0,0,0.6)", "rgba(0,0,0,0.3)", "transparent"]}
        style={styles.topGradient}
        pointerEvents="none"
      />

      {/* Bottom gradient overlay */}
      <LinearGradient
        colors={["transparent", "rgba(0,0,0,0.4)", "rgba(0,0,0,0.75)"]}
        style={styles.bottomGradient}
        pointerEvents="none"
      />

      {/* ---- TOP FLOATING UI ---- */}
      <View style={styles.topBar}>
        {/* ELORA pill badge */}
        <Animated.View style={[styles.eloraBadge, { transform: [{ scale: badgePulse }] }]}>
          <LinearGradient
            colors={colors.gradientGold as [string, string]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 0 }}
            style={styles.eloraBadgeGradient}
          >
            <View style={styles.eloraBadgeDot} />
            <Text style={styles.eloraBadgeText}>ELORA</Text>
          </LinearGradient>
        </Animated.View>

        {/* Call duration / status */}
        <CallTimer isActive={true} />

        {/* Menu button */}
        <TouchableOpacity style={styles.menuButton} onPress={onFlipCamera}>
          <Ionicons name="camera-reverse-outline" size={20} color="rgba(255,255,255,0.8)" />
        </TouchableOpacity>
      </View>

      {/* ---- CENTER: AI Scanning indicator ---- */}
      <Animated.View style={[styles.scanIndicator, {
        opacity: scanOpacity,
        transform: [{ rotate: scanSpin }],
      }]}>
        <Ionicons name="sync-outline" size={32} color={colors.gold} />
      </Animated.View>

      {/* ---- REAL-TIME MESSAGE LOG ---- */}
      {showLog && messages.length > 0 && (
        <View style={styles.messageLogContainer}>
          <View style={styles.messageLogHeader}>
            <Text style={styles.messageLogTitle}>Live Transcript</Text>
            <TouchableOpacity onPress={() => setShowLog(false)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
              <Ionicons name="chevron-down" size={16} color="rgba(255,255,255,0.5)" />
            </TouchableOpacity>
          </View>
          <ScrollView
            ref={scrollRef}
            style={styles.messageLogScroll}
            contentContainerStyle={styles.messageLogContent}
            showsVerticalScrollIndicator={false}
          >
            {messages.slice(-30).map((msg) => (
              <View
                key={msg.id}
                style={[
                  styles.logBubble,
                  msg.role === "user" ? styles.logBubbleUser : styles.logBubbleElora,
                ]}
              >
                <Text style={styles.logRole}>
                  {msg.role === "user" ? "You" : "Elora"}
                  {msg.toolName ? ` → ${msg.toolName}` : ""}
                </Text>
                <Text style={styles.logText} numberOfLines={4}>
                  {msg.toolName && !msg.content
                    ? `Using ${msg.toolName}...`
                    : msg.content || "..."}
                </Text>
              </View>
            ))}
          </ScrollView>
        </View>
      )}

      {/* Collapsed log toggle */}
      {!showLog && messages.length > 0 && (
        <TouchableOpacity style={styles.showLogButton} onPress={() => setShowLog(true)}>
          <Ionicons name="chatbubbles-outline" size={14} color="rgba(255,255,255,0.7)" />
          <Text style={styles.showLogButtonText}>Show transcript ({messages.length})</Text>
        </TouchableOpacity>
      )}

      {/* ---- LIVE CAPTIONS (most recent Elora text) ---- */}
      {eloraText && !showLog && (
        <Animated.View style={[styles.captionContainer, { opacity: captionOpacity }]}>
          <Text style={styles.captionText} numberOfLines={3}>
            {eloraText}
          </Text>
        </Animated.View>
      )}

      {/* Listening indicator */}
      {isListening && (
        <View style={styles.listeningBadge}>
          <View style={styles.listeningDot} />
          <Text style={styles.listeningText}>Listening...</Text>
        </View>
      )}

      {/* ---- BOTTOM CONTROLS ---- */}
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={styles.bottomArea}
      >
        {/* Text input row */}
        <View style={styles.inputRow}>
          <View style={styles.textInputWrapper}>
            <TextInput
              style={styles.textInput}
              value={textInput}
              onChangeText={setTextInput}
              placeholder="Ask Elora..."
              placeholderTextColor="rgba(255,255,255,0.4)"
              returnKeyType="send"
              onSubmitEditing={handleSend}
            />
            {textInput.trim() ? (
              <TouchableOpacity onPress={handleSend} style={styles.sendBtn}>
                <Ionicons name="arrow-up" size={18} color={colors.background} />
              </TouchableOpacity>
            ) : null}
          </View>
        </View>

        {/* Action buttons row */}
        <View style={styles.controlsRow}>
          {/* End call */}
          <TouchableOpacity style={styles.endCallButton} onPress={handleEndCall}>
            <Ionicons name="close" size={24} color="#FFFFFF" />
          </TouchableOpacity>

          {/* Mute/unmute toggle (replaces hold-to-talk) */}
          <TouchableOpacity
            style={[
              styles.micButton,
              isMuted && styles.micButtonMuted,
              !isMuted && !isSpeaking && styles.micButtonActive,
            ]}
            onPress={() => {
              Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
              onToggleMute?.();
            }}
            activeOpacity={0.8}
          >
            <Ionicons
              name={isMuted ? "mic-off" : "mic"}
              size={28}
              color={isMuted ? "#FF4444" : "#FFFFFF"}
            />
          </TouchableOpacity>

          {/* Camera toggle */}
          <TouchableOpacity
            style={[styles.actionButton, liveCamera && styles.actionButtonActive]}
            onPress={onToggleCamera}
          >
            <Ionicons
              name={liveCamera ? "videocam" : "videocam-outline"}
              size={22}
              color={liveCamera ? colors.gold : "rgba(255,255,255,0.7)"}
            />
          </TouchableOpacity>

          {/* Waveform indicator */}
          <View style={styles.waveformContainer}>
            {[wave1, wave2, wave3].map((bar, i) => (
              <Animated.View
                key={i}
                style={[
                  styles.waveformBar,
                  {
                    height: bar.interpolate({
                      inputRange: [0, 1],
                      outputRange: [4, maxBarHeight],
                    }),
                    backgroundColor: isSpeaking
                      ? colors.gold
                      : isListening
                      ? colors.error
                      : "rgba(255,255,255,0.3)",
                  },
                ]}
              />
            ))}
          </View>
        </View>

        {/* Status text */}
        <Text style={styles.statusText}>
          {isMuted
            ? "Muted"
            : isSpeaking
            ? "Elora is speaking"
            : isListening
            ? "Listening..."
            : isThinking
            ? "Processing..."
            : liveCamera
            ? "Camera active"
            : "Streaming audio..."}
        </Text>
      </KeyboardAvoidingView>
    </View>
  );
}

// -- Call Timer sub-component --

function CallTimer({ isActive }: { isActive: boolean }) {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    if (!isActive) return;
    const interval = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(interval);
  }, [isActive]);

  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  const display = `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;

  return (
    <View style={styles.timerContainer}>
      <View style={styles.timerDot} />
      <Text style={styles.timerText}>{display}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#000",
  },
  noCameraBg: {
    alignItems: "center",
    justifyContent: "center",
  },

  // Elora orb visualization
  orbContainer: {
    alignItems: "center",
    justifyContent: "center",
    width: 280,
    height: 280,
  },
  orbRing: {
    position: "absolute",
    borderRadius: 999,
    borderWidth: 1.5,
  },
  orbRing1: {
    width: 120,
    height: 120,
    borderColor: colors.gold,
    backgroundColor: "rgba(212, 168, 83, 0.08)",
  },
  orbRing2: {
    width: 180,
    height: 180,
    borderColor: colors.gold,
    backgroundColor: "rgba(212, 168, 83, 0.04)",
    borderStyle: "dashed" as any,
  },
  orbRing3: {
    width: 250,
    height: 250,
    borderColor: "rgba(212, 168, 83, 0.5)",
    backgroundColor: "rgba(212, 168, 83, 0.02)",
  },
  orbCenter: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.gold,
    shadowColor: colors.gold,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 12,
    elevation: 8,
  },
  orbLabel: {
    position: "absolute",
    bottom: 20,
    color: "rgba(255,255,255,0.4)",
    fontSize: 11,
    fontWeight: "600",
    letterSpacing: 2,
    textTransform: "uppercase" as any,
  },

  // Gradient overlays
  topGradient: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    height: 140,
    zIndex: 1,
  },
  bottomGradient: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    height: 280,
    zIndex: 1,
  },

  // Top bar
  topBar: {
    position: "absolute",
    top: Platform.OS === "ios" ? 60 : 40,
    left: 0,
    right: 0,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    zIndex: 10,
  },
  eloraBadge: {
    borderRadius: borderRadius.full,
    overflow: "hidden",
  },
  eloraBadgeGradient: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 14,
    paddingVertical: 7,
    gap: 6,
  },
  eloraBadgeDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: "#0A0E1A",
  },
  eloraBadgeText: {
    color: "#0A0E1A",
    fontSize: 12,
    fontWeight: "800",
    letterSpacing: 1.5,
  },
  menuButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: "rgba(255,255,255,0.15)",
    alignItems: "center",
    justifyContent: "center",
  },

  // Timer
  timerContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "rgba(0,0,0,0.4)",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: borderRadius.full,
  },
  timerDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.error,
  },
  timerText: {
    color: "rgba(255,255,255,0.9)",
    fontSize: 13,
    fontWeight: "600",
    fontVariant: ["tabular-nums"],
  },

  // Scanning indicator
  scanIndicator: {
    position: "absolute",
    top: "40%",
    right: 24,
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: "rgba(0,0,0,0.3)",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 5,
  },

  // Real-time message log
  messageLogContainer: {
    position: "absolute",
    top: Platform.OS === "ios" ? 110 : 90,
    left: 12,
    right: 12,
    bottom: 240,
    backgroundColor: "rgba(0,0,0,0.6)",
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
    zIndex: 5,
    overflow: "hidden",
  },
  messageLogHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255,255,255,0.08)",
  },
  messageLogTitle: {
    color: "rgba(255,255,255,0.5)",
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 1,
    textTransform: "uppercase" as any,
  },
  messageLogScroll: {
    flex: 1,
  },
  messageLogContent: {
    paddingHorizontal: 10,
    paddingVertical: 8,
    gap: 6,
  },
  logBubble: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: borderRadius.md,
    maxWidth: "85%",
  },
  logBubbleUser: {
    alignSelf: "flex-end",
    backgroundColor: "rgba(212, 168, 83, 0.2)",
    borderWidth: 1,
    borderColor: "rgba(212, 168, 83, 0.3)",
  },
  logBubbleElora: {
    alignSelf: "flex-start",
    backgroundColor: "rgba(255,255,255,0.08)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
  },
  logRole: {
    fontSize: 9,
    fontWeight: "700",
    letterSpacing: 0.5,
    color: "rgba(255,255,255,0.4)",
    marginBottom: 2,
    textTransform: "uppercase" as any,
  },
  logText: {
    color: "rgba(255,255,255,0.85)",
    fontSize: 13,
    lineHeight: 18,
  },
  showLogButton: {
    position: "absolute",
    top: Platform.OS === "ios" ? 110 : 90,
    alignSelf: "center",
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "rgba(0,0,0,0.5)",
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: borderRadius.full,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.15)",
    zIndex: 5,
  },
  showLogButtonText: {
    color: "rgba(255,255,255,0.6)",
    fontSize: 12,
    fontWeight: "600",
  },

  // Live captions (shown when log is collapsed)
  captionContainer: {
    position: "absolute",
    bottom: 260,
    left: 20,
    right: 20,
    backgroundColor: "rgba(0,0,0,0.55)",
    borderRadius: borderRadius.md,
    paddingHorizontal: 16,
    paddingVertical: 10,
    zIndex: 5,
  },
  captionText: {
    color: "#FFFFFF",
    fontSize: 15,
    lineHeight: 21,
    fontWeight: "500",
  },

  // Listening indicator
  listeningBadge: {
    position: "absolute",
    bottom: 300,
    alignSelf: "center",
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "rgba(229, 62, 62, 0.3)",
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: borderRadius.full,
    borderWidth: 1,
    borderColor: "rgba(229, 62, 62, 0.5)",
    zIndex: 6,
  },
  listeningDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.error,
  },
  listeningText: {
    color: "#FFFFFF",
    fontSize: 13,
    fontWeight: "600",
  },

  // Bottom area
  bottomArea: {
    position: "absolute",
    bottom: Platform.OS === "ios" ? 40 : 20,
    left: 0,
    right: 0,
    zIndex: 10,
    paddingHorizontal: 20,
  },

  // Text input
  inputRow: {
    marginBottom: 16,
  },
  textInputWrapper: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.12)",
    borderRadius: borderRadius.full,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.15)",
    paddingHorizontal: 16,
    paddingVertical: Platform.OS === "ios" ? 10 : 4,
  },
  textInput: {
    flex: 1,
    color: "#FFFFFF",
    fontSize: 15,
  },
  sendBtn: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: colors.gold,
    alignItems: "center",
    justifyContent: "center",
    marginLeft: 8,
  },

  // Controls row
  controlsRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 18,
    marginBottom: 8,
  },
  endCallButton: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.error,
    alignItems: "center",
    justifyContent: "center",
    ...shadows.soft,
  },
  micButton: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: "rgba(255,255,255,0.15)",
    borderWidth: 2,
    borderColor: colors.gold,
    alignItems: "center",
    justifyContent: "center",
  },
  micButtonActive: {
    backgroundColor: colors.gold,
    borderColor: colors.gold,
    ...shadows.glow,
  },
  micButtonMuted: {
    backgroundColor: "rgba(255,68,68,0.15)",
    borderColor: "#FF4444",
  },
  actionButton: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: "rgba(255,255,255,0.12)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.2)",
    alignItems: "center",
    justifyContent: "center",
  },
  actionButtonActive: {
    backgroundColor: colors.goldMuted,
    borderColor: colors.gold,
  },

  // Waveform
  waveformContainer: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 3,
    height: 28,
    paddingBottom: 2,
  },
  waveformBar: {
    width: 4,
    borderRadius: 2,
    minHeight: 4,
  },

  // Status
  statusText: {
    color: "rgba(255,255,255,0.6)",
    fontSize: 12,
    textAlign: "center",
    marginTop: 6,
    fontWeight: "500",
  },
});

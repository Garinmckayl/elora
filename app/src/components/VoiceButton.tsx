/**
 * VoiceButton -- Premium push-to-talk button with gold glow animation
 * Warm/Elegant theme
 */

import React, { useEffect, useRef } from "react";
import {
  TouchableOpacity,
  Animated,
  StyleSheet,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useTheme } from "../theme";

interface VoiceButtonProps {
  isListening: boolean;
  isThinking: boolean;
  onPressIn: () => void;
  onPressOut: () => void;
  disabled?: boolean;
}

export default function VoiceButton({
  isListening,
  isThinking,
  onPressIn,
  onPressOut,
  disabled = false,
}: VoiceButtonProps) {
  const { colors, shadows } = useTheme();
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const glowAnim = useRef(new Animated.Value(0)).current;
  const ringScale = useRef(new Animated.Value(1)).current;
  const outerRingOpacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (isListening) {
      // Pulsing animation while listening
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, {
            toValue: 1.08,
            duration: 700,
            useNativeDriver: true,
          }),
          Animated.timing(pulseAnim, {
            toValue: 1,
            duration: 700,
            useNativeDriver: true,
          }),
        ])
      ).start();

      // Ring expansion
      Animated.loop(
        Animated.sequence([
          Animated.timing(ringScale, {
            toValue: 1.4,
            duration: 1200,
            useNativeDriver: true,
          }),
          Animated.timing(ringScale, {
            toValue: 1,
            duration: 0,
            useNativeDriver: true,
          }),
        ])
      ).start();

      Animated.loop(
        Animated.sequence([
          Animated.timing(outerRingOpacity, {
            toValue: 0.6,
            duration: 100,
            useNativeDriver: true,
          }),
          Animated.timing(outerRingOpacity, {
            toValue: 0,
            duration: 1100,
            useNativeDriver: true,
          }),
        ])
      ).start();

      Animated.timing(glowAnim, {
        toValue: 1,
        duration: 300,
        useNativeDriver: true,
      }).start();
    } else if (isThinking) {
      // Subtle breathing while thinking
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, {
            toValue: 1.03,
            duration: 1000,
            useNativeDriver: true,
          }),
          Animated.timing(pulseAnim, {
            toValue: 1,
            duration: 1000,
            useNativeDriver: true,
          }),
        ])
      ).start();

      ringScale.stopAnimation();
      outerRingOpacity.stopAnimation();
      Animated.timing(outerRingOpacity, {
        toValue: 0,
        duration: 200,
        useNativeDriver: true,
      }).start();

      Animated.timing(glowAnim, {
        toValue: 0.5,
        duration: 300,
        useNativeDriver: true,
      }).start();
    } else {
      // Reset all
      pulseAnim.stopAnimation();
      ringScale.stopAnimation();
      outerRingOpacity.stopAnimation();

      Animated.parallel([
        Animated.timing(pulseAnim, {
          toValue: 1,
          duration: 200,
          useNativeDriver: true,
        }),
        Animated.timing(glowAnim, {
          toValue: 0,
          duration: 200,
          useNativeDriver: true,
        }),
        Animated.timing(outerRingOpacity, {
          toValue: 0,
          duration: 200,
          useNativeDriver: true,
        }),
      ]).start();
    }
  }, [isListening, isThinking]);

  const handlePressIn = () => {
    if (disabled) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    onPressIn();
  };

  const handlePressOut = () => {
    if (disabled) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    onPressOut();
  };

  const buttonColor = isListening
    ? colors.error
    : isThinking
    ? colors.goldDark
    : colors.gold;

  const iconName = isListening
    ? "mic"
    : isThinking
    ? "ellipsis-horizontal"
    : "mic-outline";

  const glowBgColor = isListening
    ? `${colors.error}14`
    : `${colors.gold}14`;

  return (
    <View style={styles.container}>
      {/* Expanding ring (listening) */}
      <Animated.View
        style={[
          styles.outerRing,
          {
            opacity: outerRingOpacity,
            transform: [{ scale: ringScale }],
            borderColor: buttonColor,
          },
        ]}
      />

      {/* Glow ring */}
      <Animated.View
        style={[
          styles.glowRing,
          {
            opacity: glowAnim,
            transform: [{ scale: pulseAnim }],
            borderColor: buttonColor,
            backgroundColor: glowBgColor,
          },
        ]}
      />

      {/* Main button */}
      <Animated.View
        style={[
          styles.buttonWrapper,
          { transform: [{ scale: pulseAnim }] },
        ]}
      >
        <TouchableOpacity
          style={[
            styles.button,
            { backgroundColor: buttonColor },
            isListening && shadows.glow,
            !isListening && !isThinking && shadows.glow,
          ]}
          onPressIn={handlePressIn}
          onPressOut={handlePressOut}
          activeOpacity={0.8}
          disabled={disabled}
        >
          <Ionicons name={iconName} size={36} color={isListening ? "#FFFFFF" : colors.background} />
        </TouchableOpacity>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: "center",
    justifyContent: "center",
    width: 130,
    height: 130,
  },
  outerRing: {
    position: "absolute",
    width: 120,
    height: 120,
    borderRadius: 60,
    borderWidth: 2,
  },
  glowRing: {
    position: "absolute",
    width: 110,
    height: 110,
    borderRadius: 55,
    borderWidth: 2,
  },
  buttonWrapper: {
    width: 80,
    height: 80,
    borderRadius: 40,
  },
  button: {
    width: 80,
    height: 80,
    borderRadius: 40,
    alignItems: "center",
    justifyContent: "center",
  },
});

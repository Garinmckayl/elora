/**
 * Toast -- lightweight in-app notification banner
 *
 * Shows at the top of the screen, auto-dismisses after `duration` ms.
 * Supports: error (red), warning (amber), success (green), info (default).
 */

import React, { useEffect, useRef, useMemo } from "react";
import { Animated, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useTheme, borderRadius } from "../theme";

export type ToastType = "error" | "warning" | "success" | "info";

export interface ToastMessage {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number; // ms, default 4000
}

interface ToastProps {
  toast: ToastMessage;
  onDismiss: (id: string) => void;
}

function getTypeConfig(textSecondary: string): Record<ToastType, { icon: string; color: string; bg: string; border: string }> {
  return {
    error:   { icon: "alert-circle-outline",    color: "#FC8181", bg: "rgba(229,62,62,0.12)",   border: "rgba(229,62,62,0.3)" },
    warning: { icon: "warning-outline",         color: "#F6AD55", bg: "rgba(214,158,46,0.12)", border: "rgba(214,158,46,0.3)" },
    success: { icon: "checkmark-circle-outline",color: "#68D391", bg: "rgba(72,187,120,0.12)", border: "rgba(72,187,120,0.3)" },
    info:    { icon: "information-circle-outline",color: textSecondary, bg: "rgba(155,163,184,0.1)", border: "rgba(155,163,184,0.2)" },
  };
}

export function Toast({ toast, onDismiss }: ToastProps) {
  const { colors } = useTheme();
  const TYPE_CONFIG = useMemo(() => getTypeConfig(colors.textSecondary), [colors.textSecondary]);
  const cfg = TYPE_CONFIG[toast.type];
  const opacity = useRef(new Animated.Value(0)).current;
  const translateY = useRef(new Animated.Value(-20)).current;
  const duration = toast.duration ?? 4000;

  useEffect(() => {
    // Slide in
    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 250, useNativeDriver: true }),
      Animated.spring(translateY, { toValue: 0, tension: 80, friction: 10, useNativeDriver: true }),
    ]).start();

    // Auto-dismiss
    const timer = setTimeout(() => dismiss(), duration);
    return () => clearTimeout(timer);
  }, []);

  const dismiss = () => {
    Animated.parallel([
      Animated.timing(opacity, { toValue: 0, duration: 200, useNativeDriver: true }),
      Animated.timing(translateY, { toValue: -20, duration: 200, useNativeDriver: true }),
    ]).start(() => onDismiss(toast.id));
  };

  return (
    <Animated.View style={[
      styles.container,
      { backgroundColor: cfg.bg, borderColor: cfg.border, opacity, transform: [{ translateY }] },
    ]}>
      <Ionicons name={cfg.icon as any} size={18} color={cfg.color} style={styles.icon} />
      <View style={styles.textContainer}>
        <Text style={[styles.title, { color: cfg.color }]} numberOfLines={1}>{toast.title}</Text>
        {toast.message ? (
          <Text style={[styles.message, { color: colors.textSecondary }]} numberOfLines={2}>{toast.message}</Text>
        ) : null}
      </View>
      <TouchableOpacity onPress={dismiss} hitSlop={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <Ionicons name="close" size={16} color={colors.textTertiary} />
      </TouchableOpacity>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    borderRadius: borderRadius.md,
    paddingHorizontal: 14,
    paddingVertical: 10,
    marginHorizontal: 16,
    marginTop: 8,
    gap: 10,
  },
  icon: {
    flexShrink: 0,
  },
  textContainer: {
    flex: 1,
  },
  title: {
    fontSize: 13,
    fontWeight: "600",
  },
  message: {
    fontSize: 12,
    marginTop: 2,
    lineHeight: 16,
  },
});

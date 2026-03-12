/**
 * BrowserModal -- shows a live browser screenshot stream while Elora
 * executes a browser_task on the backend.
 *
 * Usage:
 *   <BrowserModal
 *     visible={isBrowsing}
 *     screenshotBase64={latestScreenshot}
 *     currentUrl={browserUrl}
 *     stepText={latestStep}
 *     onClose={() => setIsBrowsing(false)}
 *   />
 */

import React, { useEffect, useRef } from "react";
import {
  Modal,
  View,
  Text,
  Image,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  ScrollView,
  Animated,
  Platform,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "../theme";
import { Ionicons } from "@expo/vector-icons";

interface BrowserModalProps {
  visible: boolean;
  /** Base64-encoded PNG screenshot from the backend */
  screenshotBase64: string | null;
  /** URL shown in the browser address bar */
  currentUrl: string | null;
  /** Latest step/reasoning text from the computer-use model */
  stepText: string | null;
  onClose?: () => void;
}

export function BrowserModal({
  visible,
  screenshotBase64,
  currentUrl,
  stepText,
  onClose,
}: BrowserModalProps) {
  const { colors, isDark } = useTheme();
  const insets = useSafeAreaInsets();
  const pulseAnim = useRef(new Animated.Value(1)).current;

  // Pulse the dot to indicate live activity
  useEffect(() => {
    if (!visible) return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, { toValue: 0.3, duration: 700, useNativeDriver: true }),
        Animated.timing(pulseAnim, { toValue: 1, duration: 700, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [visible, pulseAnim]);

  const truncatedUrl = currentUrl
    ? currentUrl.length > 60
      ? currentUrl.slice(0, 57) + "..."
      : currentUrl
    : "Opening browser\u2026";

  const bgDark = isDark ? "#1A1816" : "#0F0D0B";
  const surfaceDark = isDark ? "#24201C" : "#1A1714";
  const borderSubtle = isDark ? "rgba(244,164,96,0.12)" : "rgba(244,164,96,0.15)";
  const textPrimary = isDark ? "#F5F0EB" : "#F0EBE5";
  const textSecondary = isDark ? "#B8B0A8" : "#9E9690";

  return (
    <Modal
      visible={visible}
      animationType="slide"
      transparent={false}
      statusBarTranslucent
      onRequestClose={onClose}
    >
      <View style={[styles.container, { backgroundColor: bgDark, paddingTop: insets.top + 8 }]}>
        {/* Header */}
        <View style={[styles.header, { borderBottomColor: borderSubtle }]}>
          <View style={styles.headerLeft}>
            <Animated.View style={[styles.liveDot, { opacity: pulseAnim, backgroundColor: colors.success || "#88C9A1" }]} />
            <Text style={[styles.headerTitle, { color: textPrimary }]}>Elora is browsing</Text>
          </View>
          {onClose && (
            <TouchableOpacity onPress={onClose} style={styles.closeButton} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
              <Ionicons name="close" size={20} color={textSecondary} />
            </TouchableOpacity>
          )}
        </View>

        {/* URL bar */}
        <View style={[styles.urlBar, { backgroundColor: surfaceDark, borderColor: borderSubtle }]}>
          <Ionicons name="globe-outline" size={14} color={colors.gold} style={{ marginRight: 6 }} />
          <Text style={[styles.urlText, { color: textSecondary }]} numberOfLines={1}>{truncatedUrl}</Text>
        </View>

        {/* Screenshot */}
        <View style={[styles.screenshotContainer, { borderColor: borderSubtle }]}>
          {screenshotBase64 ? (
            <Image
              source={{ uri: `data:image/png;base64,${screenshotBase64}` }}
              style={styles.screenshot}
              resizeMode="contain"
            />
          ) : (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color={colors.gold} />
              <Text style={[styles.loadingText, { color: textSecondary }]}>Starting browser\u2026</Text>
            </View>
          )}
        </View>

        {/* Step narration */}
        {stepText ? (
          <View style={[styles.stepContainer, { backgroundColor: surfaceDark, borderColor: borderSubtle }]}>
            <ScrollView style={styles.stepScroll} showsVerticalScrollIndicator={false}>
              <Text style={[styles.stepText, { color: textPrimary }]}>{stepText}</Text>
            </ScrollView>
          </View>
        ) : null}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
  },
  headerLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  liveDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  headerTitle: {
    fontSize: 16,
    fontWeight: "600",
    letterSpacing: 0.3,
  },
  closeButton: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  urlBar: {
    flexDirection: "row",
    alignItems: "center",
    marginHorizontal: 12,
    marginVertical: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 10,
    borderWidth: 1,
  },
  urlText: {
    flex: 1,
    fontSize: 12,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
  },
  screenshotContainer: {
    flex: 1,
    backgroundColor: "#000",
    marginHorizontal: 12,
    borderRadius: 12,
    overflow: "hidden",
    borderWidth: 1,
  },
  screenshot: {
    width: "100%",
    height: "100%",
  },
  loadingContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
  },
  loadingText: {
    fontSize: 14,
  },
  stepContainer: {
    marginHorizontal: 12,
    marginTop: 8,
    marginBottom: 16,
    borderRadius: 10,
    borderWidth: 1,
    maxHeight: 90,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  stepScroll: {
    flex: 1,
  },
  stepText: {
    fontSize: 12,
    lineHeight: 18,
  },
});

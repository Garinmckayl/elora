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
    : "Opening browser…";

  return (
    <Modal
      visible={visible}
      animationType="slide"
      transparent={false}
      statusBarTranslucent
      onRequestClose={onClose}
    >
      <View style={styles.container}>
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <Animated.View style={[styles.liveDot, { opacity: pulseAnim }]} />
            <Text style={styles.headerTitle}>Elora is browsing</Text>
          </View>
          {onClose && (
            <TouchableOpacity onPress={onClose} style={styles.closeButton} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
              <Text style={styles.closeText}>✕</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* URL bar */}
        <View style={styles.urlBar}>
          <Text style={styles.urlText} numberOfLines={1}>{truncatedUrl}</Text>
        </View>

        {/* Screenshot */}
        <View style={styles.screenshotContainer}>
          {screenshotBase64 ? (
            <Image
              source={{ uri: `data:image/png;base64,${screenshotBase64}` }}
              style={styles.screenshot}
              resizeMode="contain"
            />
          ) : (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color="#7C83FD" />
              <Text style={styles.loadingText}>Starting browser…</Text>
            </View>
          )}
        </View>

        {/* Step narration */}
        {stepText ? (
          <View style={styles.stepContainer}>
            <ScrollView style={styles.stepScroll} showsVerticalScrollIndicator={false}>
              <Text style={styles.stepText}>{stepText}</Text>
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
    backgroundColor: "#0A0E1A",
    paddingTop: Platform.OS === "ios" ? 50 : 30,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: "#1E2340",
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
    backgroundColor: "#48BB78",
  },
  headerTitle: {
    color: "#E8EAF0",
    fontSize: 16,
    fontWeight: "600",
    letterSpacing: 0.3,
  },
  closeButton: {
    padding: 4,
  },
  closeText: {
    color: "#9BA3B8",
    fontSize: 18,
    fontWeight: "400",
  },
  urlBar: {
    backgroundColor: "#141929",
    marginHorizontal: 12,
    marginVertical: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#2A3050",
  },
  urlText: {
    color: "#9BA3B8",
    fontSize: 12,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
  },
  screenshotContainer: {
    flex: 1,
    backgroundColor: "#000",
    marginHorizontal: 12,
    borderRadius: 8,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "#2A3050",
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
    color: "#9BA3B8",
    fontSize: 14,
  },
  stepContainer: {
    backgroundColor: "#141929",
    marginHorizontal: 12,
    marginTop: 8,
    marginBottom: 16,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#2A3050",
    maxHeight: 90,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  stepScroll: {
    flex: 1,
  },
  stepText: {
    color: "#C5CBE0",
    fontSize: 12,
    lineHeight: 18,
  },
});

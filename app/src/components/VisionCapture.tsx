/**
 * VisionCapture -- Camera component for Elora vision
 * Premium Warm/Elegant design
 */

import React, { useRef, useState, useMemo } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Modal,
  ActivityIndicator,
} from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { useTheme, borderRadius } from "../theme";

interface VisionCaptureProps {
  visible: boolean;
  onClose: () => void;
  onCapture: (base64Image: string) => void;
}

export default function VisionCapture({ visible, onClose, onCapture }: VisionCaptureProps) {
  const { colors, shadows } = useTheme();
  const styles = useMemo(() => createStyles(colors, shadows), [colors, shadows]);
  const [permission, requestPermission] = useCameraPermissions();
  const [isCapturing, setIsCapturing] = useState(false);
  const cameraRef = useRef<CameraView>(null);

  const handleCapture = async () => {
    if (!cameraRef.current || isCapturing) return;

    setIsCapturing(true);
    try {
      const photo = await cameraRef.current.takePictureAsync({
        base64: true,
        quality: 0.7,
        imageType: "jpg",
        shutterSound: false,
      });

      if (photo?.base64) {
        onCapture(photo.base64);
        onClose();
      }
    } catch (err) {
      console.error("[Vision] Capture error:", err);
    } finally {
      setIsCapturing(false);
    }
  };

  if (!permission?.granted) {
    return (
      <Modal visible={visible} animationType="slide">
        <LinearGradient
          colors={colors.gradientHero as [string, string, string]}
          style={styles.permissionContainer}
        >
          <LinearGradient
            colors={colors.gradientGold as [string, string]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={[styles.permissionIcon, shadows.glow]}
          >
            <Ionicons name="eye-outline" size={40} color={colors.background} />
          </LinearGradient>
          <Text style={styles.permissionTitle}>Camera Access</Text>
          <Text style={styles.permissionText}>
            Elora needs camera access to see what you're looking at and help you.
          </Text>
          <TouchableOpacity onPress={requestPermission} activeOpacity={0.8}>
            <LinearGradient
              colors={colors.gradientGold as [string, string]}
              style={styles.permissionButton}
            >
              <Text style={styles.permissionButtonText}>Enable Camera</Text>
            </LinearGradient>
          </TouchableOpacity>
          <TouchableOpacity style={styles.cancelButton} onPress={onClose}>
            <Text style={styles.cancelButtonText}>Not now</Text>
          </TouchableOpacity>
        </LinearGradient>
      </Modal>
    );
  }

  return (
    <Modal visible={visible} animationType="slide">
      <View style={styles.container}>
        <CameraView
          ref={cameraRef}
          style={styles.camera}
          facing="back"
        >
          {/* Top bar */}
          <View style={styles.topBar}>
            <TouchableOpacity onPress={onClose} style={styles.closeButton}>
              <View style={styles.closeButtonBg}>
                <Ionicons name="close" size={22} color="#FFFFFF" />
              </View>
            </TouchableOpacity>
            <View style={styles.topBarLabel}>
              <Ionicons name="scan-outline" size={16} color={colors.gold} />
              <Text style={styles.topBarText}>Point at anything</Text>
            </View>
            <View style={{ width: 44 }} />
          </View>

          {/* Capture button */}
          <View style={styles.bottomBar}>
            <TouchableOpacity
              style={[styles.captureButton, shadows.glow]}
              onPress={handleCapture}
              disabled={isCapturing}
            >
              {isCapturing ? (
                <ActivityIndicator size="large" color={colors.gold} />
              ) : (
                <LinearGradient
                  colors={colors.gradientGold as [string, string]}
                  style={styles.captureInner}
                >
                  <Ionicons name="scan" size={28} color={colors.background} />
                </LinearGradient>
              )}
            </TouchableOpacity>
          </View>
        </CameraView>
      </View>
    </Modal>
  );
}

function createStyles(colors: any, shadows: any) {
  return StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: "#000",
    },
    camera: {
      flex: 1,
      justifyContent: "space-between",
    },
    topBar: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      paddingTop: 60,
      paddingHorizontal: 16,
    },
    closeButton: {
      width: 44,
      height: 44,
      alignItems: "center",
      justifyContent: "center",
    },
    closeButtonBg: {
      width: 36,
      height: 36,
      borderRadius: 18,
      backgroundColor: "rgba(0,0,0,0.5)",
      alignItems: "center",
      justifyContent: "center",
    },
    topBarLabel: {
      flexDirection: "row",
      alignItems: "center",
      gap: 6,
      backgroundColor: "rgba(0,0,0,0.5)",
      paddingHorizontal: 14,
      paddingVertical: 8,
      borderRadius: borderRadius.full,
    },
    topBarText: {
      color: "#FFFFFF",
      fontSize: 14,
      fontWeight: "600",
    },
    bottomBar: {
      alignItems: "center",
      paddingBottom: 50,
    },
    captureButton: {
      width: 80,
      height: 80,
      borderRadius: 40,
      backgroundColor: `${colors.gold}33`,
      alignItems: "center",
      justifyContent: "center",
      borderWidth: 3,
      borderColor: colors.gold,
    },
    captureInner: {
      width: 60,
      height: 60,
      borderRadius: 30,
      alignItems: "center",
      justifyContent: "center",
    },
    permissionContainer: {
      flex: 1,
      alignItems: "center",
      justifyContent: "center",
      paddingHorizontal: 40,
    },
    permissionIcon: {
      width: 80,
      height: 80,
      borderRadius: 24,
      alignItems: "center",
      justifyContent: "center",
    },
    permissionTitle: {
      color: colors.textPrimary,
      fontSize: 26,
      fontWeight: "700",
      marginTop: 24,
    },
    permissionText: {
      color: colors.textSecondary,
      fontSize: 16,
      textAlign: "center",
      marginTop: 12,
      lineHeight: 24,
    },
    permissionButton: {
      paddingHorizontal: 32,
      paddingVertical: 14,
      borderRadius: borderRadius.full,
      marginTop: 28,
    },
    permissionButtonText: {
      color: colors.background,
      fontSize: 16,
      fontWeight: "700",
    },
    cancelButton: {
      marginTop: 16,
    },
    cancelButtonText: {
      color: colors.textSecondary,
      fontSize: 16,
    },
  });
}

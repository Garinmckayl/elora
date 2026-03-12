/**
 * AudioPlayer -- Inline audio playback for generated music/audio in chat
 *
 * Writes base64 audio to a temp file instead of using data URIs,
 * which fail on Android for large payloads.
 */

import React, { useState, useRef, useEffect, useMemo } from "react";
import { View, Text, TouchableOpacity, StyleSheet, Animated } from "react-native";
import { Audio } from "expo-av";
import { File, Paths } from "expo-file-system/next";
import { Ionicons } from "@expo/vector-icons";
import { borderRadius, useTheme, type ThemeColors } from "../theme";

interface AudioPlayerProps {
  audioBase64: string;
  mimeType?: string;
  caption?: string;
}

let _fileCounter = 0;

export default function AudioPlayer({ audioBase64, mimeType = "audio/wav", caption }: AudioPlayerProps) {
  const { colors, isDark } = useTheme();
  const dynamicStyles = useMemo(() => createDynamicStyles(colors, isDark), [colors, isDark]);
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [position, setPosition] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const soundRef = useRef<Audio.Sound | null>(null);
  const fileRef = useRef<File | null>(null);
  const progressAnim = useRef(new Animated.Value(0)).current;

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      soundRef.current?.unloadAsync().catch(() => {});
      try { fileRef.current?.delete(); } catch {}
    };
  }, []);

  const loadAndPlay = async () => {
    try {
      setIsLoading(true);
      setError(null);

      // If already loaded, toggle play/pause
      if (soundRef.current) {
        const status = await soundRef.current.getStatusAsync();
        if (status.isLoaded) {
          if (status.isPlaying) {
            await soundRef.current.pauseAsync();
            setIsPlaying(false);
          } else {
            await soundRef.current.playAsync();
            setIsPlaying(true);
          }
          setIsLoading(false);
          return;
        }
      }

      // Write base64 to a temp file (data URIs break on Android for large audio)
      const ext = mimeType.includes("wav") ? "wav" : mimeType.includes("mp4") ? "m4a" : "mp3";
      _fileCounter += 1;
      const file = new File(Paths.cache, `elora_audio_${_fileCounter}.${ext}`);
      // Decode base64 to bytes and write
      const binaryStr = atob(audioBase64);
      const bytes = new Uint8Array(binaryStr.length);
      for (let i = 0; i < binaryStr.length; i++) {
        bytes[i] = binaryStr.charCodeAt(i);
      }
      file.write(bytes);
      fileRef.current = file;

      // Set audio mode for playback
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: false,
        playsInSilentModeIOS: true,
        staysActiveInBackground: false,
      });

      // Load sound from file
      const { sound } = await Audio.Sound.createAsync(
        { uri: file.uri },
        { shouldPlay: true },
        (status) => {
          if (status.isLoaded) {
            setPosition(status.positionMillis);
            setDuration(status.durationMillis || 0);
            setIsPlaying(status.isPlaying);

            if (status.durationMillis && status.durationMillis > 0) {
              const progress = status.positionMillis / status.durationMillis;
              progressAnim.setValue(progress);
            }

            // Auto-stop at end
            if (status.didJustFinish) {
              setIsPlaying(false);
              setPosition(0);
              progressAnim.setValue(0);
            }
          }
        }
      );

      soundRef.current = sound;
      setIsPlaying(true);
    } catch (e: any) {
      console.warn("[AudioPlayer] Playback error:", e);
      setError("Playback failed");
    } finally {
      setIsLoading(false);
    }
  };

  const formatTime = (ms: number) => {
    const totalSec = Math.floor(ms / 1000);
    const min = Math.floor(totalSec / 60);
    const sec = totalSec % 60;
    return `${min}:${sec.toString().padStart(2, "0")}`;
  };

  return (
    <View style={staticStyles.container}>
      {caption && <Text style={[staticStyles.caption, { color: colors.textPrimary }]} numberOfLines={2}>{caption}</Text>}
      <View style={[staticStyles.playerRow, dynamicStyles.playerRow]}>
        <TouchableOpacity
          onPress={loadAndPlay}
          style={[staticStyles.playButton, { backgroundColor: colors.gold }]}
          activeOpacity={0.7}
        >
          <Ionicons
            name={isLoading ? "hourglass-outline" : isPlaying ? "pause" : "play"}
            size={22}
            color={colors.background}
          />
        </TouchableOpacity>
        <View style={staticStyles.progressContainer}>
          <View style={[staticStyles.progressTrack, dynamicStyles.progressTrack]}>
            <Animated.View
              style={[
                staticStyles.progressFill,
                {
                  backgroundColor: colors.gold,
                  width: progressAnim.interpolate({
                    inputRange: [0, 1],
                    outputRange: ["0%", "100%"],
                  }),
                },
              ]}
            />
          </View>
          <View style={staticStyles.timeRow}>
            <Text style={[staticStyles.timeText, { color: colors.textTertiary }]}>{formatTime(position)}</Text>
            {duration > 0 && <Text style={[staticStyles.timeText, { color: colors.textTertiary }]}>{formatTime(duration)}</Text>}
          </View>
        </View>
      </View>
      {error && <Text style={[staticStyles.errorText, { color: colors.error }]}>{error}</Text>}
    </View>
  );
}

function createDynamicStyles(colors: ThemeColors, isDark: boolean) {
  return StyleSheet.create({
    playerRow: {
      backgroundColor: `${colors.gold}18`,
      borderColor: `${colors.gold}33`,
    },
    progressTrack: {
      backgroundColor: isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.08)",
    },
  });
}

const staticStyles = StyleSheet.create({
  container: {
    marginTop: 6,
    gap: 6,
  },
  caption: {
    fontSize: 14,
    lineHeight: 20,
  },
  playerRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    padding: 10,
  },
  playButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  progressContainer: {
    flex: 1,
    gap: 4,
  },
  progressTrack: {
    height: 8,
    borderRadius: 4,
    overflow: "hidden",
  },
  progressFill: {
    height: "100%",
    borderRadius: 4,
  },
  timeRow: {
    flexDirection: "row",
    justifyContent: "space-between",
  },
  timeText: {
    fontSize: 10,
    fontVariant: ["tabular-nums"],
  },
  errorText: {
    fontSize: 11,
    textAlign: "center",
  },
});

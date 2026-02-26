/**
 * useVoice -- Audio recording for Elora
 *
 * Uses expo-audio (SDK 54+) for recording.
 * Records M4A (AAC) on Android, WAV on iOS.
 * Returns file URI + mime type for sending to backend.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { Platform } from "react-native";
import {
  useAudioRecorder,
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  IOSOutputFormat,
  AudioQuality,
} from "expo-audio";
import type { RecordingOptions, RecordingStatus } from "expo-audio";

// Android: use M4A/AAC (reliable, well-supported)
// iOS: use WAV/LPCM (best quality for Gemini)
const VOICE_RECORDING_OPTIONS: RecordingOptions = Platform.select({
  android: {
    extension: ".m4a",
    sampleRate: 16000,
    numberOfChannels: 1,
    bitRate: 128000,
    android: {
      outputFormat: "mpeg4",
      audioEncoder: "aac",
    },
    ios: {
      outputFormat: IOSOutputFormat.MPEG4AAC,
      audioQuality: AudioQuality.HIGH,
      linearPCMBitDepth: 16,
      linearPCMIsBigEndian: false,
      linearPCMIsFloat: false,
    },
    web: {
      mimeType: "audio/webm",
      bitsPerSecond: 128000,
    },
  },
  ios: {
    extension: ".wav",
    sampleRate: 16000,
    numberOfChannels: 1,
    bitRate: 256000,
    android: {
      outputFormat: "mpeg4",
      audioEncoder: "aac",
    },
    ios: {
      outputFormat: IOSOutputFormat.LINEARPCM,
      audioQuality: AudioQuality.HIGH,
      linearPCMBitDepth: 16,
      linearPCMIsBigEndian: false,
      linearPCMIsFloat: false,
    },
    web: {
      mimeType: "audio/webm",
      bitsPerSecond: 128000,
    },
  },
  default: RecordingPresets.HIGH_QUALITY,
})!;

/** Returns the MIME type for the recorded audio based on platform */
export function getRecordingMimeType(): string {
  return Platform.OS === "ios" ? "audio/wav" : "audio/mp4";
}

export function useVoice() {
  const [hasPermission, setHasPermission] = useState(false);

  // Promise resolver to wait for recording URL from status callback
  const uriResolverRef = useRef<((uri: string | null) => void) | null>(null);

  const onRecordingStatus = useCallback((status: RecordingStatus) => {
    console.log("[Voice] Status:", JSON.stringify(status));
    if (status.isFinished) {
      const url = status.url && status.url !== "null" ? status.url : null;
      if (url) {
        console.log("[Voice] Recording finished, url:", url);
      } else {
        console.warn("[Voice] Recording finished but no URL");
      }
      uriResolverRef.current?.(url);
      uriResolverRef.current = null;
    } else if (status.hasError) {
      console.error("[Voice] Recording error:", status.error);
      uriResolverRef.current?.(null);
      uriResolverRef.current = null;
    }
  }, []);

  const recorder = useAudioRecorder(VOICE_RECORDING_OPTIONS, onRecordingStatus);

  // Request mic permission on mount
  useEffect(() => {
    (async () => {
      const { granted } = await requestRecordingPermissionsAsync();
      setHasPermission(granted);

      await setAudioModeAsync({
        allowsRecording: true,
        playsInSilentMode: true,
        shouldPlayInBackground: false,
        interruptionMode: "duckOthers",
        shouldRouteThroughEarpiece: false,
      });
    })();
  }, []);

  const startRecording = useCallback(async () => {
    if (!hasPermission) {
      console.warn("[Voice] No mic permission");
      return;
    }

    try {
      // Must prepare before recording (allocates file, sets up encoder)
      await recorder.prepareToRecordAsync();
      recorder.record();
      console.log("[Voice] Recording started");
    } catch (err) {
      console.error("[Voice] Start recording error:", err);
    }
  }, [hasPermission, recorder]);

  const stopRecording = useCallback(async (): Promise<string | null> => {
    try {
      // Create a promise that resolves when the status callback fires with the URL
      const uriPromise = new Promise<string | null>((resolve) => {
        uriResolverRef.current = resolve;
        // Timeout after 5 seconds
        setTimeout(() => {
          if (uriResolverRef.current === resolve) {
            console.warn("[Voice] Timeout waiting for recording URL");
            uriResolverRef.current = null;
            // Last resort: try recorder.uri
            const fallback = recorder.uri && recorder.uri !== "null" ? recorder.uri : null;
            resolve(fallback);
          }
        }, 5000);
      });

      await recorder.stop();
      console.log("[Voice] Stop called, recorder.uri:", recorder.uri);

      // If recorder.uri is already set and valid, use it directly
      if (recorder.uri && recorder.uri !== "null" && recorder.uri.startsWith("file://")) {
        uriResolverRef.current = null;
        console.log("[Voice] Got URI from recorder:", recorder.uri);
        return recorder.uri;
      }

      // Otherwise wait for the status callback
      const uri = await uriPromise;
      console.log("[Voice] Got URI from callback:", uri);
      return uri;
    } catch (err) {
      console.error("[Voice] Stop recording error:", err);
      return null;
    }
  }, [recorder]);

  return {
    isRecording: recorder.isRecording,
    hasPermission,
    startRecording,
    stopRecording,
  };
}

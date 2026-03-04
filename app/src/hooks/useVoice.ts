/**
 * useVoice -- Audio recording for Elora
 *
 * Uses expo-av (works in both Expo Go and dev client).
 * Records M4A (AAC) on Android, WAV on iOS.
 * Returns file URI + mime type for sending to backend.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { Platform } from "react-native";
import { Audio } from "expo-av";

// Recording presets per platform
const RECORDING_OPTIONS_ANDROID: Audio.RecordingOptions = {
  ...Audio.RecordingOptionsPresets.HIGH_QUALITY,
  android: {
    extension: ".m4a",
    outputFormat: Audio.AndroidOutputFormat.MPEG_4,
    audioEncoder: Audio.AndroidAudioEncoder.AAC,
    sampleRate: 16000,
    numberOfChannels: 1,
    bitRate: 128000,
  },
  ios: {
    ...Audio.RecordingOptionsPresets.HIGH_QUALITY.ios,
    extension: ".m4a",
    sampleRate: 16000,
    numberOfChannels: 1,
    bitRate: 128000,
  },
  web: {
    mimeType: "audio/webm",
    bitsPerSecond: 128000,
  },
};

const RECORDING_OPTIONS_IOS: Audio.RecordingOptions = {
  ...Audio.RecordingOptionsPresets.HIGH_QUALITY,
  android: RECORDING_OPTIONS_ANDROID.android,
  ios: {
    extension: ".wav",
    outputFormat: Audio.IOSOutputFormat.LINEARPCM,
    audioQuality: Audio.IOSAudioQuality.HIGH,
    sampleRate: 16000,
    numberOfChannels: 1,
    bitRate: 256000,
    linearPCMBitDepth: 16,
    linearPCMIsBigEndian: false,
    linearPCMIsFloat: false,
  },
  web: {
    mimeType: "audio/webm",
    bitsPerSecond: 128000,
  },
};

const RECORDING_OPTIONS =
  Platform.OS === "ios" ? RECORDING_OPTIONS_IOS : RECORDING_OPTIONS_ANDROID;

/** Returns the MIME type for the recorded audio based on platform */
export function getRecordingMimeType(): string {
  return Platform.OS === "ios" ? "audio/wav" : "audio/mp4";
}

export function useVoice() {
  const [hasPermission, setHasPermission] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const recordingRef = useRef<Audio.Recording | null>(null);

  // Request mic permission on mount
  useEffect(() => {
    (async () => {
      try {
        const { granted } = await Audio.requestPermissionsAsync();
        setHasPermission(granted);

        await Audio.setAudioModeAsync({
          allowsRecordingIOS: true,
          playsInSilentModeIOS: true,
          staysActiveInBackground: false,
          shouldDuckAndroid: true,
        });
      } catch (e) {
        console.warn("[Voice] Permission/mode setup error:", e);
      }
    })();
  }, []);

  const startRecording = useCallback(async () => {
    if (!hasPermission) {
      console.warn("[Voice] No mic permission");
      return;
    }

    try {
      // Make sure audio mode allows recording
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      const recording = new Audio.Recording();
      await recording.prepareToRecordAsync(RECORDING_OPTIONS);
      await recording.startAsync();
      recordingRef.current = recording;
      setIsRecording(true);
      console.log("[Voice] Recording started");
    } catch (err) {
      console.error("[Voice] Start recording error:", err);
    }
  }, [hasPermission]);

  const stopRecording = useCallback(async (): Promise<string | null> => {
    const recording = recordingRef.current;
    if (!recording) {
      console.warn("[Voice] No active recording");
      return null;
    }

    try {
      await recording.stopAndUnloadAsync();
      const uri = recording.getURI();
      recordingRef.current = null;
      setIsRecording(false);

      // Reset audio mode for playback
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: false,
        playsInSilentModeIOS: true,
      });

      console.log("[Voice] Recording stopped, URI:", uri);
      return uri;
    } catch (err) {
      console.error("[Voice] Stop recording error:", err);
      recordingRef.current = null;
      setIsRecording(false);
      return null;
    }
  }, []);

  return {
    isRecording,
    hasPermission,
    startRecording,
    stopRecording,
  };
}

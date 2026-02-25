/**
 * useLiveAudioStream -- Continuous audio streaming for live calls
 *
 * Records short WAV chunks (~300ms) in a loop and sends them as
 * `audio_chunk` messages over the live WebSocket. Pauses when
 * Elora is speaking to avoid echo and enable natural barge-in.
 *
 * Uses expo-av (same approach as useWakeWord) to avoid conflicts
 * with the expo-audio recorder used by useVoice.
 */

import { useRef, useEffect } from "react";
import * as FileSystem from "expo-file-system/legacy";

const CHUNK_DURATION_MS = 300;

interface UseLiveAudioStreamOptions {
  /** Reference to the live WebSocket */
  wsRef: React.RefObject<WebSocket | null>;
  /** Whether Elora is currently speaking (pauses recording) */
  isSpeaking: boolean;
  /** Whether streaming is enabled (master switch) */
  enabled: boolean;
}

export function useLiveAudioStream({
  wsRef,
  isSpeaking,
  enabled,
}: UseLiveAudioStreamOptions) {
  const recordingRef = useRef(false);
  const isSpeakingRef = useRef(isSpeaking);

  // Keep speaking ref in sync without triggering re-renders
  useEffect(() => {
    isSpeakingRef.current = isSpeaking;
  }, [isSpeaking]);

  // Keep wsRef ref stable
  const wsRefStable = useRef(wsRef);
  useEffect(() => {
    wsRefStable.current = wsRef;
  }, [wsRef]);

  useEffect(() => {
    if (!enabled) {
      recordingRef.current = false;
      return;
    }

    // Already running
    if (recordingRef.current) return;

    let cancelled = false;

    const streamLoop = async () => {
      console.log("[AudioStream] streamLoop called, cancelled=", cancelled);

      // Lazy import expo-av
      let Audio: any;
      try {
        const av = await import("expo-av");
        Audio = av.Audio;
        console.log("[AudioStream] expo-av loaded");
      } catch (e) {
        console.warn("[AudioStream] expo-av not available:", e);
        return;
      }

      try {
        const { granted } = await Audio.requestPermissionsAsync();
        if (!granted) {
          console.warn("[AudioStream] Mic permission denied");
          return;
        }
        console.log("[AudioStream] Mic permission granted");
      } catch (e) {
        console.warn("[AudioStream] Permission request failed:", e);
        return;
      }

      try {
        await Audio.setAudioModeAsync({
          allowsRecordingIOS: true,
          playsInSilentModeIOS: true,
          staysActiveInBackground: false,
          shouldDuckAndroid: true,
          playThroughEarpieceAndroid: false,
        });
        console.log("[AudioStream] Audio mode set");
      } catch (e) {
        console.warn("[AudioStream] setAudioModeAsync failed:", e);
        // Continue anyway -- recording may still work
      }

      if (cancelled) {
        console.log("[AudioStream] Cancelled before loop start");
        return;
      }

      recordingRef.current = true;
      console.log("[AudioStream] Loop starting");

      while (recordingRef.current && !cancelled) {
        const ws = wsRefStable.current?.current;

        // Wait for WS to be open
        if (!ws || ws.readyState !== WebSocket.OPEN) {
          console.log("[AudioStream] Waiting for WS (state:", ws?.readyState, ")");
          await new Promise((r) => setTimeout(r, 300));
          continue;
        }

        // Pause while Elora is speaking
        if (isSpeakingRef.current) {
          await new Promise((r) => setTimeout(r, 100));
          continue;
        }

        let recording: any = null;
        try {
          console.log("[AudioStream] Recording chunk...");
          recording = new Audio.Recording();
          await recording.prepareToRecordAsync({
            android: {
              extension: ".wav",
              outputFormat: Audio.AndroidOutputFormat.DEFAULT,
              audioEncoder: Audio.AndroidAudioEncoder.DEFAULT,
              sampleRate: 16000,
              numberOfChannels: 1,
              bitRate: 256000,
            },
            ios: {
              extension: ".wav",
              outputFormat: Audio.IOSOutputFormat.LINEARPCM,
              audioQuality: Audio.IOSAudioQuality.LOW,
              sampleRate: 16000,
              numberOfChannels: 1,
              bitRate: 256000,
              linearPCMBitDepth: 16,
              linearPCMIsBigEndian: false,
              linearPCMIsFloat: false,
            },
            web: {},
          });
          await recording.startAsync();

          // Record for CHUNK_DURATION_MS
          await new Promise((r) => setTimeout(r, CHUNK_DURATION_MS));

          if (!recordingRef.current || cancelled) {
            try {
              await recording.stopAndUnloadAsync();
            } catch {}
            break;
          }

          await recording.stopAndUnloadAsync();
          const uri = recording.getURI();
          recording = null;
          console.log("[AudioStream] Chunk recorded, uri:", uri ? "ok" : "null");

          if (!uri) continue;

          // Read as base64 and send
          try {
            const b64 = await FileSystem.readAsStringAsync(uri, {
              encoding: "base64",
            });
            // Clean up temp file
            FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {});

            const currentWs = wsRefStable.current?.current;
            if (currentWs?.readyState === WebSocket.OPEN && b64 && b64.length > 50) {
              console.log(`[AudioStream] Sending chunk: ${b64.length} chars b64`);
              currentWs.send(
                JSON.stringify({
                  type: "audio_chunk",
                  content: b64,
                })
              );
            } else {
              console.warn(`[AudioStream] Skip chunk: ws=${currentWs?.readyState}, b64len=${b64?.length}`);
            }
          } catch (readErr) {
            console.warn("[AudioStream] File read failed:", readErr);
          }
        } catch (recErr) {
          console.warn("[AudioStream] Chunk error:", recErr);
          if (recording) {
            try {
              await recording.stopAndUnloadAsync();
            } catch {}
          }
          // Brief pause before retry
          await new Promise((r) => setTimeout(r, 500));
        }
      }

      recordingRef.current = false;
      console.log("[AudioStream] Loop stopped");
    };

    // Start after a short delay to let call_start settle
    console.log("[AudioStream] Effect fired, enabled=", enabled, "scheduling streamLoop in 500ms");
    const timer = setTimeout(() => {
      if (!cancelled) {
        console.log("[AudioStream] Timer fired, starting streamLoop");
        streamLoop();
      } else {
        console.log("[AudioStream] Timer fired but cancelled, skipping");
      }
    }, 500);

    return () => {
      console.log("[AudioStream] Cleanup: cancelling");
      cancelled = true;
      recordingRef.current = false;
      clearTimeout(timer);
    };
  }, [enabled]);

  return {
    isStreaming: recordingRef.current,
  };
}

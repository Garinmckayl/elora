/**
 * useWakeWord -- always-on "Hey Elora" detection
 *
 * Streams short audio clips from the mic to the backend wake-word WebSocket.
 * When the backend detects "Hey Elora" it sends {"type":"wake"} and we
 * fire the onWake callback so the app can start a full conversation turn.
 *
 * Approach: record 800ms clips in a loop using expo-av, encode as base64,
 * send as {"type":"audio_chunk","content":"...","mime_type":"audio/wav"}.
 * The backend decodes and feeds to Gemini Live's send_realtime_input.
 *
 * Battery notes:
 * - Only active when `enabled` is true
 * - Short clips at low quality = minimal CPU + bandwidth
 * - Reconnects automatically on disconnect
 */

import { useEffect, useRef, useCallback, useState } from "react";
import * as FileSystem from "expo-file-system/legacy";
import { WAKE_WS_URL, wsUrl } from "../config";

interface UseWakeWordOptions {
  userId?: string;
  token?: string | null;
  enabled?: boolean;
  onWake: () => void;
}

export function useWakeWord({
  userId = "anonymous",
  token = null,
  enabled = true,
  onWake,
}: UseWakeWordOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalRef = useRef(false);
  const recordingRef = useRef(false);
  const [isListening, setIsListening] = useState(false);
  const onWakeRef = useRef(onWake);
  const reconnectDelayRef = useRef(3000);  // exponential backoff
  const MAX_RECONNECT_DELAY = 60000;       // cap at 60s
  useEffect(() => { onWakeRef.current = onWake; }, [onWake]);

  // ── Connect to wake endpoint ─────────────────────────────────────────────
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const url = wsUrl(WAKE_WS_URL, userId, token);
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsListening(true);
      reconnectDelayRef.current = 3000;  // reset on successful connect
      console.log("[Wake] WS connected");
    };

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === "wake") {
          console.log("[Wake] Triggered!");
          onWakeRef.current();
        }
      } catch {}
    };

    ws.onerror = (err) => {
      console.log("[Wake] WS error");
      setIsListening(false);
    };

    ws.onclose = () => {
      setIsListening(false);
      if (!intentionalRef.current && enabled) {
        const delay = reconnectDelayRef.current;
        reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY);
        console.log(`[Wake] WS closed, reconnecting in ${delay / 1000}s...`);
        reconnectRef.current = setTimeout(connect, delay);
      }
    };
  }, [userId, token, enabled]);

  const disconnect = useCallback(() => {
    intentionalRef.current = true;
    if (reconnectRef.current) clearTimeout(reconnectRef.current);
    wsRef.current?.close();
    wsRef.current = null;
    setIsListening(false);
  }, []);

  // ── Continuous audio recording loop ────────────────────────────────────────
  // Record short ~800ms clips and send them as base64 audio_chunk messages.
  const streamLoop = useCallback(async () => {
    // Lazy import to avoid issues if expo-av isn't installed
    let Audio: any;
    try {
      const av = await import("expo-av");
      Audio = av.Audio;
    } catch (e) {
      console.warn("[Wake] expo-av not available, wake word disabled");
      return;
    }

    let granted = false;
    try {
      const perm = await Audio.requestPermissionsAsync();
      granted = perm.granted;
    } catch (permErr) {
      console.warn("[Wake] Permission request failed:", permErr);
      return;
    }
    if (!granted) {
      console.warn("[Wake] Mic permission denied");
      return;
    }

    try {
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
        staysActiveInBackground: true,
        // Use numeric values directly -- expo-av 16.x removed the
        // Audio.INTERRUPTION_MODE_* constants in favour of enums.
        // 1 = MixWithOthers (iOS), 1 = DoNotMix (Android)
        interruptionModeIOS: 1,
        shouldDuckAndroid: false,
        interruptionModeAndroid: 1,
        playThroughEarpieceAndroid: false,
      });
    } catch (modeErr) {
      console.warn("[Wake] Audio mode setup error (non-fatal):", modeErr);
    }

    recordingRef.current = true;
    console.log("[Wake] Audio stream loop starting");

    while (recordingRef.current) {
      // Wait for WS to be open
      if (wsRef.current?.readyState !== WebSocket.OPEN) {
        await new Promise(r => setTimeout(r, 500));
        continue;
      }

      let recording: any = null;
      try {
        // Record a short clip
        recording = new Audio.Recording();
        await recording.prepareToRecordAsync({
          android: {
            extension: ".wav",
            outputFormat: Audio.AndroidOutputFormat.DEFAULT,
            audioEncoder: Audio.AndroidAudioEncoder.DEFAULT,
            sampleRate: 16000,
            numberOfChannels: 1,
            bitRate: 32000,
          },
          ios: {
            extension: ".wav",
            outputFormat: Audio.IOSOutputFormat.LINEARPCM,
            audioQuality: Audio.IOSAudioQuality.LOW,
            sampleRate: 16000,
            numberOfChannels: 1,
            bitRate: 32000,
            linearPCMBitDepth: 16,
            linearPCMIsBigEndian: false,
            linearPCMIsFloat: false,
          },
          web: {},
        });
        await recording.startAsync();

        // Record for 800ms
        await new Promise(r => setTimeout(r, 800));

        if (!recordingRef.current) {
          try { await recording.stopAndUnloadAsync(); } catch {}
          break;
        }

        await recording.stopAndUnloadAsync();
        const uri = recording.getURI();
        recording = null;

        if (!uri) continue;

        // Read as base64 and send
        try {
          const b64 = await FileSystem.readAsStringAsync(uri, {
            encoding: FileSystem.EncodingType.Base64,
          });
          // Clean up temp file
          FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {});

          if (wsRef.current?.readyState === WebSocket.OPEN && b64) {
            wsRef.current.send(JSON.stringify({
              type: "audio_chunk",
              content: b64,
              mime_type: "audio/wav",
            }));
          }
        } catch (readErr) {
          console.warn("[Wake] File read error:", readErr);
        }

      } catch (recErr) {
        console.warn("[Wake] Recording error:", recErr);
        if (recording) {
          try { await recording.stopAndUnloadAsync(); } catch {}
        }
        await new Promise(r => setTimeout(r, 1000));
      }
    }

    console.log("[Wake] Audio stream loop stopped");
  }, []);

  // ── Lifecycle ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!enabled) {
      recordingRef.current = false;
      disconnect();
      return;
    }

    intentionalRef.current = false;
    connect();
    // Start audio stream after a short delay to let WS connect
    const startDelay = setTimeout(() => {
      if (recordingRef.current) return; // already running
      streamLoop().catch((err) => {
        console.warn("[Wake] Stream loop error:", err);
      });
    }, 1000);

    return () => {
      clearTimeout(startDelay);
      recordingRef.current = false;
      disconnect();
    };
  }, [enabled, connect, disconnect, streamLoop]);

  return { isListening };
}

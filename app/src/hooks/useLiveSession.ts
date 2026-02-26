/**
 * useLiveSession -- WebSocket connection to Elora Live API
 *
 * Handles bidirectional audio streaming:
 *   - Sends binary PCM/WAV audio to server
 *   - Receives binary PCM audio + JSON text from server
 *   - Buffers received audio and plays it back
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { Platform } from "react-native";
import { useAudioPlayer, setAudioModeAsync } from "expo-audio";
import { File, Paths } from "expo-file-system";
import { LIVE_WS_URL, wsUrl } from "../config";

export interface LiveMessage {
  type: "text" | "transcript" | "tool_call" | "status" | "browser_screenshot" | "browser_step" | "tool_result";
  content?: string;
  name?: string;
  args?: Record<string, any>;
  result?: Record<string, any>;
}

interface UseLiveSessionOptions {
  userId?: string;
  token?: string | null;
  onText?: (text: string) => void;
  onTranscript?: (transcript: string) => void;
  onToolCall?: (name: string, args: Record<string, any>) => void;
  onAudioStart?: () => void;
  onAudioEnd?: () => void;
  /** Called with a base64 PNG and the current URL when the browser takes a screenshot */
  onBrowserScreenshot?: (base64Png: string) => void;
  /** Called with reasoning text at each browser step */
  onBrowserStep?: (text: string) => void;
}

export function useLiveSession(options: UseLiveSessionOptions = {}) {
  const {
    userId = "anonymous",
    token = null,
    onText,
    onTranscript,
    onToolCall,
    onAudioStart,
    onAudioEnd,
    onBrowserScreenshot,
    onBrowserStep,
  } = options;

  const [isLiveConnected, setIsLiveConnected] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const audioChunksRef = useRef<Uint8Array[]>([]);
  const isPlayingRef = useRef(false);
  const audioFileCountRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalCloseRef = useRef(false);

  // Player for response audio
  const player = useAudioPlayer(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const url = wsUrl(LIVE_WS_URL, userId, token);
    console.log("[Live] Connecting to:", url);

    intentionalCloseRef.current = false;
    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      console.log("[Live] Connected");
      setIsLiveConnected(true);
      // Clear any pending reconnect timer
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };

    ws.onmessage = (event: MessageEvent) => {
      if (event.data instanceof ArrayBuffer) {
        // Binary = PCM audio response (24kHz, 16-bit, mono)
        const pcmBytes = new Uint8Array(event.data);
        audioChunksRef.current.push(pcmBytes);

        if (!isPlayingRef.current) {
          isPlayingRef.current = true;
          setIsSpeaking(true);
          onAudioStart?.();
          // Start playback after a small buffer (150ms worth = 7200 bytes at 48000 bytes/s)
          setTimeout(() => flushAudio(), 150);
        }
      } else {
        // Text JSON message
        try {
          const data: LiveMessage = JSON.parse(event.data);
          if (data.type === "text" && data.content) {
            onText?.(data.content);
          } else if (data.type === "transcript" && data.content) {
            onTranscript?.(data.content);
          } else if (data.type === "tool_call" && data.name) {
            onToolCall?.(data.name, data.args || {});
          } else if (data.type === "browser_screenshot" && data.content) {
            onBrowserScreenshot?.(data.content);
          } else if (data.type === "browser_step" && data.content) {
            onBrowserStep?.(data.content);
          } else if (data.type === "status") {
            console.log("[Live] Status:", data.content);
            if (data.content === "interrupted") {
              // Barge-in: Elora was interrupted — stop playback, clear buffer
              console.log("[Live] Barge-in: clearing audio buffer");
              audioChunksRef.current = [];
              if (isPlayingRef.current) {
                try { player.pause(); } catch {}
              }
              isPlayingRef.current = false;
              setIsSpeaking(false);
              onAudioEnd?.();
            } else if (data.content === "done" || data.content?.startsWith("error")) {
              // Response complete -- flush any remaining audio
              if (audioChunksRef.current.length > 0 && !isPlayingRef.current) {
                isPlayingRef.current = true;
                setIsSpeaking(true);
                flushAudio();
              } else if (!isPlayingRef.current) {
                onAudioEnd?.();
              }
            }
          }
        } catch (e) {
          console.warn("[Live] Parse error:", e);
        }
      }
    };

    ws.onerror = (e) => {
      console.error("[Live] WebSocket error:", e);
    };

    ws.onclose = (e) => {
      console.log("[Live] Disconnected:", e.code, e.reason);
      setIsLiveConnected(false);

      // Auto-reconnect unless we closed intentionally
      if (!intentionalCloseRef.current) {
        const delay = 3000;
        console.log(`[Live] Reconnecting in ${delay}ms...`);
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          connect();
        }, delay);
      }
    };

    wsRef.current = ws;
  }, [userId, token, onText, onTranscript, onToolCall, onAudioStart, onBrowserScreenshot, onBrowserStep]);

  const disconnect = useCallback(() => {
    intentionalCloseRef.current = true;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    wsRef.current?.close();
    wsRef.current = null;
    setIsLiveConnected(false);
  }, []);

  /**
   * Flush buffered PCM audio: create a WAV file from accumulated chunks and play it.
   */
  const flushAudio = useCallback(async () => {
    // Wait a bit more for chunks to accumulate
    await new Promise((r) => setTimeout(r, 300));

    const chunks = audioChunksRef.current;
    audioChunksRef.current = [];

    if (chunks.length === 0) {
      isPlayingRef.current = false;
      setIsSpeaking(false);
      onAudioEnd?.();
      return;
    }

    try {
      // Merge all PCM chunks
      const totalLength = chunks.reduce((sum, c) => sum + c.length, 0);
      const pcmData = new Uint8Array(totalLength);
      let offset = 0;
      for (const chunk of chunks) {
        pcmData.set(chunk, offset);
        offset += chunk.length;
      }

      // Create WAV header (24kHz, 16-bit, mono)
      const wavBuffer = createWavBuffer(pcmData, 24000, 1, 16);

      // Write to temp file
      const fileNum = audioFileCountRef.current++;
      const tempFile = new File(
        Paths.cache,
        `elora_response_${fileNum}.wav`
      );
      tempFile.write(wavBuffer);

      // Configure audio for playback (disable recording mode)
      await setAudioModeAsync({
        allowsRecording: false,
        playsInSilentMode: true,
        shouldPlayInBackground: false,
        interruptionMode: "duckOthers",
        shouldRouteThroughEarpiece: false,
      });

      // Play the audio
      player.replace(tempFile.uri);
      player.play();

      console.log(
        `[Live] Playing audio: ${pcmData.length} bytes PCM -> ${(pcmData.length / 48000).toFixed(1)}s`
      );

      // Wait for playback to finish, then check for more chunks
      const durationMs = (pcmData.length / 48000) * 1000; // 24kHz * 2 bytes = 48000 bytes/s
      setTimeout(async () => {
        // Re-enable recording mode
        await setAudioModeAsync({
          allowsRecording: true,
          playsInSilentMode: true,
          shouldPlayInBackground: false,
          interruptionMode: "duckOthers",
          shouldRouteThroughEarpiece: false,
        });

        // Check if more audio arrived while playing
        if (audioChunksRef.current.length > 0) {
          flushAudio();
        } else {
          isPlayingRef.current = false;
          setIsSpeaking(false);
          onAudioEnd?.();
        }

        // Cleanup temp file
        try {
          tempFile.delete();
        } catch {}
      }, durationMs + 100);
    } catch (err) {
      console.error("[Live] Audio playback error:", err);
      isPlayingRef.current = false;
      setIsSpeaking(false);
      onAudioEnd?.();
    }
  }, [player, onAudioEnd]);

  /**
   * Send recorded audio (WAV/M4A file) to the live session.
   * Reads the file as base64 and sends as JSON with mime type.
   */
  const sendAudioFile = useCallback(
    async (fileUri: string, mimeType: string = "audio/mp4") => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        console.warn("[Live] Not connected, can't send audio");
        return;
      }

      try {
        const audioFile = new File(fileUri);
        const b64 = await audioFile.base64();
        console.log(`[Live] Sending audio: ${b64.length} chars base64, mime: ${mimeType}`);
        wsRef.current.send(
          JSON.stringify({ type: "audio", content: b64, mime_type: mimeType })
        );
      } catch (err) {
        console.error("[Live] Send audio error:", err);
      }
    },
    []
  );

  /**
   * Send a text message through the live session.
   */
  const sendText = useCallback((text: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.warn("[Live] Not connected, can't send text");
      return;
    }
    wsRef.current.send(JSON.stringify({ type: "text", content: text }));
  }, []);

  /**
   * Start a call (persistent Gemini session).
   */
  const startCall = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.warn("[Live] Not connected, can't start call");
      return;
    }
    console.log("[Live] Starting call...");
    wsRef.current.send(JSON.stringify({ type: "call_start" }));
  }, []);

  /**
   * End a call.
   */
  const endCall = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    console.log("[Live] Ending call...");
    wsRef.current.send(JSON.stringify({ type: "call_end" }));
  }, []);

  /**
   * Send a single camera frame (base64 JPEG) to the live session.
   * Only sent if an active call session exists on the server side.
   * Frames are fire-and-forget ambient context — no reply expected.
   */
  const sendVideoFrame = useCallback((base64Jpeg: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(
      JSON.stringify({ type: "video_frame", content: base64Jpeg, mime_type: "image/jpeg" })
    );
  }, []);

  /**
   * Notify the server that the camera is now active or inactive.
   * This enables/disables proactive vision commentary on the backend.
   */
  const setCameraActive = useCallback((active: boolean) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: "camera_active", active }));
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      intentionalCloseRef.current = true;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      wsRef.current?.close();
    };
  }, []);

  return {
    isLiveConnected,
    isSpeaking,
    wsRef,
    connect,
    disconnect,
    sendAudioFile,
    sendText,
    startCall,
    endCall,
    sendVideoFrame,
    setCameraActive,
  };
}

/**
 * Create a WAV file buffer from raw PCM data.
 */
function createWavBuffer(
  pcmData: Uint8Array,
  sampleRate: number,
  numChannels: number,
  bitsPerSample: number
): Uint8Array {
  const byteRate = (sampleRate * numChannels * bitsPerSample) / 8;
  const blockAlign = (numChannels * bitsPerSample) / 8;
  const dataSize = pcmData.length;
  const headerSize = 44;
  const buffer = new Uint8Array(headerSize + dataSize);
  const view = new DataView(buffer.buffer);

  // RIFF header
  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeString(view, 8, "WAVE");

  // fmt chunk
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true); // chunk size
  view.setUint16(20, 1, true); // PCM format
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);

  // data chunk
  writeString(view, 36, "data");
  view.setUint32(40, dataSize, true);

  // PCM data
  buffer.set(pcmData, headerSize);

  return buffer;
}

function writeString(view: DataView, offset: number, str: string) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i));
  }
}

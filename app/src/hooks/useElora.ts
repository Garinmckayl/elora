/**
 * useElora -- main hook for interacting with the Elora agent
 */

import { useState, useEffect, useRef, useCallback } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import EloraWebSocket from "../services/websocket";
import { WS_URL } from "../config";

// Globally unique message ID generator
let _eloraSeq = 0;
function uid(prefix = "e"): string {
  return `${prefix}_${Date.now()}_${++_eloraSeq}`;
}

export interface Message {
  id: string;
  role: "user" | "elora";
  content: string;
  timestamp: Date;
  imageBase64?: string;
  // Audio content (e.g. from generate_music tool)
  audioBase64?: string;
  audioMimeType?: string;
  // Tool-use card fields
  toolName?: string;
  toolArgs?: Record<string, any>;
  toolResult?: Record<string, any>;
  subAgentName?: string;
  isThinking?: boolean;
  // Photo search results (attached to the message when search completes)
  photoUris?: string[];
}

interface UseEloraOptions {
  serverUrl?: string;
  userId?: string;
  token?: string | null;
  onBrowserScreenshot?: (base64Png: string) => void;
  onBrowserStep?: (text: string) => void;
  onBrowserStart?: () => void;
  /** Called when Elora requests a photo search for a person */
  onPhotoSearchRequest?: (personName: string) => void;
}

export function useElora(options: UseEloraOptions = {}) {
  const {
    serverUrl = WS_URL,
    userId = "anonymous",
    token = null,
    onBrowserScreenshot,
    onBrowserStep,
    onBrowserStart,
    onPhotoSearchRequest,
  } = options;

  const [messages, setMessages] = useState<Message[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const wsRef = useRef<EloraWebSocket | null>(null);
  const messagesLoadedRef = useRef(false);

  // Storage key scoped to the user
  const storageKey = `elora_messages_${userId}`;

  // Load persisted messages on mount
  useEffect(() => {
    AsyncStorage.getItem(storageKey).then((json) => {
      if (json) {
        try {
          const parsed: Message[] = JSON.parse(json).map((m: any) => ({
            ...m,
            timestamp: new Date(m.timestamp),
          }));
          // Only load the most recent 100 messages to avoid memory issues
          setMessages(parsed.slice(-100));
        } catch (e) {
          console.warn("[Chat] Failed to parse saved messages:", e);
        }
      }
      messagesLoadedRef.current = true;
    });
  }, [storageKey]);

  // Persist messages when they change (debounced to avoid excessive writes)
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!messagesLoadedRef.current) return; // Don't save during initial load
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    saveTimeoutRef.current = setTimeout(() => {
      // Save last 100 messages
      const toSave = messages.slice(-100);
      AsyncStorage.setItem(storageKey, JSON.stringify(toSave)).catch((e) =>
        console.warn("[Chat] Failed to save messages:", e)
      );
    }, 500);
  }, [messages, storageKey]);

  const onBrowserScreenshotRef = useRef(onBrowserScreenshot);
  const onBrowserStepRef = useRef(onBrowserStep);
  const onBrowserStartRef = useRef(onBrowserStart);
  const onPhotoSearchRequestRef = useRef(onPhotoSearchRequest);
  useEffect(() => { onBrowserScreenshotRef.current = onBrowserScreenshot; }, [onBrowserScreenshot]);
  useEffect(() => { onBrowserStepRef.current = onBrowserStep; }, [onBrowserStep]);
  useEffect(() => { onBrowserStartRef.current = onBrowserStart; }, [onBrowserStart]);
  useEffect(() => { onPhotoSearchRequestRef.current = onPhotoSearchRequest; }, [onPhotoSearchRequest]);

  // Only reconnect when serverUrl or userId changes — NOT when token changes.
  // The token is only used to build the initial WS URL; once connected the
  // session is established. Reconnecting on token change wipes messages.
  useEffect(() => {
    const ws = new EloraWebSocket(serverUrl, userId, token);
    wsRef.current = ws;

    ws.connect(
      // onMessage
      (data) => {
        if (data.type === "text" && data.content) {
          const msg: Message = {
            id: uid("txt"),
            role: "elora",
            content: data.content,
            timestamp: new Date(),
          };
          setMessages((prev) => [...prev, msg]);
          setIsThinking(false);
        } else if (data.type === "tool_call" && data.name) {
          const msg: Message = {
            id: uid("tool"),
            role: "elora",
            content: "",
            toolName: data.name,
            toolArgs: data.args || {},
            isThinking: true,
            timestamp: new Date(),
          };
          setMessages((prev) => [...prev, msg]);
        } else if (data.type === "tool_result" && data.name) {
          // Check if this is a photo search request signal
          if (data.name === "request_photo_search" && data.result?.photo_search_request) {
            const personName = data.result?.person_name ?? "";
            if (personName) {
              onPhotoSearchRequestRef.current?.(personName);
            }
          }
          // Check if this is a music generation result with audio data (legacy path)
          if (
            (data.name === "generate_music" || data.name === "generate_audio") &&
            data.result?.audio_base64
          ) {
            const audioMsg: Message = {
              id: uid("audio"),
              role: "elora",
              content: data.result?.report || "Generated audio",
              audioBase64: data.result.audio_base64,
              audioMimeType: data.result.mime_type || "audio/wav",
              timestamp: new Date(),
            };
            setMessages((prev) => [...prev, audioMsg]);
          }
          setMessages((prev) =>
            prev.map((m) => {
              if (m.toolName === data.name && m.isThinking) {
                return {
                  ...m,
                  isThinking: false,
                  toolResult: data.result,
                };
              }
              return m;
            })
          );
        } else if (data.type === "audio_result" && data.audio_base64) {
          // Dedicated audio message from backend (avoids huge tool_result frames)
          const audioMsg: Message = {
            id: uid("audio"),
            role: "elora",
            content: data.report || "Generated audio",
            audioBase64: data.audio_base64,
            audioMimeType: data.mime_type || "audio/wav",
            timestamp: new Date(),
          };
          setMessages((prev) => [...prev, audioMsg]);
        } else if (data.type === "image_result" && data.image_base64) {
          // Dedicated image message from backend
          const imageMsg: Message = {
            id: uid("img"),
            role: "elora",
            content: data.report || "Generated image",
            imageBase64: data.image_base64,
            timestamp: new Date(),
          };
          setMessages((prev) => [...prev, imageMsg]);
        } else if (data.type === "browser_screenshot" && data.content) {
          onBrowserScreenshotRef.current?.(data.content);
        } else if (data.type === "browser_step" && data.content) {
          onBrowserStepRef.current?.(data.content);
        } else if (data.type === "status" && data.content === "browser_starting") {
          onBrowserStartRef.current?.();
        }
      },
      // onStatusChange
      (status) => {
        setIsConnected(status === "connected");
      }
    );

    return () => {
      ws.disconnect();
    };
  // Intentionally excludes `token` — token changes must NOT reset the connection or messages
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverUrl, userId]);

  const sendMessage = useCallback(
    (text: string) => {
      if (!text.trim()) return;

      const msg: Message = {
        id: uid("msg"),
        role: "user",
        content: text,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, msg]);
      setIsThinking(true);

      wsRef.current?.sendText(text);
    },
    []
  );

  const sendImage = useCallback((base64: string) => {
    const msg: Message = {
      id: uid("msg"),
      role: "user",
      content: "[Image]",
      timestamp: new Date(),
      imageBase64: base64,
    };
    setMessages((prev) => [...prev, msg]);
    setIsThinking(true);
    wsRef.current?.sendImage(base64);
  }, []);

  const addMessage = useCallback((msg: Message) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    AsyncStorage.removeItem(storageKey).catch(() => {});
  }, [storageKey]);

  /** After a photo search completes on-device, send results back to Elora as a text message */
  const sendPhotoSearchResults = useCallback(
    (personName: string, photoUris: string[]) => {
      const count = photoUris.length;
      const resultText =
        count === 0
          ? `I searched your camera roll for photos of ${personName} but didn't find any matches.`
          : `I found ${count} photo${count === 1 ? "" : "s"} of ${personName} in your camera roll.`;

      // Add the result as a message with attached photo URIs for the UI grid
      const msg: Message = {
        id: uid("msg"),
        role: "elora",
        content: resultText,
        timestamp: new Date(),
        photoUris: photoUris.slice(0, 20), // cap at 20 for display
      };
      setMessages((prev) => [...prev, msg]);

      // Also send result back to agent so it can respond naturally
      wsRef.current?.sendText(
        `[Photo search complete] Found ${count} photo(s) of ${personName} in the camera roll.`
      );
    },
    []
  );

  return {
    messages,
    isConnected,
    isThinking,
    setIsThinking,
    sendMessage,
    sendImage,
    addMessage,
    clearMessages,
    sendPhotoSearchResults,
  };
}

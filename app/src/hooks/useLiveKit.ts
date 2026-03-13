/**
 * useLiveKit -- LiveKit-powered voice sessions for Elora
 *
 * In Expo Go, Metro replaces livekit-client and @livekit/react-native with
 * empty shims (see metro.config.js), so all imports resolve safely.
 * In dev client builds, the real native modules are used.
 */

import { useRef, useState, useCallback, useEffect } from "react";
import { BACKEND_URL } from "../config";

// Lazy-load livekit-client to avoid crash if native WebRTC module is missing
let Room: any = null;
let RoomEvent: any = null;
let Track: any = null;
let ConnectionState: any = null;
try {
  const lk = require("livekit-client");
  Room = lk.Room;
  RoomEvent = lk.RoomEvent;
  Track = lk.Track;
  ConnectionState = lk.ConnectionState;
} catch (e) {
  console.warn("[LiveKit] livekit-client not available:", e);
}

// AudioSession -- shimmed to no-ops in Expo Go via metro.config.js
let _AudioSession: any = null;
try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  _AudioSession = require("@livekit/react-native").AudioSession;
} catch {
  // shim doesn't have it or something went wrong
}

interface UseLiveKitOptions {
  userId: string;
  token?: string | null;
  onText?: (text: string) => void;
  onTranscript?: (transcript: string) => void;
  onToolCall?: (name: string, args: Record<string, any>) => void;
  onAudioEnd?: () => void;
}

export function useLiveKit({
  userId,
  token,
  onText,
  onTranscript,
  onToolCall,
  onAudioEnd,
}: UseLiveKitOptions) {
  const roomRef = useRef<any>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [inCall, setInCall] = useState(false);
  const connectingRef = useRef(false);

  const onTextRef = useRef(onText);
  const onTranscriptRef = useRef(onTranscript);
  const onToolCallRef = useRef(onToolCall);
  const onAudioEndRef = useRef(onAudioEnd);

  useEffect(() => { onTextRef.current = onText; }, [onText]);
  useEffect(() => { onTranscriptRef.current = onTranscript; }, [onTranscript]);
  useEffect(() => { onToolCallRef.current = onToolCall; }, [onToolCall]);
  useEffect(() => { onAudioEndRef.current = onAudioEnd; }, [onAudioEnd]);

  const connect = useCallback(async () => {
    // Room is shimmed to an empty function in Expo Go -- guard against it
    if (!Room || typeof Room !== "function" || !RoomEvent?.Connected) {
      console.warn("[LiveKit] LiveKit not available (Expo Go shim). Voice calls require a dev client build.");
      return;
    }

    if (roomRef.current?.state === ConnectionState.Connected) {
      console.log("[LiveKit] Already connected");
      return;
    }
    if (connectingRef.current) return;

    connectingRef.current = true;

    try {
      if (_AudioSession?.configureAudio) {
        await _AudioSession.configureAudio({
          android: {
            audioTypeOptions: {
              manageAudioFocus: true,
              audioMode: "inCommunication",
              audioFocusMode: "gain",
              audioStreamType: "voiceCall",
              audioAttributesUsageType: "voiceCommunication",
              audioAttributesContentType: "speech",
            },
          },
          ios: { defaultOutput: "speaker" },
        });
        await _AudioSession.startAudioSession();
        console.log("[LiveKit] AudioSession started");
      }

      const params = new URLSearchParams({ user_id: userId });
      if (token) params.set("token", token);

      const res = await fetch(`${BACKEND_URL}/livekit/token?${params}`, { method: "POST" });
      const data = await res.json();

      const tokenData = Array.isArray(data) ? data[0] : data;
      if (tokenData.error || !res.ok) {
        console.error("[LiveKit] Token error:", tokenData.error || `HTTP ${res.status}`);
        if (_AudioSession?.stopAudioSession) await _AudioSession.stopAudioSession().catch(() => {});
        return;
      }

      console.log("[LiveKit] Got token for room:", tokenData.room);

      const room = new Room({ adaptiveStream: true, dynacast: true });

      room.on(RoomEvent.Connected, () => {
        console.log("[LiveKit] Connected to room");
        setIsConnected(true);
      });

      room.on(RoomEvent.Disconnected, () => {
        setIsConnected(false);
        setInCall(false);
        setIsSpeaking(false);
      });

      room.on(RoomEvent.DataReceived, (payload: Uint8Array) => {
        try {
          const msg = JSON.parse(new TextDecoder().decode(payload));
          if (msg.type === "transcript") onTranscriptRef.current?.(msg.content);
          else if (msg.type === "tool_call") onToolCallRef.current?.(msg.name, msg.args || {});
          else if (msg.type === "text") onTextRef.current?.(msg.content);
        } catch { /* ignore non-JSON */ }
      });

      room.on(RoomEvent.TrackUnsubscribed, (track: any) => {
        if (track.kind === Track.Kind?.Audio) setIsSpeaking(false);
      });

      room.on(RoomEvent.ActiveSpeakersChanged, (speakers: any[]) => {
        setIsSpeaking(speakers.some((s: any) => s.isAgent));
      });

      room.on(RoomEvent.TranscriptionReceived, (segments: any[], participant: any) => {
        if (!segments?.length) return;
        for (const seg of segments) {
          if (!seg.text || !seg.final) continue;
          if (participant?.isAgent) onTextRef.current?.(seg.text);
          else onTranscriptRef.current?.(seg.text);
        }
      });

      await room.connect(tokenData.url, tokenData.token);
      roomRef.current = room;
      console.log("[LiveKit] Room connected");
    } catch (e) {
      console.error("[LiveKit] Connection error:", e);
    } finally {
      connectingRef.current = false;
    }
  }, [userId, token]);

  const startCall = useCallback(async () => {
    if (!Room || typeof Room !== "function" || !RoomEvent?.Connected) return;

    const room = roomRef.current;
    if (!room || room.state !== ConnectionState.Connected) {
      await connect();
      await new Promise(r => setTimeout(r, 500));
    }

    const currentRoom = roomRef.current;
    if (!currentRoom || currentRoom.state !== ConnectionState.Connected) return;

    try {
      await currentRoom.localParticipant.setMicrophoneEnabled(true);
      setInCall(true);
      console.log("[LiveKit] Call started");
    } catch (e) {
      console.error("[LiveKit] Failed to start call:", e);
    }
  }, [connect]);

  const endCall = useCallback(async () => {
    try {
      await roomRef.current?.localParticipant?.setMicrophoneEnabled(false);
      await roomRef.current?.localParticipant?.setCameraEnabled(false);
    } catch { /* ignore */ }
    setInCall(false);
    setIsSpeaking(false);
    onAudioEndRef.current?.();
  }, []);

  const toggleCamera = useCallback(async (enabled: boolean) => {
    try { await roomRef.current?.localParticipant?.setCameraEnabled(enabled); } catch { /* */ }
  }, []);

  const toggleMute = useCallback(async (muted: boolean) => {
    try { await roomRef.current?.localParticipant?.setMicrophoneEnabled(!muted); } catch { /* */ }
  }, []);

  const disconnect = useCallback(async () => {
    roomRef.current?.disconnect();
    roomRef.current = null;
    setIsConnected(false);
    setInCall(false);
    setIsSpeaking(false);
    if (_AudioSession?.stopAudioSession) {
      await _AudioSession.stopAudioSession().catch(() => {});
    }
  }, []);

  useEffect(() => {
    return () => {
      roomRef.current?.disconnect();
      _AudioSession?.stopAudioSession?.().catch(() => {});
    };
  }, []);

  return {
    isConnected,
    isSpeaking,
    inCall,
    connect,
    startCall,
    endCall,
    toggleCamera,
    toggleMute,
    disconnect,
    roomRef,
  };
}

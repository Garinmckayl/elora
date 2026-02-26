/**
 * useLiveKit -- LiveKit-powered voice sessions for Elora
 *
 * Replaces useLiveSession + useLiveAudioStream with a single hook
 * that uses LiveKit's React Native SDK for WebRTC-based voice calls.
 *
 * The app fetches a room token from the backend, connects to LiveKit,
 * and the LiveKit agent (livekit_agent.py) handles Gemini Live, tools,
 * interruptions, and audio transport automatically.
 */

import { useRef, useState, useCallback, useEffect } from "react";
import {
  Room,
  RoomEvent,
  Track,
  RemoteTrack,
  RemoteTrackPublication,
  RemoteParticipant,
  Participant,
  ConnectionState,
} from "livekit-client";
import { BACKEND_URL } from "../config";

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
  const roomRef = useRef<Room | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [inCall, setInCall] = useState(false);
  const connectingRef = useRef(false);

  // Callbacks refs to avoid stale closures
  const onTextRef = useRef(onText);
  const onTranscriptRef = useRef(onTranscript);
  const onToolCallRef = useRef(onToolCall);
  const onAudioEndRef = useRef(onAudioEnd);

  useEffect(() => { onTextRef.current = onText; }, [onText]);
  useEffect(() => { onTranscriptRef.current = onTranscript; }, [onTranscript]);
  useEffect(() => { onToolCallRef.current = onToolCall; }, [onToolCall]);
  useEffect(() => { onAudioEndRef.current = onAudioEnd; }, [onAudioEnd]);

  /**
   * Fetch a room token from the backend and connect to LiveKit.
   */
  const connect = useCallback(async () => {
    if (roomRef.current?.state === ConnectionState.Connected) {
      console.log("[LiveKit] Already connected");
      return;
    }
    if (connectingRef.current) {
      console.log("[LiveKit] Connection already in progress");
      return;
    }

    connectingRef.current = true;

    try {
      // Fetch token from backend
      const params = new URLSearchParams({ user_id: userId });
      if (token) params.set("token", token);

      console.log("[LiveKit] Fetching token from:", `${BACKEND_URL}/livekit/token`);
      const res = await fetch(`${BACKEND_URL}/livekit/token?${params}`, {
        method: "POST",
      });
      const data = await res.json();

      if (data.error) {
        console.error("[LiveKit] Token error:", data.error);
        return;
      }

      console.log("[LiveKit] Got token for room:", data.room, "url:", data.url);

      // Create and connect to room
      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
      });

      // Wire up events
      room.on(RoomEvent.Connected, () => {
        console.log("[LiveKit] Connected to room");
        setIsConnected(true);
      });

      room.on(RoomEvent.Disconnected, (reason) => {
        console.log("[LiveKit] Disconnected, reason:", reason);
        setIsConnected(false);
        setInCall(false);
        setIsSpeaking(false);
      });

      room.on(RoomEvent.ParticipantConnected, (participant) => {
        console.log("[LiveKit] Participant joined:", participant.identity, "isAgent:", participant.isAgent);
      });

      room.on(RoomEvent.ParticipantDisconnected, (participant) => {
        console.log("[LiveKit] Participant left:", participant.identity);
      });

      // Handle data messages from the agent (transcripts, tool calls, etc.)
      room.on(RoomEvent.DataReceived, (payload: Uint8Array, participant, kind, topic) => {
        try {
          const text = new TextDecoder().decode(payload);
          console.log("[LiveKit] DataReceived topic:", topic, "text:", text.substring(0, 100));
          const msg = JSON.parse(text);

          if (msg.type === "transcript" && onTranscriptRef.current) {
            onTranscriptRef.current(msg.content);
          } else if (msg.type === "tool_call" && onToolCallRef.current) {
            onToolCallRef.current(msg.name, msg.args || {});
          } else if (msg.type === "text" && onTextRef.current) {
            onTextRef.current(msg.content);
          }
        } catch (e) {
          // Not JSON or not a message we care about
        }
      });

      // Track agent speaking state via audio track activity
      room.on(RoomEvent.TrackSubscribed, (
        track: RemoteTrack,
        publication: RemoteTrackPublication,
        participant: RemoteParticipant,
      ) => {
        console.log("[LiveKit] TrackSubscribed:", track.kind, "from:", participant.identity, "isAgent:", participant.isAgent);
        // Don't set isSpeaking here -- the track being subscribed doesn't mean audio is playing.
        // isSpeaking is driven by ActiveSpeakersChanged or TranscriptionReceived below.
      });

      room.on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack, publication, participant) => {
        console.log("[LiveKit] TrackUnsubscribed:", track.kind);
        if (track.kind === Track.Kind.Audio) {
          setIsSpeaking(false);
        }
      });

      // Use ActiveSpeakersChanged to detect when the agent is actually speaking
      room.on(RoomEvent.ActiveSpeakersChanged, (speakers: Participant[]) => {
        const agentSpeaking = speakers.some((s) => s.isAgent);
        setIsSpeaking(agentSpeaking);
      });

      // Handle agent transcription events (agent's spoken text as transcriptions)
      // LiveKit agents send TranscriptionReceived events with the text the agent spoke.
      // Segments arrive incrementally; we emit completed text on `final` segments.
      room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
        console.log("[LiveKit] TranscriptionReceived:", segments?.length, "segments, from:", participant?.identity, "isAgent:", participant?.isAgent);
        if (!segments || segments.length === 0) return;

        for (const seg of segments) {
          console.log("[LiveKit] Segment:", JSON.stringify({ id: seg.id, text: seg.text?.substring(0, 50), final: seg.final, firstReceivedTime: seg.firstReceivedTime }));
          if (seg.text) {
            if (participant?.isAgent) {
              // Agent transcription -- this is what Elora said
              if (seg.final) {
                onTextRef.current?.(seg.text);
              }
            } else {
              // User transcription (STT of the user's speech)
              if (seg.final) {
                onTranscriptRef.current?.(seg.text);
              }
            }
          }
        }
      });

      // Log all room events for debugging
      room.on(RoomEvent.RoomMetadataChanged, (metadata) => {
        console.log("[LiveKit] Room metadata changed:", metadata);
      });

      room.on(RoomEvent.ConnectionStateChanged, (state) => {
        console.log("[LiveKit] ConnectionStateChanged:", state);
      });

      // Connect to the room
      console.log("[LiveKit] Connecting to room...");
      await room.connect(data.url, data.token);
      roomRef.current = room;
      console.log("[LiveKit] Room connected, state:", room.state);
      console.log("[LiveKit] Local participant:", room.localParticipant.identity);
      console.log("[LiveKit] Remote participants:", room.remoteParticipants.size);

    } catch (e) {
      console.error("[LiveKit] Connection error:", e, JSON.stringify(e));
    } finally {
      connectingRef.current = false;
    }
  }, [userId, token]);

  /**
   * Start a voice call -- publish microphone track
   */
  const startCall = useCallback(async () => {
    const room = roomRef.current;
    console.log("[LiveKit] startCall -- room state:", room?.state);
    
    if (!room || room.state !== ConnectionState.Connected) {
      console.log("[LiveKit] Not connected, connecting first...");
      await connect();
      // Wait a bit for the connection to establish
      await new Promise(resolve => setTimeout(resolve, 500));
    }

    const currentRoom = roomRef.current;
    if (!currentRoom || currentRoom.state !== ConnectionState.Connected) {
      console.error("[LiveKit] Still not connected after connect() -- cannot start call");
      return;
    }

    try {
      console.log("[LiveKit] Enabling mic...");
      await currentRoom.localParticipant.setMicrophoneEnabled(true);
      setInCall(true);
      console.log("[LiveKit] Call started -- mic enabled");
      console.log("[LiveKit] Remote participants:", currentRoom.remoteParticipants.size);
      
      // Log all remote participants
      for (const [id, p] of currentRoom.remoteParticipants) {
        console.log("[LiveKit] Remote participant:", id, "identity:", p.identity, "isAgent:", p.isAgent);
      }
    } catch (e) {
      console.error("[LiveKit] Failed to start call:", e, JSON.stringify(e));
    }
  }, [connect]);

  /**
   * End the call -- mute mic and optionally disconnect
   */
  const endCall = useCallback(async () => {
    try {
      await roomRef.current?.localParticipant.setMicrophoneEnabled(false);
      // Also disable camera if it was on
      await roomRef.current?.localParticipant.setCameraEnabled(false);
    } catch (e) {
      console.warn("[LiveKit] End call error:", e);
    }
    setInCall(false);
    setIsSpeaking(false);
    onAudioEndRef.current?.();
    console.log("[LiveKit] Call ended");
  }, []);

  /**
   * Toggle camera for proactive vision
   */
  const toggleCamera = useCallback(async (enabled: boolean) => {
    try {
      await roomRef.current?.localParticipant.setCameraEnabled(enabled);
      console.log("[LiveKit] Camera:", enabled ? "on" : "off");
    } catch (e) {
      console.warn("[LiveKit] Camera toggle error:", e);
    }
  }, []);

  /**
   * Toggle microphone mute
   */
  const toggleMute = useCallback(async (muted: boolean) => {
    try {
      await roomRef.current?.localParticipant.setMicrophoneEnabled(!muted);
      console.log("[LiveKit] Mic:", muted ? "muted" : "unmuted");
    } catch (e) {
      console.warn("[LiveKit] Mute toggle error:", e);
    }
  }, []);

  /**
   * Disconnect from the room entirely
   */
  const disconnect = useCallback(() => {
    roomRef.current?.disconnect();
    roomRef.current = null;
    setIsConnected(false);
    setInCall(false);
    setIsSpeaking(false);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      roomRef.current?.disconnect();
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

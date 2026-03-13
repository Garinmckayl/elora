import React, { useState, useRef, useEffect, useCallback, useMemo } from "react";
import {
  StyleSheet,
  Text,
  View,
  TextInput,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
  Alert,
  Modal,
  Animated,
  Image,
} from "react-native";
import { SafeAreaView, SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { CameraView, useCameraPermissions } from "expo-camera";
import { useElora, Message } from "./src/hooks/useElora";
import { useVoice } from "./src/hooks/useVoice";
import { useLiveKit } from "./src/hooks/useLiveKit";
import { useFirebaseAuth } from "./src/hooks/useFirebaseAuth";
import { useWakeWord } from "./src/hooks/useWakeWord";
import { useExpoPush } from "./src/hooks/useExpoPush";
import { useToast } from "./src/hooks/useToast";
import { usePhotoSearch } from "./src/hooks/usePhotoSearch";
import VoiceButton from "./src/components/VoiceButton";
import ChatBubble from "./src/components/ChatBubble";
import VisionCapture from "./src/components/VisionCapture";
import { BrowserModal } from "./src/components/BrowserModal";
import { Toast } from "./src/components/Toast";
import LiveCallScreen from "./src/components/LiveCallScreen";
import EloraAvatar from "./components/EloraAvatar";
import OnboardingScreen from "./src/screens/OnboardingScreen";
import SettingsScreen from "./src/screens/SettingsScreen";
import SkillsScreen from "./src/screens/SkillsScreen";
import HomeScreen from "./src/screens/HomeScreen";
import JourneyScreen from "./src/screens/JourneyScreen";
import { colors as defaultColors, spacing, borderRadius, shadows as defaultShadows, ThemeProvider, useTheme } from "./src/theme";
import { WS_URL, BACKEND_URL } from "./src/config";

// Check if Firebase is configured (has API key set)
function firebaseConfigured(): boolean {
  return !!(process.env.EXPO_PUBLIC_FIREBASE_API_KEY);
}

// Simple Sign-In screen
function SignInScreen({ onSignIn }: { onSignIn: () => Promise<void> }) {
  const [loading, setLoading] = useState(false);
  const { colors, shadows } = useTheme();

  const handleSignIn = async () => {
    setLoading(true);
    try {
      await onSignIn();
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.background }}>
      <StatusBar style="dark" />
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", paddingHorizontal: 40 }}>
        <LinearGradient
          colors={colors.gradientGoldSoft as [string, string]}
          style={{ position: "absolute", width: 200, height: 200, borderRadius: 100 }}
        />
        <Image
          source={require("./assets/icons/app-icon-1024.png")}
          style={{ width: 80, height: 80, borderRadius: 28, ...shadows.glow }}
        />
        <Text style={{ color: colors.textPrimary, fontSize: 28, fontWeight: "700", marginTop: 24, letterSpacing: -0.5 }}>
          Welcome to Elora
        </Text>
        <Text style={{ color: colors.textSecondary, fontSize: 15, textAlign: "center", marginTop: 8, lineHeight: 22 }}>
          Your personal AI agent. Sign in with Google to get started.
        </Text>
        <TouchableOpacity
          onPress={handleSignIn}
          disabled={loading}
          activeOpacity={0.8}
          style={{ marginTop: 40, width: "100%" }}
        >
          <LinearGradient
            colors={colors.gradientGold as [string, string]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 0 }}
            style={{
              flexDirection: "row",
              alignItems: "center",
              justifyContent: "center",
              paddingVertical: 16,
              borderRadius: borderRadius.full,
              gap: 10,
              ...shadows.glow,
            }}
          >
            <Ionicons name="logo-google" size={20} color={colors.background} />
            <Text style={{ color: colors.background, fontSize: 17, fontWeight: "700" }}>
              {loading ? "Signing in..." : "Continue with Google"}
            </Text>
          </LinearGradient>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

// Cloud Run backend URL
const SERVER_URL = WS_URL;

// Globally unique message ID generator -- avoids duplicate React keys
// when multiple messages arrive within the same millisecond.
let _msgSeq = 0;
function uid(prefix = "m"): string {
  return `${prefix}_${Date.now()}_${++_msgSeq}`;
}

export default function App() {
  return (
    <ThemeProvider>
      <AppInner />
    </ThemeProvider>
  );
}

function AppInner() {
  const { colors, shadows, isDark } = useTheme();
  const [showOnboarding, setShowOnboarding] = useState<boolean | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showJourney, setShowJourney] = useState(false);
  const [showSkills, setShowSkills] = useState(false);
  const [showHome, setShowHome] = useState(true);

  // Intent from HomeScreen -- tells MainScreen what to do on mount
  const [initialIntent, setInitialIntent] = useState<"chat" | "voice" | "camera" | null>(null);

  // Lift user name to App level so HomeScreen can use it
  const [userName, setUserName] = useState<string>("");
  useEffect(() => {
    AsyncStorage.getItem("elora_user_name").then((n) => {
      if (n) setUserName(n);
    });
  }, []);

  // Lift Firebase auth to App level so SettingsScreen gets the real userId
  const { uid: firebaseUid, idToken, loading: authLoading, user: authUser, signIn, signOut } = useFirebaseAuth();
  const userId = firebaseUid ?? "anonymous";

  // Check if onboarding was completed
  useEffect(() => {
    AsyncStorage.getItem("elora_onboarded").then((val) => {
      setShowOnboarding(val !== "true");
    });
  }, []);

  const handleOnboardingComplete = async (name: string) => {
    await AsyncStorage.setItem("elora_onboarded", "true");
    if (name) {
      await AsyncStorage.setItem("elora_user_name", name);
      // Save name to backend — fire-and-forget (will retry next launch if it fails)
      const savedUid = await AsyncStorage.getItem("elora_user_id") ?? userId;
      try {
        await fetch(`${BACKEND_URL}/user/profile`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: savedUid, name }),
        });
      } catch (e) {
        console.warn("[Onboarding] Failed to save name to backend:", e);
      }
    }
    setShowOnboarding(false);
  };

  // Wait for onboarding check
  if (showOnboarding === null) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.background }} />
    );
  }

  if (showOnboarding) {
    return (
      <SafeAreaProvider>
        <OnboardingScreen onComplete={handleOnboardingComplete} />
      </SafeAreaProvider>
    );
  }

  // Show sign-in screen if user is not authenticated
  // (Firebase config is set but no user signed in)
  if (!authLoading && !authUser && firebaseConfigured()) {
    return (
      <SafeAreaProvider>
        <SignInScreen onSignIn={signIn} />
      </SafeAreaProvider>
    );
  }

  // Settings rendered as a Modal overlay -- never unmounts MainScreen/HomeScreen
  const settingsModal = (
    <Modal visible={showSettings} animationType="slide" presentationStyle="pageSheet">
      <SettingsScreen
        onClose={() => setShowSettings(false)}
        userId={userId}
        user={authUser}
        onSignIn={signIn}
        onSignOut={signOut}
      />
    </Modal>
  );

  // Journey rendered as a Modal overlay
  const journeyModal = (
    <Modal visible={showJourney} animationType="slide" presentationStyle="pageSheet">
      <JourneyScreen
        onClose={() => setShowJourney(false)}
        userId={userId}
        idToken={idToken}
      />
    </Modal>
  );

  // Skills rendered as a Modal overlay
  const skillsModal = (
    <Modal visible={showSkills} animationType="slide" presentationStyle="pageSheet">
      <SkillsScreen
        onClose={() => setShowSkills(false)}
        userId={userId}
      />
    </Modal>
  );

  // Show minimalist home screen when not in active conversation
  if (showHome) {
    return (
      <SafeAreaProvider>
        <HomeScreen
          userName={userName}
          userId={userId}
          idToken={idToken}
          onOpenChat={() => {
            setInitialIntent("chat");
            setShowHome(false);
          }}
          onOpenVoice={() => {
            setInitialIntent("voice");
            setShowHome(false);
          }}
          onOpenCamera={() => {
            setInitialIntent("camera");
            setShowHome(false);
          }}
          onOpenSettings={() => setShowSettings(true)}
          onOpenJourney={() => setShowJourney(true)}
          onOpenSkills={() => setShowSkills(true)}
        />
        {settingsModal}
        {journeyModal}
        {skillsModal}
      </SafeAreaProvider>
    );
  }

  return (
    <SafeAreaProvider>
      <MainScreen 
        onOpenSettings={() => setShowSettings(true)} 
        appUserId={userId} 
        appIdToken={idToken} 
        isDark={isDark} 
        colors={colors} 
        shadows={shadows}
        onBackToHome={() => setShowHome(true)}
        initialIntent={initialIntent}
        onIntentConsumed={() => setInitialIntent(null)}
      />
      {settingsModal}
      {journeyModal}
      {skillsModal}
    </SafeAreaProvider>
  );
}

// -- Main Chat/Voice Screen --

function MainScreen({ onOpenSettings, appUserId, appIdToken, isDark, colors, shadows, onBackToHome, initialIntent, onIntentConsumed }: { onOpenSettings: () => void; appUserId: string; appIdToken?: string | null; isDark: boolean; colors: any; shadows: any; onBackToHome?: () => void; initialIntent?: "chat" | "voice" | "camera" | null; onIntentConsumed?: () => void }) {
  // Firebase auth is now lifted to App level — receive userId and idToken as props
  const userId = appUserId;
  const idToken = appIdToken ?? null;

  // Compute styles dynamically based on current theme colors
  const styles = useMemo(() => createStyles(colors, shadows, isDark), [colors, shadows, isDark]);

  // Toast notifications for errors and connection state
  const { toasts, showToast, dismissToast } = useToast();

  // Photo search (face matching across camera roll)
  const { findPhotosWithPerson } = usePhotoSearch();

  // Load user name and sync uid to AsyncStorage for onboarding save
  const [userName, setUserName] = useState<string>("");
  useEffect(() => {
    AsyncStorage.getItem("elora_user_name").then((n) => {
      if (n) setUserName(n);
    });
  }, []);

  // Once we have a real uid, persist it and re-save the name to backend with the real uid
  useEffect(() => {
    if (!userId || userId === "anonymous") return;
    AsyncStorage.setItem("elora_user_id", userId);
    AsyncStorage.getItem("elora_user_name").then((savedName) => {
      if (!savedName) return;
      // Re-post with real uid (onboarding may have posted with "anonymous")
      fetch(`${BACKEND_URL}/user/profile`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          name: savedName,
          token: idToken ?? "",
        }),
      }).catch((e) => console.warn("[Profile] re-save failed:", e));
    });
  }, [userId, idToken]);

  // UI state -- declared early so hooks below can reference setters
  const [inputText, setInputText] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [showChat, setShowChat] = useState(false);
  const [showCamera, setShowCamera] = useState(false);
  const [inCall, setInCall] = useState(false);
  const [liveCamera, setLiveCamera] = useState(false);
  const [isBrowsing, setIsBrowsing] = useState(false);
  const [browserScreenshot, setBrowserScreenshot] = useState<string | null>(null);
  const [browserUrl, setBrowserUrl] = useState<string | null>(null);
  const [browserStep, setBrowserStep] = useState<string | null>(null);
  const [cameraFacing, setCameraFacing] = useState<"front" | "back">("back");
  const [lastEloraText, setLastEloraText] = useState<string | null>(null);
  const [lastUserTranscript, setLastUserTranscript] = useState<string | null>(null);
  const [isMuted, setIsMuted] = useState(false);

  // Text mode -- ADK agent via WebSocket
  const {
    messages, isConnected, isThinking, setIsThinking,
    sendMessage, sendImage, addMessage, sendPhotoSearchResults,
  } = useElora({
    serverUrl: SERVER_URL,
    userId,
    token: idToken,
    onBrowserStart: useCallback(() => {
      setBrowserScreenshot(null);
      setBrowserStep(null);
      setIsBrowsing(true);
    }, []),
    onBrowserScreenshot: useCallback((b64: string) => {
      setBrowserScreenshot(b64);
      setIsBrowsing(true);
    }, []),
    onBrowserStep: useCallback((text: string) => {
      setBrowserStep(text);
    }, []),
    onPhotoSearchRequest: useCallback((personName: string) => {
      findPhotosWithPerson(personName, userId, idToken ?? undefined)
        .then((results) => {
          sendPhotoSearchResultsRef.current?.(personName, results.map((r) => r.uri));
        })
        .catch((e) => console.warn("[PhotoSearch] failed:", e));
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [userId, idToken, findPhotosWithPerson]),
  });

  // Register Expo push token so Elora can send proactive notifications + reminders
  useExpoPush({
    userId,
    token: idToken,
    enabled: userId !== "anonymous",
    onNotificationTap: useCallback((data: Record<string, any>) => {
      // Open chat view so user can reply or see context
      setShowChat(true);
      // Add a contextual message so the user knows what was tapped
      const type = data?.type ?? "";
      let hint = "";
      if (type === "reminder") hint = `Reminder: ${data?.message ?? "You have a reminder."}`;
      else if (type === "new_email") hint = `You have a new email. Want me to read it?`;
      else if (type === "briefing") hint = "Your morning briefing is ready.";
      else if (type === "proactive") {
        // Proactive notifications carry the full message from the evaluator
        const signal = data?.signal_type ?? "";
        const msg = data?.message ?? "";
        if (msg) {
          hint = msg;
        } else if (signal === "meeting_soon") {
          hint = "You have a meeting coming up. Want me to help you prepare?";
        } else if (signal === "birthday") {
          hint = "Someone special has a birthday coming up!";
        } else if (signal === "stale_contact") {
          hint = "It's been a while since you reached out to someone close.";
        } else {
          hint = "Hey, I noticed something you might want to know about.";
        }
      }
      if (hint) {
        addMessage({
          id: uid(),
          role: "elora",
          content: hint,
          timestamp: new Date(),
        });
      }
    }, [addMessage]),
  });

  // Voice recording
  const { isRecording, hasPermission, startRecording, stopRecording } = useVoice();

  // Ref to sendPhotoSearchResults — used in onPhotoSearchRequest callback (avoids circular dep)
  const sendPhotoSearchResultsRef = useRef<((name: string, uris: string[]) => void) | null>(null);

  // LiveKit voice session -- replaces useLiveSession + useLiveAudioStream
  // Audio transport is handled by WebRTC (no manual WAV recording / PCM streaming)
  const livekit = useLiveKit({
    userId,
    token: idToken,
    onText: useCallback((text: string) => {
      // If we were browsing, close the modal when Elora gives the final answer
      setIsBrowsing(false);
      setLastEloraText(text);
      addMessage({
        id: uid(),
        role: "elora",
        content: text,
        timestamp: new Date(),
      });
    }, [addMessage]),
    onTranscript: useCallback((transcript: string) => {
      // Show user's speech as a message for debugging/visibility
      addMessage({
        id: uid("tr"),
        role: "user",
        content: transcript,
        timestamp: new Date(),
      });
      setLastUserTranscript(transcript);
    }, [addMessage]),
    onToolCall: useCallback((name: string, args: Record<string, any>) => {
      if (name === "browse_web") {
        setBrowserScreenshot(null);
        setBrowserUrl(args.start_url || null);
        setBrowserStep(null);
        setIsBrowsing(true);
      }
      addMessage({
        id: uid(),
        role: "elora",
        content: "",          // empty — ChatBubble renders toolName instead
        toolName: name,
        toolArgs: args,
        isThinking: true,
        timestamp: new Date(),
      });
    }, [addMessage]),
    onAudioEnd: useCallback(() => {
      setIsThinking(false);
    }, [setIsThinking]),
  });

  // Keep sendPhotoSearchResultsRef in sync
  useEffect(() => {
    sendPhotoSearchResultsRef.current = sendPhotoSearchResults;
  }, [sendPhotoSearchResults]);


  // Wake word -- always-on "Hey Elora" detection
  // When triggered, automatically start a call so the user can speak immediately
  const handleWake = useCallback(async () => {
    if (inCall) return; // already in a call
    console.log("[Wake] Auto-starting call");
    if (!hasPermission) return;
    setInCall(true);
    setLastEloraText(null);
    livekit.startCall();
    addMessage({
      id: uid(),
      role: "elora",
      content: "Hey! I'm listening...",
      timestamp: new Date(),
    });
  }, [inCall, hasPermission, livekit, addMessage]);

  const { isListening: wakeListening } = useWakeWord({
    userId,
    token: idToken,
    enabled: !inCall,  // disable during active calls to save resources
    onWake: handleWake,
  });

  // Live camera sharing during call
  const liveCameraRef = useRef<CameraView>(null);
  const videoFrameIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [cameraPermission, requestCameraPermission] = useCameraPermissions();

  const flatListRef = useRef<FlatList>(null);
  const textInputRef = useRef<TextInput>(null);

  // Animated values for the speaking indicator
  const speakingAnim = useRef(new Animated.Value(0)).current;
  // Animated value for the wake word badge pulse
  const wakePulseAnim = useRef(new Animated.Value(0)).current;

  // Connect to LiveKit on mount and when user changes
  useEffect(() => {
    livekit.connect();
  }, [livekit.connect]);

  // Handle initial intent from HomeScreen (start call, open camera, or show chat)
  useEffect(() => {
    if (!initialIntent) return;
    const intent = initialIntent;
    onIntentConsumed?.();

    if (intent === "voice") {
      // Auto-start a live call with a small delay so MainScreen finishes mounting
      const timer = setTimeout(async () => {
        if (!hasPermission) {
          Alert.alert("Microphone Permission", "Elora needs microphone access.");
          return;
        }
        setInCall(true);
        setLastEloraText(null);
        await livekit.startCall();
        if (cameraPermission?.granted) {
          setLiveCamera(true);
          livekit.toggleCamera(true);
        }
        addMessage({
          id: uid(),
          role: "elora",
          content: "[Call started - streaming audio]",
          timestamp: new Date(),
        });
      }, 300);
      return () => clearTimeout(timer);
    } else if (intent === "camera") {
      setShowCamera(true);
    } else if (intent === "chat") {
      setShowChat(true);
      // Auto-focus the text input after a brief layout settle
      setTimeout(() => textInputRef.current?.focus(), 100);
    }
  }, [initialIntent]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (messages.length > 0) {
      setTimeout(() => {
        flatListRef.current?.scrollToEnd({ animated: true });
      }, 100);
    }
  }, [messages]);

  // Speaking animation
  useEffect(() => {
    if (livekit.isSpeaking) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(speakingAnim, {
            toValue: 1,
            duration: 800,
            useNativeDriver: true,
          }),
          Animated.timing(speakingAnim, {
            toValue: 0,
            duration: 800,
            useNativeDriver: true,
          }),
        ])
      ).start();
    } else {
      speakingAnim.stopAnimation();
      Animated.timing(speakingAnim, {
        toValue: 0,
        duration: 200,
        useNativeDriver: true,
      }).start();
    }
  }, [livekit.isSpeaking]);

  // Wake word badge pulse animation
  useEffect(() => {
    if (wakeListening && !inCall) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(wakePulseAnim, {
            toValue: 1,
            duration: 1200,
            useNativeDriver: true,
          }),
          Animated.timing(wakePulseAnim, {
            toValue: 0,
            duration: 1200,
            useNativeDriver: true,
          }),
        ])
      ).start();
    } else {
      wakePulseAnim.stopAnimation();
      wakePulseAnim.setValue(0);
    }
  }, [wakeListening, inCall]);

  // Toast on connection loss / recovery
  const prevConnected = useRef<boolean | null>(null);
  useEffect(() => {
    if (prevConnected.current === null) {
      prevConnected.current = isConnected;
      return;
    }
    if (!isConnected && prevConnected.current) {
      showToast({ type: "error", title: "Connection lost", message: "Trying to reconnect…", duration: 5000 });
    } else if (isConnected && !prevConnected.current) {
      showToast({ type: "success", title: "Reconnected", duration: 2500 });
    }
    prevConnected.current = isConnected;
  }, [isConnected]);

  const handleSend = () => {
    if (inputText.trim()) {
      sendMessage(inputText.trim());
      setInputText("");
    }
  };

  // ---- Voice: hold-to-talk ----

  const handleVoicePressIn = async () => {
    if (!hasPermission) {
      Alert.alert("Microphone Permission", "Elora needs microphone access to hear you.");
      return;
    }
    // If not in a call, auto-start a live call so audio actually goes somewhere
    if (!inCall) {
      setInCall(true);
      setLastEloraText(null);
      await livekit.startCall();
      addMessage({
        id: uid(),
        role: "elora",
        content: "[Call started]",
        timestamp: new Date(),
      });
      return;
    }
    if (!livekit.isConnected) livekit.connect();
    setIsListening(true);
    await startRecording();
  };

  const handleVoicePressOut = async () => {
    setIsListening(false);
    const uri = await stopRecording();
    if (!uri) return;
    // Audio is streamed via LiveKit WebRTC mic track during a call.
    // No manual send needed -- LiveKit handles it.
  };

  // ---- Call mode ----

  const handleCallToggle = async () => {
    if (inCall) {
      setInCall(false);
      setIsListening(false);
      setLastEloraText(null);
      setLastUserTranscript(null);
      setIsMuted(false);
      stopLiveCamera();
      try { await stopRecording(); } catch {}
      livekit.endCall();
      addMessage({
        id: uid(),
        role: "elora",
        content: "[Call ended]",
        timestamp: new Date(),
      });
    } else {
      if (!hasPermission) {
        Alert.alert("Microphone Permission", "Elora needs microphone access.");
        return;
      }
      setInCall(true);
      setLastEloraText(null);
      await livekit.startCall();
      // Auto-start camera for immersive call UI -- LiveKit handles video track
      if (cameraPermission?.granted) {
        setLiveCamera(true);
        livekit.toggleCamera(true);
      }
      addMessage({
        id: uid(),
        role: "elora",
        content: "[Call started - streaming audio]",
        timestamp: new Date(),
      });
    }
  };

  // ---- Live camera toggle (share camera feed during call) ----

  const startLiveCamera = useCallback(async () => {
    if (!cameraPermission?.granted) {
      const result = await requestCameraPermission();
      if (!result.granted) {
        Alert.alert("Camera Permission", "Elora needs camera access to see what you see.");
        return;
      }
    }
    setLiveCamera(true);
    livekit.toggleCamera(true);
  }, [cameraPermission, requestCameraPermission, livekit]);

  const stopLiveCamera = useCallback(() => {
    if (videoFrameIntervalRef.current) {
      clearInterval(videoFrameIntervalRef.current);
      videoFrameIntervalRef.current = null;
    }
    setLiveCamera(false);
    livekit.toggleCamera(false);
  }, [livekit]);

  const handleLiveCameraToggle = useCallback(async () => {
    if (liveCamera) {
      stopLiveCamera();
    } else {
      // Request camera permission if not already granted
      if (!cameraPermission?.granted) {
        const result = await requestCameraPermission();
        if (!result.granted) {
          Alert.alert("Camera Permission", "Elora needs camera access to see what you see.");
          return;
        }
      }
      startLiveCamera();
    }
  }, [liveCamera, startLiveCamera, stopLiveCamera, cameraPermission, requestCameraPermission]);

  // Stop camera when call ends
  useEffect(() => {
    if (!inCall) stopLiveCamera();
  }, [inCall]);

  const renderMessage = ({ item }: { item: Message }) => (
    <ChatBubble
      role={item.role}
      content={item.content}
      timestamp={item.timestamp}
      imageBase64={item.imageBase64}
      audioBase64={item.audioBase64}
      audioMimeType={item.audioMimeType}
      toolName={item.toolName}
      toolArgs={item.toolArgs}
      subAgentName={item.subAgentName}
      isThinking={item.isThinking}
      photoUris={item.photoUris}
    />
  );

  const anyConnected = isConnected || livekit.isConnected;
  const showThinking = isThinking && !livekit.isSpeaking;

  // Voice hint text
  const voiceHintText = isListening
    ? "Listening..."
    : livekit.isSpeaking
    ? "Elora is speaking..."
    : isThinking
    ? "Processing..."
    : inCall
    ? isMuted
      ? "Muted"
      : "Streaming audio..."
    : "Hold to talk";

  // ---- Immersive call mode ----
  if (inCall) {
    return (
      <>
        <StatusBar style={isDark ? "light" : "dark"} />
        <LiveCallScreen
          cameraRef={liveCameraRef}
          isListening={isListening}
          isSpeaking={livekit.isSpeaking}
          isThinking={isThinking}
          isScanning={liveCamera}
          liveCamera={liveCamera}
          eloraText={lastEloraText ?? undefined}
          userTranscript={lastUserTranscript ?? undefined}
          messages={messages}
          isMuted={isMuted}
          onEndCall={handleCallToggle}
          onToggleCamera={handleLiveCameraToggle}
          onToggleMute={() => {
            const newMuted = !isMuted;
            setIsMuted(newMuted);
            livekit.toggleMute(newMuted);
          }}
          onPressIn={() => {}}
          onPressOut={() => {}}
          onSendText={(text) => {
            // During LiveKit calls, text goes through the text WS (useElora)
            sendMessage(text);
            addMessage({
              id: uid(),
              role: "user",
              content: text,
              timestamp: new Date(),
            });
          }}
          cameraFacing={cameraFacing}
          onFlipCamera={() => setCameraFacing((f) => f === "back" ? "front" : "back")}
        />
        {/* Browser task modal -- can appear over call screen too */}
        <BrowserModal
          visible={isBrowsing}
          screenshotBase64={browserScreenshot}
          currentUrl={browserUrl}
          stepText={browserStep}
          onClose={() => setIsBrowsing(false)}
        />
        {/* Toast notifications */}
        {toasts.length > 0 && (
          <View style={styles.toastStack} pointerEvents="box-none">
            {toasts.map((t) => (
              <Toast key={t.id} toast={t} onDismiss={dismissToast} />
            ))}
          </View>
        )}
      </>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style={isDark ? "light" : "dark"} />

      {/* Warm gradient background -- matches HomeScreen feel */}
      <LinearGradient
        colors={colors.gradientHero as [string, string, string]}
        style={StyleSheet.absoluteFillObject}
        start={{ x: 0.2, y: 0 }}
        end={{ x: 0.8, y: 1 }}
      />

      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          {onBackToHome && (
            <TouchableOpacity onPress={onBackToHome} style={styles.headerButton}>
              <Ionicons name="home-outline" size={22} color={colors.textSecondary} />
            </TouchableOpacity>
          )}
          <View style={styles.headerBrand}>
            <Image
              source={require("./assets/elora-avatar.png")}
              style={styles.headerLogoImage}
            />
            <View>
              <Text style={styles.headerTitle}>Elora</Text>
              <View style={styles.statusRow}>
                <View style={[styles.statusDot, {
                  backgroundColor: anyConnected ? colors.connected : colors.disconnected,
                }]} />
                <Text style={styles.statusText}>
                  {inCall ? "In Call" : anyConnected ? "Connected" : "Offline"}
                </Text>
              </View>
            </View>
          </View>
          {inCall && (
            <View style={styles.callBadge}>
              <View style={styles.callPulse} />
              <Text style={styles.callBadgeText}>CALL</Text>
            </View>
          )}
          {!inCall && livekit.isConnected && (
            <View style={styles.liveBadge}>
              <Text style={styles.liveBadgeText}>LIVE</Text>
            </View>
          )}
          {liveCamera && (
            <View style={styles.cameraBadge}>
              <Ionicons name="videocam" size={10} color={colors.gold} />
              <Text style={styles.cameraBadgeText}>CAM</Text>
            </View>
          )}
          {wakeListening && !inCall && (
            <View style={styles.wakeBadge}>
              <Animated.View style={[styles.wakePulse, {
                opacity: wakePulseAnim,
                transform: [{ scale: wakePulseAnim.interpolate({ inputRange: [0, 1], outputRange: [0.6, 1.4] }) }],
              }]} />
              <Ionicons name="mic-outline" size={10} color={colors.textSecondary} />
            </View>
          )}
        </View>
        <View style={styles.headerRight}>
          <TouchableOpacity onPress={() => setShowCamera(true)} style={styles.headerButton}>
            <Ionicons name="scan-outline" size={22} color={colors.textSecondary} />
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setShowChat(!showChat)} style={styles.headerButton}>
            <Ionicons
              name={showChat ? "mic-outline" : "chatbubble-outline"}
              size={22}
              color={colors.textSecondary}
            />
          </TouchableOpacity>
          <TouchableOpacity onPress={onOpenSettings} style={styles.headerButton}>
            <Ionicons name="settings-outline" size={22} color={colors.textSecondary} />
          </TouchableOpacity>
        </View>
      </View>

      {/* Vision Camera (single capture) */}
      <VisionCapture
        visible={showCamera}
        onClose={() => setShowCamera(false)}
        onCapture={(base64) => { sendImage(base64); }}
      />

      {/* Hidden CameraView for one-shot snaps when user says "this is [name]" (non-call mode)
          During calls, LiveCallScreen manages the camera directly */}
      {!inCall && cameraPermission?.granted && (
        <CameraView
          ref={liveCameraRef}
          style={{ width: 1, height: 1, opacity: 0, position: "absolute" }}
          facing="back"
          flash="off"
          animateShutter={false}
        />
      )}

      {/* Messages + Input wrapped in KeyboardAvoidingView */}
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        keyboardVerticalOffset={Platform.OS === "ios" ? 90 : 0}
        style={{ flex: 1 }}
      >
        <FlatList
          ref={flatListRef}
          data={messages}
          renderItem={renderMessage}
          keyExtractor={(item) => item.id}
          style={styles.messageList}
          contentContainerStyle={styles.messageListContent}
          keyboardDismissMode="interactive"
          keyboardShouldPersistTaps="handled"
          ListEmptyComponent={
            <View style={styles.emptyState}>
              <EloraAvatar state="happy" size="large" animated />
              <Text style={styles.emptyTitle}>
                {userName ? `Hey, ${userName.split(" ")[0]}` : "Hey there"}
              </Text>
              <Text style={styles.emptySubtitle}>
                {showChat
                  ? "What's on your mind?"
                  : "Hold to talk, or tap the chat icon to type"}
              </Text>
            </View>
          }
        />

        {/* Speaking / Thinking indicator */}
        {(showThinking || livekit.isSpeaking) && (
          <Animated.View style={[styles.indicatorContainer, {
            opacity: livekit.isSpeaking
              ? speakingAnim.interpolate({ inputRange: [0, 1], outputRange: [0.6, 1] })
              : 1,
          }]}>
            <LinearGradient
              colors={livekit.isSpeaking
                ? ["rgba(212, 168, 83, 0.15)", "rgba(212, 168, 83, 0.05)"]
                : ["rgba(155, 163, 184, 0.1)", "rgba(155, 163, 184, 0.02)"]
              }
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 0 }}
              style={styles.indicatorGradient}
            >
              <Ionicons
                name={livekit.isSpeaking ? "volume-medium-outline" : "ellipsis-horizontal"}
                size={16}
                color={livekit.isSpeaking ? colors.gold : colors.textSecondary}
              />
              <Text style={[styles.indicatorText, livekit.isSpeaking && { color: colors.gold }]}>
                {livekit.isSpeaking ? "Elora is speaking..." : "Elora is thinking..."}
              </Text>
            </LinearGradient>
          </Animated.View>
        )}

        {/* Input Area */}
        <View style={styles.inputArea}>
          {showChat ? (
            /* Text input mode */
            <View style={styles.textInputContainer}>
              <View style={styles.textInputWrapper}>
                <TextInput
                  ref={textInputRef}
                  style={styles.textInput}
                  value={inputText}
                  onChangeText={setInputText}
                  placeholder="Message Elora..."
                  placeholderTextColor={colors.textTertiary}
                  returnKeyType="send"
                  onSubmitEditing={handleSend}
                  onFocus={() => {
                    setTimeout(() => {
                      flatListRef.current?.scrollToEnd({ animated: true });
                    }, 300);
                  }}
                  multiline
                />
                <TouchableOpacity
                  onPress={handleSend}
                  style={[styles.sendButton, !inputText.trim() && styles.sendButtonDisabled]}
                  disabled={!inputText.trim()}
                >
                  <LinearGradient
                    colors={inputText.trim() ? colors.gradientGold as [string, string] : [colors.surfaceLight, colors.surfaceLight]}
                    style={styles.sendButtonInner}
                  >
                    <Ionicons
                      name="arrow-up"
                      size={20}
                      color={inputText.trim() ? colors.background : colors.textTertiary}
                    />
                  </LinearGradient>
                </TouchableOpacity>
              </View>
            </View>
          ) : (
            /* Voice mode */
            <View style={styles.voiceContainer}>
              <View style={styles.voiceControls}>
                {/* Call / Hang-up button */}
                <TouchableOpacity
                  style={inCall ? styles.hangUpButton : styles.callButton}
                  onPress={handleCallToggle}
                  disabled={!anyConnected}
                >
                  <Ionicons
                    name={inCall ? "call" : "call-outline"}
                    size={inCall ? 26 : 22}
                    color={inCall ? "#FFFFFF" : colors.success}
                  />
                </TouchableOpacity>

                {/* Mic button (hold to talk) */}
                <VoiceButton
                  isListening={isListening}
                  isThinking={isThinking || livekit.isSpeaking}
                  onPressIn={handleVoicePressIn}
                  onPressOut={handleVoicePressOut}
                  disabled={!anyConnected}
                />

                {/* Chat shortcut */}
                <TouchableOpacity
                  style={styles.chatShortcutButton}
                  onPress={() => setShowChat(true)}
                >
                  <Ionicons name="chatbubble-outline" size={22} color={colors.textSecondary} />
                </TouchableOpacity>

                {/* Live camera toggle (only shown during a call) */}
                {inCall && (
                  <TouchableOpacity
                    style={[
                      styles.cameraToggleButton,
                      liveCamera && styles.cameraToggleActive,
                    ]}
                    onPress={handleLiveCameraToggle}
                  >
                    <Ionicons
                      name={liveCamera ? "videocam" : "videocam-outline"}
                      size={20}
                      color={liveCamera ? colors.gold : colors.textSecondary}
                    />
                  </TouchableOpacity>
                )}
              </View>
              <Text style={styles.voiceHint}>{voiceHintText}</Text>
            </View>
          )}
        </View>
      </KeyboardAvoidingView>
      {/* Browser task modal -- shows live screenshot stream */}
      <BrowserModal
        visible={isBrowsing}
        screenshotBase64={browserScreenshot}
        currentUrl={browserUrl}
        stepText={browserStep}
        onClose={() => setIsBrowsing(false)}
      />

      {/* Toast notifications -- floating at top */}
      {toasts.length > 0 && (
        <View style={styles.toastStack} pointerEvents="box-none">
          {toasts.map((t) => (
            <Toast key={t.id} toast={t} onDismiss={dismissToast} />
          ))}
        </View>
      )}
    </SafeAreaView>
  );
}

function createStyles(colors: any, shadows: any, isDark = false) {
  return StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "transparent", // gradient fills behind
  },

  // -- Header --
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingVertical: 12,
  },
  headerLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  headerBrand: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  headerLogoImage: {
    width: 28,
    height: 28,
    borderRadius: 14,
  },
  headerTitle: {
    color: colors.textPrimary,
    fontSize: 17,
    fontWeight: "600",
    letterSpacing: -0.3,
  },
  statusRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  statusText: {
    color: colors.textTertiary,
    fontSize: 11,
  },
  headerRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  headerButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: isDark ? colors.surface : "rgba(255,255,255,0.7)",
  },
  liveBadge: {
    backgroundColor: colors.goldMuted,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: borderRadius.full,
  },
  liveBadgeText: {
    color: colors.gold,
    fontSize: 9,
    fontWeight: "600",
    letterSpacing: 0.5,
  },
  callBadge: {
    backgroundColor: colors.goldMuted,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: borderRadius.full,
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  callPulse: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: colors.gold,
  },
  callBadgeText: {
    color: colors.gold,
    fontSize: 9,
    fontWeight: "600",
    letterSpacing: 0.5,
  },

  // -- Messages --
  messageList: {
    flex: 1,
  },
  messageListContent: {
    paddingVertical: 16,
    paddingHorizontal: 4,
    flexGrow: 1,
    justifyContent: "flex-end",
  },

  // -- Empty State --
  emptyState: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingBottom: 80,
    paddingHorizontal: 24,
    gap: 16,
  },
  emptyTitle: {
    color: colors.textPrimary,
    fontSize: 28,
    fontWeight: "700",
    letterSpacing: -0.5,
  },
  emptySubtitle: {
    color: colors.textTertiary,
    fontSize: 15,
    textAlign: "center",
    lineHeight: 22,
  },

  // -- Indicator --
  indicatorContainer: {
    paddingHorizontal: 20,
    paddingVertical: 8,
  },
  indicatorGradient: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderRadius: borderRadius.full,
  },
  indicatorText: {
    color: colors.textSecondary,
    fontSize: 14,
    fontWeight: "500",
  },

  // -- Input Area --
  inputArea: {
    backgroundColor: colors.surfaceElevated,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
    paddingBottom: Platform.OS === "ios" ? 8 : 6,
  },

  // Text input
  textInputContainer: {
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  textInputWrapper: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surface,
    borderRadius: borderRadius.xl,
    borderWidth: 1,
    borderColor: colors.border,
    paddingLeft: 18,
    paddingRight: 6,
    paddingVertical: 6,
    ...shadows.soft,
  },
  textInput: {
    flex: 1,
    color: colors.textPrimary,
    fontSize: 16,
    maxHeight: 100,
    paddingVertical: 8,
    textAlignVertical: "center",
  },
  sendButton: {
    marginBottom: 4,
  },
  sendButtonDisabled: {
    opacity: 0.5,
  },
  sendButtonInner: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
  },

  // Voice mode
  voiceContainer: {
    alignItems: "center",
    paddingVertical: 16,
    backgroundColor: colors.surfaceElevated,
  },
  voiceControls: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 20,
  },
  callButton: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.goldMuted,
    alignItems: "center",
    justifyContent: "center",
    ...shadows.soft,
  },
  hangUpButton: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.error,
    alignItems: "center",
    justifyContent: "center",
    ...shadows.soft,
  },
  chatShortcutButton: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: isDark ? colors.surface : "rgba(255,255,255,0.85)",
    borderWidth: 1,
    borderColor: colors.borderLight,
    alignItems: "center",
    justifyContent: "center",
    ...shadows.soft,
  },
  cameraToggleButton: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  cameraToggleActive: {
    backgroundColor: colors.goldMuted,
    borderColor: colors.gold,
  },
  cameraBadge: {
    backgroundColor: colors.goldMuted,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: borderRadius.full,
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  cameraBadgeText: {
    color: colors.gold,
    fontSize: 9,
    fontWeight: "600",
  },
  voiceHint: {
    color: colors.textTertiary,
    fontSize: 13,
    marginTop: 12,
  },
  // Wake word indicator
  wakeBadge: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.goldMuted,
    alignItems: "center",
    justifyContent: "center",
  },
  wakePulse: {
    position: "absolute",
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.gold,
    top: 3,
    right: 3,
  },
  // Toast stack -- overlays top of screen
  toastStack: {
    position: "absolute",
    top: 60,
    left: 0,
    right: 0,
    zIndex: 100,
    pointerEvents: "box-none",
  },
});
}

/**
 * ChatBubble -- message bubble with:
 *   - Inline markdown rendering (bold, italic, inline code, code blocks, bullet lists)
 *   - Collapsible tool-use / thinking card showing sub-agent + args
 *   - Photo thumbnail for image messages
 */

import React, { useState, useMemo } from "react";
import {
  View,
  Text,
  Image,
  StyleSheet,
  TouchableOpacity,
  LayoutAnimation,
  Animated,
  UIManager,
  Platform,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { borderRadius, useTheme, type ThemeColors } from "../theme";
import { PhotoGrid } from "./PhotoGrid";
import AudioPlayer from "./AudioPlayer";

const appIcon = require("../../assets/elora-avatar.png");

// Enable LayoutAnimation on Android
if (Platform.OS === "android" && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ChatBubbleProps {
  role: "user" | "elora";
  content: string;
  timestamp: Date;
  /** Base64 JPEG for photo messages */
  imageBase64?: string;
  /** Base64 audio data (from generate_music) */
  audioBase64?: string;
  audioMimeType?: string;
  /** For tool-use bubbles: structured info */
  toolName?: string;
  toolArgs?: Record<string, any>;
  subAgentName?: string;
  isThinking?: boolean;
  /** Photo URIs from a face search result */
  photoUris?: string[];
}

// ---------------------------------------------------------------------------
// Simple inline markdown parser
// Handles: **bold**, *italic*, `code`, ```block```, - bullet, # heading
// ---------------------------------------------------------------------------

type Segment =
  | { type: "text"; value: string }
  | { type: "bold"; value: string }
  | { type: "italic"; value: string }
  | { type: "code"; value: string }
  | { type: "newline" };

function parseInline(text: string): Segment[] {
  const segments: Segment[] = [];
  // Combined regex: **bold**, *italic*, `code`
  const re = /(\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      segments.push({ type: "text", value: text.slice(last, m.index) });
    }
    if (m[2] !== undefined) segments.push({ type: "bold", value: m[2] });
    else if (m[3] !== undefined) segments.push({ type: "italic", value: m[3] });
    else if (m[4] !== undefined) segments.push({ type: "code", value: m[4] });
    last = m.index + m[0].length;
  }
  if (last < text.length) segments.push({ type: "text", value: text.slice(last) });
  return segments;
}

function MarkdownText({ text, style, bulletColor }: { text: string; style?: any; bulletColor?: string }) {
  const { colors, isDark } = useTheme();
  const mdStyles = useMemo(() => createMdStyles(colors, isDark), [colors, isDark]);
  // Split into lines first for headings / bullets / code blocks
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let inCodeBlock = false;
  let codeLines: string[] = [];

  lines.forEach((line, li) => {
    // Code block fence
    if (line.trimStart().startsWith("```")) {
      if (inCodeBlock) {
        // Close code block
        elements.push(
          <View key={`cb-${li}`} style={mdStyles.codeBlock}>
            <Text style={mdStyles.codeBlockText}>{codeLines.join("\n")}</Text>
          </View>
        );
        codeLines = [];
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
      }
      return;
    }
    if (inCodeBlock) {
      codeLines.push(line);
      return;
    }

    // Heading
    const headingMatch = line.match(/^#{1,3}\s+(.+)$/);
    if (headingMatch) {
      elements.push(
        <Text key={`h-${li}`} style={[style, mdStyles.heading]}>
          {headingMatch[1]}
        </Text>
      );
      return;
    }

    // Bullet list
    const bulletMatch = line.match(/^[-*•]\s+(.+)$/);
    if (bulletMatch) {
      elements.push(
        <View key={`li-${li}`} style={mdStyles.bulletRow}>
          <Text style={[style, mdStyles.bulletDot, bulletColor ? { color: bulletColor } : undefined]}>•</Text>
          <InlineSegments text={bulletMatch[1]} style={style} />
        </View>
      );
      return;
    }

    // Numbered list
    const numberedMatch = line.match(/^(\d+)\.\s+(.+)$/);
    if (numberedMatch) {
      elements.push(
        <View key={`nl-${li}`} style={mdStyles.bulletRow}>
          <Text style={[style, mdStyles.bulletDot]}>{numberedMatch[1]}.</Text>
          <InlineSegments text={numberedMatch[2]} style={style} />
        </View>
      );
      return;
    }

    // Empty line → small gap
    if (line.trim() === "") {
      elements.push(<View key={`gap-${li}`} style={{ height: 6 }} />);
      return;
    }

    // Normal inline text
    elements.push(<InlineSegments key={`p-${li}`} text={line} style={style} />);
  });

  // Flush unclosed code block
  if (inCodeBlock && codeLines.length > 0) {
    elements.push(
      <View key="cb-end" style={mdStyles.codeBlock}>
        <Text style={mdStyles.codeBlockText}>{codeLines.join("\n")}</Text>
      </View>
    );
  }

  return <View>{elements}</View>;
}

function InlineSegments({ text, style }: { text: string; style?: any }) {
  const { colors, isDark } = useTheme();
  const mdStyles = useMemo(() => createMdStyles(colors, isDark), [colors, isDark]);
  const segs = parseInline(text);
  return (
    <Text style={style}>
      {segs.map((seg, i) => {
        switch (seg.type) {
          case "bold":   return <Text key={i} style={mdStyles.bold}>{seg.value}</Text>;
          case "italic": return <Text key={i} style={mdStyles.italic}>{seg.value}</Text>;
          case "code":   return <Text key={i} style={mdStyles.inlineCode}>{seg.value}</Text>;
          case "newline": return <Text key={i}>{"\n"}</Text>;
          default:       return <Text key={i}>{"value" in seg ? seg.value : ""}</Text>;
        }
      })}
    </Text>
  );
}

// ---------------------------------------------------------------------------
// Tool / thinking card — collapsible
// ---------------------------------------------------------------------------

const TOOL_LABELS: Record<string, { icon: string; label: string; color: string }> = {
  web_search:                    { icon: "search-outline",      label: "Searching web",        color: "#7C83FD" },
  fetch_webpage:                 { icon: "globe-outline",        label: "Reading page",         color: "#7C83FD" },
  browse_web:                    { icon: "browsers-outline",     label: "Browsing",             color: "#48BB78" },
  send_email:                    { icon: "mail-outline",         label: "Sending email",        color: "#F6AD55" },
  read_emails:                   { icon: "mail-open-outline",    label: "Reading emails",       color: "#F6AD55" },
  create_calendar_event:         { icon: "calendar-outline",     label: "Creating event",       color: "#FC8181" },
  list_calendar_events:          { icon: "calendar-outline",     label: "Checking calendar",    color: "#FC8181" },
  save_file:                     { icon: "save-outline",         label: "Saving file",          color: "#9BA3B8" },
  read_file:                     { icon: "document-outline",     label: "Reading file",         color: "#9BA3B8" },
  remember:                      { icon: "bookmark-outline",     label: "Remembering",          color: "#68D391" },
  recall:                        { icon: "bulb-outline",         label: "Recalling memory",     color: "#68D391" },
  get_current_time:              { icon: "time-outline",         label: "Checking time",        color: "#9BA3B8" },
  web_researcher:                { icon: "search-outline",       label: "Web researcher",       color: "#7C83FD" },
  browser_worker:                { icon: "browsers-outline",     label: "Browser agent",        color: "#48BB78" },
  email_calendar:                { icon: "mail-outline",         label: "Email & Calendar",     color: "#F6AD55" },
  file_memory:                   { icon: "archive-outline",      label: "Files & Memory",       color: "#68D391" },
  remember_person:               { icon: "people-outline",       label: "Remembering person",   color: "#C084FC" },
  recall_person:                 { icon: "people-circle-outline",label: "Recalling person",     color: "#C084FC" },
  list_people:                   { icon: "people-outline",       label: "Checking people",      color: "#C084FC" },
  update_person_appearance:      { icon: "person-outline",       label: "Updating appearance",  color: "#C084FC" },
  describe_person_from_camera:   { icon: "camera-outline",       label: "Seeing person",        color: "#F472B6" },
  request_photo_search:          { icon: "images-outline",       label: "Searching photos",     color: "#38BDF8" },
  send_sms:                      { icon: "chatbubble-outline",   label: "Sending message",      color: "#34D399" },
  lookup_phone_for_person:       { icon: "call-outline",         label: "Looking up number",    color: "#34D399" },
  generate_music:                { icon: "musical-notes-outline", label: "Generating music",    color: "#D4A853" },
  generate_audio:                { icon: "musical-notes-outline", label: "Generating audio",    color: "#D4A853" },
  generate_image:                { icon: "image-outline",         label: "Generating image",    color: "#F472B6" },
  search_restaurants:            { icon: "restaurant-outline",    label: "Searching restaurants", color: "#FB923C" },
  make_reservation:              { icon: "restaurant-outline",    label: "Making reservation",  color: "#FB923C" },
  execute_skill:                 { icon: "flash-outline",         label: "Running skill",       color: "#A78BFA" },
  search_skills:                 { icon: "search-outline",        label: "Searching skills",    color: "#A78BFA" },
  install_skill:                 { icon: "download-outline",      label: "Installing skill",    color: "#A78BFA" },
  create_skill:                  { icon: "construct-outline",     label: "Creating skill",      color: "#A78BFA" },
  list_installed_skills:         { icon: "list-outline",          label: "Listing skills",      color: "#A78BFA" },
  remove_skill:                  { icon: "trash-outline",         label: "Removing skill",      color: "#A78BFA" },
  publish_skill:                 { icon: "cloud-upload-outline",  label: "Publishing skill",    color: "#A78BFA" },
  install_sandbox_package:       { icon: "cube-outline",          label: "Installing package",  color: "#6EE7B7" },
  set_reminder:                  { icon: "alarm-outline",         label: "Setting reminder",    color: "#FBBF24" },
  run_code:                      { icon: "code-slash-outline",    label: "Running code",        color: "#6EE7B7" },
};

function ToolCard({
  toolName,
  toolArgs,
  subAgentName,
  isThinking,
}: {
  toolName: string;
  toolArgs?: Record<string, any>;
  subAgentName?: string;
  isThinking?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const { colors, isDark } = useTheme();
  const tStyles = useMemo(() => createToolStyles(colors, isDark), [colors, isDark]);
  const meta = TOOL_LABELS[toolName] ?? { icon: "construct-outline", label: toolName, color: colors.gold };

  const toggle = () => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setExpanded(e => !e);
  };

  const hasDetail = !!toolArgs && Object.keys(toolArgs).length > 0;

  return (
    <TouchableOpacity
      onPress={hasDetail ? toggle : undefined}
      activeOpacity={hasDetail ? 0.7 : 1}
      style={tStyles.card}
    >
      <View style={tStyles.header}>
        <View style={[tStyles.iconDot, { backgroundColor: meta.color + "22" }]}>
          <Ionicons name={meta.icon as any} size={13} color={meta.color} />
        </View>
        <Text style={[tStyles.label, { color: meta.color }]}>{meta.label}</Text>
        {subAgentName && (
          <View style={tStyles.agentBadge}>
            <Text style={tStyles.agentBadgeText}>{subAgentName}</Text>
          </View>
        )}
        {isThinking && <ActivityDots color={meta.color} />}
        {hasDetail && (
          <Ionicons
            name={expanded ? "chevron-up" : "chevron-down"}
            size={12}
            color={colors.textTertiary}
            style={{ marginLeft: "auto" }}
          />
        )}
      </View>

      {expanded && hasDetail && (
        <View style={tStyles.detail}>
          {Object.entries(toolArgs!).map(([k, v]) => (
            <View key={k} style={tStyles.detailRow}>
              <Text style={tStyles.detailKey}>{k}: </Text>
              <Text style={tStyles.detailVal} numberOfLines={3}>
                {typeof v === "object" ? JSON.stringify(v) : String(v)}
              </Text>
            </View>
          ))}
        </View>
      )}
    </TouchableOpacity>
  );
}

function ActivityDots({ color }: { color: string }) {
  const dot1 = React.useRef(new Animated.Value(0.3)).current;
  const dot2 = React.useRef(new Animated.Value(0.3)).current;
  const dot3 = React.useRef(new Animated.Value(0.3)).current;

  React.useEffect(() => {
    const animate = (dot: Animated.Value, delay: number) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(delay),
          Animated.timing(dot, { toValue: 1, duration: 400, useNativeDriver: true }),
          Animated.timing(dot, { toValue: 0.3, duration: 400, useNativeDriver: true }),
        ])
      );
    const a1 = animate(dot1, 0);
    const a2 = animate(dot2, 150);
    const a3 = animate(dot3, 300);
    a1.start(); a2.start(); a3.start();
    return () => { a1.stop(); a2.stop(); a3.stop(); };
  }, [dot1, dot2, dot3]);

  return (
    <View style={{ flexDirection: "row", marginLeft: 6, gap: 3, alignItems: "center" }}>
      {[dot1, dot2, dot3].map((dot, i) => (
        <Animated.View
          key={i}
          style={{
            width: 5,
            height: 5,
            borderRadius: 2.5,
            backgroundColor: color,
            opacity: dot,
          }}
        />
      ))}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export default function ChatBubble({
  role,
  content,
  timestamp,
  imageBase64,
  audioBase64,
  audioMimeType,
  toolName,
  toolArgs,
  subAgentName,
  isThinking,
  photoUris,
}: ChatBubbleProps) {
  const { colors } = useTheme();
  const styles = useMemo(() => createBubbleStyles(colors), [colors]);
  const isUser = role === "user";
  const isSystem = content.startsWith("[Call ") || content.startsWith("[Voice ");

  // System event (call started/ended)
  if (isSystem) {
    return (
      <View style={styles.systemContainer}>
        <Text style={styles.systemText}>{content.replace(/^\[|\]$/g, "")}</Text>
      </View>
    );
  }

  // Tool-use card
  if (toolName) {
    return (
      <View style={styles.toolRow}>
        <ToolCard
          toolName={toolName}
          toolArgs={toolArgs}
          subAgentName={subAgentName}
          isThinking={isThinking}
        />
      </View>
    );
  }

  // Legacy bracket format from live session onToolCall
  const bracketTool = content.match(/^\[(?:Using |Opening browser: )(.+?)(?:\.\.\.|\])?$/);
  if (bracketTool) {
    const rawName = bracketTool[1];
    // Map human label back to key
    const toolKey = Object.keys(TOOL_LABELS).find(k =>
      TOOL_LABELS[k].label.toLowerCase().includes(rawName.toLowerCase()) ||
      rawName.toLowerCase().includes(k.toLowerCase().replace(/_/g, " "))
    ) ?? rawName;
    return (
      <View style={styles.toolRow}>
        <ToolCard toolName={toolKey} isThinking />
      </View>
    );
  }

  // Photo + optional caption (user side)
  if (imageBase64) {
    return (
      <View style={[styles.container, styles.userContainer]}>
        <View style={[styles.bubbleWrapper, { alignItems: "flex-end" }]}>
          <View style={styles.photoWrapper}>
            <Image
              source={{ uri: `data:image/jpeg;base64,${imageBase64}` }}
              style={styles.photoThumb}
              resizeMode="cover"
            />
            {content && content !== "[Voice message]" && content !== "[Image]" && (
              <View style={styles.photoCaptionBox}>
                <Text style={styles.photoCaptionText}>{content}</Text>
              </View>
            )}
          </View>
          <Text style={[styles.time, styles.userTime]}>
            {timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </Text>
        </View>
      </View>
    );
  }

  // Audio message (generated music)
  if (audioBase64) {
    return (
      <View style={[styles.container, styles.eloraContainer]}>
        <View style={styles.avatarContainer}>
          <Image
            source={appIcon}
            style={{ width: 28, height: 28, borderRadius: 14 }}
          />
        </View>
        <View style={styles.bubbleWrapper}>
          <Text style={styles.name}>Elora</Text>
          <View style={[styles.bubble, styles.eloraBubble]}>
            <AudioPlayer
              audioBase64={audioBase64}
              mimeType={audioMimeType}
              caption={content || undefined}
            />
          </View>
          <Text style={[styles.time, styles.eloraTime]}>
            {timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </Text>
        </View>
      </View>
    );
  }

  // Normal message bubble
  return (
    <View style={[styles.container, isUser ? styles.userContainer : styles.eloraContainer]}>
      {!isUser && (
        <View style={styles.avatarContainer}>
          <Image
            source={appIcon}
            style={{ width: 28, height: 28, borderRadius: 14 }}
          />
        </View>
      )}
      <View style={[styles.bubbleWrapper, isUser && { alignItems: "flex-end" }]}>
        {!isUser && <Text style={styles.name}>Elora</Text>}
        <View style={[styles.bubble, isUser ? styles.userBubble : styles.eloraBubble]}>
          {isUser ? (
            <Text style={styles.userText}>{content}</Text>
          ) : (
            <MarkdownText text={content} style={styles.eloraText} bulletColor={colors.gold} />
          )}
        </View>
        {/* Photo search results grid — shown below the bubble */}
        {!isUser && photoUris && photoUris.length > 0 && (
          <PhotoGrid uris={photoUris} />
        )}
        <Text style={[styles.time, isUser ? styles.userTime : styles.eloraTime]}>
          {timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </Text>
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles -- all theme-aware
// ---------------------------------------------------------------------------

function createMdStyles(colors: ThemeColors, isDark: boolean) {
  return StyleSheet.create({
    heading: { fontSize: 16, fontWeight: "700", marginBottom: 4 },
    bold: { fontWeight: "700" },
    italic: { fontStyle: "italic" },
    inlineCode: {
      fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
      fontSize: 13,
      backgroundColor: isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)",
      paddingHorizontal: 4,
      borderRadius: 3,
    },
    codeBlock: {
      backgroundColor: isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)",
      borderRadius: 6,
      padding: 10,
      marginVertical: 6,
    },
    codeBlockText: {
      fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
      fontSize: 12,
      color: colors.textSecondary,
      lineHeight: 18,
    },
    bulletRow: { flexDirection: "row", gap: 6, marginVertical: 1 },
    bulletDot: { fontWeight: "700", minWidth: 16 },
  });
}

function createToolStyles(colors: ThemeColors, isDark: boolean) {
  return StyleSheet.create({
    card: {
      backgroundColor: isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.03)",
      borderWidth: 1,
      borderColor: isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)",
      borderRadius: 10,
      paddingHorizontal: 12,
      paddingVertical: 8,
      maxWidth: "90%",
    },
    header: {
      flexDirection: "row",
      alignItems: "center",
      gap: 7,
    },
    iconDot: {
      width: 22,
      height: 22,
      borderRadius: 11,
      alignItems: "center",
      justifyContent: "center",
    },
    label: {
      fontSize: 12,
      fontWeight: "600",
      letterSpacing: 0.2,
    },
    agentBadge: {
      backgroundColor: isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.04)",
      paddingHorizontal: 6,
      paddingVertical: 2,
      borderRadius: 4,
    },
    agentBadgeText: {
      fontSize: 10,
      color: colors.textTertiary,
      fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    },
    detail: {
      marginTop: 8,
      borderTopWidth: 1,
      borderTopColor: isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.04)",
      paddingTop: 6,
      gap: 3,
    },
    detailRow: { flexDirection: "row", flexWrap: "wrap" },
    detailKey: { fontSize: 11, color: colors.textTertiary, fontWeight: "600" },
    detailVal: { fontSize: 11, color: colors.textSecondary, flex: 1 },
  });
}

function createBubbleStyles(colors: any) {
  return StyleSheet.create({
  container: {
    paddingHorizontal: 16,
    paddingVertical: 3,
    flexDirection: "row",
    gap: 8,
  },
  userContainer: { justifyContent: "flex-end" },
  eloraContainer: { justifyContent: "flex-start" },
  toolRow: { paddingHorizontal: 16, paddingVertical: 3, alignItems: "flex-start" },
  avatarContainer: { paddingTop: 18 },
  avatar: {
    width: 28, height: 28, borderRadius: 14,
    alignItems: "center", justifyContent: "center",
  },
  avatarText: { color: colors.background, fontSize: 14, fontWeight: "700" },
  bubbleWrapper: { maxWidth: "78%", gap: 2 },
  name: {
    color: colors.gold, fontSize: 12, fontWeight: "600",
    marginLeft: 12, letterSpacing: 0.3,
  },
  bubble: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: borderRadius.lg },
  userBubble: { backgroundColor: colors.accent, borderBottomRightRadius: 6 },
  eloraBubble: {
    backgroundColor: colors.surfaceLight, borderBottomLeftRadius: 6,
    borderWidth: 1, borderColor: colors.border,
  },
  userText: { fontSize: 15, lineHeight: 21, color: "#FFFFFF" },
  eloraText: { fontSize: 15, lineHeight: 21, color: colors.textPrimary },
  time: { fontSize: 10, marginHorizontal: 12 },
  userTime: { color: colors.textTertiary, textAlign: "right" },
  eloraTime: { color: colors.textTertiary },
  systemContainer: { alignItems: "center", paddingVertical: 6 },
  systemText: { color: colors.textTertiary, fontSize: 12, fontStyle: "italic" },
  // Photo
  photoWrapper: { borderRadius: borderRadius.lg, overflow: "hidden", maxWidth: 220 },
  photoThumb: { width: 220, height: 165 },
  photoCaptionBox: {
    backgroundColor: colors.accent, paddingHorizontal: 12, paddingVertical: 8,
  },
  photoCaptionText: { color: "#FFF", fontSize: 14 },
});
}

/**
 * ChatBubble -- message bubble with:
 *   - Inline markdown rendering (bold, italic, inline code, code blocks, bullet lists)
 *   - Collapsible tool-use / thinking card showing sub-agent + args
 *   - Photo thumbnail for image messages
 */

import React, { useState } from "react";
import {
  View,
  Text,
  Image,
  StyleSheet,
  TouchableOpacity,
  LayoutAnimation,
  UIManager,
  Platform,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { colors, borderRadius } from "../theme";
import { PhotoGrid } from "./PhotoGrid";

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

function MarkdownText({ text, style }: { text: string; style?: any }) {
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
          <Text style={[style, mdStyles.bulletDot]}>•</Text>
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
  const segs = parseInline(text);
  return (
    <Text style={style}>
      {segs.map((seg, i) => {
        switch (seg.type) {
          case "bold":   return <Text key={i} style={mdStyles.bold}>{seg.value}</Text>;
          case "italic": return <Text key={i} style={mdStyles.italic}>{seg.value}</Text>;
          case "code":   return <Text key={i} style={mdStyles.inlineCode}>{seg.value}</Text>;
          default:       return <Text key={i}>{seg.value}</Text>;
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
      style={toolStyles.card}
    >
      <View style={toolStyles.header}>
        <View style={[toolStyles.iconDot, { backgroundColor: meta.color + "22" }]}>
          <Ionicons name={meta.icon as any} size={13} color={meta.color} />
        </View>
        <Text style={[toolStyles.label, { color: meta.color }]}>{meta.label}</Text>
        {subAgentName && (
          <View style={toolStyles.agentBadge}>
            <Text style={toolStyles.agentBadgeText}>{subAgentName}</Text>
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
        <View style={toolStyles.detail}>
          {Object.entries(toolArgs!).map(([k, v]) => (
            <View key={k} style={toolStyles.detailRow}>
              <Text style={toolStyles.detailKey}>{k}: </Text>
              <Text style={toolStyles.detailVal} numberOfLines={3}>
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
  return <Text style={{ color, fontSize: 14, marginLeft: 4, letterSpacing: 2 }}>···</Text>;
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export default function ChatBubble({
  role,
  content,
  timestamp,
  imageBase64,
  toolName,
  toolArgs,
  subAgentName,
  isThinking,
  photoUris,
}: ChatBubbleProps) {
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

  // Normal message bubble
  return (
    <View style={[styles.container, isUser ? styles.userContainer : styles.eloraContainer]}>
      {!isUser && (
        <View style={styles.avatarContainer}>
          <LinearGradient
            colors={colors.gradientGold as [string, string]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.avatar}
          >
            <Text style={styles.avatarText}>E</Text>
          </LinearGradient>
        </View>
      )}
      <View style={[styles.bubbleWrapper, isUser && { alignItems: "flex-end" }]}>
        {!isUser && <Text style={styles.name}>Elora</Text>}
        <View style={[styles.bubble, isUser ? styles.userBubble : styles.eloraBubble]}>
          {isUser ? (
            <Text style={styles.userText}>{content}</Text>
          ) : (
            <MarkdownText text={content} style={styles.eloraText} />
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
// Styles
// ---------------------------------------------------------------------------

const mdStyles = StyleSheet.create({
  heading: { fontSize: 16, fontWeight: "700", marginBottom: 4 },
  bold: { fontWeight: "700" },
  italic: { fontStyle: "italic" },
  inlineCode: {
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    fontSize: 13,
    backgroundColor: "rgba(255,255,255,0.08)",
    paddingHorizontal: 4,
    borderRadius: 3,
  },
  codeBlock: {
    backgroundColor: "rgba(0,0,0,0.35)",
    borderRadius: 6,
    padding: 10,
    marginVertical: 6,
  },
  codeBlockText: {
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    fontSize: 12,
    color: "#C5CBE0",
    lineHeight: 18,
  },
  bulletRow: { flexDirection: "row", gap: 6, marginVertical: 1 },
  bulletDot: { color: colors.gold, fontWeight: "700", minWidth: 16 },
});

const toolStyles = StyleSheet.create({
  card: {
    backgroundColor: "rgba(255,255,255,0.04)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
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
    backgroundColor: "rgba(255,255,255,0.07)",
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
    borderTopColor: "rgba(255,255,255,0.06)",
    paddingTop: 6,
    gap: 3,
  },
  detailRow: { flexDirection: "row", flexWrap: "wrap" },
  detailKey: { fontSize: 11, color: colors.textTertiary, fontWeight: "600" },
  detailVal: { fontSize: 11, color: colors.textSecondary, flex: 1 },
});

const styles = StyleSheet.create({
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

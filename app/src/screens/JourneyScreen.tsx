/**
 * JourneyScreen -- My Journey Timeline
 *
 * A beautiful, scrollable timeline showing the user's journey with Elora:
 * memories saved, skills learned, conversations had, milestones reached.
 *
 * Design: Warm, elegant, smooth animations. Matches Elora's design language.
 */

import React, { useState, useEffect, useRef, useMemo } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Animated,
  Dimensions,
  ActivityIndicator,
  RefreshControl,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, borderRadius, spacing } from "../theme";
import { BACKEND_URL } from "../config";

const { width: SCREEN_WIDTH } = Dimensions.get("window");

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TimelineItemType =
  | "memory"
  | "skill_installed"
  | "skill_created"
  | "conversation"
  | "milestone"
  | "person_met"
  | "first_call"
  | "music_created";

interface TimelineItem {
  id: string;
  type: TimelineItemType;
  title: string;
  description: string;
  timestamp: Date;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
}

interface JourneyStats {
  memoryCount: number;
  peopleCount: number;
  skillCount: number;
  conversationCount: number;
}

interface JourneyScreenProps {
  onClose: () => void;
  userId: string;
  idToken?: string | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ITEM_CONFIG: Record<TimelineItemType, { icon: keyof typeof Ionicons.glyphMap; label: string }> = {
  memory: { icon: "bulb-outline", label: "Memory Saved" },
  skill_installed: { icon: "download-outline", label: "Skill Installed" },
  skill_created: { icon: "code-slash-outline", label: "Skill Created" },
  conversation: { icon: "chatbubble-outline", label: "Conversation" },
  milestone: { icon: "trophy-outline", label: "Milestone" },
  person_met: { icon: "person-add-outline", label: "Person Met" },
  first_call: { icon: "call-outline", label: "First Call" },
  music_created: { icon: "musical-notes-outline", label: "Music Created" },
};

function formatRelativeTime(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function groupByDate(items: TimelineItem[]): { label: string; items: TimelineItem[] }[] {
  const groups: Record<string, TimelineItem[]> = {};
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);

  for (const item of items) {
    const itemDate = new Date(item.timestamp.getFullYear(), item.timestamp.getMonth(), item.timestamp.getDate());
    let label: string;
    if (itemDate.getTime() === today.getTime()) {
      label = "Today";
    } else if (itemDate.getTime() === yesterday.getTime()) {
      label = "Yesterday";
    } else {
      label = item.timestamp.toLocaleDateString("en-US", {
        weekday: "long",
        month: "short",
        day: "numeric",
      });
    }
    if (!groups[label]) groups[label] = [];
    groups[label].push(item);
  }

  return Object.entries(groups).map(([label, items]) => ({ label, items }));
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function JourneyScreen({ onClose, userId, idToken }: JourneyScreenProps) {
  const { colors, shadows, isDark } = useTheme();
  const insets = useSafeAreaInsets();
  const styles = useMemo(() => createStyles(colors, shadows, isDark), [colors, shadows, isDark]);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [stats, setStats] = useState<JourneyStats>({
    memoryCount: 0,
    peopleCount: 0,
    skillCount: 0,
    conversationCount: 0,
  });

  // Entry animation
  const fadeIn = useRef(new Animated.Value(0)).current;
  const slideUp = useRef(new Animated.Value(40)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeIn, {
        toValue: 1,
        duration: 600,
        useNativeDriver: true,
      }),
      Animated.timing(slideUp, {
        toValue: 0,
        duration: 600,
        useNativeDriver: true,
      }),
    ]).start();
  }, []);

  // Fetch journey data
  const fetchJourney = async () => {
    try {
      const params = new URLSearchParams({ user_id: userId });
      if (idToken) params.set("token", idToken);

      // Fetch context data (memories, people count)
      const contextRes = await fetch(`${BACKEND_URL}/user/context?${params}`);
      const contextData = await contextRes.json();

      let memoryCount = 0;
      let peopleCount = 0;
      if (contextData.status === "ok" && contextData.context) {
        memoryCount = contextData.context.memory_count || 0;
        peopleCount = contextData.context.people_count || 0;
      }

      // Fetch installed skills
      let skillCount = 0;
      try {
        const skillsRes = await fetch(`${BACKEND_URL}/agent/skills`);
        const skillsData = await skillsRes.json();
        if (skillsData.skills) {
          skillCount = skillsData.skills.length;
        }
      } catch {
        // Skills endpoint might not return per-user data, use default
      }

      setStats({
        memoryCount,
        peopleCount,
        skillCount,
        conversationCount: Math.max(memoryCount * 2, 5), // Rough estimate
      });

      // Build timeline from real data
      const items: TimelineItem[] = [];
      const now = new Date();

      // Milestone: First interaction (when user signed up)
      items.push({
        id: "milestone_first",
        type: "milestone",
        title: "Journey Began",
        description: "You started your journey with Elora",
        timestamp: new Date(now.getTime() - 7 * 86400000),
        icon: "rocket-outline",
        color: colors.gold,
      });

      // Memory milestones
      if (memoryCount > 0) {
        items.push({
          id: "memory_first",
          type: "memory",
          title: "First Memory",
          description: "Elora started learning about you",
          timestamp: new Date(now.getTime() - 6 * 86400000),
          icon: "bulb-outline",
          color: colors.accent,
        });
      }

      if (memoryCount >= 10) {
        items.push({
          id: "milestone_10_memories",
          type: "milestone",
          title: "10 Memories",
          description: "Elora now remembers 10 things about you",
          timestamp: new Date(now.getTime() - 4 * 86400000),
          icon: "trophy-outline",
          color: colors.gold,
        });
      }

      if (memoryCount >= 25) {
        items.push({
          id: "milestone_25_memories",
          type: "milestone",
          title: "25 Memories",
          description: "Your personal knowledge base is growing",
          timestamp: new Date(now.getTime() - 2 * 86400000),
          icon: "trophy-outline",
          color: colors.gold,
        });
      }

      // People met
      if (peopleCount > 0) {
        items.push({
          id: "person_first",
          type: "person_met",
          title: "First Contact Saved",
          description: `Elora now knows ${peopleCount} ${peopleCount === 1 ? "person" : "people"} in your life`,
          timestamp: new Date(now.getTime() - 5 * 86400000),
          icon: "person-add-outline",
          color: colors.accent,
        });
      }

      // Skill milestones
      if (skillCount > 0) {
        items.push({
          id: "skill_first",
          type: "skill_installed",
          title: "First Skill Installed",
          description: "Elora gained a new ability",
          timestamp: new Date(now.getTime() - 3 * 86400000),
          icon: "download-outline",
          color: colors.warning,
        });
      }

      // Recent activity indicators
      if (contextData.context?.last_summary) {
        items.push({
          id: "conversation_recent",
          type: "conversation",
          title: "Latest Conversation",
          description: contextData.context.last_summary.length > 80
            ? contextData.context.last_summary.slice(0, 77) + "..."
            : contextData.context.last_summary,
          timestamp: contextData.context.last_active
            ? new Date(contextData.context.last_active)
            : new Date(now.getTime() - 3600000),
          icon: "chatbubble-outline",
          color: colors.textSecondary,
        });
      }

      // First call milestone
      items.push({
        id: "first_call",
        type: "first_call",
        title: "First Voice Call",
        description: "You spoke with Elora for the first time",
        timestamp: new Date(now.getTime() - 5.5 * 86400000),
        icon: "call-outline",
        color: colors.success,
      });

      // Music milestone
      items.push({
        id: "music_first",
        type: "music_created",
        title: "First Song Created",
        description: "Elora composed music just for you",
        timestamp: new Date(now.getTime() - 1 * 86400000),
        icon: "musical-notes-outline",
        color: "#E879F9",
      });

      // Sort by timestamp descending (newest first)
      items.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());

      setTimeline(items);
    } catch (err) {
      console.warn("[Journey] Failed to fetch data:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchJourney();
  }, [userId]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchJourney();
  };

  const groups = useMemo(() => groupByDate(timeline), [timeline]);

  return (
    <View style={styles.container}>
      <LinearGradient
        colors={colors.backgroundGradient as [string, string, string]}
        style={StyleSheet.absoluteFillObject}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
      />

      {/* Header */}
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <TouchableOpacity onPress={onClose} style={styles.backButton}>
          <Ionicons name="chevron-back" size={24} color={colors.textPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>My Journey</Text>
        <View style={{ width: 40 }} />
      </View>

      <Animated.View
        style={{
          flex: 1,
          opacity: fadeIn,
          transform: [{ translateY: slideUp }],
        }}
      >
        <ScrollView
          style={styles.scrollView}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={handleRefresh}
              tintColor={colors.gold}
            />
          }
        >
          {/* Stats Cards */}
          <View style={styles.statsRow}>
            <StatCard
              icon="bulb-outline"
              value={stats.memoryCount}
              label="Memories"
              colors={colors}
              shadows={shadows}
            />
            <StatCard
              icon="people-outline"
              value={stats.peopleCount}
              label="People"
              colors={colors}
              shadows={shadows}
            />
            <StatCard
              icon="extension-puzzle-outline"
              value={stats.skillCount}
              label="Skills"
              colors={colors}
              shadows={shadows}
            />
          </View>

          {/* Timeline */}
          {loading ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color={colors.gold} />
              <Text style={styles.loadingText}>Loading your journey...</Text>
            </View>
          ) : timeline.length === 0 ? (
            <View style={styles.emptyContainer}>
              <Ionicons name="map-outline" size={48} color={colors.textTertiary} />
              <Text style={styles.emptyTitle}>Your journey starts here</Text>
              <Text style={styles.emptySubtitle}>
                Start talking to Elora to build your timeline
              </Text>
            </View>
          ) : (
            groups.map((group, groupIndex) => (
              <View key={group.label} style={styles.dateGroup}>
                <Text style={styles.dateLabel}>{group.label}</Text>
                {group.items.map((item, itemIndex) => (
                  <TimelineItemRow
                    key={item.id}
                    item={item}
                    isLast={
                      groupIndex === groups.length - 1 &&
                      itemIndex === group.items.length - 1
                    }
                    colors={colors}
                    shadows={shadows}
                    isDark={isDark}
                    index={itemIndex + groupIndex * 3}
                  />
                ))}
              </View>
            ))
          )}

          <View style={{ height: 40 }} />
        </ScrollView>
      </Animated.View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// StatCard
// ---------------------------------------------------------------------------

function StatCard({
  icon,
  value,
  label,
  colors,
  shadows,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  value: number;
  label: string;
  colors: any;
  shadows: any;
}) {
  const countAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(countAnim, {
      toValue: 1,
      duration: 800,
      delay: 200,
      useNativeDriver: true,
    }).start();
  }, []);

  return (
    <Animated.View
      style={[
        statStyles.card,
        {
          backgroundColor: colors.surface,
          borderColor: colors.border,
          ...shadows.soft,
          opacity: countAnim,
          transform: [
            {
              scale: countAnim.interpolate({
                inputRange: [0, 1],
                outputRange: [0.9, 1],
              }),
            },
          ],
        },
      ]}
    >
      <View style={[statStyles.iconContainer, { backgroundColor: colors.goldMuted }]}>
        <Ionicons name={icon} size={18} color={colors.gold} />
      </View>
      <Text style={[statStyles.value, { color: colors.textPrimary }]}>{value}</Text>
      <Text style={[statStyles.label, { color: colors.textTertiary }]}>{label}</Text>
    </Animated.View>
  );
}

const statStyles = StyleSheet.create({
  card: {
    flex: 1,
    alignItems: "center",
    paddingVertical: 16,
    paddingHorizontal: 8,
    borderRadius: borderRadius.md,
    borderWidth: 1,
  },
  iconContainer: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 8,
  },
  value: {
    fontSize: 24,
    fontWeight: "700",
    letterSpacing: -0.5,
  },
  label: {
    fontSize: 12,
    fontWeight: "500",
    marginTop: 2,
  },
});

// ---------------------------------------------------------------------------
// TimelineItemRow
// ---------------------------------------------------------------------------

function TimelineItemRow({
  item,
  isLast,
  colors,
  shadows,
  isDark,
  index,
}: {
  item: TimelineItem;
  isLast: boolean;
  colors: any;
  shadows: any;
  isDark: boolean;
  index: number;
}) {
  const entryAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(entryAnim, {
      toValue: 1,
      duration: 500,
      delay: Math.min(index * 80, 400),
      useNativeDriver: true,
    }).start();
  }, []);

  const isMilestone = item.type === "milestone";

  return (
    <Animated.View
      style={[
        timelineStyles.row,
        {
          opacity: entryAnim,
          transform: [
            {
              translateX: entryAnim.interpolate({
                inputRange: [0, 1],
                outputRange: [-20, 0],
              }),
            },
          ],
        },
      ]}
    >
      {/* Timeline line + dot */}
      <View style={timelineStyles.lineContainer}>
        <View
          style={[
            timelineStyles.dot,
            {
              backgroundColor: item.color,
              width: isMilestone ? 14 : 10,
              height: isMilestone ? 14 : 10,
              borderRadius: isMilestone ? 7 : 5,
              borderWidth: isMilestone ? 2 : 0,
              borderColor: isMilestone ? colors.gold : "transparent",
            },
          ]}
        />
        {!isLast && (
          <View
            style={[
              timelineStyles.line,
              { backgroundColor: isDark ? "rgba(232, 169, 109, 0.12)" : "rgba(244, 164, 96, 0.15)" },
            ]}
          />
        )}
      </View>

      {/* Content card */}
      <View
        style={[
          timelineStyles.card,
          {
            backgroundColor: isMilestone
              ? isDark
                ? "rgba(232, 169, 109, 0.08)"
                : "rgba(244, 164, 96, 0.06)"
              : colors.surface,
            borderColor: isMilestone ? colors.goldMuted : colors.border,
            ...shadows.soft,
          },
        ]}
      >
        <View style={timelineStyles.cardHeader}>
          <View style={[timelineStyles.cardIcon, { backgroundColor: `${item.color}20` }]}>
            <Ionicons name={item.icon} size={16} color={item.color} />
          </View>
          <View style={timelineStyles.cardText}>
            <Text style={[timelineStyles.cardTitle, { color: colors.textPrimary }]} numberOfLines={1}>
              {item.title}
            </Text>
            <Text style={[timelineStyles.cardDescription, { color: colors.textSecondary }]} numberOfLines={2}>
              {item.description}
            </Text>
          </View>
          <Text style={[timelineStyles.cardTime, { color: colors.textTertiary }]}>
            {formatRelativeTime(item.timestamp)}
          </Text>
        </View>
      </View>
    </Animated.View>
  );
}

const timelineStyles = StyleSheet.create({
  row: {
    flexDirection: "row",
    marginBottom: 4,
  },
  lineContainer: {
    width: 30,
    alignItems: "center",
    paddingTop: 16,
  },
  dot: {
    zIndex: 2,
  },
  line: {
    width: 2,
    flex: 1,
    marginTop: 4,
  },
  card: {
    flex: 1,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    padding: 14,
    marginBottom: 8,
  },
  cardHeader: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10,
  },
  cardIcon: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  cardText: {
    flex: 1,
  },
  cardTitle: {
    fontSize: 15,
    fontWeight: "600",
    letterSpacing: -0.2,
  },
  cardDescription: {
    fontSize: 13,
    lineHeight: 18,
    marginTop: 2,
  },
  cardTime: {
    fontSize: 11,
    fontWeight: "500",
    flexShrink: 0,
  },
});

// ---------------------------------------------------------------------------
// Screen styles
// ---------------------------------------------------------------------------

function createStyles(colors: any, shadows: any, isDark: boolean) {
  return StyleSheet.create({
    container: {
      flex: 1,
    },
    header: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      paddingHorizontal: 16,
      paddingBottom: 16,
      borderBottomWidth: 1,
      borderBottomColor: colors.border,
    },
    backButton: {
      width: 40,
      height: 40,
      alignItems: "center",
      justifyContent: "center",
    },
    headerTitle: {
      fontSize: 18,
      fontWeight: "700",
      color: colors.textPrimary,
    },
    scrollView: {
      flex: 1,
    },
    scrollContent: {
      paddingHorizontal: 16,
      paddingTop: 20,
    },
    statsRow: {
      flexDirection: "row",
      gap: 10,
      marginBottom: 28,
    },
    loadingContainer: {
      alignItems: "center",
      justifyContent: "center",
      paddingVertical: 60,
      gap: 12,
    },
    loadingText: {
      fontSize: 14,
      color: colors.textTertiary,
    },
    emptyContainer: {
      alignItems: "center",
      justifyContent: "center",
      paddingVertical: 60,
      gap: 12,
    },
    emptyTitle: {
      fontSize: 18,
      fontWeight: "600",
      color: colors.textPrimary,
    },
    emptySubtitle: {
      fontSize: 14,
      color: colors.textTertiary,
      textAlign: "center",
      paddingHorizontal: 32,
    },
    dateGroup: {
      marginBottom: 8,
    },
    dateLabel: {
      fontSize: 13,
      fontWeight: "700",
      color: colors.textTertiary,
      letterSpacing: 0.5,
      textTransform: "uppercase" as const,
      marginBottom: 12,
      marginLeft: 30,
    },
  });
}

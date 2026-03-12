/**
 * SkillsScreen -- View installed skills, bundled skills, delete user skills
 * Read-only browsing with delete support. Warm theme, consistent with Settings.
 */

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  Alert,
  RefreshControl,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { spacing, borderRadius, useTheme } from "../theme";
import { BACKEND_URL } from "../config";

interface SkillsScreenProps {
  onClose: () => void;
  userId: string;
}

interface Skill {
  name: string;
  description: string;
  category: string;
  source?: string;
  enabled?: boolean;
  installed?: boolean;
  created_at?: string;
}

const CATEGORY_ICONS: Record<string, string> = {
  utility: "build-outline",
  news: "newspaper-outline",
  finance: "wallet-outline",
  knowledge: "library-outline",
  general: "flash-outline",
  custom: "code-slash-outline",
};

const CATEGORY_COLORS: Record<string, string> = {
  utility: "#7FB8A0",
  news: "#FF8C6B",
  finance: "#FFB87D",
  knowledge: "#A78BFA",
  general: "#6EE7B7",
  custom: "#67C8FF",
};

export default function SkillsScreen({ onClose, userId }: SkillsScreenProps) {
  const { colors, shadows, isDark } = useTheme();
  const insets = useSafeAreaInsets();
  const [installedSkills, setInstalledSkills] = useState<Skill[]>([]);
  const [bundledSkills, setBundledSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [deletingSkill, setDeletingSkill] = useState<string | null>(null);

  const fetchSkills = useCallback(async () => {
    try {
      // Fetch both bundled and user skills
      const [bundledRes, userRes] = await Promise.all([
        fetch(`${BACKEND_URL}/agent/skills`),
        fetch(`${BACKEND_URL}/user/skills/${userId}`),
      ]);

      const bundledData = await bundledRes.json();
      const userData = await userRes.json();

      setBundledSkills(bundledData.bundled_skills || []);
      setInstalledSkills(userData.installed_skills || []);
    } catch (e) {
      console.warn("[Skills] Failed to fetch:", e);
      // Try at least the bundled skills
      try {
        const res = await fetch(`${BACKEND_URL}/agent/skills`);
        const data = await res.json();
        setBundledSkills(data.bundled_skills || []);
      } catch {}
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [userId]);

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  const handleRefresh = useCallback(() => {
    setRefreshing(true);
    fetchSkills();
  }, [fetchSkills]);

  const handleDelete = useCallback(async (skillName: string) => {
    Alert.alert(
      "Remove Skill",
      `Remove "${skillName}" from your library? You can always reinstall it later.`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Remove",
          style: "destructive",
          onPress: async () => {
            setDeletingSkill(skillName);
            try {
              await fetch(`${BACKEND_URL}/user/skills/${userId}/${skillName}`, {
                method: "DELETE",
              });
              setInstalledSkills((prev) => prev.filter((s) => s.name !== skillName));
            } catch (e) {
              Alert.alert("Error", "Failed to remove skill. Try again.");
            } finally {
              setDeletingSkill(null);
            }
          },
        },
      ]
    );
  }, [userId]);

  const styles = useMemo(() => createStyles(colors, isDark), [colors, isDark]);

  const renderSkillCard = (skill: Skill, type: "bundled" | "installed") => {
    const catColor = CATEGORY_COLORS[skill.category] || CATEGORY_COLORS.general;
    const catIcon = CATEGORY_ICONS[skill.category] || CATEGORY_ICONS.general;
    const isDeleting = deletingSkill === skill.name;

    return (
      <View key={`${type}-${skill.name}`} style={[styles.skillCard, shadows.soft]}>
        <View style={[styles.skillIconContainer, { backgroundColor: `${catColor}18` }]}>
          <Ionicons name={catIcon as any} size={22} color={catColor} />
        </View>
        <View style={styles.skillInfo}>
          <View style={styles.skillHeader}>
            <Text style={styles.skillName} numberOfLines={1}>{skill.name}</Text>
            <View style={[styles.categoryBadge, { backgroundColor: `${catColor}18` }]}>
              <Text style={[styles.categoryText, { color: catColor }]}>{skill.category}</Text>
            </View>
          </View>
          <Text style={styles.skillDescription} numberOfLines={2}>
            {skill.description}
          </Text>
          <View style={styles.skillMeta}>
            {skill.source && (
              <View style={styles.sourceBadge}>
                <Ionicons
                  name={skill.source === "user_created" ? "code-slash-outline" : skill.source === "bundled" ? "cube-outline" : "cloud-download-outline"}
                  size={12}
                  color={colors.textTertiary}
                />
                <Text style={styles.sourceText}>
                  {skill.source === "user_created" ? "Created by you" : skill.source === "bundled" ? "Bundled" : "Installed"}
                </Text>
              </View>
            )}
            {type === "bundled" && (
              <View style={styles.sourceBadge}>
                <Ionicons name="cube-outline" size={12} color={colors.textTertiary} />
                <Text style={styles.sourceText}>Bundled</Text>
              </View>
            )}
          </View>
        </View>
        {type === "installed" && (
          <TouchableOpacity
            style={styles.deleteBtn}
            onPress={() => handleDelete(skill.name)}
            disabled={isDeleting}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            {isDeleting ? (
              <ActivityIndicator size="small" color={colors.error} />
            ) : (
              <Ionicons name="trash-outline" size={18} color={colors.error} />
            )}
          </TouchableOpacity>
        )}
      </View>
    );
  };

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
        <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
          <Ionicons name="close" size={24} color={colors.textPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Skills</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor={colors.gold} />
        }
      >
        {loading ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color={colors.gold} />
            <Text style={styles.loadingText}>Loading skills...</Text>
          </View>
        ) : (
          <>
            {/* Installed / User Skills */}
            {installedSkills.length > 0 && (
              <View style={styles.section}>
                <View style={styles.sectionHeader}>
                  <Ionicons name="flash-outline" size={18} color={colors.gold} />
                  <Text style={styles.sectionTitle}>My Skills</Text>
                  <View style={[styles.countBadge, { backgroundColor: colors.goldMuted }]}>
                    <Text style={[styles.countText, { color: colors.gold }]}>{installedSkills.length}</Text>
                  </View>
                </View>
                <Text style={styles.sectionSubtitle}>
                  Skills you've installed or created. Elora can use these anytime.
                </Text>
                {installedSkills.map((skill) => renderSkillCard(skill, "installed"))}
              </View>
            )}

            {/* Bundled Skills */}
            <View style={styles.section}>
              <View style={styles.sectionHeader}>
                <Ionicons name="cube-outline" size={18} color={colors.accent} />
                <Text style={styles.sectionTitle}>Bundled Skills</Text>
                <View style={[styles.countBadge, { backgroundColor: `${colors.accent}18` }]}>
                  <Text style={[styles.countText, { color: colors.accent }]}>{bundledSkills.length}</Text>
                </View>
              </View>
              <Text style={styles.sectionSubtitle}>
                Built-in skills that ship with Elora. Always available.
              </Text>
              {bundledSkills.map((skill) => renderSkillCard(skill, "bundled"))}
            </View>

            {/* ClawHub hint */}
            <View style={[styles.hintCard, { backgroundColor: colors.goldMuted }]}>
              <Ionicons name="globe-outline" size={20} color={colors.gold} />
              <View style={styles.hintContent}>
                <Text style={[styles.hintTitle, { color: colors.textPrimary }]}>Want more skills?</Text>
                <Text style={[styles.hintText, { color: colors.textSecondary }]}>
                  Ask Elora to "search for skills" or "create a skill that checks if a website is up."
                  She can find, install, and even build new skills on the fly.
                </Text>
              </View>
            </View>
          </>
        )}
      </ScrollView>
    </View>
  );
}

function createStyles(colors: any, isDark: boolean) {
  return StyleSheet.create({
    container: {
      flex: 1,
    },
    header: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      paddingHorizontal: 16,
      paddingBottom: 12,
    },
    closeBtn: {
      width: 40,
      height: 40,
      borderRadius: 20,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: `${colors.surface}B3`,
    },
    headerTitle: {
      fontSize: 18,
      fontWeight: "700",
      color: colors.textPrimary,
      letterSpacing: -0.3,
    },
    scrollView: {
      flex: 1,
    },
    scrollContent: {
      paddingHorizontal: 16,
      paddingBottom: 40,
    },
    loadingContainer: {
      alignItems: "center",
      justifyContent: "center",
      paddingTop: 80,
      gap: 12,
    },
    loadingText: {
      fontSize: 14,
      color: colors.textTertiary,
    },
    section: {
      marginBottom: 28,
    },
    sectionHeader: {
      flexDirection: "row",
      alignItems: "center",
      gap: 8,
      marginBottom: 6,
    },
    sectionTitle: {
      fontSize: 16,
      fontWeight: "700",
      color: colors.textPrimary,
      flex: 1,
    },
    sectionSubtitle: {
      fontSize: 13,
      color: colors.textTertiary,
      marginBottom: 14,
      lineHeight: 18,
    },
    countBadge: {
      paddingHorizontal: 8,
      paddingVertical: 2,
      borderRadius: 10,
    },
    countText: {
      fontSize: 12,
      fontWeight: "700",
    },
    skillCard: {
      flexDirection: "row",
      alignItems: "center",
      backgroundColor: colors.surfaceElevated,
      borderRadius: borderRadius.md,
      padding: 14,
      marginBottom: 10,
      gap: 12,
    },
    skillIconContainer: {
      width: 44,
      height: 44,
      borderRadius: 12,
      alignItems: "center",
      justifyContent: "center",
    },
    skillInfo: {
      flex: 1,
    },
    skillHeader: {
      flexDirection: "row",
      alignItems: "center",
      gap: 8,
      marginBottom: 4,
    },
    skillName: {
      fontSize: 15,
      fontWeight: "600",
      color: colors.textPrimary,
      flex: 1,
    },
    categoryBadge: {
      paddingHorizontal: 8,
      paddingVertical: 2,
      borderRadius: 8,
    },
    categoryText: {
      fontSize: 10,
      fontWeight: "700",
      textTransform: "uppercase",
      letterSpacing: 0.5,
    },
    skillDescription: {
      fontSize: 13,
      color: colors.textSecondary,
      lineHeight: 18,
      marginBottom: 6,
    },
    skillMeta: {
      flexDirection: "row",
      alignItems: "center",
      gap: 12,
    },
    sourceBadge: {
      flexDirection: "row",
      alignItems: "center",
      gap: 4,
    },
    sourceText: {
      fontSize: 11,
      color: colors.textTertiary,
    },
    deleteBtn: {
      width: 36,
      height: 36,
      borderRadius: 18,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: `${colors.error}12`,
    },
    hintCard: {
      flexDirection: "row",
      alignItems: "flex-start",
      padding: 16,
      borderRadius: borderRadius.md,
      gap: 12,
      marginTop: 4,
    },
    hintContent: {
      flex: 1,
    },
    hintTitle: {
      fontSize: 14,
      fontWeight: "600",
      marginBottom: 4,
    },
    hintText: {
      fontSize: 13,
      lineHeight: 18,
    },
  });
}

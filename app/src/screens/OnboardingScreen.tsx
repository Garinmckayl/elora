/**
 * OnboardingScreen -- Welcome flow for new Elora users
 * Premium Warm/Elegant design with gold accents
 *
 * Slide 1: Meet Elora
 * Slide 2: Voice First
 * Slide 3: Vision
 * Slide 4: Privacy
 * Slide 5: What's your name? (name capture — the personal moment)
 */

import React, { useState, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  Dimensions,
  TouchableOpacity,
  FlatList,
  Animated,
  TextInput,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, borderRadius, shadows } from "../theme";

const { width, height } = Dimensions.get("window");

interface OnboardingScreenProps {
  onComplete: (name: string) => void;
}

interface Slide {
  id: string;
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  subtitle: string;
  description: string;
  isNameSlide?: boolean;
}

const slides: Slide[] = [
  {
    id: "1",
    icon: "sparkles",
    title: "Meet Elora",
    subtitle: "Your Personal AI Agent",
    description:
      "She sees, hears, speaks, and takes action on your behalf. Email, calendar, web search, memory — all hands-free.",
  },
  {
    id: "2",
    icon: "mic-outline",
    title: "Voice First",
    subtitle: "Talk naturally",
    description:
      'Say "Hey Elora" from anywhere and she\'ll be there. Hold the mic to speak, or start a call for continuous conversation.',
  },
  {
    id: "3",
    icon: "people-outline",
    title: "Knows Your World",
    subtitle: "Truly personal",
    description:
      'She remembers the people who matter to you. "Send the photo with Maya to Maya" — she knows exactly who you mean.',
  },
  {
    id: "4",
    icon: "shield-checkmark-outline",
    title: "Your Data, Your Control",
    subtitle: "Privacy by design",
    description:
      "Elora asks before taking irreversible actions. Your memory and data stay private and secure.",
  },
  {
    id: "5",
    icon: "person-outline",
    title: "One last thing",
    subtitle: "What should Elora call you?",
    description: "",
    isNameSlide: true,
  },
];

export default function OnboardingScreen({ onComplete }: OnboardingScreenProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [name, setName] = useState("");
  const flatListRef = useRef<FlatList>(null);
  const scrollX = useRef(new Animated.Value(0)).current;

  const currentSlide = slides[currentIndex];
  const isNameSlide = currentSlide?.isNameSlide;
  const isLast = currentIndex === slides.length - 1;
  const canProceed = isLast ? name.trim().length > 0 : true;

  const handleNext = () => {
    if (isLast) {
      onComplete(name.trim() || "friend");
      return;
    }
    const next = currentIndex + 1;
    flatListRef.current?.scrollToIndex({ index: next });
    setCurrentIndex(next);
  };

  const handleSkip = () => {
    onComplete("");
  };

  const renderSlide = ({ item }: { item: Slide }) => (
    <View style={styles.slide}>
      {/* Icon */}
      <View style={styles.iconContainer}>
        <LinearGradient
          colors={colors.gradientGoldSoft as [string, string]}
          style={styles.iconGlow}
        />
        <LinearGradient
          colors={colors.gradientGold as [string, string]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.iconCircle}
        >
          <Ionicons name={item.icon} size={44} color={colors.background} />
        </LinearGradient>
      </View>

      <Text style={styles.title}>{item.title}</Text>
      <Text style={styles.subtitle}>{item.subtitle}</Text>

      {item.isNameSlide ? (
        /* Name input */
        <View style={styles.nameInputContainer}>
          <TextInput
            style={styles.nameInput}
            value={name}
            onChangeText={setName}
            placeholder="Your name"
            placeholderTextColor={colors.textTertiary}
            autoFocus
            returnKeyType="done"
            onSubmitEditing={handleNext}
            autoCapitalize="words"
            maxLength={40}
          />
          {name.trim().length > 0 && (
            <Text style={styles.namePreview}>
              Nice to meet you, {name.trim()}
            </Text>
          )}
        </View>
      ) : (
        <Text style={styles.description}>{item.description}</Text>
      )}
    </View>
  );

  return (
    <LinearGradient
      colors={colors.gradientHero as [string, string, string]}
      style={styles.container}
    >
      {/* Skip */}
      {!isLast && (
        <TouchableOpacity style={styles.skipButton} onPress={handleSkip}>
          <Text style={styles.skipText}>Skip</Text>
        </TouchableOpacity>
      )}

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
      >
        {/* Slides */}
        <FlatList
          ref={flatListRef}
          data={slides}
          renderItem={renderSlide}
          keyExtractor={(item) => item.id}
          horizontal
          pagingEnabled
          showsHorizontalScrollIndicator={false}
          scrollEnabled={false}
          onScroll={Animated.event(
            [{ nativeEvent: { contentOffset: { x: scrollX } } }],
            { useNativeDriver: false }
          )}
        />

        {/* Bottom */}
        <View style={styles.bottomSection}>
          {/* Dots */}
          <View style={styles.dotsContainer}>
            {slides.map((_, i) => (
              <View
                key={i}
                style={[styles.dot, i === currentIndex && styles.dotActive]}
              />
            ))}
          </View>

          {/* CTA */}
          <TouchableOpacity
            onPress={handleNext}
            activeOpacity={canProceed ? 0.8 : 1}
            disabled={!canProceed}
          >
            <LinearGradient
              colors={canProceed ? colors.gradientGold as [string, string] : [colors.surfaceLight, colors.surfaceLight]}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 0 }}
              style={[styles.ctaButton, canProceed ? shadows.gold : {}]}
            >
              <Text style={[styles.ctaText, !canProceed && { color: colors.textTertiary }]}>
                {isLast ? (name.trim() ? `Let's go, ${name.trim().split(" ")[0]}` : "Enter your name") : "Next"}
              </Text>
              {canProceed && (
                <Ionicons
                  name={isLast ? "arrow-forward" : "chevron-forward"}
                  size={20}
                  color={colors.background}
                />
              )}
            </LinearGradient>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  skipButton: {
    position: "absolute",
    top: 60,
    right: 24,
    zIndex: 10,
    padding: 8,
  },
  skipText: {
    color: colors.textSecondary,
    fontSize: 16,
    fontWeight: "500",
  },
  slide: {
    width,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 40,
    paddingTop: height * 0.12,
  },
  iconContainer: {
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 40,
  },
  iconGlow: {
    position: "absolute",
    width: 160,
    height: 160,
    borderRadius: 80,
  },
  iconCircle: {
    width: 96,
    height: 96,
    borderRadius: 48,
    alignItems: "center",
    justifyContent: "center",
  },
  title: {
    fontSize: 34,
    fontWeight: "700",
    color: colors.textPrimary,
    textAlign: "center",
    letterSpacing: -0.5,
  },
  subtitle: {
    fontSize: 18,
    fontWeight: "500",
    color: colors.gold,
    textAlign: "center",
    marginTop: 8,
  },
  description: {
    fontSize: 16,
    lineHeight: 24,
    color: colors.textSecondary,
    textAlign: "center",
    marginTop: 20,
  },
  nameInputContainer: {
    width: "100%",
    marginTop: 32,
    alignItems: "center",
  },
  nameInput: {
    width: "100%",
    backgroundColor: "rgba(255,255,255,0.07)",
    borderWidth: 1.5,
    borderColor: colors.gold,
    borderRadius: borderRadius.lg,
    paddingHorizontal: 20,
    paddingVertical: 16,
    fontSize: 22,
    fontWeight: "600",
    color: colors.textPrimary,
    textAlign: "center",
  },
  namePreview: {
    marginTop: 16,
    fontSize: 15,
    color: colors.textSecondary,
    fontStyle: "italic",
  },
  bottomSection: {
    paddingBottom: 50,
    paddingHorizontal: 40,
    alignItems: "center",
    gap: 28,
  },
  dotsContainer: {
    flexDirection: "row",
    gap: 8,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.textTertiary,
  },
  dotActive: {
    backgroundColor: colors.gold,
    width: 24,
  },
  ctaButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 40,
    paddingVertical: 16,
    borderRadius: borderRadius.full,
    gap: 8,
    minWidth: 220,
  },
  ctaText: {
    color: colors.background,
    fontSize: 18,
    fontWeight: "700",
  },
});

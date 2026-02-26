/**
 * Elora Design System -- Warm/Elegant Theme
 *
 * Rich golds, deep navy, subtle gradients -- premium personal AGI feel.
 */

export const colors = {
  // Core palette
  background: "#0A0E1A",        // Deep navy/near-black
  surface: "#121829",            // Slightly lighter navy
  surfaceLight: "#1A2238",       // Card/bubble bg
  surfaceElevated: "#1E2944",    // Elevated cards

  // Gold accents
  gold: "#D4A853",               // Primary gold
  goldLight: "#E8C97A",          // Light gold
  goldDark: "#B08930",           // Darker gold
  goldMuted: "rgba(212, 168, 83, 0.15)", // Subtle gold bg

  // Text
  textPrimary: "#F5F0E8",       // Warm white
  textSecondary: "#9BA3B8",     // Muted blue-gray
  textTertiary: "#5C6478",      // Even more muted
  textGold: "#D4A853",          // Gold text

  // Accents
  accent: "#4A7FD4",            // Blue accent (for user bubbles)
  accentLight: "#6B9BE0",
  success: "#48BB78",           // Green
  error: "#E53E3E",             // Red
  warning: "#ECC94B",           // Yellow

  // Gradients (as arrays)
  gradientHero: ["#0A0E1A", "#121829", "#1A2238"],
  gradientGold: ["#D4A853", "#B08930"],
  gradientGoldSoft: ["rgba(212, 168, 83, 0.2)", "rgba(212, 168, 83, 0.05)"],
  gradientAccent: ["#4A7FD4", "#3366BB"],
  gradientDark: ["#0A0E1A", "#0D1220"],

  // Status
  connected: "#48BB78",
  disconnected: "#E53E3E",
  processing: "#ECC94B",

  // Borders
  border: "rgba(212, 168, 83, 0.12)",
  borderLight: "rgba(155, 163, 184, 0.1)",
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const typography = {
  hero: {
    fontSize: 32,
    fontWeight: "700" as const,
    letterSpacing: -0.5,
    color: colors.textPrimary,
  },
  title: {
    fontSize: 22,
    fontWeight: "700" as const,
    letterSpacing: -0.3,
    color: colors.textPrimary,
  },
  subtitle: {
    fontSize: 16,
    fontWeight: "600" as const,
    color: colors.textSecondary,
  },
  body: {
    fontSize: 16,
    lineHeight: 22,
    color: colors.textPrimary,
  },
  caption: {
    fontSize: 12,
    color: colors.textTertiary,
  },
  label: {
    fontSize: 14,
    fontWeight: "600" as const,
    color: colors.textSecondary,
    letterSpacing: 0.5,
    textTransform: "uppercase" as const,
  },
};

export const shadows = {
  gold: {
    shadowColor: "#D4A853",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
    elevation: 8,
  },
  soft: {
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 4,
  },
  glow: {
    shadowColor: "#D4A853",
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.5,
    shadowRadius: 20,
    elevation: 12,
  },
};

export const borderRadius = {
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  full: 999,
};

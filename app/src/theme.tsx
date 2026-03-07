/**
 * Elora Design System -- Warm Minimalist
 *
 * Inspired by: Calm, intentional, blank-canvas UX
 * Soft gradients, warm tones, high transparency
 */

import React, { createContext, useContext, useState, useCallback, useEffect } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";

// ---------------------------------------------------------------------------
// Color palettes -- Warm & Inviting
// ---------------------------------------------------------------------------

const lightColors = {
  // Core palette -- Warm gradient background
  background: "#FFFFFF",
  backgroundGradient: ["#FFFFFF", "#FFFBF5", "#FFF8F0"], // White → Pale peach
  surface: "#FFFBF7",
  surfaceLight: "#FFF5ED",
  surfaceElevated: "#FFFFFF",

  // Warm accent (replaces cold gold)
  gold: "#F4A460", // Sandy brown -- warmer, softer
  goldLight: "#FFB87D",
  goldDark: "#D48845",
  goldMuted: "rgba(244, 164, 96, 0.12)",

  // Text -- Softer than pure black
  textPrimary: "#2D2D2D",
  textSecondary: "#6B6B6B",
  textTertiary: "#9E9E9E",
  textGold: "#D48845",

  // Accents -- Muted, natural tones
  accent: "#7FB8A0", // Sage green
  accentLight: "#A8D5C0",
  success: "#88C9A1",
  error: "#E57373",
  warning: "#FFB74D",

  // Gradients -- Soft & warm
  gradientHero: ["#FFFFFF", "#FFFBF5", "#FFF8F0"],
  gradientGold: ["#FFB87D", "#F4A460"],
  gradientGoldSoft: ["rgba(244, 164, 96, 0.08)", "rgba(244, 164, 96, 0.02)"],
  gradientAccent: ["#7FB8A0", "#5FA380"],
  gradientWarm: ["#FFF5ED", "#FFEBE0"],

  // Status -- Muted indicators
  connected: "#88C9A1",
  disconnected: "#E57373",
  processing: "#FFB74D",

  // Borders -- Ultra subtle
  border: "rgba(0, 0, 0, 0.04)",
  borderLight: "rgba(0, 0, 0, 0.02)",
};

const darkColors = {
  // Core palette -- Warm dark mode
  background: "#1A1816",
  backgroundGradient: ["#1A1816", "#24201C", "#2A221E"],
  surface: "#24201C",
  surfaceLight: "#2A221E",
  surfaceElevated: "#2D2622",

  // Warm accent
  gold: "#E8A96D",
  goldLight: "#FFC48A",
  goldDark: "#C98B5A",
  goldMuted: "rgba(232, 169, 109, 0.15)",

  // Text -- Warm off-white
  textPrimary: "#F5F0EB",
  textSecondary: "#B8B0A8",
  textTertiary: "#7D7570",
  textGold: "#E8A96D",

  // Accents
  accent: "#6FA390",
  accentLight: "#8FC4B0",
  success: "#7BC495",
  error: "#E87B7B",
  warning: "#FFC96D",

  // Gradients
  gradientHero: ["#1A1816", "#24201C", "#2A221E"],
  gradientGold: ["#FFC48A", "#E8A96D"],
  gradientGoldSoft: ["rgba(232, 169, 109, 0.12)", "rgba(232, 169, 109, 0.03)"],
  gradientAccent: ["#6FA390", "#5A8F7A"],
  gradientWarm: ["#2A221E", "#332822"],

  // Status
  connected: "#7BC495",
  disconnected: "#E87B7B",
  processing: "#FFC96D",

  // Borders
  border: "rgba(232, 169, 109, 0.08)",
  borderLight: "rgba(184, 176, 168, 0.06)",
};

export type ThemeColors = typeof lightColors;
export type ThemeMode = "light" | "dark";

// ---------------------------------------------------------------------------
// Shared tokens (don't change with theme)
// ---------------------------------------------------------------------------

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
  },
  title: {
    fontSize: 22,
    fontWeight: "700" as const,
    letterSpacing: -0.3,
  },
  subtitle: {
    fontSize: 16,
    fontWeight: "600" as const,
  },
  body: {
    fontSize: 16,
    lineHeight: 22,
  },
  caption: {
    fontSize: 12,
  },
  label: {
    fontSize: 14,
    fontWeight: "600" as const,
    letterSpacing: 0.5,
    textTransform: "uppercase" as const,
  },
};

export const borderRadius = {
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  full: 999,
};

// Shadows -- Soft, diffused, natural
const lightShadows = {
  soft: {
    shadowColor: "#D48845",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 16,
    elevation: 4,
  },
  medium: {
    shadowColor: "#D48845",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 20,
    elevation: 8,
  },
  glow: {
    shadowColor: "#F4A460",
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.15,
    shadowRadius: 24,
    elevation: 12,
  },
};

const darkShadows = {
  soft: {
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.15,
    shadowRadius: 16,
    elevation: 4,
  },
  medium: {
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 20,
    elevation: 8,
  },
  glow: {
    shadowColor: "#E8A96D",
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.25,
    shadowRadius: 24,
    elevation: 12,
  },
};

// ---------------------------------------------------------------------------
// Theme Context
// ---------------------------------------------------------------------------

interface ThemeContextValue {
  mode: ThemeMode;
  colors: ThemeColors;
  shadows: typeof lightShadows;
  isDark: boolean;
  toggleTheme: () => void;
  setMode: (mode: ThemeMode) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  mode: "light",
  colors: lightColors,
  shadows: lightShadows,
  isDark: false,
  toggleTheme: () => {},
  setMode: () => {},
});

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}

const THEME_STORAGE_KEY = "elora_theme_mode";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>("light");

  // Load saved theme preference
  useEffect(() => {
    AsyncStorage.getItem(THEME_STORAGE_KEY).then((saved) => {
      if (saved === "light" || saved === "dark") {
        setModeState(saved);
      }
    });
  }, []);

  const setMode = useCallback((newMode: ThemeMode) => {
    setModeState(newMode);
    AsyncStorage.setItem(THEME_STORAGE_KEY, newMode).catch(() => {});
  }, []);

  const toggleTheme = useCallback(() => {
    setMode(mode === "light" ? "dark" : "light");
  }, [mode, setMode]);

  const value: ThemeContextValue = {
    mode,
    colors: mode === "dark" ? darkColors : lightColors,
    shadows: mode === "dark" ? darkShadows : lightShadows,
    isDark: mode === "dark",
    toggleTheme,
    setMode,
  };

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Legacy exports for backward compat -- uses light theme as default
// @deprecated -- Use useTheme() hook instead. These static exports do not
// respond to dark mode and will be removed in a future release.
// ---------------------------------------------------------------------------

/** @deprecated Use useTheme().colors instead */
export const colors = lightColors;
/** @deprecated Use useTheme().shadows instead */
export const shadows = lightShadows;

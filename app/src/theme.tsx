/**
 * Elora Design System -- Dual Theme (Light Default + Dark Toggle)
 *
 * Clean, premium design. Light mode is default.
 */

import React, { createContext, useContext, useState, useCallback, useEffect } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";

// ---------------------------------------------------------------------------
// Color palettes
// ---------------------------------------------------------------------------

const lightColors = {
  // Core palette
  background: "#FFFFFF",
  surface: "#F7F7F8",
  surfaceLight: "#EEEEF0",
  surfaceElevated: "#FFFFFF",

  // Gold accents
  gold: "#B08930",
  goldLight: "#D4A853",
  goldDark: "#8B6914",
  goldMuted: "rgba(176, 137, 48, 0.1)",

  // Text
  textPrimary: "#1A1A1A",
  textSecondary: "#6B7280",
  textTertiary: "#9CA3AF",
  textGold: "#B08930",

  // Accents
  accent: "#3B82F6",
  accentLight: "#60A5FA",
  success: "#22C55E",
  error: "#EF4444",
  warning: "#F59E0B",

  // Gradients
  gradientHero: ["#FFFFFF", "#F9FAFB", "#F3F4F6"],
  gradientGold: ["#D4A853", "#B08930"],
  gradientGoldSoft: ["rgba(212, 168, 83, 0.15)", "rgba(212, 168, 83, 0.03)"],
  gradientAccent: ["#3B82F6", "#2563EB"],
  gradientDark: ["#FFFFFF", "#F9FAFB"],

  // Status
  connected: "#22C55E",
  disconnected: "#EF4444",
  processing: "#F59E0B",

  // Borders
  border: "rgba(0, 0, 0, 0.08)",
  borderLight: "rgba(0, 0, 0, 0.05)",
};

const darkColors = {
  // Core palette
  background: "#0A0E1A",
  surface: "#121829",
  surfaceLight: "#1A2238",
  surfaceElevated: "#1E2944",

  // Gold accents
  gold: "#D4A853",
  goldLight: "#E8C97A",
  goldDark: "#B08930",
  goldMuted: "rgba(212, 168, 83, 0.15)",

  // Text
  textPrimary: "#F5F0E8",
  textSecondary: "#9BA3B8",
  textTertiary: "#5C6478",
  textGold: "#D4A853",

  // Accents
  accent: "#4A7FD4",
  accentLight: "#6B9BE0",
  success: "#48BB78",
  error: "#E53E3E",
  warning: "#ECC94B",

  // Gradients
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

// Shadows adapt to theme
const lightShadows = {
  gold: {
    shadowColor: "#B08930",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 12,
    elevation: 8,
  },
  soft: {
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 4,
  },
  glow: {
    shadowColor: "#B08930",
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.3,
    shadowRadius: 20,
    elevation: 12,
  },
};

const darkShadows = {
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
// These will be used by files that haven't migrated to useTheme() yet
// ---------------------------------------------------------------------------

export const colors = lightColors;
export const shadows = lightShadows;

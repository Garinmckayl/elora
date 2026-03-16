// Learn more https://docs.expo.io/guides/customizing-metro
const { getDefaultConfig } = require("expo/metro-config");
const path = require("path");

/** @type {import('expo/metro-config').MetroConfig} */
const config = getDefaultConfig(__dirname);

// ---------------------------------------------------------------------------
// Block LiveKit native modules from being bundled in Expo Go.
// These packages require native code that only exists in dev client builds.
// We intercept Metro's module resolution and return an empty shim instead.
// ---------------------------------------------------------------------------
const BLOCKED_MODULES = [
  "@livekit/react-native",
  "@livekit/react-native-webrtc",
  "livekit-client",
  "react-native-webrtc",
];

// Detect if we're running in Expo Go (no custom native modules)
// EAS_BUILD or EXPO_DEV_CLIENT indicate a dev client build.
// Also check for a local prebuild (android/ or ios/ directory exists) which
// means native modules are available even without EAS.
const fs = require("fs");
const hasNativeProject = fs.existsSync(path.resolve(__dirname, "android")) || fs.existsSync(path.resolve(__dirname, "ios"));
const isExpoGo = !hasNativeProject && !process.env.EAS_BUILD && !process.env.EXPO_DEV_CLIENT;

if (isExpoGo) {
  const originalResolveRequest = config.resolver.resolveRequest;

  config.resolver.resolveRequest = (context, moduleName, platform) => {
    // Check if the module being resolved is one of the blocked native modules
    if (BLOCKED_MODULES.some((blocked) => moduleName === blocked || moduleName.startsWith(blocked + "/"))) {
      // Return an empty module that exports nothing
      return {
        filePath: path.resolve(__dirname, "src", "shims", "empty-module.js"),
        type: "sourceFile",
      };
    }

    // Default resolution
    if (originalResolveRequest) {
      return originalResolveRequest(context, moduleName, platform);
    }
    return context.resolveRequest(context, moduleName, platform);
  };
}

module.exports = config;

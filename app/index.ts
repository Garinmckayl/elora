// LiveKit React Native requires WebRTC globals to be registered before anything else.
// In Expo Go, metro.config.js shims @livekit/react-native to an empty module,
// so registerGlobals() is a no-op.
try {
  const { registerGlobals } = require("@livekit/react-native");
  registerGlobals();
} catch (e) {
  console.warn("[LiveKit] registerGlobals failed. Voice calls may not work.");
}

import { registerRootComponent } from "expo";
import App from "./App";

registerRootComponent(App);

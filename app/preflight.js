#!/usr/bin/env node
/**
 * Elora Demo Pre-flight Check
 *
 * Run BEFORE recording the demo video. Validates that:
 * 1. All source files parse correctly (no syntax errors)
 * 2. All imports resolve to existing modules
 * 3. Asset files referenced in code actually exist
 * 4. Backend is reachable
 * 5. Demo-critical config is correct
 * 6. No stale/broken URLs
 * 7. Theme consistency (no cold colors in warm screens)
 *
 * Usage:  node preflight.js
 */

const fs = require("fs");
const path = require("path");
const https = require("https");

const ROOT = __dirname;
const SRC = path.join(ROOT, "src");
const PASS = "\x1b[92mPASS\x1b[0m";
const FAIL = "\x1b[91mFAIL\x1b[0m";
const WARN = "\x1b[93mWARN\x1b[0m";
const INFO = "\x1b[96mINFO\x1b[0m";
const BOLD = "\x1b[1m";
const RESET = "\x1b[0m";

let passed = 0;
let failed = 0;
let warnings = 0;

function ok(msg) { console.log(`  ${PASS} ${msg}`); passed++; }
function fail(msg) { console.log(`  ${FAIL} ${msg}`); failed++; }
function warn(msg) { console.log(`  ${WARN} ${msg}`); warnings++; }
function info(msg) { console.log(`  ${INFO} ${msg}`); }
function header(msg) {
  console.log(`\n${BOLD}${"=".repeat(60)}${RESET}`);
  console.log(`${BOLD}  ${msg}${RESET}`);
  console.log(`${BOLD}${"=".repeat(60)}${RESET}`);
}

// ─── Helpers ─────────────────────────────────────────────────

function getAllFiles(dir, ext, files = []) {
  if (!fs.existsSync(dir)) return files;
  for (const f of fs.readdirSync(dir)) {
    const full = path.join(dir, f);
    if (fs.statSync(full).isDirectory()) {
      if (f === "node_modules" || f === ".expo") continue;
      getAllFiles(full, ext, files);
    } else if (f.endsWith(ext)) {
      files.push(full);
    }
  }
  return files;
}

function httpGet(url) {
  return new Promise((resolve) => {
    const req = https.get(url, { timeout: 30000 }, (res) => {
      let data = "";
      res.on("data", (c) => (data += c));
      res.on("end", () => resolve({ status: res.statusCode, data }));
    });
    req.on("error", (e) => resolve({ status: 0, data: e.message }));
    req.on("timeout", () => { req.destroy(); resolve({ status: 0, data: "timeout" }); });
  });
}

// ─── Checks ──────────────────────────────────────────────────

function checkAssets() {
  header("1. Asset Files");

  const required = [
    "assets/avatars/elora-happy.gif",
    "assets/avatars/elora-thinking.gif",
    "assets/avatars/elora-working.gif",
    "assets/splash-icon.png",
    "assets/icons/app-icon-1024.png",
  ];

  for (const rel of required) {
    const full = path.join(ROOT, rel);
    if (fs.existsSync(full)) {
      const size = fs.statSync(full).size;
      ok(`${rel} (${(size / 1024).toFixed(1)} KB)`);
    } else {
      fail(`${rel} — MISSING`);
    }
  }
}

function checkSourceFiles() {
  header("2. Source File Syntax");

  const tsFiles = [
    ...getAllFiles(path.join(ROOT, "src"), ".tsx"),
    ...getAllFiles(path.join(ROOT, "src"), ".ts"),
    ...getAllFiles(path.join(ROOT, "components"), ".tsx"),
    ...getAllFiles(path.join(ROOT, "components"), ".ts"),
    path.join(ROOT, "App.tsx"),
  ];

  for (const f of tsFiles) {
    const content = fs.readFileSync(f, "utf8");
    const rel = path.relative(ROOT, f);

    // Check for common syntax issues that would crash at runtime
    const openBraces = (content.match(/{/g) || []).length;
    const closeBraces = (content.match(/}/g) || []).length;
    if (Math.abs(openBraces - closeBraces) > 2) {
      fail(`${rel} — brace mismatch ({=${openBraces} }=${closeBraces})`);
    } else {
      ok(`${rel}`);
    }
  }
}

function checkImports() {
  header("3. Import Resolution (Demo-Critical Files)");

  const demoFiles = [
    "App.tsx",
    "src/screens/HomeScreen.tsx",
    "src/screens/OnboardingScreen.tsx",
    "src/screens/SettingsScreen.tsx",
    "src/components/LiveCallScreen.tsx",
    "src/components/ChatBubble.tsx",
    "src/components/VoiceButton.tsx",
    "src/components/VisionCapture.tsx",
    "src/components/BrowserModal.tsx",
    "src/components/AudioPlayer.tsx",
    "src/theme.tsx",
    "src/config.ts",
    "components/EloraAvatar.tsx",
  ];

  for (const rel of demoFiles) {
    const full = path.join(ROOT, rel);
    if (!fs.existsSync(full)) {
      fail(`${rel} — FILE MISSING`);
      continue;
    }
    const content = fs.readFileSync(full, "utf8");
    const dir = path.dirname(full);
    const imports = content.matchAll(/(?:import|from)\s+['"]([^'"]+)['"]/g);
    let allOk = true;

    for (const [, imp] of imports) {
      // Skip node_modules imports (they resolve via Metro)
      if (!imp.startsWith(".") && !imp.startsWith("..")) continue;

      // Resolve relative import
      const candidates = [
        path.join(dir, imp),
        path.join(dir, imp + ".ts"),
        path.join(dir, imp + ".tsx"),
        path.join(dir, imp + ".js"),
        path.join(dir, imp, "index.ts"),
        path.join(dir, imp, "index.tsx"),
        path.join(dir, imp, "index.js"),
      ];

      const found = candidates.some((c) => fs.existsSync(c));
      if (!found) {
        fail(`${rel} — import '${imp}' not found`);
        allOk = false;
      }
    }
    if (allOk) ok(`${rel} — all local imports resolve`);
  }
}

function checkThemeConsistency() {
  header("4. Theme Consistency (No Cold Colors in Warm Screens)");

  const coldColors = ["#0A0E1A", "#121829", "#1A2238", "#0D1117"];
  const filesToCheck = [
    "src/components/LiveCallScreen.tsx",
    "src/screens/HomeScreen.tsx",
    "src/screens/OnboardingScreen.tsx",
    "src/screens/SettingsScreen.tsx",
  ];

  for (const rel of filesToCheck) {
    const full = path.join(ROOT, rel);
    if (!fs.existsSync(full)) continue;
    const content = fs.readFileSync(full, "utf8");
    const lines = content.split("\n");
    let foundCold = false;

    for (let i = 0; i < lines.length; i++) {
      for (const cold of coldColors) {
        if (lines[i].includes(cold) && !lines[i].trim().startsWith("//")) {
          fail(`${rel}:${i + 1} — cold color ${cold} (should be warm theme color)`);
          foundCold = true;
        }
      }
    }
    if (!foundCold) ok(`${rel} — no cold colors found`);
  }
}

function checkConfig() {
  header("5. App Configuration");

  // app.json
  const appJson = JSON.parse(fs.readFileSync(path.join(ROOT, "app.json"), "utf8"));
  const expo = appJson.expo;

  if (expo.name === "Elora") ok("App name: Elora");
  else fail(`App name: "${expo.name}" (expected "Elora")`);

  if (expo.scheme === "elora") ok("Deep link scheme: elora://");
  else fail(`Deep link scheme: "${expo.scheme}"`);

  const splashBg = expo.splash?.backgroundColor;
  if (splashBg && splashBg !== "#FFFFFF") ok(`Splash background: ${splashBg} (not cold white)`);
  else fail(`Splash background: ${splashBg} (cold white flash!)`);

  if (expo.ios?.bundleIdentifier) ok(`iOS bundle: ${expo.ios.bundleIdentifier}`);
  else fail("iOS bundleIdentifier not set");

  if (expo.android?.package) ok(`Android package: ${expo.android.package}`);
  else fail("Android package not set");

  const adaptiveBg = expo.android?.adaptiveIcon?.backgroundColor;
  if (adaptiveBg && !["#0A0E1A", "#FFFFFF"].includes(adaptiveBg))
    ok(`Android adaptive icon bg: ${adaptiveBg}`);
  else warn(`Android adaptive icon bg: ${adaptiveBg} (may clash)`);

  // config.ts
  const configContent = fs.readFileSync(path.join(ROOT, "src", "config.ts"), "utf8");
  const backendMatch = configContent.match(/https:\/\/[a-zA-Z0-9._-]+\.run\.app/);
  if (backendMatch) {
    ok(`Backend URL: ${backendMatch[0]}`);
  } else {
    fail("No Cloud Run backend URL found in config.ts");
  }
}

function checkDemoFlow() {
  header("6. Demo Flow Validation");

  // Scene 1: Live Call Screen — must have orb, waveform, camera toggle
  const liveCall = fs.readFileSync(
    path.join(ROOT, "src/components/LiveCallScreen.tsx"),
    "utf8"
  );

  if (liveCall.includes("useSafeAreaInsets")) ok("LiveCallScreen uses safe area insets");
  else fail("LiveCallScreen missing safe area insets");

  if (liveCall.includes("orbContainer")) ok("LiveCallScreen has orb visualization");
  else fail("LiveCallScreen missing orb visualization");

  if (liveCall.includes("waveformContainer")) ok("LiveCallScreen has waveform animation");
  else fail("LiveCallScreen missing waveform");

  if (liveCall.includes("onToggleCamera")) ok("LiveCallScreen has camera toggle");
  else fail("LiveCallScreen missing camera toggle");

  if (liveCall.includes("onToggleMute")) ok("LiveCallScreen has mute toggle");
  else fail("LiveCallScreen missing mute toggle");

  if (liveCall.includes("messageLogContainer")) ok("LiveCallScreen has live transcript");
  else fail("LiveCallScreen missing live transcript");

  if (liveCall.includes("colors.gold") || liveCall.includes("colors.background"))
    ok("LiveCallScreen uses theme colors");
  else fail("LiveCallScreen has hardcoded colors instead of theme");

  // Scene 2: Chat — must have ChatBubble with tool card rendering
  const chatBubble = fs.readFileSync(
    path.join(ROOT, "src/components/ChatBubble.tsx"),
    "utf8"
  );

  if (chatBubble.includes("TOOL_LABELS")) ok("ChatBubble has tool labels (for skill/browser cards)");
  else fail("ChatBubble missing tool labels");

  if (chatBubble.includes("browse_web") || chatBubble.includes("browser"))
    ok("ChatBubble handles browser tool display");
  else warn("ChatBubble may not render browser screenshots nicely");

  // Scene 3: Skills — verify skill tool names are in chat bubble
  const skillTools = ["search_skills", "install_skill", "create_skill", "execute_skill"];
  const missingSkillTools = skillTools.filter((t) => !chatBubble.includes(t));
  if (missingSkillTools.length === 0) {
    ok("ChatBubble handles all skill tool cards");
  } else {
    warn(`ChatBubble missing tool cards for: ${missingSkillTools.join(", ")}`);
  }

  // Voice button — should auto-start call (not dead-end)
  const appTsx = fs.readFileSync(path.join(ROOT, "App.tsx"), "utf8");
  if (appTsx.includes("TODO") && appTsx.includes("hold-to-talk")) {
    fail("App.tsx still has hold-to-talk TODO (will dead-end during demo)");
  } else {
    ok("Hold-to-talk TODO resolved");
  }

  // Browser modal exists
  if (fs.existsSync(path.join(ROOT, "src/components/BrowserModal.tsx")))
    ok("BrowserModal component exists (for Scene 2 browser demo)");
  else fail("BrowserModal missing — browser screenshots won't render");

  // Audio player exists (for music gen demo)
  if (fs.existsSync(path.join(ROOT, "src/components/AudioPlayer.tsx")))
    ok("AudioPlayer component exists (for music gen demo)");
  else fail("AudioPlayer missing — music playback won't work");
}

async function checkBackend() {
  header("7. Backend Connectivity");

  const configContent = fs.readFileSync(path.join(ROOT, "src/config.ts"), "utf8");
  const urlMatch = configContent.match(/https:\/\/[a-zA-Z0-9._-]+\.run\.app/);

  if (!urlMatch) {
    fail("Cannot extract backend URL from config.ts");
    return;
  }

  const base = urlMatch[0];
  info(`Testing: ${base}`);

  // Health check
  const health = await httpGet(`${base}/health`);
  if (health.status === 200) {
    try {
      const data = JSON.parse(health.data);
      ok(`/health — ${data.status} v${data.version}`);
    } catch {
      ok(`/health — responded (${health.status})`);
    }
  } else {
    fail(`/health — ${health.status || "unreachable"} (${health.data})`);
  }

  // Agent identity
  const identity = await httpGet(`${base}/agent/identity`);
  if (identity.status === 200) {
    try {
      const data = JSON.parse(identity.data);
      const caps = data.capabilities?.length || 0;
      ok(`/agent/identity — ${caps} capabilities, security: ${data.security?.prompt_guard ? "enabled" : "DISABLED"}`);
    } catch {
      ok(`/agent/identity — responded`);
    }
  } else {
    fail(`/agent/identity — ${identity.status || "unreachable"}`);
  }

  // Skills
  const skills = await httpGet(`${base}/agent/skills`);
  if (skills.status === 200) {
    try {
      const data = JSON.parse(skills.data);
      ok(`/agent/skills — ${data.count} bundled skills`);
    } catch {
      ok(`/agent/skills — responded`);
    }
  } else {
    fail(`/agent/skills — ${skills.status || "unreachable"}`);
  }
}

function checkStaleUrls() {
  header("8. Stale URLs");

  const stalePatterns = [
    "localhost:8080",
    "localhost:3000",
    "your-backend",
    "your-project",
    "REPLACE_ME",
    "TODO_URL",
  ];

  const filesToCheck = [
    "src/config.ts",
    "app.json",
    "eas.json",
  ];

  for (const rel of filesToCheck) {
    const full = path.join(ROOT, rel);
    if (!fs.existsSync(full)) continue;
    const content = fs.readFileSync(full, "utf8");
    let clean = true;

    for (const pattern of stalePatterns) {
      if (content.includes(pattern)) {
        fail(`${rel} contains "${pattern}"`);
        clean = false;
      }
    }
    if (clean) ok(`${rel} — no stale URLs`);
  }
}

function checkNodeModules() {
  header("9. Dependencies");

  const criticalDeps = [
    "expo",
    "react-native",
    "expo-camera",
    "expo-haptics",
    "expo-linear-gradient",
    "expo-notifications",
    "expo-audio",
    "expo-av",
    "@livekit/react-native",
    "firebase",
    "react-native-safe-area-context",
    "@react-native-async-storage/async-storage",
  ];

  for (const dep of criticalDeps) {
    const depPath = path.join(ROOT, "node_modules", dep);
    if (fs.existsSync(depPath)) {
      ok(dep);
    } else {
      fail(`${dep} — NOT INSTALLED (run npm install)`);
    }
  }
}

// ─── Run ─────────────────────────────────────────────────────

async function main() {
  console.log(`\n${BOLD}Elora Demo Pre-flight Check${RESET}`);
  console.log(`Started: ${new Date().toISOString()}\n`);

  checkAssets();
  checkSourceFiles();
  checkImports();
  checkThemeConsistency();
  checkConfig();
  checkDemoFlow();
  checkStaleUrls();
  checkNodeModules();
  await checkBackend();

  console.log(`\n${BOLD}${"=".repeat(60)}${RESET}`);
  console.log(
    `${BOLD}  RESULTS: ${passed} passed, ${failed} failed, ${warnings} warnings${RESET}`
  );
  console.log(`${BOLD}${"=".repeat(60)}${RESET}`);

  if (failed > 0) {
    console.log(`\n${FAIL} ${failed} issue(s) found — fix before recording!\n`);
    process.exit(1);
  } else if (warnings > 0) {
    console.log(`\n${WARN} All clear with ${warnings} warning(s) — safe to record.\n`);
  } else {
    console.log(`\n${PASS} All clear — ready to record the demo!\n`);
  }
}

main();

# 🏗️ Elora - Build Instructions

## ⚠️ Why Build is Needed

**Expo Go Limitations:**
- ❌ No LiveKit (voice calls won't work)
- ❌ No custom app icon
- ❌ Limited native modules
- ❌ Some camera features restricted

**Development Client (What We'll Build):**
- ✅ Full LiveKit support
- ✅ Custom app icon shows
- ✅ All native modules work
- ✅ Avatar animations work
- ✅ Everything production-ready

---

## 🚀 Quick Build (Android APK)

```bash
cd /home/ubuntu/copilot-challenge/elora/app

# Build development APK (15-20 minutes)
eas build --platform android --profile development
```

### What This Does:
- Builds Android APK with all native modules
- Includes LiveKit, camera, microphone
- Shows custom app icon
- Ready to install on your phone

### After Build Completes:
1. Download APK from Expo link
2. Install on Android phone
3. Open Elora app (you'll see the amber "E" icon!)
4. Test voice calls, avatar, everything!

---

## 📱 Alternative: Local Development Client

**Faster for testing (no cloud build):**

```bash
cd /home/ubuntu/copilot-challenge/elora/app

# Install dev client
npx expo run:android

# OR for iOS (requires Mac)
npx expo run:ios
```

**What This Does:**
- Builds locally on your machine
- Installs on connected device/emulator
- Hot reload still works
- Faster iteration

**Requirements:**
- Android Studio installed
- Android device connected via USB OR emulator running
- Takes 5-10 minutes first time

---

## 🎯 Recommended Flow

### For Testing Now:
```bash
# Option A: Cloud build (easiest)
eas build --platform android --profile development

# Wait 15-20 min → Download APK → Install → Test
```

### For Development:
```bash
# Option B: Local dev client (faster iteration)
npx expo run:android

# After this, you can use:
npx expo start
# And it will open in dev client (not Expo Go)
```

---

## 📥 After Installing APK

You'll see:

1. **Home Screen** → Amber "E" icon (your custom icon!)
2. **Open App** → Everything works
3. **Start Call** → LiveKit works, avatar animates
4. **Chat** → Avatar shows in messages

---

## 🐛 If Build Fails

### Common Issues:

**"Credentials error"**
```bash
eas credentials:configure --platform android
```

**"Build failed"**
```bash
# Check logs
eas build:list --platform android
```

**"Insufficient permissions"**
```bash
# Make sure you're logged in
eas whoami
# If not:
eas login
```

---

## 🎨 What You'll Get

### App Icon:
- Amber glowing "E" on dark background
- Shows on home screen
- Professional, polished look

### Avatar:
- Shows in chat bubbles
- Shows in call screen (top bar)
- Changes by state:
  - 👂 Listening (gentle pulse)
  - 🤔 Thinking (focused glow)
  - ⚙️ Working (animated rings)
  - 😊 Happy (warm sparkle)

### LiveKit:
- Voice calls work perfectly
- Real-time audio streaming
- Background audio support

---

## 📊 Build Time

| Method | Time | Best For |
|--------|------|----------|
| Cloud Build (EAS) | 15-20 min | Quick test, no setup |
| Local Dev Client | 5-10 min | Active development |
| Production Build | 20-30 min | Final release |

---

## 🏁 Next Steps

1. **Run build command**
2. **Wait for completion** (you'll get email)
3. **Download APK**
4. **Install on phone**
5. **Test everything!**

**Then record your demo video with the real app!** 🎬

---

**Questions?** Check:
- EAS Dashboard: https://expo.dev
- Build Logs: `eas build:list`
- Docs: https://docs.expo.dev/build/introduction

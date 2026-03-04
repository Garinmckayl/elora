# Weekly Recap Demo Script

This script demonstrates Elora's signature "Recap My Week" feature that combines:
- **Lyria 3** - Music generation for theme songs
- **Imagen 3** - Image generation for photo montages  
- **Gemini TTS** - Voice narration
- **MemU** - Memory retrieval for highlights

## Usage

```bash
cd core
export GOOGLE_API_KEY=your-key
python examples/weekly_recap_demo.py
```

## What It Does

1. Gathers highlights from the user's memory (MemU)
2. Generates a custom theme song (Lyria 3)
3. Creates a photo montage (Imagen 3)
4. Produces voice narration (Gemini TTS)
5. Combines everything into a shareable recap

## Demo Flow

```python
from tools.weekly_recap import generate_weekly_recap

result = generate_weekly_recap(
    user_id="demo_user",
    days=7,
    include_music=True,      # Lyria 3 theme song
    include_montage=True,    # Imagen 3 photo collage
    include_narration=True   # Gemini TTS voiceover
)

# Result contains:
{
    "status": "success",
    "highlights": [...],      # From MemU memory
    "music": {...},           # Lyria 3 audio
    "montage": {...},         # Imagen 3 images
    "narration": {...}        # TTS audio
}
```

## API Keys Needed

- `GOOGLE_API_KEY` - For all Google AI services (Lyria, Imagen, TTS, Gemini)
- `MEMU_CLOUD=false` - Use self-hosted MemU with Gemini

## Sample Output

```
📊 Weekly Recap Generated
━━━━━━━━━━━━━━━━━━━━━━━━━
Period: Last 7 days
Highlights: 8 memories found

🎵 Theme Song (Lyria 3)
   Duration: 45s
   Style: Cinematic
   Mood: Uplifting

🖼️ Photo Montage (Imagen 3)
   Size: 1536x1024
   Images: 1 collage

🎙️ Voice Narration (Gemini TTS)
   Duration: 62s
   Voice: Elora

✅ Complete recap ready for playback!
```

## Integration Points

The weekly recap feature is called via:
- Agent tool: `generate_weekly_recap()`
- HTTP endpoint: `POST /recap/weekly`
- Voice command: "Recap my week"

## Demo Script for Judges

> "Elora doesn't just remember your week — she celebrates it.
> With a single command, she creates a multimedia recap:
> A custom theme song composed by Lyria 3,
> A beautiful photo montage from Imagen 3,
> And her own voice narrating your highlights.
> This isn't just AI — this is your personal storyteller."

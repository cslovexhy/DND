# Transcribe Audio to Text

## Purpose
Transcribe meeting recordings or audio files to text using whisper-cpp (local, offline, fast on Apple Silicon).

## Prerequisites

Install once:
```bash
brew install whisper-cpp ffmpeg
```

Download model once (base.en = good speed/quality balance, ~141MB):
```bash
mkdir -p ~/.local/share/whisper-cpp
curl -L -o ~/.local/share/whisper-cpp/ggml-base.en.bin \
  "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"
```

For better accuracy (slower, ~500MB):
```bash
curl -L -o ~/.local/share/whisper-cpp/ggml-medium.en.bin \
  "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.en.bin"
```

## Steps

### 1. Convert audio to 16kHz mono WAV (whisper-cpp requirement)
```bash
ffmpeg -i "<input_file>.m4a" -ar 16000 -ac 1 -c:a pcm_s16le /tmp/meeting_recording.wav
```

Supports any input format ffmpeg can read: .m4a, .mp3, .ogg, .webm, .mp4, etc.

### 2. Run transcription
```bash
whisper-cli -m ~/.local/share/whisper-cpp/ggml-base.en.bin \
  -f /tmp/meeting_recording.wav \
  -otxt \
  -of /tmp/meeting_transcript
```

Output: `/tmp/meeting_transcript.txt`

### 3. Save to project
```bash
cp /tmp/meeting_transcript.txt <project_path>/References/meeting_transcript_<date>_<topic>.txt
```

## Options

| Flag | Purpose |
|------|---------|
| `-m <model>` | Model file (base.en, medium.en, large) |
| `-otxt` | Output plain text |
| `-osrt` | Output SRT subtitles (with timestamps) |
| `-ovtt` | Output VTT subtitles |
| `-of <path>` | Output file prefix (extension added automatically) |
| `-l en` | Force English language detection |
| `-t 8` | Number of threads (default: auto) |

## Troubleshooting

- **"failed to read audio data"**: whisper-cli can't decode the format directly. Convert to WAV first with ffmpeg (Step 1).
- **Poor quality**: Use `medium.en` model instead of `base.en`. Takes ~3x longer but much better for accents/multiple speakers.
- **Very long audio (>1hr)**: Still works, just takes proportionally longer. ~15s for 21min audio on base.en with M-series Mac.

## Performance (Apple Silicon M-series)

| Model | Size | Speed (21min audio) | Quality |
|-------|------|---------------------|---------|
| base.en | 141MB | ~15s | Good for clear speech, single speaker |
| medium.en | 500MB | ~45s | Better for accents, multiple speakers |
| large | 1.5GB | ~2min | Best quality, all languages |

## Cleanup
```bash
rm /tmp/meeting_recording.wav  # large WAV file
# Keep transcript — it's small
```

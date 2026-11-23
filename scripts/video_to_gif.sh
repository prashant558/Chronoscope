#!/usr/bin/env bash
# Usage: scripts/video_to_gif.sh [video] [start_seconds] [duration_seconds]
set -euo pipefail
VID="${1:-$(ls -t ./*.mp4 ./*.mov ./*.webm 2>/dev/null | head -1 || true)}"
START="${2:-0}"; DUR="${3:-}"
[ -n "$VID" ] && [ -f "$VID" ] || { echo "❌ No video found. Drag the .mp4 into the Chronoscope folder first."; exit 1; }
command -v ffmpeg >/dev/null || { echo "❌ ffmpeg missing"; exit 1; }

LEN=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$VID" | cut -d. -f1)
echo "🎬 $VID  (${LEN}s)"
[ "${LEN:-0}" -gt 60 ] && [ -z "$DUR" ] && echo "⚠️  Over 60 s. Consider trimming: $0 \"$VID\" <start> <duration>"

mkdir -p docs
TRIM=(-ss "$START"); [ -n "$DUR" ] && TRIM+=(-t "$DUR")
for SET in "10 960" "8 900" "8 800" "6 800" "6 700" "5 640"; do
  read -r FPS W <<< "$SET"
  ffmpeg -y -loglevel error "${TRIM[@]}" -i "$VID" -vf \
    "fps=$FPS,scale=$W:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4" \
    docs/demo.gif
  MB=$(du -m docs/demo.gif | cut -f1)
  echo "   fps=$FPS width=$W → ${MB} MB"
  [ "$MB" -lt 8 ] && { echo "✅ docs/demo.gif ready (${MB} MB)"; break; }
done
[ "$(du -m docs/demo.gif | cut -f1)" -lt 8 ] || echo "⚠️  Still ≥ 8 MB. Trim the video (see usage above)."

grep -qxF '*.mp4' .gitignore || printf '*.mp4\n*.mov\n*.webm\n' >> .gitignore
echo "ℹ️  Videos are git-ignored; only the GIF gets committed."

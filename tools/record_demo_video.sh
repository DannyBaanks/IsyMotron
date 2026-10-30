#!/usr/bin/env bash
# Record the hackathon demo (X11): screen + optional mic, then run the walkthrough.
#   tools/record_demo_video.sh            # screen only, narrate afterwards
#   MIC=1 tools/record_demo_video.sh      # also record the default microphone
# Output: ~/Videos/isymotron-demo-<timestamp>.mp4. Max 3 min of demo; the script
# stops recording when the walkthrough ends (press Ctrl-C to abort early).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$HOME/Videos"
OUT="$HOME/Videos/isymotron-demo-$(date +%Y%m%d-%H%M%S).mp4"
SIZE="$(xdpyinfo | awk '/dimensions:/ {print $2}')"
AUDIO=()
if [[ "${MIC:-0}" == "1" ]]; then AUDIO=(-f pulse -i default -c:a aac -b:a 128k); fi
clear
echo "Recording ${SIZE} -> $OUT"
echo "Starts in 5 s. Make the terminal fullscreen with a large font (Ctrl-+)."
sleep 5
ffmpeg -loglevel error -y -f x11grab -framerate 30 -video_size "$SIZE" -i "${DISPLAY:-:0}" \
  "${AUDIO[@]}" -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p "$OUT" &
FF=$!
trap 'kill -INT $FF 2>/dev/null || true; wait $FF 2>/dev/null || true' EXIT
sleep 1
python3 "$ROOT/tools/isymotron_cli.py" demo-video --pause "${PAUSE:-3}"
sleep 4
echo; echo "Saved: $OUT"

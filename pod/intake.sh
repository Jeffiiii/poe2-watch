#!/bin/bash
# Intake of raw recordings on a rented machine (the owner's PC must stay usable): per recording -> game/mic audio,
# 1280x800 copy for the teacher, 4 fps 384 px frames, HUD montage + OCR readings, alert sounds, and the 896/1280 px
# frames for the student. Everything of one recording is packed into out/<session>.tar and served on port 8000.
# Expects: SESSIONS (space-separated names) and, per session, URL_<n> presigned links in sessions.txt ("name url" lines).
mkdir -p /workspace/job/out && cd /workspace/job
(cd out && nohup python -m http.server 8000 > /dev/null 2>&1 &)
exec > out/intake.log 2>&1
set -x
wget -q 'TOOLS_URL' -O tools.tar && tar xf tools.tar 2>/dev/null
apt-get install -y -qq ffmpeg > /dev/null 2>&1 || (apt-get update -qq && apt-get install -y -qq ffmpeg > /dev/null)
pip install -q rapidocr-onnxruntime librosa soundfile pillow numpy
export PYTHONUTF8=1
W=/workspace/job/work
mkdir -p $W/raw $W/audio $W/label_src $W/frames $W/hud $W/pod/f896 $W/pod/f1280
while read -r -u 3 S URL; do      # fd 3: ffmpeg/python inside the loop would otherwise eat the rest of sessions.txt from stdin
  [ -z "$S" ] && continue
  echo "== $S $(date +%H:%M)"
  wget -q "$URL" -O $W/raw/$S.mp4 || { echo "download failed $S"; continue; }
  ffmpeg -nostdin -v error -y -i $W/raw/$S.mp4 -map 0:a:0 -ac 1 -ar 48000 $W/audio/$S.game.flac -map 0:a:1 -ac 1 -ar 48000 $W/audio/$S.mic.flac
  ffmpeg -nostdin -v error -y -i $W/raw/$S.mp4 -map 0:v:0 -map 0:a:0 -vf scale=1280:800 -c:v h264_nvenc -preset p4 -cq 23 -c:a aac -b:a 96k $W/label_src/$S.mp4 \
    || ffmpeg -nostdin -v error -y -i $W/raw/$S.mp4 -map 0:v:0 -map 0:a:0 -vf scale=1280:800 -c:v libx264 -preset fast -crf 23 -c:a aac -b:a 96k $W/label_src/$S.mp4
  python watch/extract_frames.py $W/raw/$S.mp4 --out-root $W/frames
  python watch/hud_extract.py $W/raw/$S.mp4 --out-root $W/hud
  python watch/hud_read.py $S --work $W 2>&1 | grep -v "^  "
  python watch/alert_cnn.py detect $S --work $W --sounds alert_sounds/ingame
  mkdir -p $W/pod/f896/$S $W/pod/f1280/$S
  ffmpeg -nostdin -v error -y -i $W/label_src/$S.mp4 -vf "fps=4/5:start_time=0:round=down,scale=896:-2" -q:v 4 $W/pod/f896/$S/%05d.jpg
  ffmpeg -nostdin -v error -y -i $W/label_src/$S.mp4 -vf "fps=4/5:start_time=0:round=down" -q:v 4 $W/pod/f1280/$S/%05d.jpg
  rm -f $W/raw/$S.mp4
  (cd $W && tar cf /workspace/job/out/$S.tar audio/$S.game.flac audio/$S.mic.flac label_src/$S.mp4 frames/$S hud/$S raw/$S.hud.csv raw/$S.hud_events.csv raw/$S.alerts.csv pod/f896/$S pod/f1280/$S)
  echo "packed $S $(du -h /workspace/job/out/$S.tar | cut -f1)"
done 3< sessions.txt
echo "intake done $(date +%H:%M)"
touch out/DONE
sleep 21600

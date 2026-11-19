#!/bin/bash
# The eyes on a rented machine: MediaMTX takes the owner's OBS stream (RTMP 1935), vLLM serves the merged student
# (port 8001, local), live.py watches and answers on port 8000 (/monitor, /state, /events, /speak).
# Placeholders are filled by the launcher: TOOLS_URL (live.tar), ADAPTER_URL (lora.tgz), SAMPLE_URL (optional test video).
mkdir -p /workspace/live && cd /workspace/live
exec > /workspace/live/serve.log 2>&1
set -x
(python3 -m http.server 8002 > /dev/null 2>&1 &)                                    # serve.log and log.jsonl readable at :8002
wget -q 'TOOLS_URL' -O live.tar && tar xf live.tar
wget -q 'ADAPTER_URL' -O lora.tgz && mkdir -p lora && tar xzf lora.tgz -C lora --strip-components=1 && ls lora
apt-get install -y -qq ffmpeg > /dev/null 2>&1 || (apt-get update -qq && apt-get install -y -qq ffmpeg > /dev/null)
pip install -q peft==0.21.2 rapidocr-onnxruntime pillow numpy
export HF_HOME=/workspace/hf PYTHONUTF8=1
MXURL=$(curl -s https://api.github.com/repos/bluenviron/mediamtx/releases/latest | grep browser_download_url | grep linux_amd64.tar.gz | head -1 | cut -d '"' -f 4)
wget -q "$MXURL" -O mx.tgz && tar xzf mx.tgz mediamtx && (./mediamtx mediamtx.yml > mediamtx.log 2>&1 &)
python3 merge_lora.py --base Qwen/Qwen3-VL-4B-Instruct --adapter lora --out /workspace/merged
python3 -m vllm.entrypoints.openai.api_server --model /workspace/merged --served-model-name student --port 8001 \
  --max-model-len 8192 --limit-mm-per-prompt '{"image":4}' --gpu-memory-utilization 0.85 --enforce-eager > vllm.log 2>&1 &
for i in $(seq 1 120); do curl -sf http://127.0.0.1:8001/v1/models > /dev/null && break; sleep 5; done
curl -s http://127.0.0.1:8001/v1/models | head -c 300
if [ -n "SAMPLE_URL" ] && [ "SAMPLE_URL" != "" ]; then
  wget -q 'SAMPLE_URL' -O sample.mp4 && (ffmpeg -nostdin -loglevel error -re -stream_loop -1 -i sample.mp4 -c copy -f flv rtmp://127.0.0.1:1935/game > /dev/null 2>&1 &)
fi
python3 live.py --stream rtsp://127.0.0.1:8554/game --vllm http://127.0.0.1:8001/v1 --model student --port 8000 --log /workspace/live/log.jsonl

#!/usr/bin/env bash
# Instala dependencias y descarga el modelo + voces de Kokoro (release model-files-v1.0 de kokoro-onnx).
set -e
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || (apt-get update && apt-get install -y ffmpeg fonts-inter)
pip install -r requirements.txt
npm install --no-audit --no-fund      # three, lucide-static, world-atlas, d3-geo, topojson-client
node -e "require('playwright')" 2>/dev/null || npm install --no-save playwright   # usa el Chromium del sistema
mkdir -p models
for f in kokoro-v1.0.onnx voices-v1.0.bin; do
  [ -f models/$f ] || curl -fSL -o models/$f https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/$f
done
echo "OK"

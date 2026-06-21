#!/usr/bin/env bash
# Idempotent setup of the ISOLATED ACE-Step venv on the data mount.
# Reuses the worker image's SM_120 torch (--system-site-packages); ACE-Step's own deps
# stay in the venv so they can't disturb YuE / Fish Speech. Run INSIDE the audio worker:
#   docker exec creative-audio-worker bash /data/ai/06-configs/audio/setup-acestep-venv.sh
set -e
REPO=/data/ai/03-data/audio/ace-step-repo
VENV=/data/ai/03-data/audio/ace-step-venv
[ -d "$REPO/.git" ] || git clone --depth 1 https://github.com/ace-step/ACE-Step.git "$REPO"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv --system-site-packages "$VENV"
  grep -ivE '^torch' "$REPO/requirements.txt" > /tmp/ace-reqs.txt
  "$VENV/bin/pip" install --no-cache-dir -q -r /tmp/ace-reqs.txt
  "$VENV/bin/pip" install --no-cache-dir -q -e "$REPO" --no-deps
fi
"$VENV/bin/python" -c "from acestep.pipeline_ace_step import ACEStepPipeline; print('ACE-Step venv OK')"

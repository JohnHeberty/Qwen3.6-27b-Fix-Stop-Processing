#!/bin/bash
# Runs OpenCode 2.2.7 (the harness the adapter was trained on) HEADLESS on one of the mini-tasks
# in lora/tests/tasks.py, against the LoRA instance (18021), and grades it with the original tests.
#
#   bash lora/opencode2/run_task.sh <task> [model] [out_dir]
#     task : slugify-bug | intervals-impl | inventory-multi | lru-cache | csv-report
#     model: opencode-adapted (default) | qwen3.8-27b   (both thinking off, card sampling)
#   OC_BASEURL=http://127.0.0.1:18099/v1 ...   # point elsewhere (e.g. tests/fake_openai_server.py)
#
# Isolation: HOME/XDG in a temp directory (does not touch ~/.config/opencode or the global OpenCode 1.x),
# OPENCODE_DISABLE_CLAUDE_CODE=1 (does not inject ~/.claude skills/CLAUDE.md into the prompt),
# no project config, no autoupdate, --standalone (private server, no daemon left behind),
# --auto (approves permissions; the config denies websearch/webfetch, as in the card's eval).
# WARNING: --auto lets the model run shell commands AS THE CURRENT USER in the task directory.
# Run as an unprivileged user if possible (e.g. `sudo -u nobody`), see lora/README.md.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LORA="$(dirname "$HERE")"
TASK=${1:?usage: run_task.sh <task> [model] [out_dir]}
MODEL=${2:-opencode-adapted}
OUT=${3:-$LORA/results/opencode2-$(date +%Y%m%d-%H%M%S)-$MODEL-$TASK}
OC="$HERE/node_modules/.bin/opencode"
[ -x "$OC" ] || { echo "OpenCode 2 not installed: npm install --prefix $HERE @opencode/cli@2.2.7 (see README)" >&2; exit 1; }
case "${OC_BASEURL:-http://127.0.0.1:18021/v1}" in *:18020*) echo "refused: 18020 is production" >&2; exit 1;; esac

mkdir -p "$OUT"
H=$(mktemp -d /tmp/oc2-home.XXXXXX)
W="$H/work"
mkdir -p "$W"
trap 'rm -rf "$H"' EXIT
# creates the task's repository
python3 -I - "$LORA/tests" "$TASK" "$W" <<'EOF'
import os, sys
sys.path.insert(0, sys.argv[1])
from tasks import TASKS
for rel, c in TASKS[sys.argv[2]]["files"].items():
    p = os.path.join(sys.argv[3], rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "w").write(c)
print(TASKS[sys.argv[2]]["prompt"], file=open(os.path.join(sys.argv[3], "..", "prompt.txt"), "w"))
EOF
CFG="$H/opencode.json"
python3 -I - "$HERE/opencode.json" "$CFG" "${OC_BASEURL:-}" <<'EOF'
import json, sys
c = json.load(open(sys.argv[1]))
if sys.argv[3]:
    c["provider"]["lora"]["options"]["baseURL"] = sys.argv[3]
json.dump(c, open(sys.argv[2], "w"), indent=1)
EOF

cd "$W"
T0=$(date +%s)
env -i PATH="/usr/local/bin:/usr/bin:/bin" HOME="$H" TERM=dumb LANG=C.UTF-8 \
  XDG_CONFIG_HOME="$H/.config" XDG_DATA_HOME="$H/.local/share" XDG_CACHE_HOME="$H/.cache" XDG_STATE_HOME="$H/.local/state" \
  OPENCODE_CONFIG="$CFG" OPENCODE_DISABLE_AUTOUPDATE=1 OPENCODE_DISABLE_MODELS_FETCH=1 \
  OPENCODE_DISABLE_PROJECT_CONFIG=1 OPENCODE_DISABLE_CLAUDE_CODE=1 \
  timeout "${OC_TIMEOUT:-1800}" "$OC" run --standalone --auto --format json --model "lora/$MODEL" \
  "$(cat "$H/prompt.txt")" > "$OUT/events.jsonl" 2> "$OUT/stderr.log"
RC=$?
T1=$(date +%s)
# grading: restores the original tests and runs the suite
python3 -I - "$LORA/tests" "$TASK" "$W" <<'EOF'
import os, sys
sys.path.insert(0, sys.argv[1])
from tasks import TASKS
for rel, c in TASKS[sys.argv[2]]["files"].items():
    if rel.startswith("tests/"):
        open(os.path.join(sys.argv[3], rel), "w").write(c)
EOF
python3 -m unittest discover -s tests > "$OUT/grade.log" 2>&1
GR=$?
cp -r "$W" "$OUT/workdir"
N_EV=$(wc -l < "$OUT/events.jsonl")
echo "{\"task\":\"$TASK\",\"model\":\"$MODEL\",\"opencode_rc\":$RC,\"success\":$([ $GR = 0 ] && echo true || echo false),\"seconds\":$((T1 - T0)),\"events\":$N_EV}" | tee "$OUT/result.json"

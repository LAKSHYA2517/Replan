#!/usr/bin/env bash
# One-command reproduction: Full-Duplex-Bench v3 against RePlan's LiveKit agent
# (agent.py). Installs what's missing, starts the agent, runs the benchmark
# against it, scores the run, and stops the agent.
#
#   ./reproduce_fdb_v3.sh            # full 100-example run (~90+ minutes)
#   DRY_RUN_SECONDS=600 ./reproduce_fdb_v3.sh   # time-boxed smoke run
#
# Requires: git, python3.10 (for the benchmark's NeMo ASR), ffmpeg, a .env
# with LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET / GOOGLE_API_KEY.
# No OpenAI key is needed: scoring runs without the LLM judge.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FDB_REPO_URL="https://github.com/DanielLin94144/Full-Duplex-Bench.git"
FDB_DIR="${FDB_DIR:-$ROOT/.fdb_v3}"
FDB_V3="$FDB_DIR/v3"
FDB_DATA_GDRIVE_ID="1SO_4MTazWQ_jvCx0dtmpQ-t40bdd07yz"
PROVIDER_LABEL="replan_gemini2_5"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
RESULTS="$ROOT/results/$RUN_ID"
AGENT_PID=""

log() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

cleanup() {
  if [[ -n "$AGENT_PID" ]] && kill -0 "$AGENT_PID" 2>/dev/null; then
    log "Stopping agent (pid $AGENT_PID)"
    kill "$AGENT_PID" 2>/dev/null || true
    wait "$AGENT_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# ── 1. Preconditions ─────────────────────────────────────────────────────────
log "Checking tools"
for tool in git python3.10 ffmpeg; do
  command -v "$tool" >/dev/null 2>&1 || die "'$tool' not found. On macOS: brew install git python@3.10 ffmpeg"
done

log "Checking configuration (.env)"
[[ -f "$ROOT/.env" ]] || die "Missing .env. Copy .env.example to .env and fill in the keys."
set -a; source "$ROOT/.env"; set +a
for var in LIVEKIT_URL LIVEKIT_API_KEY LIVEKIT_API_SECRET GOOGLE_API_KEY; do
  [[ -n "${!var:-}" ]] || die "$var is empty in .env"
done
export FDB_V3_PATH="$FDB_V3"

# ── 2. RePlan environment ────────────────────────────────────────────────────
log "Setting up RePlan environment"
if [[ ! -d "$ROOT/.venv" ]]; then
  python3 -m venv "$ROOT/.venv"
fi
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -e "$ROOT[dev]"

# ── 3. Benchmark repository and data ─────────────────────────────────────────
log "Fetching Full-Duplex-Bench (v3)"
if [[ ! -d "$FDB_DIR/.git" ]]; then
  git clone --depth 1 "$FDB_REPO_URL" "$FDB_DIR"
fi
if [[ ! -d "$FDB_V3/fdb_v3_data_released" ]]; then
  log "Downloading benchmark audio (about 2 GB)"
  pip install --quiet gdown
  ZIP="$FDB_DIR/fdb_v3_data.zip"
  gdown --id "$FDB_DATA_GDRIVE_ID" -O "$ZIP" || die "Automatic download failed. Download the file from the link in $FDB_V3/README.md, extract fdb_v3_data_released/ into $FDB_V3/, then re-run this script."
  unzip -q -o "$ZIP" -d "$FDB_V3"
fi
[[ -f "$FDB_V3/mock_apis.py" ]] || die "mock_apis.py not found in $FDB_V3"
[[ -d "$FDB_V3/fdb_v3_data_released" ]] || die "fdb_v3_data_released/ not found in $FDB_V3"

# ── 4. Benchmark environment (NeMo ASR, separate from RePlan's) ──────────────
log "Setting up benchmark environment"
if [[ ! -x "$FDB_V3/.venv/bin/python" ]]; then
  python3.10 -m venv "$FDB_V3/.venv"
fi
"$FDB_V3/.venv/bin/pip" install --quiet --upgrade pip
"$FDB_V3/.venv/bin/pip" install --quiet "nemo_toolkit[asr]" pydub ffmpeg-python python-dotenv \
  livekit-agents livekit-plugins-google "livekit[crypto]" openai

# ── 5. Start RePlan's agent ──────────────────────────────────────────────────
mkdir -p "$RESULTS"

# The harness reuses an existing output_<provider>.wav instead of streaming the
# example again, and skips examples with a result file. Clear both for this
# provider so every example is genuinely run against the current agent.
log "Clearing previous outputs for provider $PROVIDER_LABEL"
find "$FDB_V3/fdb_v3_data_released" \( -name "output_${PROVIDER_LABEL}.wav" -o -name "result_${PROVIDER_LABEL}.json" \) -delete
log "Starting agent.py (logs: $RESULTS/agent.log)"
cd "$ROOT"
"$ROOT/.venv/bin/python" agent.py start > "$RESULTS/agent.log" 2>&1 &
AGENT_PID=$!

log "Waiting for the agent to register with LiveKit"
for _ in $(seq 1 60); do
  if grep -q "registered worker" "$RESULTS/agent.log" 2>/dev/null; then
    break
  fi
  kill -0 "$AGENT_PID" 2>/dev/null || die "Agent exited early; see $RESULTS/agent.log"
  sleep 1
done
grep -q "registered worker" "$RESULTS/agent.log" || die "Agent did not register within 60s; see $RESULTS/agent.log"

# ── 6. Run the benchmark against the agent ───────────────────────────────────
log "Running FDB-v3 against the agent (provider label: $PROVIDER_LABEL)"
cd "$FDB_V3"
HARNESS=( .venv/bin/python run_tool_benchmark_all_released.py --provider "$PROVIDER_LABEL" )
if [[ -n "${DRY_RUN_SECONDS:-}" ]]; then
  log "Dry run: stopping the benchmark after ${DRY_RUN_SECONDS}s"
  "${HARNESS[@]}" > "$RESULTS/benchmark.log" 2>&1 &
  HARNESS_PID=$!
  sleep "$DRY_RUN_SECONDS"
  kill "$HARNESS_PID" 2>/dev/null || true
  wait "$HARNESS_PID" 2>/dev/null || true
else
  "${HARNESS[@]}" > "$RESULTS/benchmark.log" 2>&1
fi

# ── 7. Score the run (no LLM judge, so no OpenAI key is needed) ──────────────
log "Scoring"
.venv/bin/python evaluate_tool_calls.py \
  --benchmark benchmark_data_v2.json --results-dir fdb_v3_data_released \
  --provider "$PROVIDER_LABEL" --output "$RESULTS/tool_calls_report.json" \
  | tee "$RESULTS/tool_calls_summary.txt"
.venv/bin/python evaluate_pass_rate.py \
  --benchmark benchmark_data_v2.json --results-dir fdb_v3_data_released \
  --provider "$PROVIDER_LABEL" --output "$RESULTS/pass_rate_report.json" \
  | tee "$RESULTS/pass_rate_summary.txt"

log "Done. Results in $RESULTS"

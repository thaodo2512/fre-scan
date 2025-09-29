#!/usr/bin/env bash
# Run Freqtrade validation and backtesting workflows inside the dev container.

set -euo pipefail

: "${FREQTRADE_DIR:=/freqtrade}"
: "${USER_DATA_DIR:=/freqtrade/user_data}"
: "${CONFIG:=/freqtrade/user_data/config.json}"
: "${STRATEGY:=SampleStrategy}"

log() {
  printf "[TEST] %s\n" "$*"
}

log "Validating pairlist configuration..."
python -m freqtrade list-pairs --config "${CONFIG}" --print-json >/tmp/pairs.json
log "Pairlist output stored at /tmp/pairs.json"

log "Running strategy backtest (dry-run data)..."
freqtrade backtesting --config "${CONFIG}" --strategy "${STRATEGY}" --cache none

log "Running hyperopt parameter validation..."
freqtrade hyperopt --spaces buy sell --config "${CONFIG}" --strategy "${STRATEGY}" --epochs 1 --dry-run-series 1

log "All tests completed."

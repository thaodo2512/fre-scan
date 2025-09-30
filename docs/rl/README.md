# RL Pair Selection + Freqtrade Integration Prompt

Copy/paste the following prompt for an AI to implement an RL‑driven pair selection + inference pipeline that integrates with Freqtrade. This version requires auto‑pulling Binance USDT‑M perpetual pairs into the training config.

---

Goal: Build an RL‑driven pair selection and inference system integrated with Freqtrade. I want to train models on a Jetson Orin Nano (2–3 days per round), then use the trained policy to score all candidate pairs and output a top‑N whitelist for Freqtrade to trade. I will retrain manually later.

New hard requirement: Automatically fetch Binance USDT‑M perpetual pairs (linear futures) and write them into the training config before each training run.

Scope and Platform
- Device: NVIDIA Jetson Orin Nano (ARM64, JetPack/CUDA). Keep training heavy, inference lightweight. Prefer PyTorch + SB3 (PPO/A2C) or a small custom policy. ONNX export for inference if possible.
- Timeframe: 5m. Markets: Binance USDT‑M futures (linear, perpetual). Optionally support spot as a toggle later.

Deliverables
- Pair Discovery (must‑have)
  - Module `rl/pairs.py` (or `rl/update_pairs.py`) to auto‑pull Binance USDT‑M perpetual pairs using CCXT:
    - CCXT config: `options.defaultType = "future"`, `options.defaultSubType = "linear"`, enable rate‑limit.
    - Load markets, select only symbols that are:
      - Swap/perpetual (contractType PERPETUAL), linear, quote == USDT, active/tradable.
      - Symbol format must be `BTC/USDT:USDT` (Binance USDT‑M).
    - Optional filters: min 24h quote volume threshold, spread sanity check.
  - Outputs:
    - `user_data/rl/pairs_usdtm.json` (the raw discovered list).
    - Update training config file with `pairs` automatically before each training run.
  - CLI:
    - `python rl/update_pairs.py --exchange binance --market futures --quote USDT --min-volume 1_000_000 --out user_data/rl/pairs_usdtm.json --update-config rl/config.train.json`
  - Schedule: run at the start of every training; optionally add a daily refresh.

- Code Structure
  - `rl/env.py`: Gymnasium env (per pair):
    - Observation: windowed OHLCV + engineered features (returns/log‑returns, rolling vol, RSI/EMAs, spread proxy).
    - Action space: discrete {0=no‑position, 1=long} for pair selection scoring; optionally a confidence head.
    - Reward: risk‑adjusted next‑step return with penalties (fees/turnover/drawdown).
  - `rl/train.py`: Training loop to:
    - Auto‑call `rl/update_pairs.py` first to populate pairs.
    - Train 1 policy per pair (simple baseline) or a shared policy (multi‑task) later.
    - Save best checkpoints/metrics to `user_data/rl/models/<PAIR>.pt` (and optional `.onnx`).
  - `rl/infer.py`: Inference to:
    - Load trained models and compute a score for each pair on the latest window.
    - Output `user_data/rl/pair_scores.json` and `user_data/rl/whitelist.json` (top‑K).
  - `rl/inference_server.py` (optional): FastAPI endpoint `/score` returning an array of pairs for RemotePairList.
  - `rl/utils.py`: Feature engineering, dataset caching, slippage/fees, metrics, model I/O.

- Training/Inference Config
  - `rl/config.train.json` example keys:
    - `pairs_path`: `user_data/rl/pairs_usdtm.json`
    - `pairs`: []  (auto‑populated by `update_pairs.py`)
    - `timeframe`: "5m"
    - `lookback`: 96
    - `episode_days`: 30
    - `fees_bps`: 7
    - `min_volume_usd`: 1_000_000
    - `market`: "futures"
    - `exchange`: "binance"
    - `ccxt_options`: `{ "defaultType": "future", "defaultSubType": "linear" }`
    - `total_timesteps`: e.g., 5e6
    - `checkpoint_dir`: `user_data/rl/checkpoints`
  - `rl/config.infer.json`:
    - `models_dir`: `user_data/rl/models`
    - `pairs_path`: `user_data/rl/pairs_usdtm.json`
    - `top_k`: 50
    - Output `whitelist_path`: `user_data/rl/whitelist.json`

- Freqtrade Integration
  - Option A (file producer preferred): Use ProducerPairList to read `user_data/rl/whitelist.json`, updated by `rl/infer.py` every N minutes. Support `freqtrade reload_config` or pairlist refresh without restart.
  - Option B (remote): Use RemotePairList pointing to `rl/inference_server.py /score`.
  - Keep the Strategy minimal (no signals) or a simple rule (EMA cross) if needed. RL gating via pairlist determines the tradable universe.

- Docker/Compose
  - Add `rl-trainer` service (NVIDIA runtime) to run `rl/train.py` (long‑running). It must:
    - Call `rl/update_pairs.py` before starting.
    - Use Jetson‑compatible PyTorch/SB3 image or Dockerfile based on an L4T PyTorch image.
  - Add `rl-infer` service (lightweight) to run `rl/infer.py` periodically (cron‑like loop) and write `whitelist.json`.
  - Mount `user_data/rl` for models, pairs, and outputs. Pass env vars for CCXT options and thresholds.

- Performance and Correctness
  - Inference latency: < 1s per pair on Jetson (batching ok).
  - No lookahead bias; only use data up to t for scoring t+1.
  - Include trading costs; penalize churn and drawdown.
  - Unit tests for env and feature window shapes.

- Documentation
  - README with Jetson setup (NVIDIA runtime, JetPack), how to build/run `rl-trainer` and `rl-infer`, how to wire ProducerPairList/RemotePairList.
  - Example configs and a small test set of pairs/time periods to sanity‑check quickly.

- RL Details (baseline)
  - Algorithm: PPO first; try A2C later if needed.
  - Features: [close_norm, hl2, ohlc returns, rolling vol, RSI(14), EMA(20/50)] over last 96 candles.
  - Reward: `return_t+1 − α*turnover − β*drawdown_penalty`. Add cooldown to discourage churn.
  - Start with per‑pair models to keep complexity low.

- Output Formats
  - `whitelist.json`:
    - `{ "pairs": ["BTC/USDT:USDT", ...], "generated_at": "...", "top_k": 50, "scoring": "ppo_expected_reward_v1" }`
  - `pair_scores.json`:
    - `[{ "pair": "...", "score": 0.123, "rank": 1 }, ...]`

- Acceptance Criteria
  - `rl/update_pairs.py` reliably fetches Binance USDT‑M perpetual pairs and updates `rl/config.train.json` automatically.
  - `rl/train.py` runs on Jetson and produces model files for at least a small subset within ~1 hour when configured for a short test.
  - `rl/infer.py` writes a valid `whitelist.json` with top‑K pairs.
  - Freqtrade consumes `whitelist.json` via ProducerPairList (or through RemotePairList) without restart and updates the tradable universe.

Implementation Notes
- Markets fetch: Use CCXT `binance.load_markets()` with `options.defaultType="future"`, `options.defaultSubType="linear"`. Filter where `market["swap"] == True`, `market["linear"] == True`, `market["quote"] == "USDT"`, `market["active"] == True`. Use `market["symbol"]` like `BTC/USDT:USDT`.
- Optional extra filters: exclude maintenance, delisted, or low volume; log skipped reasons.
- Data download: parallelized OHLCV prefetch for training time ranges (respect rate limits).
- Provide a dry‑run mode for `update_pairs.py` to print changes without writing files.

---

Use this as the implementation brief for the RL components. Keep dependencies minimal and Jetson‑friendly.


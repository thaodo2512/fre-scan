# Changelog

## [Unreleased]
- Add Freqtrade development environment setup script via Docker Compose
- Provide sample Freqtrade Docker configuration with dynamic pairlists and integrations
- Introduce development docker-compose definition with persistent volumes and dry-run trade command
- Add Telegram status reporting script for Freqtrade REST API polling
- Configure VSCode devcontainer for Freqtrade with automated dev dependency install and test script
- Fix docker-compose command invocation and volume configuration for Freqtrade service
- Move config.json to user_data/config.json to match container path
- Add Telegram silent notifications and HTTP retries in report.py
- Reporter: Optional pairlist section with clean formatting (list/columns)
- Scrub Telegram secrets from config; disable by default and document env overrides
- Add reporter sidecar service to docker-compose to send Telegram status updates periodically
- Fix reporter service entrypoint to run the Python script (not the freqtrade CLI)
- Add .env.example and ignore local .env for safe configuration
- Add RL implementation brief at docs/rl/README.md (auto-pull Binance USDT-M pairs into training config)
- Add user_data/requirements-dev.txt to satisfy devcontainer postCreate install
- Add entry_pricing/exit_pricing sections to config for exchange schema compliance
- Add minimal SampleStrategy at user_data/strategies/sample_strategy.py
- Update pairlists schema: use "method" and flatten plugin options (remove nested "config")
- Set max_open_trades to 5 and initial_state to running to streamline startup
- Switch exchange to Binance USDT-M futures: enable trading_mode=futures, margin_mode=isolated, position_mode=single, leverage=2, and set CCXT defaultType=future (linear)

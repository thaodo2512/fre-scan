from pandas import DataFrame

from freqtrade.strategy import IStrategy


class SampleStrategy(IStrategy):
    """
    Minimal strategy for bootstrapping.
    - Uses 5m timeframe
    - Long-only, does not enter trades by default
    Replace conditions with your real logic.
    """

    timeframe = "5m"
    can_short = False

    # Minimal ROI (time: profit) mapping
    minimal_roi = {
        "0": 0.02,  # 2% target
    }

    stoploss = -0.05  # -5%
    trailing_stop = False

    use_exit_signal = True
    exit_profit_only = False
    ignore_buying_expired_candle_after = 0

    startup_candle_count = 20

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Add indicators here if needed.
        return dataframe

    # New-style API (Freqtrade 2023+)
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        return dataframe

    # Legacy API (kept for compatibility with older versions)
    def populate_buy_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["buy"] = 0
        return dataframe

    def populate_sell_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sell"] = 0
        return dataframe

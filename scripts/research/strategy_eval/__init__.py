"""Frozen, offline P1 position-overhang discriminator. No execution interfaces."""

TASK = "V065-P1-COST-AWARE-POSITION-Z-ENGINE-R1"
SEED = 650410
DAY = 86400
HORIZONS = (8, 4, 12, 24)
LABELS = (
    "SOURCE_NOT_ADMITTED", "PIT_UNKNOWN", "COST_UNVALIDATED_REAL_FILL",
    "NO_ALPHA_ESTABLISHED", "G4_TESTNET_NO_GO", "LIVE_NO_GO", "REAL_FUNDS_WRITE_NONE",
)
X_NAMES = (
    "log_return_1h", "log_return_4h", "log_return_24h",
    "realized_volatility_1h", "realized_volatility_24h", "log1p_quote_volume_1h",
    "log_relative_base_volume_1h", "quote_taker_imbalance_1h",
    "close_in_range_24h_centered", "mean_log_usdm_spot_basis_1h",
)
PLAN = {
    "task": TASK, "seed": SEED, "labels": list(LABELS),
    "mechanism": "A_POSITION_OVERHANG", "B_status": "RESERVED_NOT_ENABLED",
    "origin_second_of_hour": 60, "cutoff_second_of_hour": 0,
    "bar_interval_s": 60, "bar_end_rule": "STRICTLY_BEFORE_CUTOFF",
    "entry_rule": "FIRST_MINUTE_OPEN_STRICTLY_AFTER_ORIGIN_HH02",
    "price_reference": "LAST_PRICE_PROXY_NOT_EXECUTABLE_QUOTE",
    "z_native_interval_s": 300, "z_age_window_s": [300, 600],
    "z_predecessor_s": 14400, "z_base_field": "sum_open_interest",
    "z_ratio_field": "sum_toptrader_long_short_ratio", "x_names": list(X_NAMES),
    "horizons_h": list(HORIZONS), "primary_horizon_h": 8,
    "outer_development_days": [42, 56, 70], "outer_validation_days": 14,
    "inner_validation_days": 7, "inner_folds": 3,
    "purge_max_horizon_h": 24, "embargo_s": 3600,
    "ridge_lambdas": [0.1, 1.0, 10.0], "score_coefficient_upper_bound": 0.0,
    "cost_scenarios": ["baseline_16bp", "stress_32bp"],
    "carry_reserve_bp_per_day": 5.0, "edge_buffer_bp": 1.0,
    "funding_endpoints": "entry < settlement <= exit",
    "capital": "1/H_FIXED_SLEEVES_NO_LEVERAGE_NO_REINVESTMENT",
    "claim_slots": 8, "alpha": 0.05, "bootstrap_reps": 9999,
    "bootstrap_days": 7, "minimum_week_blocks": 12,
    "historical_receiver_clock": "UNKNOWN_NOT_RECONSTRUCTED",
}

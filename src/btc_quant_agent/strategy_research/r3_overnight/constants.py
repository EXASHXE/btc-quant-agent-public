"""Constants for G2 R3 overnight discovery research sidecar."""

from decimal import Decimal

# Controller task and version identifiers
TASK_ID = "V06_G2_R3_PARALLEL_P0_OFFLINE_PREPARATION"
CONTROLLER_DISPATCH_SHA = "56f8a9faa1a4539124ab006b49bf42b6e7c997e3"
METHOD_ADDENDUM_HEAD_SHA = "cf2d5cc33774cdcff7d709636305bba830e977ef"
METHOD_START_SHA = "e5b2006a89441f7eb2ec900e508aff451106b87a"
FROZEN_CODE_BASE_SHA = "e0ff8c3473de4bfa3e66fe7928d42992a4d38a32"

# Candidate registry constants
EXPECTED_CANDIDATE_COUNT = 8
SUPPORTED_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")

CANDIDATE_IDS = (
    "STRUCTURAL_CONTINUATION_LONG_04H",
    "STRUCTURAL_CONTINUATION_LONG_12H",
    "STRUCTURAL_CONTINUATION_SHORT_04H",
    "STRUCTURAL_CONTINUATION_SHORT_12H",
    "CLOSED_RETEST_LONG_04H",
    "CLOSED_RETEST_LONG_12H",
    "CLOSED_RETEST_SHORT_04H",
    "CLOSED_RETEST_SHORT_12H",
)

# Virtual book capital and risk parameters
INITIAL_EQUITY_USDT = Decimal("1000.000000000000")
ALLOCATION_CEILING_PER_ASSET_USDT = Decimal("333.333333333333")
EQUITY_RESERVE_FRACTION = Decimal("0.05")  # 5% reserve
DRAWDOWN_KILL_THRESHOLD_USDT = Decimal("100.000000000000")  # 10% of 1000 USDT
RESERVE_BUFFER_MULTIPLIER = Decimal("1.10")  # 10% adverse pricing buffer

# Risk distance constraints (bps as decimals)
MIN_RISK_BPS = Decimal("0.0030")  # 30 bps
MAX_RISK_BPS = Decimal("0.0250")  # 250 bps
MAX_GAP_ATR_FRACTION = Decimal("0.25")  # 0.25 ATR20 gap limit
TARGET_R_MULTIPLE = Decimal("2.0")  # 2R target

# Cost model parameters: Base scenario (22 bps round trip)
BASE_TAKER_FEE_BPS = Decimal(6)
BASE_HALF_SPREAD_BPS = Decimal(2)
BASE_SLIPPAGE_BPS = Decimal(3)
BASE_TOTAL_LEG_FRICTION_BPS = Decimal(5)  # half_spread + slippage embedded
BASE_TOTAL_LEG_FEE_BPS = Decimal(6)  # fee debited separately
BASE_ROUND_TRIP_BPS = Decimal(22)

# Cost model parameters: Stress scenario (44 bps round trip)
STRESS_TAKER_FEE_BPS = Decimal(12)
STRESS_HALF_SPREAD_BPS = Decimal(4)
STRESS_SLIPPAGE_BPS = Decimal(6)
STRESS_TOTAL_LEG_FRICTION_BPS = Decimal(10)  # half_spread + slippage embedded
STRESS_TOTAL_LEG_FEE_BPS = Decimal(12)  # fee debited separately
STRESS_ROUND_TRIP_BPS = Decimal(44)

# Funding proxy parameters
BASE_FUNDING_RATE_PER_EVENT = Decimal("0.0004")  # 4 bps adverse
STRESS_FUNDING_RATE_PER_EVENT = Decimal("0.0008")  # 8 bps adverse
FUNDING_OWNERSHIP_HALF_WINDOW_MS = 15_000  # +/- 15 seconds around whole hour

# Timing and clocks
MINUTE_MS = 60_000
HOUR_MS = 3_600_000
FOUR_HOUR_MS = 14_400_000
DECISION_AVAILABILITY_LAG_MS = 60_000  # Bar close + 60s
FILL_DELAY_FROM_DECISION_MS = 60_000  # Order due at open O + 60s
FILL_ACK_DELAY_MS = 60_000  # Fill acknowledgment available at fill + 60s
MARK_STALENESS_LIMIT_MS = 120_000  # 120s mark freshness limit
COOLDOWN_DURATION_MS = 4 * 3_600_000  # 4 hours

# Ineligibility labels
STRESS_COST_GEOMETRY_INELIGIBLE = "STRESS_COST_GEOMETRY_INELIGIBLE"
SOURCE_OR_PERMISSION_BLOCKED = "SOURCE_OR_PERMISSION_BLOCKED"
NO_EMPIRICAL_RESULTS = "NO_EMPIRICAL_RESULTS"
REAL_FUNDS_WRITE_AUTHORITY = "NONE"

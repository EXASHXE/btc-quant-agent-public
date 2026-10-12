# R3 frozen developmental experiment

Task: V06_G2_CODEX_BTC_EXIT_AWARE_DEVELOPMENT_R3. Actual model/effort mode:
UNKNOWN (no authoritative runtime selector available). Parent:
3df7a9a490a06c398d20da57bf19fc48d3b1c74e. Authority:
c852c7285f92d0780cba23a44cb8d8afb7b5428a. No trading authority.

This protocol and its JSON roster are committed and pushed before any new
strategy scoring. They are immutable thereafter. Exactly 27 combinations:
A/B/C × X0/X1/X2 × H08/H18/H24, two fixed cost scenarios each. No tuning,
additional entry rule, winner-dependent scenario or reserved source access.
R2's six development hypotheses all ended DEVELOPMENT_NO_GO. R2 already had
2R targets, stops, adverse gaps and caps. These are exposed development samples,
not pristine OOS, regardless of this new freeze.

## Bars, entry identity and clocks

Input is dense UTC 1m Last OHLCV and taker-buy base volume. Complete UTC 15m,
1h and 4h groups only. I=(2×sum taker-buy / sum base volume)−1; zero volume is
undefined. ATR20 is arithmetic mean of 20 true ranges, TR=max(H−L, |H−priorC|,
|L−priorC|), first TR=H−L. EMA20/50 use SMA seeds then alpha=2/(N+1). ER12 is
absolute 12-bar change divided by sum of 12 absolute changes, zero denominator
undefined. No forward seeding, filling gaps or use of an unclosed bar.

All entries need 60 completed 4h bars and 20 completed 1h bars. Global latest
1h ATR20 / current 15m close must lie in [15,250] bp. Let side s=+1 long, −1
short. Feature bars close at exclusive UTC minute E. signal_available=E+60000;
decision=signal_available; order_possible=decision+60000; fill=order_possible
at that minute's open. Actual historical ingress is UNKNOWN: this is a fixed
conservative event-time reconstruction. The entry-open gap versus signal close
must be <=0.25×latest signal 1h ATR. Raw entry to initial stop risk must be
[30,300] bp. Stop rounded outward to assumed 0.1 USDT tick. Targets are based
on effective entry and R=s×(effective entry−rounded initial stop), R>0.

A: execute unchanged R2 generate() with its exact six-family frozen roster,
retain only FLOW_CONFIRMED_TREND_08H events, including original event_id,
window, side, stop, ATR and clocks. Other R2 events are discarded without
outcome replay. No cap- or exit-dependent entry signal changes. A exact source
and roster hashes are in FREEZE_AND_SOURCE_IDENTITY.json.

B: breakout–retest–reacceptance. At breakout b, 4h C/EMA20/EMA50 are ordered
in direction s, s×(EMA20−EMA20 three bars earlier)>0, ER12>=0.25; latest 1h
s×(C−EMA20)>0 and s×(EMA20−EMA20 three bars earlier)>0, s×I1h>=0.05.
Freeze the preceding 8 completed 15m bars' directional edge (HH long, LL short)
and breakout ATR15. Breakout close extends beyond edge by >0.10 ATR15,
signed body>=0.20 ATR15, s×I15>=0.10, volume>=1.10×mean preceding20 volumes.
Retest must be a distinct bar b+1..b+3: directional extreme relative to edge
in [−0.25,+0.20] breakout ATR15, close on accepted side of edge. A subsequent
distinct bar, no later than b+4, reaccepts: close beyond edge by >0.10 breakout
ATR15 and beyond previous bar's directional extreme; signed body>=0.20 current
ATR15, s×I15>=0.10, volume>=mean preceding20 volumes. The same regime rules
must hold at confirmation. Stop=min lows from retest through confirmation−
0.25 current ATR1h long, max highs+0.25 ATR1h short. One pending setup per side;
new breakouts ignored while pending. Any intermediate close beyond the wrong
side by >0.25 breakout ATR invalidates it; expire after b+4. Consume on emission.

C: failed-breakout exhaustion followed by next-bar range reentry. Freeze the
preceding16 completed 15m HH/LL before breakout b. For long: Lb<LL−0.15 ATR15b,
Cb<=LL; short: Hb>HH+0.15 ATR15b, Cb>=HH. The breakout has signed body<=0,
s×Ib<=−0.15, volume>=1.20×mean preceding20 volumes. Exactly the next completed
15m bar must close strictly inside the frozen range, beyond the breached edge
by >0.10 breakout ATR15; signed body>=0.20 current ATR15, s×I>=0.10,
s×(I−Ib)>=0.25. At confirmation ER12_4h<=0.25 and
|C4h−EMA20_4h|<=1.25 ATR20_4h. Stop=min(b/current lows)−0.25 ATR1h long,
max(b/current highs)+0.25 ATR1h short. No RSI condition and no same-bar reentry.
Missing required features produce no signal, with diagnostics; no retry tuning.

## Execution and complete per-leg accounting

X0: full 2R target; original structural/ATR stop; cap or causal account risk
closure. X1: 40/30/30% of initial quantity at 1/1.8/3R. X2: 50% at1.5R,
remainder trailing, bounded by3R. Partial quantities floor to assumed0.001BTC
lot; final leg closes the entire lot-aligned remainder. Reject entry if any
required initial partial quantity is zero or below assumed5USDT notional;
report PARTIAL_LOT_INELIGIBLE. All fill events have unique IDs; duplicates
cannot mutate quantity/cash. Sum exited quantity must equal initial quantity
at completion; otherwise INCOMPLETE_FILLS. No maker-fill guarantee is assumed.

BASE fee/spread/slippage per leg=6/2/3bp; STRESS=12/4/6bp. Effective prices
apply adverse spread+slip then adverse tick rounding. Entry fee is charged once
on full effective entry notional; each exit fee once on its actual effective
price×actual quantity. Entry and exit friction components plus tick drag are
reported separately. Cash, prices and fees use Decimal, cash quantized to8
places HALF_EVEN. USDT/bps/netR denominators are initial raw entry notional and
initial R×initial quantity, never final exit price times full quantity.

Protective bracket prices are assumed standing atomically at entry open, as in
R2; real submission/fills are unverified. At a minute open, adverse stop gaps
execute at worse open. Otherwise active stop touch precedes every TP touch.
Favorable TP gaps execute at target, never better. Multiple increasing TPs may
execute in one minute only if active stop is not touched. Any minute spanning
stop and a target records MINUTE_PATH_UNKNOWN with conservative stop-first.
At cap, first enforce adverse open stop, then close remaining at open capped
at the furthest standing profit target. Intrabar fills time at minute end−1;
open fills time at open. ACK=ceil(fill/minute)×minute+minute.

TP1 must execute and ACK before any protection transition. X1 residual break-even
solves residual entry fee + prospective exit fee + adverse spread/slip/tick so
residual net>=0, without crediting TP1 profit. Queue replacement at the next
minute open after TP1 ACK. Never apply it to the TP1 minute or retroactively.
X2 after TP1 ACK uses latest observed completed1h close ±1.5×ATR20_1h,
available no earlier than hour end+60000, replacement next minute after that
observation (and after TP1 ACK). Reevaluate on each newly observed hour bar;
missing ATR retains initial/current stop. Active and pending stops only tighten,
never loosen; raw 3R profit cap remains standing. The conservative ACK/next-open
replacement can take 2–3 minutes after a TP1 fill.

## Folds, paired episodes, accounts and risk

Scored Feb/Jun/Sep/Dec in2021–2023; warmups Jan/May/Aug/Nov. Exactly24 public
archives. Retain R2 half-open score windows: second day00:00 through last
day00:00 (24h purge each edge). Warmups never scored. Common eligibility across
all27 requires entry+24h+60s ACK<=score_end, preventing cap-dependent missing
future. Preserve raw signal identities and log all cutoff/refusal reasons.

Every candidate/cost/month starts an independent1000USDT account, one position,
50%allocation after5%equity reserve. Size includes R2 conservative entry/gap,
exit-cost and unknown hourly8bp financing reserves; reserves are not billed
as fabricated funding. One-hour cooldown begins at final exit ACK; partial
proceeds cannot fund a second position. No reentry while any residual/pending
ACK remains. Dense Last-close liquidation-cost proxy equity is measured each
minute. Known equity uses the close two minute opens earlier. Peak-to-known
equity loss>=100USDT disables entries and queues full risk close next open;
known remaining notional>known equity likewise queues full risk close. This
R3 full risk-close differs from R2 account partial exposure reductions and is
reported explicitly. No leverage and no continuous-year ROI from reset books.

Pair X1−X0 and X2−X0 on every common feasible frozen entry, same side/time,
same initial quantity sized from fixed1000USDT and same cap/cost. These episodes
ignore portfolio blocking/cooldown and are unfunded controls, not account
returns. Also report actual portfolio entry-ID intersections and differences
from funding/cooldown/risk disable. Preserve rejected and zero-trade cells.

## Source admission, funding and preregistered inference

Use only exact authorized Binance Vision futures/um/monthly/klines/BTCUSDT/1m
URLs and companion CHECKSUM. Verify provider SHA256 before ZIP extraction;
exactly one expected CSV member,12columns, exact UTC full-calendar row count,
unique dense60s opens, close=open+59999, finite valid OHLCV, nonnegative counts,
and0<=taker_buy_base<=base (Decimal check). Header aliases follow pinned R2.
No forward fill, owner-cache fallback or reserved paths. Fail closed on missing
archive, checksum mismatch, schema or continuity failure. At most3 transient
requests per object; explicit403/451 immediately stops source acquisition,
without proxy rotation or TLS weakening. Scratch raw bodies never committed.

Binance Vision attribution; source-derived results CC BY-NC-SA4.0. Current
official dataset terms permit this non-commercial historical/open evaluation;
code repository MIT is not treated as the dataset license. Official references:
https://github.com/binance/binance-public-data and
https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md.
Archives can be corrected; current archive SHA is not historical-ingress proof.
Real Mark, OI, depth, funding and historical venue filters/fees remain UNKNOWN.
All PnL is NET_EX_FUNDING_PROXY. Adverse funding sensitivity:4/8bp per possible
UTC8h settlement window (±15s) and unknown-hourly8bp, on remaining quantity at
the time, conservative contemporaneous minute high. Never treat unknown funding
as verified zero. Separately disclose an additional fixed2bp exit spread and
3bp exit slippage sensitivity, with no selection or parameter retuning.

Selection uses STRESS only: >=50 completed trades, >=6active months, >=2years,
equal represented-year mean trade netbps>0, >=2nonnegative year means, netUSDT
PF>1, every monthly closed+dense MTM DD<=15%. X1/X2 additionally need positive
same-entry paired mean improvement and paired worst5%tail no worse than X0 by
more than10bp. X0 cells are baseline comparators, not new promoted hypotheses.
Require corrected one-sided net and paired p<=.05; rank at most3eligible by
paired mean netbps, then STRESS mean netbps, then lexical ID.

Exactly27 hypotheses count for multiplicity, including zero-trade/baseline
cells. Predeclare10000 UTC calendar-week block bootstrap draws within year,
include zero-trade eligible weeks; shared draws across candidates, seed27182026,
95%CI. Undefined no-trade resamples explicitly counted, never zero-imputed.
One-sided centered block-bootstrap p=(1+#(bootstrap−observed>=observed))/(B+1),
Bonferroni p_adj=min(1,27×p); net and paired both must meet threshold. Repeat
descriptive uncertainty with calendar-month blocks, same seed, no new trial.
Small-support/uncertain intervals remain developmental, never independent Alpha.

No winner => R3_DEV_NO_GO. Inaccessible/invalid required sources or unresolved
engine correctness => R3_SOURCE_OR_SCIENCE_BLOCKED, unexecuted scores null.
No 28th candidate, no2024–25 confirmation, and no trading/live/testnet authority.

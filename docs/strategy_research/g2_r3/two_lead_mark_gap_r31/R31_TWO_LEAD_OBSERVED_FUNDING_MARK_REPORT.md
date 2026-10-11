# Fixed two12h BTC leads — gap repair and observed Funding/Mark economics R3.1

**EX_POST_EXPOSED_DEV_ONLY;MONTHLY_VERIFIED_PLUS_GAP_ONLY_VERIFIED_DAILY_OR_API**

Terminal `R31_TWO_LEAD_OBSERVED_FUNDING_MARK_COMPLETE_DEVELOPMENT_ONLY`. **No Alpha, OOS, promotion, later holdout or trading authority.**

Frozen implementation `c36df02a438dd0b46a02168d910479853c294dd4`; Controller `6b08af95335a4d577e1367a9b0652258bad1ca35`; start `057c47a4bfd248131f4fd94d12d3deef73c65e1f`.
Original authenticated Mark rows1,565,280 preserved; inserted 11,520 gap rows; composite 1,576,800/1,576,800. Actual signed Funding events3285; original Last rows1,576,800. All36 months2021–23 retained; Jan2021warmup and35scoremonths/24hpurge unchanged.

## Actual eight-day source recovery

| UTC gap day | Daily rows | API rows | Still missing | Authentication/cross-source |
|---|---:|---:|---:|---|
| 2021-07-01 | 1440 | 0 | 0 | No direct same-clock monthly overlap (entire days missing); daily SHA authentic, API has lower transport provenance |
| 2021-07-24 | 1440 | 0 | 0 | No direct same-clock monthly overlap (entire days missing); daily SHA authentic, API has lower transport provenance |
| 2021-07-25 | 1440 | 0 | 0 | No direct same-clock monthly overlap (entire days missing); daily SHA authentic, API has lower transport provenance |
| 2021-07-26 | 1440 | 0 | 0 | No direct same-clock monthly overlap (entire days missing); daily SHA authentic, API has lower transport provenance |
| 2021-07-27 | 1440 | 0 | 0 | No direct same-clock monthly overlap (entire days missing); daily SHA authentic, API has lower transport provenance |
| 2022-07-31 | 1440 | 0 | 0 | No direct same-clock monthly overlap (entire days missing); daily SHA authentic, API has lower transport provenance |
| 2022-10-02 | 1440 | 0 | 0 | No direct same-clock monthly overlap (entire days missing); daily SHA authentic, API has lower transport provenance |
| 2023-02-24 | 1440 | 0 | 0 | No direct same-clock monthly overlap (entire days missing); daily SHA authentic, API has lower transport provenance |

All daily/API requests were frozen before body inspection. Only exact8days requested, daily first, API only its remaining missing intervals. Existing monthly values were never overwritten; clock-counts, OHLC, duplicates, overlap tolerances and source hashes were checked. API rows are `PROVIDER_API_SECONDARY_NOT_ZIP_AUTHENTICATED`, never equated to provider SHA ZIP. Repair is retrospective and does not establish2021publicationknown-at. R3 public cache was read-only and signature/hash verified; new bodies/ledgers only in R31scratch.

## Measured two-lead comparison

**EX_POST_EXPOSED_DEV_ONLY;MONTHLY_VERIFIED_PLUS_GAP_ONLY_VERIFIED_DAILY_OR_API**

| Candidate | Cost | N baseline/funded | Before Funding bp | Fixed-trade Funding bp | Funded bp | Net PF funded | Mark DD funded % | Funded1000USDT return % | Funding debit/credit USDT | 48FW7/14d LCB funded |
|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | BASE | 34/34 | 37.6205 | 37.3500 | 37.3500 | 1.6955 | 7.7299 | 11.6978 | 1.7126/0.8689 | -60.6725/-66.2742 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | STRESS | 34/34 | 11.5036 | 11.2047 | 11.2047 | 1.1578 | 10.0641 | 3.2529 | 1.7960/0.8599 | -85.2583/-89.5697 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | BASE | 55/55 | 46.0478 | 45.9244 | 45.9244 | 2.0955 | 6.1570 | 23.2855 | 2.1546/1.5264 | -18.6230/-20.9963 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | STRESS | 55/55 | 19.1322 | 19.0135 | 19.0135 | 1.3631 | 9.2338 | 9.6831 | 2.1481/1.5451 | -41.4854/-44.7969 |

No-funding full trade/event/control ledger and uncompressed minute cash curve SHA exactly matched R2. STRESS n34/+11.504bp and n55/+19.132bp precede observed funding. Baseline execution remains Last-price based; repaired Mark never determines entries/stops/targets/fills. Cash-neutral means selection/quantity fixed; its diagnostic cash equity includes funding. Funding-aware uses settled past cash for future quantities; cash reconciliation/month continuity are audited.

### W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H

**EX_POST_EXPOSED_DEV_ONLY;MONTHLY_VERIFIED_PLUS_GAP_ONLY_VERIFIED_DAILY_OR_API**

**BASE / cash_neutral_same_trade_overlay / EX_POST_EXPOSED_DEV_ONLY;MONTHLY_VERIFIED_PLUS_GAP_ONLY_VERIFIED_DAILY_OR_API**

| Year | N | Gross bp | Net bp | Net R | Net PF | Mark DD % | Funded cash return % | Signed Funding USDT | LONG/SHORT N |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2021 | 8 | 144.7084 | 122.7601 | 0.4170 | 2.3840 | 7.7299 | 9.1080 | 0.0199 | 4/4 |
| 2022 | 10 | 31.2595 | 8.5850 | 0.0149 | 1.1738 | 4.4553 | 0.7128 | -0.5755 | 6/4 |
| 2023 | 16 | 34.8413 | 12.6232 | 0.1730 | 1.3144 | 5.4273 | 1.6490 | -0.2880 | 9/7 |

Matched balanced-control increment=57.7320bp; PAUSE=0. Side diagnostics={'LONG': {'scientific_grade': 'COST_PROXY_LAST_TRADE_PLUS_OBSERVED_FUNDING_AND_MARK_DEV_ONLY', 'n': 19, 'mean_gross_bps': 40.18245391691022, 'mean_net_bps': 17.159975544782725, 'net_profit_factor': 1.31826189123643, 'mean_net_R': 0.007603671159564074, 'max_within_trade_mark_mtm_dd_pct': 2.802113049282371, 'side_risk_basis': 'actualaccountwithintrade conditionalDD;notseparatelyfundedsideportfolio'}, 'SHORT': {'scientific_grade': 'COST_PROXY_LAST_TRADE_PLUS_OBSERVED_FUNDING_AND_MARK_DEV_ONLY', 'n': 15, 'mean_gross_bps': 84.28372953437864, 'mean_net_bps': 62.92411308394258, 'net_profit_factor': 2.1808229504721908, 'mean_net_R': 0.40719571146276545, 'max_within_trade_mark_mtm_dd_pct': 3.2622447680906888, 'side_risk_basis': 'actualaccountwithintrade conditionalDD;notseparatelyfundedsideportfolio'}}. Signed funding total=-0.8437USDT, 36 event/trade attributions; 7 trades cross no settlement in complete observed stream. Extra roundtrip cost drag sensitivity mean bp={'-10': 47.35003622382384, '-5': 42.35003622382384, '-2': 39.35003622382384, '2': 35.35003622382384, '5': 32.35003622382384, '10': 27.350036223823842}; descriptive gross+funding break-even friction=59.3684bp. This is not a maker-fill or optimized cost claim.

**BASE / funding_aware_funded_replay / EX_POST_EXPOSED_DEV_ONLY;MONTHLY_VERIFIED_PLUS_GAP_ONLY_VERIFIED_DAILY_OR_API**

| Year | N | Gross bp | Net bp | Net R | Net PF | Mark DD % | Funded cash return % | Signed Funding USDT | LONG/SHORT N |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2021 | 8 | 144.7084 | 122.7601 | 0.4170 | 2.3840 | 7.7299 | 9.1080 | 0.0199 | 4/4 |
| 2022 | 10 | 31.2595 | 8.5850 | 0.0149 | 1.1738 | 4.4553 | 0.7128 | -0.5755 | 6/4 |
| 2023 | 16 | 34.8413 | 12.6232 | 0.1730 | 1.3144 | 5.4273 | 1.6490 | -0.2880 | 9/7 |

Matched balanced-control increment=57.7320bp; PAUSE=0. Side diagnostics={'LONG': {'scientific_grade': 'COST_PROXY_LAST_TRADE_PLUS_OBSERVED_FUNDING_AND_MARK_DEV_ONLY', 'n': 19, 'mean_gross_bps': 40.18245391691022, 'mean_net_bps': 17.159975544782725, 'net_profit_factor': 1.31826189123643, 'mean_net_R': 0.007603671159564074, 'max_within_trade_mark_mtm_dd_pct': 2.802113049282371, 'side_risk_basis': 'actualaccountwithintrade conditionalDD;notseparatelyfundedsideportfolio'}, 'SHORT': {'scientific_grade': 'COST_PROXY_LAST_TRADE_PLUS_OBSERVED_FUNDING_AND_MARK_DEV_ONLY', 'n': 15, 'mean_gross_bps': 84.28372953437864, 'mean_net_bps': 62.92411308394258, 'net_profit_factor': 2.1808229504721908, 'mean_net_R': 0.40719571146276545, 'max_within_trade_mark_mtm_dd_pct': 3.2622447680906888, 'side_risk_basis': 'actualaccountwithintrade conditionalDD;notseparatelyfundedsideportfolio'}}. Signed funding total=-0.8437USDT, 36 event/trade attributions; 7 trades cross no settlement in complete observed stream. Extra roundtrip cost drag sensitivity mean bp={'-10': 47.35003622382384, '-5': 42.35003622382384, '-2': 39.35003622382384, '2': 35.35003622382384, '5': 32.35003622382384, '10': 27.350036223823842}; descriptive gross+funding break-even friction=59.3684bp. This is not a maker-fill or optimized cost claim.

**BASE monthly funded accounts / EX_POST_EXPOSED_DEV_ONLY;MONTHLY_VERIFIED_PLUS_GAP_ONLY_VERIFIED_DAILY_OR_API**

| Month | Baseline N | Funded N | Overlay funding USDT | Funded end cash | Within-month Mark DD % |
|---|---:|---:|---:|---:|---:|
| 2021-02 | 0 | 0 | 0.0000 | 1000.0000 | 0.0000 |
| 2021-03 | 0 | 0 | 0.0000 | 1000.0000 | 0.0000 |
| 2021-04 | 1 | 1 | -0.0951 | 1037.5531 | 1.2253 |
| 2021-05 | 0 | 0 | 0.0000 | 1037.5531 | 0.0000 |
| 2021-06 | 0 | 0 | 0.0000 | 1037.5531 | 0.0000 |
| 2021-07 | 1 | 1 | -0.1842 | 1054.3557 | 2.0730 |
| 2021-08 | 1 | 1 | -0.0899 | 1024.8115 | 2.8021 |
| 2021-09 | 2 | 2 | 0.0153 | 997.7749 | 4.3140 |
| 2021-10 | 0 | 0 | 0.0000 | 997.7749 | 0.0000 |
| 2021-11 | 2 | 2 | 0.2826 | 1033.6636 | 1.7337 |
| 2021-12 | 1 | 1 | 0.0912 | 1091.0797 | 1.2319 |
| 2022-01 | 0 | 0 | 0.0000 | 1091.0797 | 0.0000 |
| 2022-02 | 0 | 0 | 0.0000 | 1091.0797 | 0.0000 |
| 2022-03 | 0 | 0 | 0.0000 | 1091.0797 | 0.0000 |
| 2022-04 | 0 | 0 | 0.0000 | 1091.0797 | 0.0000 |
| 2022-05 | 2 | 2 | -0.0903 | 1085.9062 | 1.7062 |
| 2022-06 | 1 | 1 | -0.1790 | 1092.9698 | 1.4156 |
| 2022-07 | 1 | 1 | -0.1808 | 1096.8724 | 1.9353 |
| 2022-08 | 1 | 1 | -0.0256 | 1112.7026 | 0.9510 |
| 2022-09 | 0 | 0 | 0.0000 | 1112.7026 | 0.0000 |
| 2022-10 | 3 | 3 | -0.1220 | 1106.5091 | 2.6270 |
| 2022-11 | 1 | 1 | 0.0000 | 1090.1461 | 1.5565 |
| 2022-12 | 1 | 1 | 0.0222 | 1098.8573 | 0.4049 |
| 2023-01 | 2 | 2 | -0.0947 | 1106.5813 | 2.5585 |
| 2023-02 | 0 | 0 | 0.0000 | 1106.5813 | 0.0000 |
| 2023-03 | 2 | 2 | -0.0685 | 1103.8571 | 2.4271 |
| 2023-04 | 0 | 0 | 0.0000 | 1103.8571 | 0.0000 |
| 2023-05 | 1 | 1 | -0.1846 | 1097.5931 | 1.6579 |
| 2023-06 | 1 | 1 | 0.0870 | 1099.2673 | 0.4434 |
| 2023-07 | 2 | 2 | 0.0000 | 1076.7229 | 2.0509 |
| 2023-08 | 1 | 1 | 0.0937 | 1081.4171 | 0.2412 |
| 2023-09 | 3 | 3 | 0.0824 | 1082.6952 | 1.9423 |
| 2023-10 | 2 | 2 | -0.0196 | 1101.5794 | 1.1689 |
| 2023-11 | 2 | 2 | -0.1837 | 1116.9780 | 1.7653 |
| 2023-12 | 0 | 0 | 0.0000 | 1116.9780 | 0.0000 |

**STRESS / cash_neutral_same_trade_overlay / EX_POST_EXPOSED_DEV_ONLY;MONTHLY_VERIFIED_PLUS_GAP_ONLY_VERIFIED_DAILY_OR_API**

| Year | N | Gross bp | Net bp | Net R | Net PF | Mark DD % | Funded cash return % | Signed Funding USDT | LONG/SHORT N |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2021 | 8 | 148.4616 | 104.5763 | 0.3505 | 2.0438 | 8.3207 | 7.4974 | 0.0138 | 4/4 |
| 2022 | 10 | 32.7514 | -11.9236 | -0.1198 | 0.7955 | 5.3035 | -1.0451 | -0.5711 | 6/4 |
| 2023 | 16 | 23.2390 | -21.0260 | -0.2388 | 0.6070 | 8.2525 | -2.9340 | -0.3787 | 9/7 |

Matched balanced-control increment=55.4497bp; PAUSE=0. Side diagnostics={'LONG': {'scientific_grade': 'COST_PROXY_LAST_TRADE_PLUS_OBSERVED_FUNDING_AND_MARK_DEV_ONLY', 'n': 19, 'mean_gross_bps': 34.8325794167114, 'mean_net_bps': -10.272484152202974, 'net_profit_factor': 0.8433773201669473, 'mean_net_R': -0.1683168137398061, 'max_within_trade_mark_mtm_dd_pct': 3.000546299799464, 'side_risk_basis': 'actualaccountwithintrade conditionalDD;notseparatelyfundedsideportfolio'}, 'SHORT': {'scientific_grade': 'COST_PROXY_LAST_TRADE_PLUS_OBSERVED_FUNDING_AND_MARK_DEV_ONLY', 'n': 15, 'mean_gross_bps': 81.68077413028962, 'mean_net_bps': 38.40908122569869, 'net_profit_factor': 1.5386186592482778, 'mean_net_R': 0.06551054883821106, 'max_within_trade_mark_mtm_dd_pct': 3.291406102615494, 'side_risk_basis': 'actualaccountwithintrade conditionalDD;notseparatelyfundedsideportfolio'}}. Signed funding total=-0.9361USDT, 37 event/trade attributions; 6 trades cross no settlement in complete observed stream. Extra roundtrip cost drag sensitivity mean bp={'-10': 21.204677043930115, '-5': 16.204677043930115, '-2': 13.204677043930115, '2': 9.204677043930115, '5': 6.204677043930115, '10': 1.2046770439301149}; descriptive gross+funding break-even friction=55.2020bp. This is not a maker-fill or optimized cost claim.

**STRESS / funding_aware_funded_replay / EX_POST_EXPOSED_DEV_ONLY;MONTHLY_VERIFIED_PLUS_GAP_ONLY_VERIFIED_DAILY_OR_API**

| Year | N | Gross bp | Net bp | Net R | Net PF | Mark DD % | Funded cash return % | Signed Funding USDT | LONG/SHORT N |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2021 | 8 | 148.4616 | 104.5763 | 0.3505 | 2.0438 | 8.3207 | 7.4974 | 0.0138 | 4/4 |
| 2022 | 10 | 32.7514 | -11.9236 | -0.1198 | 0.7955 | 5.3035 | -1.0451 | -0.5711 | 6/4 |
| 2023 | 16 | 23.2390 | -21.0260 | -0.2388 | 0.6070 | 8.2525 | -2.9340 | -0.3787 | 9/7 |

Matched balanced-control increment=55.4497bp; PAUSE=0. Side diagnostics={'LONG': {'scientific_grade': 'COST_PROXY_LAST_TRADE_PLUS_OBSERVED_FUNDING_AND_MARK_DEV_ONLY', 'n': 19, 'mean_gross_bps': 34.8325794167114, 'mean_net_bps': -10.272484152202974, 'net_profit_factor': 0.8433773201669473, 'mean_net_R': -0.1683168137398061, 'max_within_trade_mark_mtm_dd_pct': 3.000546299799464, 'side_risk_basis': 'actualaccountwithintrade conditionalDD;notseparatelyfundedsideportfolio'}, 'SHORT': {'scientific_grade': 'COST_PROXY_LAST_TRADE_PLUS_OBSERVED_FUNDING_AND_MARK_DEV_ONLY', 'n': 15, 'mean_gross_bps': 81.68077413028962, 'mean_net_bps': 38.40908122569869, 'net_profit_factor': 1.5386186592482778, 'mean_net_R': 0.06551054883821106, 'max_within_trade_mark_mtm_dd_pct': 3.291406102615494, 'side_risk_basis': 'actualaccountwithintrade conditionalDD;notseparatelyfundedsideportfolio'}}. Signed funding total=-0.9361USDT, 37 event/trade attributions; 6 trades cross no settlement in complete observed stream. Extra roundtrip cost drag sensitivity mean bp={'-10': 21.204677043930115, '-5': 16.204677043930115, '-2': 13.204677043930115, '2': 9.204677043930115, '5': 6.204677043930115, '10': 1.2046770439301149}; descriptive gross+funding break-even friction=55.2020bp. This is not a maker-fill or optimized cost claim.

**STRESS monthly funded accounts / EX_POST_EXPOSED_DEV_ONLY;MONTHLY_VERIFIED_PLUS_GAP_ONLY_VERIFIED_DAILY_OR_API**

| Month | Baseline N | Funded N | Overlay funding USDT | Funded end cash | Within-month Mark DD % |
|---|---:|---:|---:|---:|---:|
| 2021-02 | 0 | 0 | 0.0000 | 1000.0000 | 0.0000 |
| 2021-03 | 0 | 0 | 0.0000 | 1000.0000 | 0.0000 |
| 2021-04 | 1 | 1 | -0.0951 | 1035.4663 | 1.2265 |
| 2021-05 | 0 | 0 | 0.0000 | 1035.4663 | 0.0000 |
| 2021-06 | 0 | 0 | 0.0000 | 1035.4663 | 0.0000 |
| 2021-07 | 1 | 1 | -0.1842 | 1050.2742 | 2.0785 |
| 2021-08 | 1 | 1 | -0.0899 | 1018.7602 | 3.0005 |
| 2021-09 | 2 | 2 | 0.0153 | 987.6950 | 4.5462 |
| 2021-10 | 0 | 0 | 0.0000 | 987.6950 | 0.0000 |
| 2021-11 | 2 | 2 | 0.2765 | 1018.1261 | 1.7717 |
| 2021-12 | 1 | 1 | 0.0912 | 1074.9737 | 1.2543 |
| 2022-01 | 0 | 0 | 0.0000 | 1074.9737 | 0.0000 |
| 2022-02 | 0 | 0 | 0.0000 | 1074.9737 | 0.0000 |
| 2022-03 | 0 | 0 | 0.0000 | 1074.9737 | 0.0000 |
| 2022-04 | 0 | 0 | 0.0000 | 1074.9737 | 0.0000 |
| 2022-05 | 2 | 2 | -0.0903 | 1065.7305 | 1.9805 |
| 2022-06 | 1 | 1 | -0.1790 | 1070.7915 | 1.4433 |
| 2022-07 | 1 | 1 | -0.1764 | 1072.5867 | 1.9287 |
| 2022-08 | 1 | 1 | -0.0256 | 1086.3987 | 1.1634 |
| 2022-09 | 0 | 0 | 0.0000 | 1086.3987 | 0.0000 |
| 2022-10 | 3 | 3 | -0.1220 | 1074.0807 | 3.0595 |
| 2022-11 | 1 | 1 | 0.0000 | 1055.6632 | 1.7147 |
| 2022-12 | 1 | 1 | 0.0222 | 1063.7394 | 0.6106 |
| 2023-01 | 2 | 2 | -0.0947 | 1067.3990 | 2.6493 |
| 2023-02 | 0 | 0 | 0.0000 | 1067.3990 | 0.0000 |
| 2023-03 | 2 | 2 | -0.0685 | 1060.6413 | 2.5181 |
| 2023-04 | 0 | 0 | 0.0000 | 1060.6413 | 0.0000 |
| 2023-05 | 1 | 1 | -0.1846 | 1052.3438 | 1.7263 |
| 2023-06 | 1 | 1 | 0.0870 | 1052.0080 | 0.4635 |
| 2023-07 | 2 | 2 | 0.0000 | 1025.4333 | 2.5261 |
| 2023-08 | 1 | 1 | 0.0908 | 1018.9763 | 0.8292 |
| 2023-09 | 3 | 3 | 0.0824 | 1015.5650 | 2.2639 |
| 2023-10 | 2 | 2 | -0.1073 | 1019.7588 | 1.6646 |
| 2023-11 | 2 | 2 | -0.1837 | 1032.5287 | 2.2837 |
| 2023-12 | 0 | 0 | 0.0000 | 1032.5287 | 0.0000 |

### W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H

**EX_POST_EXPOSED_DEV_ONLY;MONTHLY_VERIFIED_PLUS_GAP_ONLY_VERIFIED_DAILY_OR_API**

**BASE / cash_neutral_same_trade_overlay / EX_POST_EXPOSED_DEV_ONLY;MONTHLY_VERIFIED_PLUS_GAP_ONLY_VERIFIED_DAILY_OR_API**

| Year | N | Gross bp | Net bp | Net R | Net PF | Mark DD % | Funded cash return % | Signed Funding USDT | LONG/SHORT N |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2021 | 10 | 171.6298 | 149.6341 | 0.5360 | 6.3688 | 5.0844 | 13.7791 | -0.0455 | 5/5 |
| 2022 | 21 | 100.7250 | 78.3479 | 0.5566 | 3.3348 | 4.6325 | 13.3533 | -0.5244 | 9/12 |
| 2023 | 24 | -3.5740 | -25.6586 | -0.2214 | 0.5332 | 6.1570 | -4.4093 | -0.0582 | 15/9 |

Matched balanced-control increment=64.7351bp; PAUSE=0. Side diagnostics={'LONG': {'scientific_grade': 'COST_PROXY_LAST_TRADE_PLUS_OBSERVED_FUNDING_AND_MARK_DEV_ONLY', 'n': 29, 'mean_gross_bps': 81.66876079716248, 'mean_net_bps': 58.97030150440567, 'net_profit_factor': 2.873678080627825, 'mean_net_R': 0.3371270721924905, 'max_within_trade_mark_mtm_dd_pct': 3.027536609935061, 'side_risk_basis': 'actualaccountwithintrade conditionalDD;notseparatelyfundedsideportfolio'}, 'SHORT': {'scientific_grade': 'COST_PROXY_LAST_TRADE_PLUS_OBSERVED_FUNDING_AND_MARK_DEV_ONLY', 'n': 26, 'mean_gross_bps': 52.97508444244269, 'mean_net_bps': 31.373173838030194, 'net_profit_factor': 1.5825432296012687, 'mean_net_R': 0.07530004747972315, 'max_within_trade_mark_mtm_dd_pct': 4.575831191647013, 'side_risk_basis': 'actualaccountwithintrade conditionalDD;notseparatelyfundedsideportfolio'}}. Signed funding total=-0.6282USDT, 60 event/trade attributions; 7 trades cross no settlement in complete observed stream. Extra roundtrip cost drag sensitivity mean bp={'-10': 55.92438660757363, '-5': 50.92438660757363, '-2': 47.92438660757363, '2': 43.92438660757363, '5': 40.92438660757363, '10': 35.92438660757363}; descriptive gross+funding break-even friction=67.9811bp. This is not a maker-fill or optimized cost claim.

**BASE / funding_aware_funded_replay / EX_POST_EXPOSED_DEV_ONLY;MONTHLY_VERIFIED_PLUS_GAP_ONLY_VERIFIED_DAILY_OR_API**

| Year | N | Gross bp | Net bp | Net R | Net PF | Mark DD % | Funded cash return % | Signed Funding USDT | LONG/SHORT N |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2021 | 10 | 171.6298 | 149.6341 | 0.5360 | 6.3688 | 5.0844 | 13.7791 | -0.0455 | 5/5 |
| 2022 | 21 | 100.7250 | 78.3479 | 0.5566 | 3.3348 | 4.6325 | 13.3533 | -0.5244 | 9/12 |
| 2023 | 24 | -3.5740 | -25.6586 | -0.2214 | 0.5332 | 6.1570 | -4.4093 | -0.0582 | 15/9 |

Matched balanced-control increment=64.7351bp; PAUSE=0. Side diagnostics={'LONG': {'scientific_grade': 'COST_PROXY_LAST_TRADE_PLUS_OBSERVED_FUNDING_AND_MARK_DEV_ONLY', 'n': 29, 'mean_gross_bps': 81.66876079716248, 'mean_net_bps': 58.97030150440567, 'net_profit_factor': 2.873678080627825, 'mean_net_R': 0.3371270721924905, 'max_within_trade_mark_mtm_dd_pct': 3.027536609935061, 'side_risk_basis': 'actualaccountwithintrade conditionalDD;notseparatelyfundedsideportfolio'}, 'SHORT': {'scientific_grade': 'COST_PROXY_LAST_TRADE_PLUS_OBSERVED_FUNDING_AND_MARK_DEV_ONLY', 'n': 26, 'mean_gross_bps': 52.97508444244269, 'mean_net_bps': 31.373173838030194, 'net_profit_factor': 1.5825432296012687, 'mean_net_R': 0.07530004747972315, 'max_within_trade_mark_mtm_dd_pct': 4.575831191647013, 'side_risk_basis': 'actualaccountwithintrade conditionalDD;notseparatelyfundedsideportfolio'}}. Signed funding total=-0.6282USDT, 60 event/trade attributions; 7 trades cross no settlement in complete observed stream. Extra roundtrip cost drag sensitivity mean bp={'-10': 55.92438660757363, '-5': 50.92438660757363, '-2': 47.92438660757363, '2': 43.92438660757363, '5': 40.92438660757363, '10': 35.92438660757363}; descriptive gross+funding break-even friction=67.9811bp. This is not a maker-fill or optimized cost claim.

**BASE monthly funded accounts / EX_POST_EXPOSED_DEV_ONLY;MONTHLY_VERIFIED_PLUS_GAP_ONLY_VERIFIED_DAILY_OR_API**

| Month | Baseline N | Funded N | Overlay funding USDT | Funded end cash | Within-month Mark DD % |
|---|---:|---:|---:|---:|---:|
| 2021-02 | 0 | 0 | 0.0000 | 1000.0000 | 0.0000 |
| 2021-03 | 0 | 0 | 0.0000 | 1000.0000 | 0.0000 |
| 2021-04 | 1 | 1 | -0.0951 | 1037.5531 | 1.2253 |
| 2021-05 | 0 | 0 | 0.0000 | 1037.5531 | 0.0000 |
| 2021-06 | 0 | 0 | 0.0000 | 1037.5531 | 0.0000 |
| 2021-07 | 1 | 1 | -0.1842 | 1039.5173 | 2.1011 |
| 2021-08 | 3 | 3 | 0.1825 | 1032.9422 | 3.1798 |
| 2021-09 | 2 | 2 | 0.0520 | 1022.5418 | 5.0844 |
| 2021-10 | 0 | 0 | 0.0000 | 1022.5418 | 0.0000 |
| 2021-11 | 1 | 1 | 0.0912 | 1071.7870 | 1.4008 |
| 2021-12 | 2 | 2 | -0.0920 | 1137.7913 | 1.1885 |
| 2022-01 | 1 | 1 | 0.0053 | 1135.8948 | 1.0758 |
| 2022-02 | 2 | 2 | -0.0279 | 1156.2330 | 1.1445 |
| 2022-03 | 0 | 0 | 0.0000 | 1156.2330 | 0.0000 |
| 2022-04 | 0 | 0 | 0.0000 | 1156.2330 | 0.0000 |
| 2022-05 | 4 | 4 | -0.2430 | 1158.4029 | 3.0827 |
| 2022-06 | 3 | 3 | -0.0267 | 1174.8542 | 4.5758 |
| 2022-07 | 2 | 2 | 0.0319 | 1224.0999 | 1.0775 |
| 2022-08 | 2 | 2 | -0.1167 | 1226.3002 | 2.0540 |
| 2022-09 | 1 | 1 | -0.0840 | 1208.7489 | 3.0242 |
| 2022-10 | 2 | 2 | -0.0301 | 1246.1340 | 0.8563 |
| 2022-11 | 2 | 2 | -0.0445 | 1281.8517 | 2.0516 |
| 2022-12 | 2 | 2 | 0.0112 | 1289.7236 | 0.6287 |
| 2023-01 | 2 | 2 | 0.0219 | 1295.6919 | 0.3713 |
| 2023-02 | 3 | 3 | 0.1949 | 1278.6802 | 2.4239 |
| 2023-03 | 2 | 2 | -0.1490 | 1276.8715 | 2.2351 |
| 2023-04 | 1 | 1 | -0.1867 | 1279.7224 | 0.8202 |
| 2023-05 | 1 | 1 | -0.0926 | 1266.8623 | 1.4554 |
| 2023-06 | 2 | 2 | 0.1139 | 1280.6196 | 0.9187 |
| 2023-07 | 3 | 3 | 0.0000 | 1252.9501 | 2.1606 |
| 2023-08 | 2 | 2 | 0.1424 | 1238.6699 | 1.4688 |
| 2023-09 | 3 | 3 | 0.0039 | 1237.2506 | 1.6475 |
| 2023-10 | 3 | 3 | -0.1073 | 1253.4857 | 1.3596 |
| 2023-11 | 2 | 2 | 0.0004 | 1232.8553 | 2.3645 |
| 2023-12 | 0 | 0 | 0.0000 | 1232.8553 | 0.0000 |

**STRESS / cash_neutral_same_trade_overlay / EX_POST_EXPOSED_DEV_ONLY;MONTHLY_VERIFIED_PLUS_GAP_ONLY_VERIFIED_DAILY_OR_API**

| Year | N | Gross bp | Net bp | Net R | Net PF | Mark DD % | Funded cash return % | Signed Funding USDT | LONG/SHORT N |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2021 | 10 | 175.1337 | 131.2168 | 0.4493 | 4.8127 | 5.3668 | 12.1766 | -0.0431 | 5/5 |
| 2022 | 21 | 83.7012 | 39.3055 | 0.2866 | 1.9379 | 5.9491 | 6.7444 | -0.4987 | 9/12 |
| 2023 | 24 | -1.3885 | -45.4933 | -0.4392 | 0.3472 | 8.8982 | -8.4007 | -0.0612 | 15/9 |

Matched balanced-control increment=61.9600bp; PAUSE=0. Side diagnostics={'LONG': {'scientific_grade': 'COST_PROXY_LAST_TRADE_PLUS_OBSERVED_FUNDING_AND_MARK_DEV_ONLY', 'n': 29, 'mean_gross_bps': 71.71316856273717, 'mean_net_bps': 26.94770043673013, 'net_profit_factor': 1.6724231191201655, 'mean_net_R': 0.08425416002779726, 'max_within_trade_mark_mtm_dd_pct': 2.9169621264315264, 'side_risk_basis': 'actualaccountwithintrade conditionalDD;notseparatelyfundedsideportfolio'}, 'SHORT': {'scientific_grade': 'COST_PROXY_LAST_TRADE_PLUS_OBSERVED_FUNDING_AND_MARK_DEV_ONLY', 'n': 26, 'mean_gross_bps': 53.69449363400825, 'mean_net_bps': 10.163865399913549, 'net_profit_factor': 1.1541875334651908, 'mean_net_R': -0.09508618848198092, 'max_within_trade_mark_mtm_dd_pct': 4.719978771941232, 'side_risk_basis': 'actualaccountwithintrade conditionalDD;notseparatelyfundedsideportfolio'}}. Signed funding total=-0.6030USDT, 61 event/trade attributions; 7 trades cross no settlement in complete observed stream. Extra roundtrip cost drag sensitivity mean bp={'-10': 29.01352387387138, '-5': 24.01352387387138, '-2': 21.01352387387138, '2': 17.01352387387138, '5': 14.013523873871382, '10': 9.013523873871382}; descriptive gross+funding break-even friction=63.0766bp. This is not a maker-fill or optimized cost claim.

**STRESS / funding_aware_funded_replay / EX_POST_EXPOSED_DEV_ONLY;MONTHLY_VERIFIED_PLUS_GAP_ONLY_VERIFIED_DAILY_OR_API**

| Year | N | Gross bp | Net bp | Net R | Net PF | Mark DD % | Funded cash return % | Signed Funding USDT | LONG/SHORT N |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2021 | 10 | 175.1337 | 131.2168 | 0.4493 | 4.8127 | 5.3668 | 12.1766 | -0.0431 | 5/5 |
| 2022 | 21 | 83.7012 | 39.3055 | 0.2866 | 1.9379 | 5.9491 | 6.7444 | -0.4987 | 9/12 |
| 2023 | 24 | -1.3885 | -45.4933 | -0.4392 | 0.3472 | 8.8982 | -8.4007 | -0.0612 | 15/9 |

Matched balanced-control increment=61.9600bp; PAUSE=0. Side diagnostics={'LONG': {'scientific_grade': 'COST_PROXY_LAST_TRADE_PLUS_OBSERVED_FUNDING_AND_MARK_DEV_ONLY', 'n': 29, 'mean_gross_bps': 71.71316856273717, 'mean_net_bps': 26.94770043673013, 'net_profit_factor': 1.6724231191201655, 'mean_net_R': 0.08425416002779726, 'max_within_trade_mark_mtm_dd_pct': 2.9169621264315264, 'side_risk_basis': 'actualaccountwithintrade conditionalDD;notseparatelyfundedsideportfolio'}, 'SHORT': {'scientific_grade': 'COST_PROXY_LAST_TRADE_PLUS_OBSERVED_FUNDING_AND_MARK_DEV_ONLY', 'n': 26, 'mean_gross_bps': 53.69449363400825, 'mean_net_bps': 10.163865399913549, 'net_profit_factor': 1.1541875334651908, 'mean_net_R': -0.09508618848198092, 'max_within_trade_mark_mtm_dd_pct': 4.719978771941232, 'side_risk_basis': 'actualaccountwithintrade conditionalDD;notseparatelyfundedsideportfolio'}}. Signed funding total=-0.6030USDT, 61 event/trade attributions; 7 trades cross no settlement in complete observed stream. Extra roundtrip cost drag sensitivity mean bp={'-10': 29.01352387387138, '-5': 24.01352387387138, '-2': 21.01352387387138, '2': 17.01352387387138, '5': 14.013523873871382, '10': 9.013523873871382}; descriptive gross+funding break-even friction=63.0766bp. This is not a maker-fill or optimized cost claim.

**STRESS monthly funded accounts / EX_POST_EXPOSED_DEV_ONLY;MONTHLY_VERIFIED_PLUS_GAP_ONLY_VERIFIED_DAILY_OR_API**

| Month | Baseline N | Funded N | Overlay funding USDT | Funded end cash | Within-month Mark DD % |
|---|---:|---:|---:|---:|---:|
| 2021-02 | 0 | 0 | 0.0000 | 1000.0000 | 0.0000 |
| 2021-03 | 0 | 0 | 0.0000 | 1000.0000 | 0.0000 |
| 2021-04 | 1 | 1 | -0.0951 | 1035.4663 | 1.2265 |
| 2021-05 | 0 | 0 | 0.0000 | 1035.4663 | 0.0000 |
| 2021-06 | 0 | 0 | 0.0000 | 1035.4663 | 0.0000 |
| 2021-07 | 1 | 1 | -0.1842 | 1035.4210 | 2.1068 |
| 2021-08 | 3 | 3 | 0.1866 | 1023.0364 | 3.3170 |
| 2021-09 | 2 | 2 | 0.0504 | 1009.2249 | 5.1550 |
| 2021-10 | 0 | 0 | 0.0000 | 1009.2249 | 0.0000 |
| 2021-11 | 1 | 1 | 0.0912 | 1058.1126 | 1.4231 |
| 2021-12 | 2 | 2 | -0.0920 | 1121.7662 | 1.2072 |
| 2022-01 | 1 | 1 | 0.0053 | 1117.8923 | 1.0940 |
| 2022-02 | 2 | 2 | -0.0279 | 1134.2189 | 1.3419 |
| 2022-03 | 0 | 0 | 0.0000 | 1134.2189 | 0.0000 |
| 2022-04 | 0 | 0 | 0.0000 | 1134.2189 | 0.0000 |
| 2022-05 | 4 | 4 | -0.2430 | 1128.2546 | 3.6746 |
| 2022-06 | 3 | 3 | -0.0267 | 1138.5976 | 4.7200 |
| 2022-07 | 2 | 2 | 0.0311 | 1150.5942 | 2.9807 |
| 2022-08 | 2 | 2 | -0.1167 | 1148.7704 | 2.4435 |
| 2022-09 | 1 | 1 | -0.0840 | 1129.1820 | 3.2335 |
| 2022-10 | 2 | 2 | -0.0301 | 1164.0551 | 1.0547 |
| 2022-11 | 2 | 2 | -0.0421 | 1196.7144 | 2.1468 |
| 2022-12 | 2 | 2 | 0.0353 | 1197.4229 | 0.8988 |
| 2023-01 | 2 | 2 | 0.0219 | 1199.2922 | 0.5704 |
| 2023-02 | 3 | 3 | 0.1949 | 1176.1830 | 2.7989 |
| 2023-03 | 2 | 2 | -0.1490 | 1170.3184 | 2.4325 |
| 2023-04 | 1 | 1 | -0.1867 | 1171.1216 | 0.8947 |
| 2023-05 | 1 | 1 | -0.0926 | 1156.2291 | 1.5906 |
| 2023-06 | 2 | 2 | 0.1139 | 1167.5659 | 1.1798 |
| 2023-07 | 3 | 3 | 0.0000 | 1133.8701 | 2.8860 |
| 2023-08 | 2 | 2 | 0.1395 | 1115.6693 | 1.7839 |
| 2023-09 | 3 | 3 | 0.0039 | 1109.7518 | 2.0137 |
| 2023-10 | 3 | 3 | -0.1073 | 1121.5124 | 1.5188 |
| 2023-11 | 2 | 2 | 0.0004 | 1096.8314 | 2.8240 |
| 2023-12 | 0 | 0 | 0.0000 | 1096.8314 | 0.0000 |

## Independent settlement audits and timing

At least5 real independent Decimal funding episodes, both sides and2021/2022/2023, are in machine results. Rates remain signed decimal fractions; positive LONG pays, SHORT credits, negative reverses. Settlements use `[entry,exit)`; each trade also records±60sec boundary sensitivities. Archive funding has no exact associated settlement Mark: latest **completed**1mMark close is a notional approximation, explicitly below exact exchange cash-authenticity. Both funding and Mark historical original publication known-at remain UNPROVEN.

## Scientific limits and immutable inheritance

The two hypotheses were selected on exposed development;48 historical A+B comparisons are retained in fixed UTC7/14d bootstrap seed42/10000 with empty weeks and undefined lower bounds asnull. Even favorable economics is not confirmatory Alpha or promotion. 2021-driven positives and2023 loss remain visible in yearly tables; no new thresholds, directions, holding periods, costs or trials.

Fees/spread/slip are unchanged BASE22/STRESS44 proxies; actual fee tiers/L2/maker queue acceptance UNKNOWN.5% reserve and1x admission are enforced; transient marked notional/equity above1x is diagnostic, not an invented liquidation engine. Side Mark risk is within-trade conditional actual-account DD, not a separately funded side strategy. Raw source and full minute equity arrays stay outside Git with SHA; eight full trade/Funding attribution ledgers (356 rows) are committed in the new evidence namespace with a SHA manifest; all originalR3/R2 code/report/evidence byte unchanged.

Binance Vision attribution: derived data artifacts/report under [CCBYNCSA4.0 dataset terms](https://raw.githubusercontent.com/binance/binance-public-data/master/TERMS_AND_CONDITIONS.md), noncommercialnonproduction research. Current source repair supplies no commercial/live rights.

Focused synthetic checks>=15, Ruff/compile/JSON and independent source/account review are recorded in execution receipt; exact final CI status is observed afterpush, no fullCI/H40loop. Root requestedSolHigh; actual rootmodel/effort not exposed.

## Narrow reproduction

```bash
python3.12 -m scripts.strategy_research.g2_btc_two_lead_mark_gap_r31.run --code-sha c36df02a438dd0b46a02168d910479853c294dd4
python3.12 -m pytest -q tests/test_v06_g2_btc_two_lead_mark_gap_r31_*.py
ruff check scripts/strategy_research/g2_btc_two_lead_mark_gap_r31 tests/test_v06_g2_btc_two_lead_mark_gap_r31_*.py
```
Completed own scratch refuses repeatfullrun. Independent replication requires unchanged frozenimplementation and fresh task-owned scratch; reuse only verifiedread-onlyR3monthlycache. No new outcome-search wave.

## Independent real settlement-boundary coverage

The additional source-decoded Decimal audit covers **20 real trade episodes / 100 timing cases**, both fixed candidates, LONG and SHORT, 2021/2022/2023, and all **9 boundary-sensitive STRESS trades** (W1:3, W2:6). Each independently checks the primary window and four ±60-second entry/exit variants against the frozen ledger. No strategy clocks or parameters changed. See `R31_INDEPENDENT_REAL_DECIMAL_BOUNDARY_AUDIT.json` and the reproducible test-only `..._METHOD.py`.

## Quantitative 2023 and concentration diagnosis

| Fixed lead / STRESS | 2023 before Funding bp | 2023 after Funding bp | Funding increment bp | 2021 / 2022 / 2023 actual account return % |
|---|---:|---:|---:|---|
| W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H | -20.772015 | -21.026000 | -0.253985 | 7.4974 / -1.0451 / -2.9340 |
| W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H | -45.467007 | -45.493320 | -0.026313 | 12.1766 / 6.7444 / -8.4007 |

2023 losses substantially predate the Funding overlay: Funding adds only −0.2540bp for C04 and −0.0263bp for C05. C05 already has negative 2023 gross mean (−1.3885bp) before the unchanged STRESS44 cost; C04 gross +23.2390bp does not cover STRESS44 and Funding. Positive full-period averages depend on earlier years, especially 2021. All 48-family 7/14-day lower bounds remain negative; sample counts34/55 and development exposure preclude confirmatory inference. No candidate is promoted.

# Codex 完整任务 Prompt — BTC Quant Agent v0.3.7 Funding Crowding Feature Qualification

项目：`EXASHXE/btc-quant-agent`
本地目录：`/root/workspace/project/Quant-agent`

当前研究分支：`codex/v0.3.6-directional-architecture-reset`
当前已知 v0.3.6 报告 HEAD：`ae521d4b836ac950caf09b5b2ea7049cbc1205d2`
v0.3.6 正式研究代码 SHA：`d147fdbe3a46bfde107bea31063457d7984c548c`

开始前先 `git pull`，以当前远端 v0.3.6 分支最新 HEAD（应包含本 Prompt）作为基线。

状态必须保持：
- Strategy/feature version `0.2.2 / 0.2.2`
- `validation_status = EXPERIMENTAL`
- execution disabled / `auto_execute=false` / `allow_live=false`
- Final Holdout `[2026-02-01, 2026-08-01)` 完全封存
- no candidate freeze / no paper / no testnet / no live
- 不修改 TP/BR runtime 策略参数

---

# 1. 已确认结论

v0.3.6 已完成 Directional Architecture Reset：

- H14 frozen 1H regime directional information = `FALSIFIED`
- H15 4H Macro incremental direction = `FALSIFIED`
- H16 confirmed 15m Structure incremental direction = `FALSIFIED`
- H17 RSI/ROC incremental direction = `FALSIFIED`
- H18 Opportunity / Movement Layer = `SUPPORTED`
- `PROPOSED_DIRECTION_ARCHITECTURE = NONE`
- Recommendation = `RECOMMEND_NEW_FEATURE_FAMILY_RESEARCH`

1H trend-regime episode onset：
- 1,396 episodes
- LONG 682 / SHORT 714
- 4h signed median `-0.057911 ATR`
- 8h signed median `-0.053878 ATR`

Frozen price-only primitives没有形成稳定 Direction Engine。

同时，BR/TP 作为无方向性的 movement detector 得到支持：

BR_PATTERN vs matched controls future-range delta：
- 4h `+0.532395 ATR`
- 8h `+0.924695 ATR`

TP_PATTERN：
- 4h `+0.479100 ATR`
- 8h `+1.176285 ATR`

因此当前合理架构假设是：

```text
Independent Direction Feature Family
            +
BR / TP Opportunity Layer
            +
Risk / Execution（后续）
```

本轮只研究第一个 genuinely new direction feature family：**已结算 Funding Crowding**。

---

# 2. 为什么优先 Funding，而不是直接研究 OI / Basis / Long-Short Ratio

仓库已经拥有 Binance 官方历史 Funding settlement 数据，并且其时间戳/费率是 point-in-time 可验证的；过去主要把 Funding 当交易成本使用，没有作为 Alpha Direction feature 正式验证。

当前虽然有 forward derivatives collector，可以收集：
- OI
- taker ratio
- basis
- long/short account ratio
- optional order book

但这些字段没有覆盖整个 2021-2026 Development 的可信历史 PIT dataset。

所以本轮严格规定：

### 允许
- 官方历史 settled funding rate
- 同一 canonical BTCUSDT 1m dataset
- 基于过去 funding settlements 的因果 rolling statistics

### 禁止
- 用当前 Binance REST 接口“回填”历史 OI/basis/long-short ratio
- fabricated/interpolated derivative history
- 未来 funding rate
- premiumIndex 当前 `lastFundingRate` 当作历史 funding feature
- 当前预测 funding rate
- OI / basis / L/S / orderbook Alpha
- cross-asset features（留给后续独立版本）

本轮必须保持“一次只验证一个新 feature family”。

---

# 3. v0.3.6 非阻塞 Research Hygiene Fix

正式 v0.3.7 run 前修正一个语义问题，但不要改写 v0.3.6 formal artifacts：

当前 `EpisodeAccumulator.continuation_rows` 在新 episode 的 onset 时也写入 `continuation_index=0`，所以 v0.3.6 报告所谓 `continuation observations` 实际包含 episode onset。

这不影响 H14-H18 primary conclusions，但语义应修正：

任选一个明确方案：

1. 真正的 `continuation_rows` 只保存 `continuation_index >= 1`；或
2. 将其明确重命名为 `episode_observations`，报告时区分 onset 与 continuation。

要求：
- 单独 correctness commit
- unit test
- 不重写旧 v0.3.6 artifact
- v0.3.7 不依赖该 secondary continuation 结果做 Funding verdict

---

# 4. 本轮目标

版本：
`v0.3.7 Funding Crowding Feature Qualification`

回答三个问题：

1. 已结算 funding 的相对 crowding extreme 是否具有稳定的 **contrarian directional information**？
2. 该 Funding direction 能否在已验证的 BR/TP movement events 上提供方向？
3. Funding-conditioned opportunity events 是否仍保留 H18 的 elevated-movement 特征？

本轮禁止交易 PnL、Entry/Stop/Target optimization 和 Candidate freeze。

---

# 5. Git

```bash
cd /root/workspace/project/Quant-agent
git status
git fetch origin
git switch codex/v0.3.6-directional-architecture-reset
git pull --ff-only
git log --oneline --decorate -20
git switch -c codex/v0.3.7-funding-crowding-qualification
```

不得 rewrite 历史 formal artifacts。

---

# 6. 开始前质量 Gate

```bash
python -m pip install -e '.[dev,research]'
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src tools skill-template/scripts
```

记录最新：
- test count
- total coverage
- new critical-path coverage
- Ruff
- strict Mypy
- compileall

---

# 7. Data Audit 必须先于 Feature Research

优先复用官方 immutable dataset，例如：
`data/research/BTCUSDT/funding_events.csv`

不要凭文件名假设；从现有 formal dataset / manifest 中解析真实位置。

对 Funding 数据做正式 audit：

- source 必须是 Binance 官方 historical fundingRate archive / 已验证既有 formal dataset
- SHA-256
- total rows
- Development rows
- Holdout rows只允许计数/manifest metadata，不读取其 feature/label 内容用于研究
- sorted timestamps
- duplicates
- missing/irregular settlement intervals
- funding rate min/max/median
- mark-price missing count
- exact first/last Development timestamp

Funding Alpha analysis 只允许：
`timestamp < 2026-02-01T00:00:00Z`

如果无法证明 Funding 历史是真实 point-in-time 数据：
`FUNDING_FEATURE_QUALIFICATION_BLOCKED`

---

# 8. Funding 可用性语义

Funding settlement 在其 settlement timestamp 发生后才可用。

对一个 funding event `F_t`：

- feature observation time = `F_t.timestamp_ms`
- future label 的第一根 1m bar必须 `open_time_ms > F_t.timestamp_ms`
- 不允许使用下一次 funding
- 不允许使用当前事件之后才知道的数据

对任意 BR/TP opportunity event timestamp `T`：

- 只允许选择 `latest funding timestamp <= T`
- 不允许 nearest / future funding
- funding age 必须记录
- 若距离上一结算事件超过 `8h + 5min`，标 `STALE_FUNDING` 并排除正式 directional sample

注意：使用最新“已结算” Funding，不使用 predicted/next funding。

---

# 9. Primary Funding Crowding Feature — 唯一正式定义

为了避免 threshold/window mining，本轮只允许一个 preregistered primary feature：

`FUNDING_90D_CAUSAL_PERCENTILE`

定义：

对当前 settlement `F_t`，只取它**之前**最近 270 个 funding settlements：

```text
history = funding[t-270 : t]
```

270 ≈ 90 days（正常 3 settlements/day）。

当前 funding rate 本身不能进入 reference distribution。

Causal percentile：

```text
percentile = (
    count(history_rate < current_rate)
    + 0.5 * count(history_rate == current_rate)
) / 270
```

要求完整 270 个历史事件，否则 `WARMUP_INCOMPLETE`。

不得改：
- 270 window
- percentile formula
- 0.25 / 0.75 cutoffs

---

# 10. Funding Direction Rule

预注册 contrarian crowding rule：

```text
percentile >= 0.75 -> SHORT
percentile <= 0.25 -> LONG
otherwise          -> NO_BIAS
```

解释：
- 极高 Funding = long crowding，测试未来 contrarian SHORT
- 极低 Funding = 相对 short / less-long crowding，测试未来 contrarian LONG

这是 research hypothesis，不代表行业定律。

不得因为结果不好改成：
- 20/80
- 10/90
- zscore 0.5/1.0
- 同向 funding
- 反转规则的反转

---

# 11. H19 — Funding Crowding Standalone Directional Information

Statement：

`Extreme settled-funding crowding contains contrarian directional information for subsequent BTCUSDT returns.`

Primary event unit：
- eligible Funding settlement events
- full 270-event warmup
- tail percentile only（<=0.25 or >=0.75）

Reference price：
- first valid tradable reference after settlement，Protocol 明确写死
- 推荐用 settlement timestamp 后第一根 1m bar open，或者严格定义的 last-close reference；只能选一个并预注册
- 必须确保 live-equivalent

ATR normalizer：
- latest fully closed 1H ATR available at settlement
- timestamp <= funding timestamp

Future horizons：
- 4h
- 8h
- 24h（secondary）

Primary：4h / 8h。

Labels：
- funding-direction signed close return / ATR
- raw BTC close return / ATR
- MFE
- MAE
- +1 / +1.5 / +2.5 ATR favorable reach

---

# 12. H19 Null A — Direction Permutation

对 eligible extreme Funding events：

在：
- same year
- same 1H ATR decile

内部 permutation `LONG/SHORT` Funding direction labels，保持 strata 内方向数量。

2,000 simulations，seed = 37。

输出：
- real signed median
- real-minus-permutation median delta
- permutation distribution p05/p50/p95

不要把每次 permutation 当独立 market sample。

---

# 13. H19 Null B — Bottom vs Top Funding Raw-Return Spread

这是比离散 Direction rule 更直接的 monotonic crowding test。

对：
- bottom quartile (`<=0.25`)
- top quartile (`>=0.75`)

比较未来原始 BTC return：

```text
spread = median(raw_return | bottom funding)
       - median(raw_return | top funding)
```

若 contrarian crowding hypothesis 成立，预期：
`spread > 0`

同时报告：
- matched year/ATR-decile tail-pair comparison
- Spearman(`funding_percentile`, `future_raw_return`)；预期 `<0`

Spearman 只作为 secondary monotonicity，不单独决定 verdict。

---

# 14. Serial Correlation / Bootstrap

Funding events每 8h 左右发生，24h labels明显重叠。

禁止把每个 Funding event 当完全 IID。

Primary uncertainty：
- cluster unit = UTC calendar week
- 2,000 cluster bootstrap
- seed 37
- resample week clusters with replacement

同时输出：
- event count
- week-cluster count
- avg events/week

Year split、LONG/SHORT funding-direction split也必须报告。

---

# 15. Early / Late Internal Confirmation

继续使用：

Early：
`[2021-01-01, 2024-01-01)`

Late internal confirmation：
`[2024-01-01, 2026-02-01)`

注意 Late 不是 pristine OOS/Holdout。

本轮 feature definition 已经提前固定，禁止根据 Early 调 window/cutoff 再测试 Late。

H19 必须报告：
- Early 4h/8h signed medians
- Late 4h/8h signed medians
- bottom-top spread Early/Late
- LONG/SHORT tail contribution Early/Late

---

# 16. H19 Verdict 预注册

先写入 Protocol，不看结果修改。

Sample gate：
- >=300 eligible extreme Funding events with complete 8h labels
- >=100 LONG and >=100 SHORT funding-direction events
- >=80 UTC-week clusters

SUPPORTED 要求全部满足：

1. 4h signed median > 0
2. 8h signed median > 0
3. 4h/8h real-minus-permutation point delta > 0
4. 4h/8h weekly-cluster bootstrap p05 for real signed median >= -0.05 ATR
5. bottom-minus-top raw-return spread > 0 at 4h and 8h
6. spread weekly-bootstrap p05 >= -0.05 ATR at both horizons
7. Spearman funding-percentile vs raw return < 0 at 4h and 8h
8. Early and Late signed medians > 0 at 4h and 8h
9. Funding LONG and Funding SHORT subgroups的4h/8h median signed return均不得明显为负；Protocol 固定允许下界（建议 >= -0.05 ATR）

FALSIFIED：
- 4h 与 8h signed median 都 <= 0；或
- bottom-top spread 4h 与 8h 都 <= 0；或
- real-minus-permutation 4h 与 8h 都 <= 0

其余：
`INCONCLUSIVE_MECHANISM`

Sample不足：
`INCONCLUSIVE_LOW_SAMPLE`

---

# 17. H20 — Funding Direction on Existing Opportunity Events

v0.3.6 已支持：
- BR_PATTERN movement detector
- TP_PATTERN movement detector

本轮将它们的原 LONG/SHORT direction **完全忽略**。

构建 direction-agnostic opportunity union：

```text
BR_PATTERN timestamp
UNION
TP_PATTERN timestamp
```

Exact same timestamp 去重，但保留 tags：
- `BR`
- `TP`
- `BR+TP`

不得用原 pattern direction 生成 Funding Direction。

对每个 event：
- as-of latest settled Funding <= event timestamp
- 计算该 Funding settlement 的 causal 90d percentile
- extreme tail -> Funding LONG/SHORT
- middle -> NO_BIAS
- stale -> STALE

Primary sample：
`OPPORTUNITY_EVENT + FUNDING_EXTREME_BIAS`

---

# 18. H20 Future Labels

Reference：原 opportunity decision close。

ATR：原 frozen 15m ATR。

Horizons：4h / 8h。

Direction：只来自 Funding rule。

输出：
- total union events
- exact duplicate timestamps
- funding available
- funding extreme-biased count
- NO_BIAS count
- stale count
- Funding LONG/SHORT count
- BR/TP/BR+TP breakdown

Labels：
- Funding-direction signed return / ATR
- MFE/MAE
- favorable reach

Original BR/TP direction表现可作为描述性 baseline引用，但不能参与 selection/verdict。

---

# 19. H20 Null

在 opportunity-biased events 内：

- same year
- same 15m ATR decile
- same setup tag (`BR`, `TP`, `BR+TP`) when feasible

permutation Funding Direction labels，保持 strata direction count。

Uncertainty：
- cluster by UTC day（同日多个 BR/TP events强相关）
- 2,000 cluster bootstrap
- seed 37

不要把重复同行情事件当 IID。

---

# 20. H20 Verdict

Sample gate：
- >=100 funding-biased opportunity events with complete 8h labels
- >=30 Funding LONG / >=30 Funding SHORT
- >=60 UTC-day clusters

SUPPORTED：
- pooled union 4h/8h signed median > 0
- real-minus-permutation >0 at both
- cluster bootstrap p05 >= -0.05 ATR at both
- Early and Late pooled signed median >0 at both
- Funding LONG/SHORT subgroups不出现明显单边失败

FALSIFIED：
- pooled 4h和8h signed median都 <=0；或
- 4h/8h real-minus-permutation都 <=0

其余 INCONCLUSIVE。

BR-only / TP-only 分解是 secondary stability diagnostics，不允许事后只挑表现好的 setup 改 overall H20 verdict。

---

# 21. H21 — Funding-Conditioned Opportunity 是否仍保留 Movement Edge

Direction feature不能把 H18 的 movement advantage 全部过滤掉。

对 funding-biased opportunity union，仍做 direction-agnostic movement analysis：

- future high-low range / ATR
- max absolute excursion / ATR
- absolute close return / ATR
- movement >=1.5 ATR
- movement >=2.5 ATR

Control：
- non-pattern trend-regime decision points
- same year
- same 15m ATR decile
- same funding tail side when possible
- >=24h separation

Primary：4h/8h future-range delta。

SUPPORTED：
- future-range delta >0 4h/8h
- max-excursion delta >0 4h/8h
- future-range cluster-bootstrap p05 >= -0.05 at both
- Early/Late future-range delta >0

如果 funding extreme 筛选后 movement edge消失，则不能直接构建 Direction+Opportunity prototype。

---

# 22. Multiple Testing Discipline

本轮只有一个 new feature family：Funding。

Hypotheses：
- H19 standalone Funding direction
- H20 Funding on Opportunity union
- H21 movement retention

禁止：
- 扫 rolling windows
- 扫 funding quantile thresholds
- 扫 horizons作为primary
- 同时测试几十个 funding transforms
- 看结果后改 contrarian -> momentum

Secondary diagnostics可以报告：
- current funding raw rate
- trailing 7d mean
- current-vs-7d delta

但它们不能参与正式 verdict 或下一轮选择，除非未来新版本重新 preregister。

---

# 23. Funding 作为成本 vs Funding 作为 Feature

明确区分：

```text
Funding Alpha Feature:
已结算 historical funding crowding，用于方向信息研究

Funding Trading Cost:
未来真实持仓跨 funding settlement 时的现金流成本
```

本轮没有交易 PnL，所以不产生双计成本问题。

未来若进入策略原型，Funding feature 和 funding cashflow 必须分别建模。

---

# 24. Forward Derivatives Collector

本轮不要把 forward OI/basis 数据混入历史研究。

但是做一次只读 operational audit：
- `collect-derivatives` 代码仍可运行
- manifest/checksum逻辑正常
- fields 的 timestamps独立保存
- order book默认关闭

如果仓库已有用户实际 forward derivative CSV：
- 只报告 coverage 起止、samples、gaps
- 不用于 v0.3.7 Formal Development hypothesis
- 不修改历史 dataset

输出：
`forward_derivatives_collection_status.json`

这为以后真正 Forward Shadow / derivative-family research 累积数据。

---

# 25. Holdout Firewall

任何正式 Feature / Label / Statistical calculation：

`timestamp < 2026-02-01T00:00:00Z`

24h future window：
- 若完整 horizon 会越过 DEV_END，标 incomplete 并排除
- 不允许读取 Holdout Kline 来完成 Development label

Funding file即便含 2026-02 至 2026-07 events，也不能用于：
- rolling feature
- percentile
- labels
- tuning
- diagnostics of effect size

只允许 data manifest 层面的“文件总范围”描述。

新增 Holdout firewall tests。

---

# 26. Artifacts

Canonical output：

`artifacts/research/v0.3.7_funding_crowding_<run_id>/`

至少包含：

- `protocol.json`
- `protocol.sha256`
- `price_data_manifest.json`
- `funding_data_audit.json`
- `funding_feature_events.parquet`
- `h19_funding_directionality.json`
- `h19_week_cluster_bootstrap.json`
- `h19_permutation.json`
- `h19_tail_spread.json`
- `h19_early_late.json`
- `opportunity_funding_events.parquet`
- `h20_opportunity_directionality.json`
- `h20_day_cluster_bootstrap.json`
- `h20_early_late.json`
- `h21_movement_retention.json`
- `h21_bootstrap.json`
- `by_year_direction.json`
- `forward_derivatives_collection_status.json`
- `experiment_summary.json`

Provenance：
- formal git SHA
- price dataset checksum
- funding CSV checksum
- protocol checksum
- config hash
- seed 37
- Python / package versions

---

# 27. Tests

至少新增：

- `test_continuation_semantics_do_not_count_onset_as_continuation`
- `test_funding_features_use_only_prior_270_settlements`
- `test_current_funding_not_in_reference_distribution`
- `test_funding_percentile_tie_formula`
- `test_funding_tail_direction_mapping`
- `test_funding_warmup_is_incomplete_before_270`
- `test_funding_future_label_starts_after_settlement`
- `test_funding_asof_never_uses_future_settlement`
- `test_opportunity_funding_stale_rule`
- `test_opportunity_union_deduplicates_exact_timestamp_only`
- `test_original_tp_br_direction_not_used_for_h20`
- `test_week_cluster_bootstrap_deterministic`
- `test_day_cluster_bootstrap_deterministic`
- `test_h19_verdict_matches_protocol_all_branches`
- `test_h20_verdict_matches_protocol_all_branches`
- `test_h21_verdict_matches_protocol_all_branches`
- `test_24h_labels_never_cross_holdout`
- `test_all_v037_artifacts_development_only`
- `test_no_oi_basis_longshort_history_used`
- `test_no_candidate_freeze_or_execution_enablement`

---

# 28. Performance

目标：
- total formal runtime < 25 min
- peak RSS < 6 GiB

Funding rolling percentile不要 O(N²)：
- event count只有几千，但仍应使用 bounded deque / sorted structure 或清晰可验证实现
- opportunity as-of lookup用 `bisect_right`

---

# 29. Formal Verdicts

Allowed：
- `SUPPORTED`
- `FALSIFIED`
- `INCONCLUSIVE_LOW_SAMPLE`
- `INCONCLUSIVE_MECHANISM`

Overall：
- `FUNDING_FEATURE_QUALIFICATION_COMPLETE`
- `FUNDING_FEATURE_QUALIFICATION_BLOCKED`

---

# 30. Final Recommendation Gate

最终 recommendation 只能从以下选择：

### A
`RECOMMEND_FUNDING_DIRECTION_PLUS_OPPORTUNITY_PROTOTYPE`

需要：
- H19 SUPPORTED
- H20 SUPPORTED
- H21 SUPPORTED

### B
`RECOMMEND_FUNDING_DIRECTION_FOLLOWUP`

适用：
- H19 SUPPORTED
- H20/H21 因 sample 或 interaction mechanism INCONCLUSIVE，而不是 FALSIFIED

### C
`RECOMMEND_NEXT_NEW_FEATURE_FAMILY_CROSS_ASSET`

适用：
- H19 FALSIFIED

不要再在 Funding window/cutoff 上继续扫参数。

### D
`INCONCLUSIVE_CONTINUE_FUNDING_DIAGNOSTIC`

只用于数据/统计机制真正不确定、且不能归为 FALSIFIED/LOW_SAMPLE 的情况。

即使 A，也不允许 Candidate freeze / Holdout / Paper。
下一轮仍需独立构建 prototype 并验证。

---

# 31. Deliverables

生成：

- `docs/V0.3.7_FUNDING_CROWDING_FEATURE_QUALIFICATION_REPORT.md`
- `deliverables/v0.3.7/README.md`
- `deliverables/v0.3.7/V0.3.7_FUNDING_CROWDING_FEATURE_QUALIFICATION_REPORT.md`
- `deliverables/v0.3.7/V0.3.7_NUMERIC_ANSWERS.json`
- `deliverables/v0.3.7/V0.3.7_RECOMMENDATION.md`

---

# 32. 最终必须数字回答

1. Funding 数据 Development 内总 settlement 数？缺失/重复/异常间隔？
2. 完整 270-event warmup 后 eligible events 数？
3. bottom quartile / top quartile / middle counts？
4. Funding LONG / SHORT counts？
5. H19 4h/8h/24h signed median？
6. H19 real-minus-permutation 4h/8h delta？
7. weekly-cluster bootstrap CI？
8. bottom-minus-top raw-return spread 4h/8h？
9. funding percentile vs future raw return Spearman？
10. Early/Late 4h/8h H19 是否同方向？
11. Funding LONG/SHORT 两侧各自表现？
12. H19 verdict？
13. BR+TP opportunity union 总 event 数、去重后数？
14. 其中 funding extreme-biased 数和 coverage %？
15. H20 pooled 4h/8h signed median？
16. H20 real-minus-permutation / bootstrap CI？
17. BR-only / TP-only secondary breakdown？
18. H20 verdict？
19. Funding-conditioned opportunity 的 future-range delta 4h/8h？
20. H21 verdict？
21. Forward derivatives collector 当前是否有真实 accumulated data，覆盖多久？
22. Final Holdout 是否仍未消费？
23. 下一步 recommendation 是 A/B/C/D 哪一个？

---

# 33. Git / PR Final

```bash
ruff check .
mypy
pytest -q
python -m compileall -q src tools skill-template/scripts
git status
git push -u origin codex/v0.3.7-funding-crowding-qualification
```

创建最新 research PR 到 `main`，但不要自动 merge。

旧 PR #1-#5 仍不擅自关闭；报告 latest lineage supersession。

---

# 34. 最终原则

> v0.3.6 已经说明：不要再要求失败的 price-only pattern 同时承担“机会”和“方向”两个职责。

> Funding 在本轮必须作为一个真正独立的新 feature family 来验证，而不是和 OI/Basis/更多指标混在一起做 feature fishing。

> 已结算 Funding 的历史真实性比“指标多”更重要。

> Crowd extreme 的 contrarian rule如果失败，就接受失败，下一轮切换到 Cross-Asset，而不是扫描 Funding 参数。

> H18 的 BR/TP movement edge可以保留，但只有独立 Direction source 通过验证以后，才有资格组合成策略原型。

> Development 的好结果仍不能解封 Final Holdout。

现在开始执行：

`v0.3.7 Funding Crowding Feature Qualification`

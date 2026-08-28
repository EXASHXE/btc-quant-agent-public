# Codex 完整任务 Prompt — BTC Quant Agent v0.3.8 Funding Stability & Serial-Dependence Diagnostic

项目：`EXASHXE/btc-quant-agent`
本地目录：`/root/workspace/project/Quant-agent`

当前研究分支：`codex/v0.3.7-funding-crowding-qualification`
v0.3.7 已发布结果 HEAD：`236a6c6b579c6a60e55e43cd1e959bfcb6eb59c8`
v0.3.7 formal code SHA：`e71c4b551b569b617c646fdf53d2c20c1b3c34a5`
v0.3.7 protocol commit：`87f5d5bb82363983f80ed2970c048325cff7672b`

执行时从 **v0.3.7 分支最新 HEAD（包含本 Prompt commit）** 创建新分支，不要硬退回上面的 report HEAD。

状态必须保持：
- Strategy/feature version `0.2.2 / 0.2.2`
- `validation_status = EXPERIMENTAL`
- execution disabled / auto_execute=false / allow_live=false
- Final Holdout `[2026-02-01, 2026-08-01)` 完全封存
- no candidate freeze / no paper / no testnet / no live

---

## 1. v0.3.7 已确认事实

Funding source：Binance official USD-M Futures settled funding archive，PIT verified。

Development：`[2021-01-01, 2026-02-01)`
- settlements = 5,571
- after 270-event causal warmup = 5,301
- bottom-quartile LONG = 1,437
- top-quartile SHORT = 1,328
- middle/no-bias = 2,536

Frozen Funding feature：
- history = strictly prior 270 settlements (~90d)
- percentile <= 0.25 -> LONG
- percentile >= 0.75 -> SHORT
- otherwise NO_BIAS
- no window scan / no threshold scan

H19 standalone contrarian direction：
- 4h signed median = +0.026066 ATR
- 8h = +0.042236 ATR
- 24h = +0.086039 ATR
- real-minus-permutation: 4h +0.027861, 8h +0.089090 ATR
- weekly bootstrap 4h p05/p50/p95 = -0.014192 / +0.027830 / +0.067602
- weekly bootstrap 8h = +0.002474 / +0.043121 / +0.086114
- LONG/SHORT medians both nonnegative at 4h/8h
- Spearman percentile vs raw return is weakly negative (~ -0.03)

但固定 Early/Late stability 失败：
- Early 4h = -0.000607
- Early 8h = +0.107219
- Late 4h = +0.064622
- Late 8h = -0.032173

因此 H19 = `INCONCLUSIVE_MECHANISM`。

H20 Funding direction on Opportunity union：
- 893 exact-timestamp BR/TP union events
- 470 extreme-funding biased events (52.63%)
- pooled 4h = -0.026408 ATR
- pooled 8h = +0.270290 ATR
- H20 = `INCONCLUSIVE_MECHANISM`

Secondary setup-tag results（**post-hoc lead，不是已验证 Alpha**）：
- BR-only: 4h -0.127761 / 8h +0.021664
- TP-only: 4h +0.286612 / 8h +0.842846
- BR+TP: 4h +0.478938 / 8h +0.078855

H21 movement retention：
- future-range delta 4h +0.527339 ATR
- 8h +0.644180 ATR
- H21 = `SUPPORTED`

v0.3.7 final：
- H19 `INCONCLUSIVE_MECHANISM`
- H20 `INCONCLUSIVE_MECHANISM`
- H21 `SUPPORTED`
- recommendation `INCONCLUSIVE_CONTINUE_FUNDING_DIAGNOSTIC`

---

# 2. 本轮定位

版本：
`v0.3.8 Funding Stability & Serial-Dependence Diagnostic`

这是 **Funding family 的最后一轮 Development-only mechanism diagnostic**。

目标不是继续试参数，而是回答：

1. v0.3.7 的弱正 Funding signal 是否只是连续极端 Funding settlement 重复计数造成的 serial-dependence artifact？
2. Early/Late 4h/8h 交叉翻转，主要来自 LONG/SHORT asymmetry、market-state interaction，还是时间非平稳？
3. v0.3.7 post-hoc 发现的 `Funding direction × TP opportunity` 是否在固定规则下具有足够稳定的内部复现价值？
4. 如果本轮仍不能得到稳定机制结论，则 **停止继续挖 Funding Development Set，下一 family 转 Cross-Asset / Market Breadth**。

禁止：
- Funding window scan
- percentile cutoff scan
- horizon selection
- 把 4h/8h 中表现较好的那个事后设为 primary
- 改 TP/BR 参数
- PnL/Entry/SL/TP 优化
- reverse failed price signals
- Final Holdout

---

# 3. Git

```bash
cd /root/workspace/project/Quant-agent
git status
git log --oneline --decorate -20
git switch -c codex/v0.3.8-funding-stability-diagnostic
```

如果分支已存在则安全复用。

不要 rewrite v0.3.7 artifacts。

---

# 4. 开始前验收

```bash
python -m pip install -e '.[dev,research]'
ruff check .
mypy
pytest -q
pytest --cov=btc_quant_agent --cov-report=term-missing
python -m compileall -q src tools skill-template/scripts
```

记录最新 tests / coverage / critical-path coverage / CI。

---

# 5. 预注册 Protocol

任何正式结果前创建并 commit：

`configs/research/v0.3.8_funding_stability_protocol.json`

固定：
- Development only
- Final Holdout forbidden
- unchanged v0.3.7 Funding feature identity
- extreme-episode definition
- episode-onset label semantics
- market-state attribution definitions
- TP/BR interaction hypotheses
- primary horizons 4h/8h
- bootstrap cluster unit
- Early/Late split
- verdict rules H22-H25
- seed = 38
- 2,000 bootstrap simulations
- no scan / no strategy PnL selection

Protocol commit 必须早于 formal implementation/run results。

---

# 6. Funding feature identity完全冻结

必须复用 v0.3.7：

```text
WINDOW = 270 prior settlements
current settlement excluded
percentile <= .25 -> LONG
percentile >= .75 -> SHORT
middle -> NO_BIAS
```

不得测试：
- 180/360 events
- 20/80, 10/90, 30/70
- z-score cutoff
- funding delta / acceleration as replacement feature
- predicted funding

这些若未来需要，必须属于新的独立 feature hypothesis，不在本轮。

---

# 7. H22 — Extreme Funding Episode Onset Direction

## 7.1 为什么做

Funding 每约 8h settlement。极端 Funding 往往连续多个 settlement 停留在同一 tail。

v0.3.7 把每个 extreme settlement 都作为 event，虽然使用 week-cluster bootstrap，但仍需要确认结果不是由同一个 crowding episode 多次重复观察造成。

## 7.2 Episode 定义

用冻结 Funding direction sequence 构建：

- `LONG_EXTREME_EPISODE`：连续 extreme LONG settlements
- `SHORT_EXTREME_EPISODE`：连续 extreme SHORT settlements
- episode 在第一条 extreme settlement 开始
- 遇到 `NO_BIAS` 或 opposite extreme 即结束
- 不允许跨过 middle settlement 后仍视为同 episode

Primary unit：`episode onset only`。

输出：
- episode count
- LONG/SHORT count
- median/p25/p75 episode length settlements
- median duration hours
- by year
- Early/Late

## 7.3 Labels

完全复用 strict-after settlement 价格语义与 frozen 1H ATR。

Primary horizons：4h/8h。
Secondary descriptive：24h（不能替代 primary verdict）。

## 7.4 H22 statement

`Extreme settled-funding episode onset contains contrarian directional information after removing repeated same-tail settlements.`

Support gate 至少要求：
- sample gate >= 250 complete 8h episodes；LONG/SHORT each >= 75；week clusters >= 80
- 4h and 8h signed median > 0
- week-cluster bootstrap p05 >= -0.05 ATR at both
- real-minus-permutation delta >0 at both
- Early and Late signed medians >0 at both
- LONG and SHORT signed medians >= -0.05 at both

Falsify：
- 4h and 8h signed median both <=0，或
- both real-minus-permutation <=0

其他 -> `INCONCLUSIVE_MECHANISM`。

如果 sample gate 不足 -> `INCONCLUSIVE_LOW_SAMPLE`。

---

# 8. Serial-Persistence Attribution（diagnostic only）

对 v0.3.7 全部 extreme settlements 标记：
- `episode_index = 0` onset
- `episode_index = 1`
- `episode_index >= 2`

按固定三层输出：
- count
- 4h/8h signed median
- MFE/MAE
- Early/Late
- LONG/SHORT

禁止基于结果选择“只交易第 N 个 settlement”。

回答：
> aggregate Funding edge 是 onset 就存在，还是主要由 repeated extreme settlements 驱动？

这个结果只解释机制，不创建策略 arm。

---

# 9. H23 — Time Instability Attribution

本轮不能继续增加随机 indicators；只允许使用已冻结、已存在的 market-state labels。

对每个 Funding episode onset，在 settlement 时点使用 latest fully closed 1H state，分类到现有 frozen regime family：
- TREND_UP
- TREND_DOWN
- RANGE
- HIGH_VOL
- TRANSITION
- 其他真实 frozen state（若代码实际 enum 不同，以真实定义为准并在 protocol 写清）

不得改 regime thresholds。

输出每个 state：
- episode count
- LONG/SHORT counts
- 4h/8h signed median
- Early/Late medians
- bootstrap CI（state n 足够时）

另外固定输出：
- positive funding tail vs negative/low funding tail 的原始 funding-rate distribution
- Early vs Late funding-rate median / quartiles / tail frequency
- episode duration distribution Early vs Late

H23 不是“挑一个最好 regime”作为策略。

H23 statement：
`The v0.3.7 Early/Late instability is attributable to a reproducible frozen market-state or side asymmetry rather than arbitrary calendar drift.`

SUPPORTED 仅当预注册的 attribution rule 有明确、一致证据，例如某个 broad state/side 在 Early 与 Late 方向一致，且另一个 state/side 稳定解释反向；否则 `INCONCLUSIVE_MECHANISM`。

不得看到结果后重写 attribution rule。

---

# 10. H24 — Funding × TP Opportunity Internal Replication

这是被 v0.3.7 **secondary post-hoc observation** 激发的新 hypothesis，因此报告必须明确：

> This is Development internal replication, not pristine OOS evidence.

严格复用：
- raw `TP_PATTERN` event identity
- original TP price direction完全不用
- funding direction = frozen v0.3.7 contrarian direction
- Funding must be latest settled, non-stale, extreme
- 4h/8h primary horizons
- original event close + frozen 15m ATR reference

建立 matched controls：
- non-TP trend-regime decision points
- same year
- same 15m ATR decile
- same Funding tail side/direction
- >=24h separation
- K=5 deterministic nearest
- no future label matching

Primary metrics：
- Funding-direction signed return
- candidate minus matched-control signed-return delta
- MFE / MAE
- +1 ATR reach

Bootstrap：UTC-day cluster，2,000，seed 38。

H24 Support 必须同时：
- TP sample gate >=150 complete 8h events；LONG/SHORT each >=30；>=60 day clusters
- 4h and 8h pooled signed median >0
- 4h and 8h candidate-minus-control signed delta >0
- both signed-return bootstrap p05 >= -0.05
- Early/Late pooled signed median >0 at both horizons
- LONG/SHORT subgroup median >= -0.05 at both

若 4h/8h pooled signed medians both <=0 或 matched-control deltas both <=0 -> FALSIFIED。

否则 INCONCLUSIVE。

注意：即使 H24 SUPPORTED，本轮仍 **不能** candidate freeze / Holdout。

---

# 11. H25 — Funding × BR Opportunity Internal Replication

与 H24 完全同构，但 event = `BR_PATTERN`。

原因：v0.3.7 secondary result 显示 BR-only 比 TP-only 弱，必须避免只追表现好的 TP；BR 作为 preregistered negative comparison 同时验证。

同样的 sample/matching/bootstrap/verdict discipline。

输出 H24 vs H25，但禁止“选胜者后回头调参数”。

---

# 12. Movement Layer 保持，不重新证明

H21 已 SUPPORTED。

本轮只做 smoke/reproduction：
- Funding-conditioned TP/BR events 的 4h/8h future-range delta 应与 v0.3.7 同方向
- 不重新修改 Opportunity Layer 定义
- 不把 movement 当 directional edge

---

# 13. Fixed Early/Late & Year Stability

继续使用：
- Early `[2021-01-01, 2024-01-01)`
- Late `[2024-01-01, 2026-02-01)`

Late 仍不是 OOS/Holdout。

额外按 calendar year 报告，但不得基于某个年份结果调规则。

---

# 14. Holdout Firewall

严禁读 Final Holdout effect sizes：
`[2026-02-01, 2026-08-01)`

允许的仅是 manifest/count metadata，不能读取 funding rates、returns、TP/BR outcomes。

新增测试：
- all formal labels < DEV_END
- future horizons never cross DEV_END
- no Holdout rates/effects loaded
- no candidate freeze artifact

---

# 15. Funding family stop rule

这是 Funding family 在当前 Development Set 上的最后一轮 diagnostic。

Final recommendation 只能是以下之一：

### A. `RECOMMEND_FUNDING_EPISODE_DIRECTION_FOR_PROTOTYPE_RESEARCH`
只有 H22 SUPPORTED，且没有重大时间/side contradiction。

### B. `RECOMMEND_FUNDING_TP_INTERACTION_FOR_PROTOTYPE_RESEARCH`
H22 未支持，但 H24 SUPPORTED，且 H25 不出现同等随机改善；必须明确这是 post-hoc-inspired internal replication，下一版需要固定 architecture 后再决定是否 candidate research。

### C. `RECOMMEND_FUNDING_DIRECTION_PLUS_OPPORTUNITY_PROTOTYPE_RESEARCH`
H22 + H24（或 H25）都有稳定支持。

### D. `STOP_FUNDING_FAMILY_MOVE_TO_CROSS_ASSET`
H22 FALSIFIED，或 H22/H24/H25 全部没有稳定支持。

### E. `INCONCLUSIVE_STOP_FUNDING_UNTIL_NEW_FORWARD_DATA`
结果仍 inconclusive 且无法从固定 diagnostics 解释；不要继续在相同 Development Set 上增加 Funding variants。

**本轮结束后禁止再以“换 Funding 窗口/阈值”作为 v0.3.9。**

---

# 16. No PnL / No Trading Candidate

本轮禁止：
- strategy PnL optimization
- Entry/Stop/Target/RR/TTL changes
- leverage
- execution
- candidate freeze
- Final Holdout

本轮只判断信息含量与机制稳定性。

---

# 17. Artifacts

输出：

`artifacts/research/v0.3.8_funding_stability_<run_id>/`

至少：
- protocol.json / protocol.sha256
- data_manifest.json
- funding_episode_onsets.parquet
- funding_episode_members.parquet
- episode_summary.json
- h22_episode_directionality.json
- h22_bootstrap.json
- persistence_attribution.json
- h23_time_state_attribution.json
- h24_tp_funding_interaction.json
- h24_tp_matched_controls.parquet
- h25_br_funding_interaction.json
- h25_br_matched_controls.parquet
- early_late_year_stability.json
- movement_reproduction.json
- experiment_summary.json

保存：
- git SHA
- config hash
- price/funding checksum
- protocol checksum
- seed

---

# 18. Tests

至少新增：
- `test_funding_episode_onset_excludes_repeated_same_tail_settlements`
- `test_funding_episode_breaks_on_middle_or_opposite_tail`
- `test_funding_episode_direction_rule_unchanged_from_v037`
- `test_episode_labels_start_strictly_after_settlement`
- `test_episode_horizons_do_not_cross_holdout`
- `test_persistence_index_is_diagnostic_only`
- `test_market_state_is_asof_closed_data_only`
- `test_h24_ignores_original_tp_direction`
- `test_h24_controls_match_funding_tail_year_atr_without_future_labels`
- `test_h25_ignores_original_br_direction`
- `test_interaction_bootstrap_clusters_by_utc_day`
- `test_h22_h24_h25_verdicts_follow_protocol`
- `test_no_funding_window_or_threshold_variants_exist`
- `test_v038_artifacts_are_development_only`
- `test_final_holdout_unconsumed`

---

# 19. Performance

目标：
- formal run <25 min
- RSS <6 GiB

避免重复 full replay；复用 frozen replay/cache。

---

# 20. Deliverables

生成：
- `docs/V0.3.8_FUNDING_STABILITY_SERIAL_DEPENDENCE_REPORT.md`
- `deliverables/v0.3.8/README.md`
- `deliverables/v0.3.8/V0.3.8_FUNDING_STABILITY_SERIAL_DEPENDENCE_REPORT.md`
- `deliverables/v0.3.8/V0.3.8_NUMERIC_ANSWERS.json`
- `deliverables/v0.3.8/V0.3.8_RECOMMENDATION.md`

---

# 21. 最终必须数字回答

1. Extreme Funding settlements 2,765 个左右，collapse 后得到多少独立 extreme episodes？
2. episode length distribution？
3. Episode-onset H22 的 4h/8h signed median？
4. H22 4h/8h bootstrap CI 与 permutation delta？
5. Early/Late、LONG/SHORT 是否同时稳定？
6. Aggregate v0.3.7 edge 有多少来自 episode_index=0 / 1 / >=2？
7. H23 是否能解释时间不稳定？哪个 frozen state/side 是主要来源？
8. Funding × TP 有多少 eligible events？4h/8h signed median？
9. TP candidate-minus-matched-control 4h/8h delta 与 CI？
10. H24 verdict？
11. Funding × BR 同样结果？H25 verdict？
12. TP 与 BR 的差异是否跨 Early/Late/side 保持？
13. H21 movement layer 是否保持方向一致的 reproduction？
14. H22/H23/H24/H25 总 verdict？
15. Funding family 是进入 prototype research，还是正式停止并转 Cross-Asset？

---

# 22. Git Final

```bash
ruff check .
mypy
pytest -q
python -m compileall -q src tools skill-template/scripts
git status
git push -u origin codex/v0.3.8-funding-stability-diagnostic
```

创建最新 research PR -> main，不自动 merge，不自动关闭旧 PR。

---

# 23. 研究原则

> Aggregate positive median 不等于 stable Alpha。

> 连续 Funding extreme 是高度自相关事件，必须先确认 episode onset 仍有信息。

> v0.3.7 的 TP-only 表现是 post-hoc lead，v0.3.8 只能做明确标注的 internal replication，不能伪装成 OOS。

> 如果本轮仍不能稳定解释 Funding mechanism，就停止在同一个 Development Set 上继续挖 Funding variants。

> Final Holdout 的价值来自它仍未被看过；不要为了一个弱信号提前消费它。

现在开始执行：
`v0.3.8 Funding Stability & Serial-Dependence Diagnostic`

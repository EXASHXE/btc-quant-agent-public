"""Async Day-1 facade: MarketWatch -> durable proposal/approval, without execution."""
from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from collections.abc import Callable
from typing import Protocol

from ..approval.feishu import FeishuAppClient
from ..approval.store import LiveState, LiveStore
from ..config import LiveV1Config
from ..market_watch.domain import SymbolAssessment
from ..market_watch.service import MarketWatchService
from .backends import AnalysisBackend, AnalysisMode, CodexExecBackend, ResponsesBackend
from .case import case_from_assessment
from .fusion import DecisionFusion
from .models import AnalysisResultV1, CasePackageV1, TradeProposalV1
from .risk import RiskCompilerV1, RiskPolicyV1


class ProposalNotifier(Protocol):
    async def send_proposal(self, proposal: TradeProposalV1) -> str: ...


class TacticalLiveService:
    def __init__(
        self, store: LiveStore, primary: AnalysisBackend, compiler: RiskCompilerV1, *,
        notifier: ProposalNotifier | None = None, secondary: AnalysisBackend | None = None,
        market_watch: MarketWatchService | None = None, fusion: DecisionFusion | None = None,
        case_ttl_ms: int = 120000, clock_ms: Callable[[], int] | None = None,
    ) -> None:
        self.store = store
        self.primary = primary
        self.secondary = secondary
        self.compiler = compiler
        self.notifier = notifier
        self.market_watch = market_watch
        self.fusion = fusion or DecisionFusion()
        self.case_ttl_ms = case_ttl_ms
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))

    @property
    def exchange_write_count(self) -> int:
        # The service has no executor, order interface, or signed exchange client.
        return 0

    @classmethod
    def from_config(cls, config: LiveV1Config, market_watch: MarketWatchService) -> TacticalLiveService:
        policy_json = os.getenv("BTC_QUANT_LIVE_RISK_POLICY_JSON")
        policy = RiskPolicyV1.model_validate_json(policy_json) if policy_json else RiskPolicyV1()
        primary = ResponsesBackend(config.responses_model, config.analysis_timeout_seconds)
        secondary = (
            CodexExecBackend(config.codex_model, config.analysis_timeout_seconds)
            if config.codex_enabled else None
        )
        secret = os.getenv("FEISHU_APP_SECRET", "")
        notifier = (
            FeishuAppClient(config.feishu_app_id, secret, config.feishu_receive_id)
            if config.feishu_app_id and secret and config.feishu_receive_id else None
        )
        return cls(LiveStore(config.sqlite_path), primary, RiskCompilerV1(policy),
                   notifier=notifier, secondary=secondary, market_watch=market_watch,
                   case_ttl_ms=config.case_ttl_ms)

    async def scan(self, symbols: list[str] | None = None) -> list[TradeProposalV1]:
        if self.market_watch is None:
            raise ValueError("MARKET_WATCH_UNAVAILABLE")
        assessments = await asyncio.to_thread(self.market_watch.scan, symbols, False)
        proposals = []
        for assessment in assessments:
            proposal = await self.run_assessment(assessment)
            if proposal is not None:
                proposals.append(proposal)
        return proposals

    async def run_assessment(self, assessment: SymbolAssessment) -> TradeProposalV1 | None:
        case = case_from_assessment(assessment, ttl_ms=self.case_ttl_ms)
        return await self.analyze_case(case)

    async def _analyze(
        self, backend: AnalysisBackend, case: CasePackageV1, mode: AnalysisMode,
    ) -> AnalysisResultV1:
        try:
            result = await backend.analyze(case, mode)
            result.verify_case(case)
            return result
        except Exception:  # noqa: BLE001 - injected/provider failures become sanitized no-action
            return AnalysisResultV1.fail_closed(case, "unavailable", "", "ANALYSIS_FAILED")

    async def analyze_case(self, case: CasePackageV1) -> TradeProposalV1 | None:
        case.verify()
        now = self.clock_ms()
        self.store.expire_cases(now)
        if (now < case.created_at_ms or now >= case.expires_at_ms
                or now - case.observed_at_ms > self.compiler.policy.max_staleness_ms):
            raise ValueError("STALE_CASE")
        if not self.store.save_case(case):
            # A reserved case is never reissued to the primary provider after retries/restart.
            return self.store.active_proposal(case.case_id)
        self.store.transition(case.case_id, LiveState.LLM_ANALYZING, now)
        try:
            primary = await self._analyze(self.primary, case, AnalysisMode.PRIMARY)
            self.store.save_analysis(primary, role="PRIMARY")
            secondary = None
            if self.fusion.needs_secondary(case, primary) and self.secondary is not None:
                secondary = await self._analyze(self.secondary, case, AnalysisMode.SECONDARY)
                self.store.save_analysis(secondary, role="SECONDARY")
            return await self._finish(case, primary, secondary)
        except asyncio.CancelledError:
            self._recover_state(case.case_id, LiveState.MANUAL)
            raise
        except (ValueError, sqlite3.Error):
            state = LiveState.EXPIRED if self.clock_ms() >= case.expires_at_ms else LiveState.MANUAL
            self._recover_state(case.case_id, state)
            return None

    def _recover_state(self, case_id: str, target: LiveState) -> None:
        try:
            if self.store.state(case_id) not in (LiveState.APPROVED, LiveState.REJECTED,
                                                LiveState.EXPIRED):
                self.store.transition(case_id, target, self.clock_ms())
        except (ValueError, sqlite3.Error):
            # A concurrent terminal transition wins; unavailable storage recovers at TTL.
            pass

    async def _finish(
        self, case: CasePackageV1, primary: AnalysisResultV1,
        secondary: AnalysisResultV1 | None, *, manual_codex_request: bool = False,
        review_claim_token: str | None = None,
    ) -> TradeProposalV1:
        fused = self.fusion.fuse(case, primary, secondary,
                                 manual_codex_request=manual_codex_request)
        if fused.selected.result_hash not in (
            primary.result_hash, secondary.result_hash if secondary else "",
        ):
            self.store.save_analysis(fused.selected, role="FUSED")
        hashes = tuple(dict.fromkeys(
            [primary.result_hash] + ([secondary.result_hash] if secondary else [])
            + [fused.selected.result_hash]
        ))
        proposal = self.compiler.compile(
            case, fused.selected, now_ms=self.clock_ms(), analysis_result_hashes=hashes,
            requires_manual_review=fused.requires_manual_review,
        )
        self.store.save_proposal(proposal, review_claim_token=review_claim_token,
                                 now_ms=self.clock_ms())
        self.store.transition(case.case_id, LiveState.PLAN_READY, self.clock_ms(),
                              review_claim_token=review_claim_token)
        if self.notifier is None:
            self.store.transition(case.case_id, LiveState.MANUAL, self.clock_ms(),
                                  review_claim_token=review_claim_token)
            return proposal
        try:
            await self.notifier.send_proposal(proposal)
        except Exception:  # noqa: BLE001 - notification failures cannot create approval authority
            self.store.transition(case.case_id, LiveState.MANUAL, self.clock_ms(),
                                  review_claim_token=review_claim_token)
            return proposal
        self.store.transition(case.case_id, LiveState.NOTIFIED, self.clock_ms(),
                              review_claim_token=review_claim_token)
        self.store.transition(case.case_id, LiveState.WAITING_APPROVAL, self.clock_ms(),
                              review_claim_token=review_claim_token)
        return proposal

    async def process_codex_reviews(self) -> list[TradeProposalV1]:
        self.store.expire_cases(self.clock_ms())
        if self.secondary is None:
            return []
        proposals = []
        for case_id in self.store.queued_codex_reviews(self.clock_ms()):
            lease_ms = int(getattr(self.secondary, "timeout_seconds", 60) * 1000) + 30000
            token = self.store.claim_codex_review(case_id, self.clock_ms(), lease_ms)
            if token is None:
                continue
            try:
                case = self.store.get_case(case_id)
                if self.clock_ms() >= case.expires_at_ms:
                    self.store.transition(case_id, LiveState.EXPIRED, self.clock_ms(),
                                          review_claim_token=token)
                    self.store.mark_codex_review_processed(case_id, token)
                    continue
                primary = self.store.get_analysis(case_id, role="PRIMARY")
                if primary is None:
                    continue
                secondary = await self._analyze(self.secondary, case, AnalysisMode.SECONDARY)
                self.store.save_analysis(secondary, role="SECONDARY")
                if not self.store.renew_codex_review(case_id, token, self.clock_ms(), lease_ms):
                    continue
                proposal = await self._finish(case, primary, secondary, manual_codex_request=True,
                                               review_claim_token=token)
                proposals.append(proposal)
                self.store.mark_codex_review_processed(case_id, token)
            except asyncio.CancelledError:
                state = self.store.state(case_id)
                if (state in (LiveState.PLAN_READY, LiveState.NOTIFIED)
                        and self.store.renew_codex_review(case_id, token, self.clock_ms(), lease_ms)):
                    self.store.transition(case_id, LiveState.MANUAL, self.clock_ms(),
                                          review_claim_token=token)
                raise
            except ValueError:
                if self.store.renew_codex_review(case_id, token, self.clock_ms(), lease_ms):
                    if self.clock_ms() >= case.expires_at_ms:
                        self.store.transition(case_id, LiveState.EXPIRED, self.clock_ms(),
                                              review_claim_token=token)
                        self.store.mark_codex_review_processed(case_id, token)
                    elif self.store.state(case_id) in (LiveState.PLAN_READY, LiveState.NOTIFIED):
                        self.store.transition(case_id, LiveState.MANUAL, self.clock_ms(),
                                              review_claim_token=token)
            finally:
                self.store.release_codex_review(case_id, token)
        return proposals

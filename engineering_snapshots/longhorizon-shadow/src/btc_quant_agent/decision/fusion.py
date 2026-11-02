"""Conservative fusion of case-bound analysis results."""

from __future__ import annotations

from .models import AnalysisResultV1, CasePackageV1, ImmutableModel


class FusionResult(ImmutableModel):
    primary: AnalysisResultV1
    secondary: AnalysisResultV1 | None
    selected: AnalysisResultV1
    requires_manual_review: bool
    reasons: tuple[str, ...]


class DecisionFusion:
    def __init__(self, confidence_threshold: float = 0.7,
                 high_exposure_fraction: float = 0.25) -> None:
        if not 0 <= confidence_threshold <= 1 or not 0 <= high_exposure_fraction <= 1:
            raise ValueError("fusion thresholds must be fractions")
        self.confidence_threshold = confidence_threshold
        self.high_exposure_fraction = high_exposure_fraction

    def _review_reasons(self, case: CasePackageV1, primary: AnalysisResultV1,
                        manual_codex_request: bool) -> list[str]:
        case.verify()
        primary.verify_case(case)
        reasons: list[str] = []
        if primary.confidence < self.confidence_threshold:
            reasons.append("LOW_CONFIDENCE")
        if primary.action == "ADD":
            reasons.append("ADD_REVIEW")
        if primary.strategy_data_disagreement:
            reasons.append("STRATEGY_DATA_DISAGREEMENT")
        if primary.requires_secondary_review:
            reasons.append("SECONDARY_REVIEW_REQUESTED")
        if manual_codex_request:
            reasons.append("MANUAL_CODEX_REQUEST")
        if case.account is not None and (
            max(case.account.symbol_exposure_usdt, case.account.portfolio_exposure_usdt)
            / case.account.equity_usdt >= self.high_exposure_fraction
        ):
            reasons.append("HIGH_EXPOSURE")
        return reasons

    def needs_secondary(self, case: CasePackageV1, primary: AnalysisResultV1, *,
                        manual_codex_request: bool = False) -> bool:
        return bool(self._review_reasons(case, primary, manual_codex_request))

    def fuse(self, case: CasePackageV1, primary: AnalysisResultV1,
             secondary: AnalysisResultV1 | None = None, *,
             manual_codex_request: bool = False) -> FusionResult:
        reasons = self._review_reasons(case, primary, manual_codex_request)
        if secondary is not None:
            secondary.verify_case(case)
        secondary_required = bool(reasons)
        if secondary_required and secondary is None:
            reasons.append("SECONDARY_UNAVAILABLE")
        if secondary is not None and (
            primary.action != secondary.action
            or primary.risk_modifier != secondary.risk_modifier
            or primary.entry_quality != secondary.entry_quality
            or abs(primary.thesis_strength - secondary.thesis_strength) >= 0.3
        ):
            reasons.append("MODEL_DISAGREEMENT")
        manual = (primary.requires_manual_review or
                  (secondary.requires_manual_review if secondary else False) or
                  "SECONDARY_UNAVAILABLE" in reasons or "MODEL_DISAGREEMENT" in reasons)
        modifier = primary.risk_modifier
        if secondary is not None and secondary.risk_modifier == "BLOCK":
            modifier = "BLOCK"
        elif secondary is not None and secondary.risk_modifier == "REDUCE" and modifier == "STANDARD":
            modifier = "REDUCE"
        if manual:
            modifier = "BLOCK"
        selected = primary.model_copy(update={"risk_modifier": modifier,
                                              "requires_manual_review": manual})
        return FusionResult(primary=primary, secondary=secondary, selected=selected,
                            requires_manual_review=manual, reasons=tuple(reasons))

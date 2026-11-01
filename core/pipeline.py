"""One function that runs the whole DataGuard analysis.

Both the Streamlit app and the daily command-line script call ``run_pipeline``,
so they always give identical answers.

    reconcile -> money at risk -> root causes -> quality rules -> health score
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from core import config
from core.health import data_completeness, health_score
from core.quality_rules import (load_rule_sets, overall_pass_rate, rule_scorecard,
                                run_quality_rules_engine)
from core.reconciliation import ReconConfig, ReconResult, reconcile
from core.risk import add_risk, risk_by_status, risk_summary
from core.root_cause import find_root_causes
from core.utils import read_any

DEFAULT_HIGH = 2000.0
DEFAULT_MEDIUM = 500.0


@dataclass
class PipelineOutput:
    config: ReconConfig
    recon: ReconResult
    results: pd.DataFrame            # all records, with risk columns
    risk: dict
    risk_by_status: pd.DataFrame
    findings: pd.DataFrame
    rule_scorecard: pd.DataFrame
    rule_issues: pd.DataFrame
    rule_pass_rate: float
    completeness: float
    health: dict
    warnings: list = field(default_factory=list)

    @property
    def exceptions(self) -> pd.DataFrame:
        return self.results[self.results["Status"] != "Matched"]


def load_pipeline_files(cfg: ReconConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the source and target files named in a pipeline config."""
    if not cfg.source_file or not cfg.target_file:
        raise ValueError(f"Pipeline '{cfg.name}' has no source_file / target_file configured.")
    source = read_any(config.BASE_DIR / cfg.source_file)
    target = read_any(config.BASE_DIR / cfg.target_file)
    return source, target


def run_pipeline(cfg: ReconConfig, source: pd.DataFrame, target: pd.DataFrame,
                 high_threshold: float = DEFAULT_HIGH, medium_threshold: float = DEFAULT_MEDIUM,
                 rules: list[dict] | None = None) -> PipelineOutput:
    """Run reconciliation, risk scoring, root-cause analysis, rules and health score."""
    recon = reconcile(source, target, cfg)
    with_risk = add_risk(recon.results, high_threshold, medium_threshold)
    findings = find_root_causes(with_risk, recon.diffs, source, cfg)

    # quality rules on the source file (from the argument, or from the pipeline's rule set)
    if rules is None and cfg.rule_set:
        rules = load_rule_sets(config.RULES_CONFIG).get(cfg.rule_set, {}).get("rules", [])
    rules = rules or []

    if rules:
        issues = run_quality_rules_engine(source, rules)
        scorecard = rule_scorecard(source, rules, issues)
        pass_rate = overall_pass_rate(scorecard)
    else:
        issues = pd.DataFrame()
        scorecard = pd.DataFrame()
        pass_rate = 100.0

    compared = [cfg.key_source, *cfg.column_map.keys()]
    completeness = data_completeness(source, compared)

    health = health_score(recon.stats, completeness, pass_rate)

    return PipelineOutput(
        config=cfg, recon=recon, results=with_risk,
        risk=risk_summary(with_risk), risk_by_status=risk_by_status(with_risk),
        findings=findings, rule_scorecard=scorecard, rule_issues=issues,
        rule_pass_rate=pass_rate, completeness=completeness, health=health,
        warnings=recon.warnings,
    )

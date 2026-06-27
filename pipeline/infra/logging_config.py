"""
Structured Logging Configuration.
Uses structlog for structured, machine-readable log entries.
Every pipeline event includes: timestamp, run_id, ticker, stage, duration, details.
"""

import uuid
import time
import logging
import structlog
from contextlib import contextmanager
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field


def configure_logging():
    """Configure structlog for the pipeline."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if True else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    """Get a structured logger."""
    return structlog.get_logger(name)


@dataclass
class StageMetrics:
    """Metrics for a single pipeline stage."""
    stage: str
    ticker: str
    duration_ms: float = 0.0
    cache_hit: bool = False
    success: bool = True
    error: Optional[str] = None
    token_count: int = 0


@dataclass
class RunSummary:
    """Summary report for a complete pipeline run."""
    run_id: str
    tickers_requested: int = 0
    tickers_succeeded: int = 0
    tickers_failed: int = 0
    tickers_skipped: int = 0
    stage_metrics: List[StageMetrics] = field(default_factory=list)
    total_duration_ms: float = 0.0
    cache_hit_rate: float = 0.0
    api_error_count: int = 0
    semantic_inconsistencies: int = 0
    data_quality_failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        # Compute averages per stage
        stage_durations: Dict[str, List[float]] = {}
        cache_hits = 0
        total_stages = 0

        for m in self.stage_metrics:
            if m.stage not in stage_durations:
                stage_durations[m.stage] = []
            stage_durations[m.stage].append(m.duration_ms)
            if m.cache_hit:
                cache_hits += 1
            total_stages += 1

        avg_durations = {
            stage: sum(durations) / len(durations)
            for stage, durations in stage_durations.items()
        }

        self.cache_hit_rate = cache_hits / total_stages if total_stages > 0 else 0.0

        return {
            "run_id": self.run_id,
            "tickers": {
                "requested": self.tickers_requested,
                "succeeded": self.tickers_succeeded,
                "failed": self.tickers_failed,
                "skipped": self.tickers_skipped,
            },
            "timing": {
                "total_ms": round(self.total_duration_ms, 2),
                "avg_per_stage_ms": {k: round(v, 2) for k, v in avg_durations.items()},
            },
            "cache_hit_rate": round(self.cache_hit_rate, 4),
            "api_error_count": self.api_error_count,
            "semantic_inconsistencies": self.semantic_inconsistencies,
            "data_quality_failures": self.data_quality_failures,
        }


class PipelineRunTracker:
    """Tracks metrics for a single pipeline run."""

    def __init__(self):
        self.run_id = str(uuid.uuid4())[:8]
        self.summary = RunSummary(run_id=self.run_id)
        self._run_start = time.time()
        self._log = get_logger("pipeline")

    @contextmanager
    def track_stage(self, stage: str, ticker: str):
        """Context manager to track timing and success/failure of a pipeline stage."""
        start = time.time()
        metrics = StageMetrics(stage=stage, ticker=ticker)

        self._log.info("stage_start", run_id=self.run_id, stage=stage, ticker=ticker)

        try:
            yield metrics
            metrics.success = True
        except Exception as e:
            metrics.success = False
            metrics.error = str(e)
            self._log.error("stage_error", run_id=self.run_id, stage=stage, ticker=ticker, error=str(e))
            raise
        finally:
            metrics.duration_ms = (time.time() - start) * 1000
            self.summary.stage_metrics.append(metrics)
            self._log.info(
                "stage_end",
                run_id=self.run_id,
                stage=stage,
                ticker=ticker,
                duration_ms=round(metrics.duration_ms, 2),
                cache_hit=metrics.cache_hit,
                success=metrics.success,
            )

    def record_cache_hit(self, stage: str, ticker: str):
        """Record a cache hit for a stage."""
        metrics = StageMetrics(stage=stage, ticker=ticker, cache_hit=True, duration_ms=0.0)
        self.summary.stage_metrics.append(metrics)

    def record_data_quality_failure(self, ticker: str, field: str, reason: str):
        """Record a data quality failure."""
        msg = f"{ticker}:{field}:{reason}"
        self.summary.data_quality_failures.append(msg)
        self._log.warning("data_quality_failure", run_id=self.run_id, ticker=ticker, field=field, reason=reason)

    def record_inconsistency(self):
        """Record a semantic inconsistency."""
        self.summary.semantic_inconsistencies += 1

    def finalize(self) -> RunSummary:
        """Finalize the run and compute summary."""
        self.summary.total_duration_ms = (time.time() - self._run_start) * 1000

        report = self.summary.to_dict()
        self._log.info("run_complete", **report)

        return self.summary


# Initialize logging on import
configure_logging()

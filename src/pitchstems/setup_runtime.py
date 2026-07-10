from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pitchstems.doctor import format_checks, run_checks
from pitchstems.model_assets import ModelAssetStatus, ensure_model_assets, model_asset_statuses
from pitchstems.model_catalog import DEFAULT_MODEL_KEY
from pitchstems.runtime_checks import RuntimeCheck


@dataclass(frozen=True)
class RuntimeSetupResult:
    checks: list[RuntimeCheck]
    model_statuses: list[ModelAssetStatus]
    error: str | None = None

    @property
    def ok(self) -> bool:
        return (
            self.error is None
            and all(check.ok for check in self.checks)
            and all(status.ok for status in self.model_statuses)
        )


def run_setup(
    *,
    log: Callable[[str], None] | None = None,
) -> RuntimeSetupResult:
    checks = run_checks(require_gpu=False)
    statuses: list[ModelAssetStatus]
    error = None
    try:
        statuses = ensure_model_assets(DEFAULT_MODEL_KEY, log=log, verify_hash=True)
    except Exception as exc:
        error = str(exc)
        if log is not None:
            log(f"Setup repair failed: {exc}")
        statuses = model_asset_statuses(DEFAULT_MODEL_KEY, verify_hash=True)
    return RuntimeSetupResult(checks=checks, model_statuses=statuses, error=error)


def format_setup_result(result: RuntimeSetupResult) -> str:
    lines = ["Runtime checks:", format_checks(result.checks), "", "Model assets:"]
    for status in result.model_statuses:
        state = "OK" if status.ok else "NEEDS FIX"
        lines.append(f"{state:9} {status.filename}: {status.detail}")
    if result.error:
        lines.extend(["", f"Setup error: {result.error}"])
    return "\n".join(lines)

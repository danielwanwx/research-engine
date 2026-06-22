"""Connector execution orchestration: concurrency, retry, cache, and telemetry."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Callable

from research_engine.models import CollectionRequest, CollectionResult, utc_now


ConnectorProvider = Any | Callable[[], Any]


@dataclass(frozen=True)
class ConnectorExecutionOptions:
    max_workers: int = 4
    retries: int = 1
    cache_dir: Path | None = None
    source_timeout_seconds: float | None = None


def execute_collection_requests(
    requests: list[CollectionRequest],
    *,
    connector_providers: dict[str, ConnectorProvider],
    options: ConnectorExecutionOptions | None = None,
) -> tuple[list[CollectionResult], list[str], dict[str, Any]]:
    """Run connector requests concurrently and return results, warnings, and telemetry."""

    resolved_options = options or ConnectorExecutionOptions()
    if not requests:
        return [], [], build_execution_report(options=resolved_options, records=[])

    max_workers = max(1, min(resolved_options.max_workers, len(requests)))
    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures: dict[int, Future[tuple[CollectionResult | None, dict[str, Any]]]] = {}
    for index, request in enumerate(requests):
        futures[index] = executor.submit(
            execute_one_request,
            request,
            connector_providers=connector_providers,
            options=resolved_options,
        )

    timed_out = False
    results_by_index: dict[int, CollectionResult] = {}
    records_by_index: dict[int, dict[str, Any]] = {}
    warnings: list[str] = []
    for index, request in enumerate(requests):
        future = futures[index]
        try:
            result, record = future.result(timeout=resolved_options.source_timeout_seconds)
        except TimeoutError:
            timed_out = True
            connector_id = str(request.source.get("connector") or "")
            warning = f"{connector_id} connector timed out for {request.source_id}"
            warnings.append(warning)
            records_by_index[index] = {
                "source_id": request.source_id,
                "connector": connector_id,
                "status": "timeout",
                "attempts": 1,
                "cache_hit": False,
                "row_count": 0,
                "warnings": [warning],
                "elapsed_ms": None,
            }
            continue
        records_by_index[index] = record
        warnings.extend(str(warning) for warning in record.get("warnings") or [])
        if result:
            results_by_index[index] = result

    executor.shutdown(wait=not timed_out, cancel_futures=timed_out)
    ordered_results = [results_by_index[index] for index in range(len(requests)) if index in results_by_index]
    ordered_records = [records_by_index[index] for index in range(len(requests)) if index in records_by_index]
    return ordered_results, warnings, build_execution_report(
        options=resolved_options,
        records=ordered_records,
    )


def execute_one_request(
    request: CollectionRequest,
    *,
    connector_providers: dict[str, ConnectorProvider],
    options: ConnectorExecutionOptions,
) -> tuple[CollectionResult | None, dict[str, Any]]:
    connector_id = str(request.source.get("connector") or "")
    started = time.monotonic()
    cache_key = build_cache_key(request, connector_id=connector_id)
    warnings: list[str] = []
    if options.cache_dir:
        cached = read_cached_result(options.cache_dir, cache_key)
        if cached:
            result = CollectionResult(
                source_id=str(cached.get("source_id") or request.source_id),
                connector=str(cached.get("connector") or connector_id),
                rows=list(cached.get("rows") or []),
                warnings=list(cached.get("warnings") or []),
                metadata={**dict(cached.get("metadata") or {}), "cache_hit": True},
            )
            return result, build_record(
                request=request,
                connector_id=connector_id,
                status="cache_hit",
                attempts=0,
                cache_hit=True,
                row_count=len(result.rows),
                warnings=result.warnings,
                started=started,
            )

    provider = connector_providers.get(connector_id)
    if not provider:
        warning = f"no connector registered for {connector_id}"
        return None, build_record(
            request=request,
            connector_id=connector_id,
            status="failed",
            attempts=0,
            cache_hit=False,
            row_count=0,
            warnings=[warning],
            started=started,
        )

    attempts = 0
    last_error = ""
    max_attempts = max(1, options.retries + 1)
    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        connector = provider() if callable(provider) else provider
        try:
            result = connector.collect(request)
        except Exception as exc:
            last_error = str(exc)
            if attempt < max_attempts:
                continue
            warning = f"{connector_id} connector crashed for {request.source_id}: {exc}"
            return None, build_record(
                request=request,
                connector_id=connector_id,
                status="failed",
                attempts=attempts,
                cache_hit=False,
                row_count=0,
                warnings=[warning],
                started=started,
            )
        if options.cache_dir:
            write_cached_result(options.cache_dir, cache_key, result)
        status = "warning" if result.warnings else "ok"
        return result, build_record(
            request=request,
            connector_id=connector_id,
            status=status,
            attempts=attempts,
            cache_hit=False,
            row_count=len(result.rows),
            warnings=result.warnings,
            started=started,
        )

    warning = f"{connector_id} connector failed for {request.source_id}: {last_error or 'unknown error'}"
    warnings.append(warning)
    return None, build_record(
        request=request,
        connector_id=connector_id,
        status="failed",
        attempts=attempts,
        cache_hit=False,
        row_count=0,
        warnings=warnings,
        started=started,
    )


def build_execution_report(
    *,
    options: ConnectorExecutionOptions,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for record in records:
        status = str(record.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "generated_at": utc_now(),
        "max_workers": options.max_workers,
        "retries": options.retries,
        "cache_enabled": options.cache_dir is not None,
        "source_timeout_seconds": options.source_timeout_seconds,
        "request_count": len(records),
        "status_counts": status_counts,
        "requests": records,
    }


def build_record(
    *,
    request: CollectionRequest,
    connector_id: str,
    status: str,
    attempts: int,
    cache_hit: bool,
    row_count: int,
    warnings: list[str],
    started: float,
) -> dict[str, Any]:
    return {
        "source_id": request.source_id,
        "connector": connector_id,
        "status": status,
        "attempts": attempts,
        "cache_hit": cache_hit,
        "row_count": row_count,
        "warnings": list(warnings),
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


def build_cache_key(request: CollectionRequest, *, connector_id: str) -> str:
    payload = {
        "connector_id": connector_id,
        "source": request.source,
        "topic": request.topic,
        "run_date": request.run_date,
        "depth": request.depth,
        "max_results": request.max_results,
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cache_path(cache_dir: Path, cache_key: str) -> Path:
    return cache_dir / f"{cache_key}.json"


def read_cached_result(cache_dir: Path, cache_key: str) -> dict[str, Any] | None:
    path = cache_path(cache_dir, cache_key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_cached_result(cache_dir: Path, cache_key: str, result: CollectionResult) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_id": result.source_id,
        "connector": result.connector,
        "rows": result.rows,
        "warnings": result.warnings,
        "metadata": result.metadata,
    }
    cache_path(cache_dir, cache_key).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

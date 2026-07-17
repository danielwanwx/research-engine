"""Connector execution orchestration: concurrency, retry, cache, and telemetry."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import random
import threading
import time
from typing import Any, Callable
from urllib.parse import urlsplit

from research_engine.models import CollectionRequest, CollectionResult, utc_now


ConnectorProvider = Any | Callable[[], Any]


@dataclass(frozen=True)
class ConnectorExecutionOptions:
    max_workers: int = 4
    retries: int = 1
    cache_dir: Path | None = None
    source_timeout_seconds: float | None = None
    backoff_base_seconds: float = 0.25
    backoff_cap_seconds: float = 4.0
    sleep_fn: Callable[[float], None] = field(default=time.sleep, repr=False, compare=False)
    jitter_fn: Callable[[], float] = field(default=random.random, repr=False, compare=False)
    monotonic_fn: Callable[[], float] = field(default=time.monotonic, repr=False, compare=False)
    overall_deadline_seconds: float | None = None
    host_max_concurrency: int = 2
    host_delay_seconds: float = 0.1


def execute_collection_requests(
    requests: list[CollectionRequest],
    *,
    connector_providers: dict[str, ConnectorProvider],
    options: ConnectorExecutionOptions | None = None,
) -> tuple[list[CollectionResult], list[str], dict[str, Any]]:
    """Run connector requests concurrently and return results, warnings, and telemetry."""

    resolved_options = options or ConnectorExecutionOptions()
    scheduler = _HostScheduler(resolved_options)
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
            scheduler=scheduler,
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
                "pass_id": str(request.source.get("pass_id") or "pass-1"),
                "facet_id": str(request.source.get("facet_id") or ""),
                "query_id": str(request.source.get("query_id") or ""),
                "target_company": str(request.source.get("target_company") or ""),
                "retry_delays_seconds": [],
                "deadline_exhausted": False,
                "host": request_host(request),
                "host_wait_seconds": 0.0,
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
    scheduler: _HostScheduler | None = None,
) -> tuple[CollectionResult | None, dict[str, Any]]:
    connector_id = str(request.source.get("connector") or "")
    resolved_scheduler = scheduler or _HostScheduler(options)
    started = options.monotonic_fn()
    cache_key = build_cache_key(request, connector_id=connector_id)
    warnings: list[str] = []
    if options.cache_dir:
        cached = read_cached_result(
            options.cache_dir,
            cache_key,
            max_age_seconds=_positive_float(request.source.get("cache_ttl_seconds")),
        )
        if cached:
            result = CollectionResult(
                source_id=str(cached.get("source_id") or request.source_id),
                connector=str(cached.get("connector") or connector_id),
                rows=list(cached.get("rows") or []),
                warnings=list(cached.get("warnings") or []),
                metadata={**dict(cached.get("metadata") or {}), "cache_hit": True},
            )
            cached_status = str(result.metadata.get("status") or "")
            return result, build_record(
                request=request,
                connector_id=connector_id,
                status=(
                    cached_status
                    if cached_status
                    in {"failed", "rate_limit", "robots_denied", "retry_exhausted"}
                    else "cache_hit"
                ),
                attempts=0,
                cache_hit=True,
                row_count=len(result.rows),
                warnings=result.warnings,
                started=started,
                provider_metadata=result.metadata,
                clock_fn=options.monotonic_fn,
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
            clock_fn=options.monotonic_fn,
        )

    attempts = 0
    last_error = ""
    retry_delays: list[float] = []
    host_wait_seconds = 0.0
    deadline_exhausted = False
    paid_connector = bool(request.source.get("paid_call")) or connector_id == "xai_discovery"
    max_attempts = 1 if paid_connector else max(1, options.retries + 1)
    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        connector = provider() if callable(provider) else provider
        try:
            with resolved_scheduler.slot(request) as host_wait:
                host_wait_seconds += host_wait
                result = connector.collect(request)
        except DeadlineExceeded:
            deadline_exhausted = True
            warning = f"{connector_id} connector deadline exhausted for {request.source_id}"
            return None, build_record(
                request=request,
                connector_id=connector_id,
                status="retry_exhausted",
                attempts=attempts,
                cache_hit=False,
                row_count=0,
                warnings=[warning],
                started=started,
                retry_delays=retry_delays,
                deadline_exhausted=True,
                host_wait_seconds=host_wait_seconds,
                clock_fn=options.monotonic_fn,
            )
        except Exception as exc:
            last_error = str(exc)
            if attempt < max_attempts:
                delay = retry_delay_seconds(
                    attempt,
                    base=options.backoff_base_seconds,
                    cap=options.backoff_cap_seconds,
                    jitter=options.jitter_fn(),
                )
                retry_after = retry_after_seconds(exc)
                if retry_after is not None:
                    delay = max(delay, min(retry_after, max(0.0, options.backoff_cap_seconds)))
                remaining = resolved_scheduler.remaining_seconds()
                if remaining is not None and delay > remaining:
                    deadline_exhausted = True
                    status = "rate_limit" if is_rate_limit(exc) else "retry_exhausted"
                    warning = failure_warning(
                        connector_id,
                        request.source_id,
                        exc,
                        status=status,
                    )
                    return None, build_record(
                        request=request,
                        connector_id=connector_id,
                        status=status,
                        attempts=attempts,
                        cache_hit=False,
                        row_count=0,
                        warnings=[warning],
                        started=started,
                        retry_delays=retry_delays,
                        deadline_exhausted=True,
                        host_wait_seconds=host_wait_seconds,
                        clock_fn=options.monotonic_fn,
                    )
                if delay:
                    options.sleep_fn(delay)
                retry_delays.append(delay)
                continue
            status = "rate_limit" if is_rate_limit(exc) else (
                "retry_exhausted" if attempts > 1 else "failed"
            )
            warning = failure_warning(connector_id, request.source_id, exc, status=status)
            return None, build_record(
                request=request,
                connector_id=connector_id,
                status=status,
                attempts=attempts,
                cache_hit=False,
                row_count=0,
                warnings=[warning],
                started=started,
                retry_delays=retry_delays,
                deadline_exhausted=deadline_exhausted,
                host_wait_seconds=host_wait_seconds,
                clock_fn=options.monotonic_fn,
            )
        for row in result.rows:
            row.setdefault("source_id", request.source_id)
            row.setdefault("query_id", str(request.source.get("query_id") or ""))
            row.setdefault("facet_id", str(request.source.get("facet_id") or ""))
            row.setdefault("pass_id", str(request.source.get("pass_id") or "pass-1"))
        result_status = str(result.metadata.get("status") or "")
        status = (
            result_status
            if result_status
            in {"failed", "rate_limit", "robots_denied", "retry_exhausted"}
            else "warning" if result.warnings else "ok"
        )
        if options.cache_dir and status not in {
            "failed",
            "rate_limit",
            "robots_denied",
            "retry_exhausted",
        }:
            write_cached_result(options.cache_dir, cache_key, result)
        return result, build_record(
            request=request,
            connector_id=connector_id,
            status=status,
            attempts=attempts,
            cache_hit=False,
            row_count=len(result.rows),
            warnings=result.warnings,
            started=started,
            retry_delays=retry_delays,
            deadline_exhausted=deadline_exhausted,
            host_wait_seconds=host_wait_seconds,
            provider_metadata=result.metadata,
            clock_fn=options.monotonic_fn,
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
        retry_delays=retry_delays,
        deadline_exhausted=deadline_exhausted,
        host_wait_seconds=host_wait_seconds,
        clock_fn=options.monotonic_fn,
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
        "overall_deadline_seconds": options.overall_deadline_seconds,
        "host_max_concurrency": options.host_max_concurrency,
        "host_delay_seconds": options.host_delay_seconds,
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
    retry_delays: list[float] | None = None,
    deadline_exhausted: bool = False,
    host_wait_seconds: float = 0.0,
    provider_metadata: dict[str, Any] | None = None,
    clock_fn: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    record = {
        "source_id": request.source_id,
        "connector": connector_id,
        "status": status,
        "attempts": attempts,
        "cache_hit": cache_hit,
        "row_count": row_count,
        "warnings": list(warnings),
        "pass_id": str(request.source.get("pass_id") or "pass-1"),
        "facet_id": str(request.source.get("facet_id") or ""),
        "query_id": str(request.source.get("query_id") or ""),
        "target_company": str(request.source.get("target_company") or ""),
        "retry_delays_seconds": list(retry_delays or []),
        "deadline_exhausted": deadline_exhausted,
        "host": request_host(request),
        "host_wait_seconds": round(host_wait_seconds, 3),
        "elapsed_ms": int((clock_fn() - started) * 1000),
    }
    safe_metadata = _safe_provider_metadata(provider_metadata or {})
    if safe_metadata:
        record["provider_metadata"] = safe_metadata
    return record


def _safe_provider_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "status",
        "stop_reason",
        "model",
        "paid_calls_allowed",
        "paid_calls_attempted",
        "paid_calls_completed",
        "external_calls_attempted",
    }
    safe = {key: metadata[key] for key in allowed if key in metadata}
    usage = metadata.get("usage")
    if isinstance(usage, dict):
        safe["usage"] = {
            str(key): value
            for key, value in usage.items()
            if isinstance(value, (int, float, str, bool)) and "key" not in str(key).lower()
        }
    return safe


def retry_delay_seconds(
    attempt: int,
    *,
    base: float,
    cap: float,
    jitter: float,
) -> float:
    """Return bounded exponential delay with 50-100% jitter."""

    bounded_jitter = min(1.0, max(0.0, float(jitter)))
    exponential = min(max(0.0, float(cap)), max(0.0, float(base)) * (2 ** max(0, attempt - 1)))
    return round(exponential * (0.5 + 0.5 * bounded_jitter), 3)


def retry_after_seconds(exc: BaseException) -> float | None:
    value = getattr(exc, "retry_after_seconds", None)
    if value is None:
        headers = getattr(exc, "headers", None)
        if hasattr(headers, "get"):
            value = headers.get("Retry-After")
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, seconds)


def is_rate_limit(exc: BaseException) -> bool:
    return getattr(exc, "code", None) == 429 or getattr(exc, "status", None) == 429


def failure_warning(
    connector_id: str,
    source_id: str,
    exc: BaseException,
    *,
    status: str,
) -> str:
    label = "rate limited" if status == "rate_limit" else "crashed"
    return f"{connector_id} connector {label} for {source_id}: {type(exc).__name__}"


def request_host(request: CollectionRequest) -> str:
    source = request.source
    candidates = [source.get("url"), source.get("endpoint")]
    pages = source.get("pages") or []
    if pages and isinstance(pages[0], dict):
        candidates.append(pages[0].get("url"))
    for value in candidates:
        host = str(urlsplit(str(value or "")).hostname or "").lower()
        if host:
            return host
    return ""


class DeadlineExceeded(TimeoutError):
    pass


class _HostScheduler:
    def __init__(self, options: ConnectorExecutionOptions) -> None:
        self.options = options
        self.started = options.monotonic_fn()
        self.deadline = (
            self.started + max(0.0, options.overall_deadline_seconds)
            if options.overall_deadline_seconds is not None
            else None
        )
        self._lock = threading.Lock()
        self._semaphores: dict[str, threading.BoundedSemaphore] = {}
        self._last_started: dict[str, float] = {}

    def remaining_seconds(self) -> float | None:
        if self.deadline is None:
            return None
        return max(0.0, self.deadline - self.options.monotonic_fn())

    @contextmanager
    def slot(self, request: CollectionRequest):
        host = request_host(request)
        if not host:
            if self.remaining_seconds() == 0:
                raise DeadlineExceeded
            yield 0.0
            return
        with self._lock:
            semaphore = self._semaphores.setdefault(
                host,
                threading.BoundedSemaphore(max(1, self.options.host_max_concurrency)),
            )
        remaining = self.remaining_seconds()
        acquired = semaphore.acquire(timeout=remaining) if remaining is not None else semaphore.acquire()
        if not acquired:
            raise DeadlineExceeded
        wait = 0.0
        try:
            with self._lock:
                now = self.options.monotonic_fn()
                target = self._last_started.get(host, now) + max(0.0, self.options.host_delay_seconds)
                wait = max(0.0, target - now) if host in self._last_started else 0.0
                remaining = self.remaining_seconds()
                if remaining is not None and wait > remaining:
                    raise DeadlineExceeded
                if wait:
                    self.options.sleep_fn(wait)
                self._last_started[host] = self.options.monotonic_fn()
            yield round(wait, 3)
        finally:
            semaphore.release()


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


def read_cached_result(
    cache_dir: Path,
    cache_key: str,
    *,
    max_age_seconds: float | None = None,
) -> dict[str, Any] | None:
    path = cache_path(cache_dir, cache_key)
    if not path.exists():
        return None
    if max_age_seconds is not None:
        try:
            if time.time() - path.stat().st_mtime > max_age_seconds:
                return None
        except OSError:
            return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


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

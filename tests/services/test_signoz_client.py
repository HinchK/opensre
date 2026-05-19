"""Unit tests for SigNoz service client."""

from __future__ import annotations

from typing import Any

import httpx

from app.integrations.signoz import SigNozConfig
from app.services.signoz.client import SigNozClient


class _FakeResult:
    def __init__(self, row: tuple[Any, ...]) -> None:
        self.row_count = 1
        self.first_row = row


class _FakeClient:
    def __init__(self, row: tuple[Any, ...]) -> None:
        self._row = row
        self.closed = False

    def query(self, _query: str, parameters: dict[str, Any] | None = None) -> _FakeResult:
        assert parameters is not None
        return _FakeResult(self._row)

    def close(self) -> None:
        self.closed = True


class _FakeMetricsResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.row_count = len(rows)
        self.first_row = rows[0] if rows else ()

    def named_results(self) -> list[dict[str, Any]]:
        return self._rows


class _CaptureMetricsClient:
    def __init__(self) -> None:
        self.closed = False
        self.last_query = ""
        self.last_params: dict[str, Any] | None = None

    def query(self, query: str, parameters: dict[str, Any] | None = None) -> _FakeMetricsResult:
        self.last_query = query
        self.last_params = parameters or {}
        return _FakeMetricsResult([])

    def close(self) -> None:
        self.closed = True


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _ErrorHTTPResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)
        self.request = httpx.Request("POST", "http://localhost")

    def raise_for_status(self) -> None:
        raise httpx.HTTPStatusError(
            f"error {self.status_code}",
            request=self.request,
            response=httpx.Response(self.status_code, request=self.request, json=self._payload),
        )

    def json(self) -> dict[str, Any]:
        return self._payload


def test_query_trace_summary_sanitizes_nan(monkeypatch) -> None:
    fake_client = _FakeClient((0, 0, float("nan"), float("nan"), float("nan"), float("nan")))
    monkeypatch.setattr("app.services.signoz.client._make_client", lambda _config: fake_client)

    config = SigNozConfig(clickhouse_host="localhost")
    result = SigNozClient(config).query_trace_summary(service="svc", time_range_minutes=60)

    assert result["total_spans"] == 0
    assert result["error_spans"] == 0
    assert result["error_rate"] == 0.0
    assert result["p99_ms"] == 0.0
    assert result["p95_ms"] == 0.0
    assert result["avg_ms"] == 0.0
    assert result["max_ms"] == 0.0
    assert fake_client.closed is True


def test_query_metrics_uses_null_safe_env_join(monkeypatch) -> None:
    fake_client = _CaptureMetricsClient()
    monkeypatch.setattr("app.services.signoz.client._make_client", lambda _config: fake_client)

    config = SigNozConfig(clickhouse_host="localhost")
    result = SigNozClient(config).query_metrics(metric_name="cpu_usage", service="svc")

    assert result["available"] is True
    assert result["metric_name"] == "cpu_usage"
    assert "coalesce(s.env, '') = coalesce(ts.env, '')" in fake_client.last_query
    assert fake_client.closed is True


def test_query_metrics_uses_metrics_api_when_configured(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_post(url: str, **kwargs: Any) -> _FakeHTTPResponse:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _FakeHTTPResponse(
            {
                "status": "success",
                "data": {
                    "type": "time_series",
                    "data": {
                        "results": [
                            {
                                "queryName": "A",
                                "aggregations": [
                                    {
                                        "series": [
                                            {
                                                "labels": [
                                                    {
                                                        "key": {"name": "service.name"},
                                                        "value": "payments",
                                                    }
                                                ],
                                                "values": [
                                                    {
                                                        "timestamp": 1_700_000_000_000,
                                                        "value": 12.34,
                                                    }
                                                ],
                                            }
                                        ]
                                    }
                                ],
                            }
                        ]
                    },
                },
            }
        )

    monkeypatch.setattr("app.services.signoz.client.httpx.post", _fake_post)

    config = SigNozConfig(
        url="http://localhost:3301",
        api_key="test-key",
    )
    result = SigNozClient(config).query_metrics(metric_name="cpu_usage", service="payments")

    assert result["available"] is True
    assert result["query_backend"] == "signoz_metrics_api"
    assert result["resolved_metric"] == "system_cpu_usage"
    assert result["metrics"][0]["service_name"] == "payments"
    assert captured["url"].endswith("/api/v5/query_range")
    headers = captured["kwargs"]["headers"]
    assert headers["SigNoz-Api-Key"] == "test-key"


def test_query_metrics_handles_empty_aggregation_series(monkeypatch) -> None:
    def _fake_post(_url: str, **_kwargs: Any) -> _FakeHTTPResponse:
        return _FakeHTTPResponse(
            {
                "status": "success",
                "data": {
                    "type": "time_series",
                    "data": {
                        "results": [
                            {
                                "queryName": "A",
                                "aggregations": None,
                            }
                        ]
                    },
                },
            }
        )

    monkeypatch.setattr("app.services.signoz.client.httpx.post", _fake_post)

    config = SigNozConfig(url="http://localhost:3301", api_key="test-key")
    result = SigNozClient(config).query_metrics(metric_name="cpu_usage")

    assert result["available"] is True
    assert result["total"] == 0


def test_query_metrics_handles_not_found_via_metrics_api(monkeypatch) -> None:
    def _fake_post(_url: str, **_kwargs: Any) -> _ErrorHTTPResponse:
        return _ErrorHTTPResponse(
            404,
            {"status": "error", "error": {"message": "could not find metric"}},
        )

    monkeypatch.setattr("app.services.signoz.client.httpx.post", _fake_post)

    config = SigNozConfig(url="http://localhost:3301", api_key="test-key")
    result = SigNozClient(config).query_metrics(metric_name="cpu_usage")

    assert result["available"] is True
    assert result["total"] == 0
    assert "warning" in result

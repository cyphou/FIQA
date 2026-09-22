"""Read-only live collection through Power BI Scanner and Fabric REST APIs."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from fabric_iq.collectors.base import BronzeRecord, CollectionResult, Collector, empty_inventory
from fabric_iq.errors import CollectionError, ConfigurationError, ThrottlingError

MAX_WORKSPACES_PER_SCAN = 100
MAX_CONCURRENT_SCANS = 16
MAX_GETINFO_CALLS_PER_HOUR = 500
MAX_MODIFIED_SINCE_DAYS = 30
ACTIVITY_RETENTION_DAYS = 28
MAX_ACTIVITY_CALLS_PER_HOUR = 200

# /admin/groups rejects a request without $top and never returns @odata.nextLink,
# so it has to be paged explicitly with $skip.
MAX_GROUPS_PER_PAGE = 5000
MAX_GROUP_PAGES = 40

# workspaces/getInfo is asynchronous: it returns a scan id that has to be polled.
SCAN_POLL_ATTEMPTS = 60
SCAN_POLL_SECONDS = 2.0

SCANNER_OPTIONS = {
    "lineage": True,
    "datasourceDetails": True,
    "datasetSchema": True,
    "datasetExpressions": True,
    "getArtifactUsers": False,
}
READ_ONLY_SCANNER_POSTS = frozenset({"workspaces/getInfo"})

# Scanner access-right values, mapped onto the role vocabulary the rules expect.
WORKSPACE_ROLE_KEYS = ("groupUserAccessRight", "workspaceUserAccessRight", "role", "accessRight")

# Scanner keys that carry Fabric items alongside the classic Power BI artefacts.
DATA_AGENT_KEYS = ("DataAgent", "dataAgents", "dataAgent")
SEMANTIC_MODEL_KEYS = ("datasets", "semanticModels")
REPORT_KEYS = ("reports",)

# Every container the Scanner may return for a workspace. Fabric item types come
# back in singular PascalCase, Power BI artefacts in plural camelCase, and empty
# containers are omitted entirely.
WORKSPACE_ITEM_KEYS = (
    "reports",
    "datasets",
    "dashboards",
    "dataflows",
    "datamarts",
    "DataAgent",
    "Ontology",
    "Lakehouse",
    "Notebook",
    "GraphModel",
    "KQLDatabase",
    "Eventhouse",
    "SQLAnalyticsEndpoint",
)

# Real tenant setting names, in fallback order. A setting that is absent stays
# None so the scoring engine records NOT_EVALUATED rather than a false failure.
TENANT_SETTING_MAP = {
    "fabric_enabled": ("FabricGAWorkloads", "FabricEnabled"),
    "copilot_enabled": ("EnableAOAI", "CopilotEnabled"),
    "agents_enabled": ("OntologyPreview", "AgentsEnabled"),
    "scanner_enabled": ("AllowServicePrincipalsUseReadAdminAPIs",),
    "sensitivity_labels_enabled": ("EimInformationProtectionEdit", "InformationProtection"),
    "cross_geo_ai_consent": ("AllowUserDataProcessedByAiServicesOutOfGeo",),
}


@dataclass(frozen=True)
class HttpResponse:
    """A parsed HTTP response with the evidence needed for a Bronze record."""

    payload: Any
    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    duration_ms: int = 0


TokenProvider = Callable[[], str]
Transport = Callable[[str, str, dict[str, Any] | None], HttpResponse | Any]


class FabricHttpTransport:
    """Stdlib HTTP transport that obtains a bearer token only at request time."""

    def __init__(
        self,
        token_provider: TokenProvider,
        *,
        timeout_seconds: float = 30,
        max_retries: int = 5,
        max_backoff_seconds: float = 60,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout_seconds <= 0 or max_retries < 0 or max_backoff_seconds <= 0:
            raise ConfigurationError("transport timeout, retries, and backoff must be positive")
        self._token_provider = token_provider
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._max_backoff_seconds = max_backoff_seconds
        self._sleep = sleep

    def __call__(self, method: str, url: str, body: dict[str, Any] | None = None) -> HttpResponse:
        self._validate_request(method, url, body)
        for attempt in range(self._max_retries + 1):
            response = self._send(method, url, body)
            if response.status_code != 429:
                return response
            retry_after = self._retry_after(response.headers.get("Retry-After"))
            if attempt == self._max_retries:
                hint = f" Retry-After={retry_after:g}s." if retry_after is not None else ""
                raise ThrottlingError(f"request throttled after {attempt + 1} attempt(s): {url}.{hint}")
            delay = retry_after if retry_after is not None else min(
                self._max_backoff_seconds, 2**attempt
            )
            self._sleep(min(delay, self._max_backoff_seconds))
        raise AssertionError("unreachable")

    @staticmethod
    def _validate_request(method: str, url: str, body: dict[str, Any] | None) -> None:
        if method not in {"GET", "POST"}:
            raise CollectionError(f"read-only transport rejects {method}")
        if method == "POST":
            path = urlsplit(url).path.rstrip("/")
            if body is None or not any(path.endswith(allowed) for allowed in READ_ONLY_SCANNER_POSTS):
                raise CollectionError(f"read-only transport rejects POST endpoint: {url}")
        elif body is not None:
            raise CollectionError("GET requests cannot include a body")

    def _send(self, method: str, url: str, body: dict[str, Any] | None) -> HttpResponse:
        token = ""
        try:
            token = self._token_provider()
            if not token:
                raise ConfigurationError("bearer token provider returned no token")
            encoded = json.dumps(body).encode("utf-8") if body is not None else None
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            if encoded is not None:
                headers["Content-Type"] = "application/json"
            request = Request(url, data=encoded, headers=headers, method=method)
            started = time.monotonic()
            with urlopen(request, timeout=self._timeout_seconds) as response:
                return self._response(response.read(), response.status, response.headers, started)
        except HTTPError as exc:
            return self._response(exc.read(), exc.code, exc.headers, started)
        except URLError as exc:
            raise CollectionError(f"HTTP request failed for {url}: {exc.reason}") from exc
        finally:
            del token

    @staticmethod
    def _response(body: bytes, status: int, headers: Any, started: float) -> HttpResponse:
        try:
            payload = json.loads(body.decode("utf-8")) if body else None
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CollectionError(f"HTTP response was not valid JSON: {exc}") from exc
        return HttpResponse(
            payload=payload,
            status_code=status,
            headers={key: value for key, value in headers.items()},
            duration_ms=round((time.monotonic() - started) * 1000),
        )

    @staticmethod
    def _retry_after(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return max(0, float(value))
        except ValueError:
            try:
                return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError):
                return None


@dataclass
class FabricApiConfig:
    """Connection settings; authentication is injected separately."""

    tenant_id: str
    scanner_base_url: str = "https://api.powerbi.com/v1.0/myorg/admin"
    fabric_base_url: str = "https://api.fabric.microsoft.com/v1"
    # Validated (see `validate`) but deliberately not yet wired into a
    # `modifiedSince` query. A true incremental scan would have to merge a new
    # partial payload into a previously persisted *full* inventory, and this
    # collector has no such store today -- only a per-call Bronze cache keyed
    # by request, not a merged Silver/Gold snapshot. Building that merge now
    # would risk presenting stale or partially-overwritten evidence as current,
    # which conflicts with "never invent evidence". Documented in
    # docs/KNOWN_LIMITATIONS.md as an intentionally deferred scope decision,
    # not an oversight; every `collect()` call remains a full, honest scan.
    modified_since_days: int = 7
    include_artifact_users: bool = True
    workspace_allowlist: list[str] = field(default_factory=list)
    checkpoint_path: str | None = None

    def validate(self) -> "FabricApiConfig":
        if not self.tenant_id:
            raise ConfigurationError("tenant_id is required")
        if not 1 <= self.modified_since_days <= MAX_MODIFIED_SINCE_DAYS:
            raise ConfigurationError(
                f"modified_since_days must be between 1 and {MAX_MODIFIED_SINCE_DAYS}"
            )
        return self


class FabricApiCollector(Collector):
    """Collect a paged, read-only Scanner inventory with resumable checkpoints."""

    mode = "live"

    def __init__(
        self,
        config: FabricApiConfig,
        transport: Transport,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config.validate()
        self.transport = transport
        self.sleep = sleep
        self.clock = clock
        self._completed: dict[str, Any] = {}
        self._checkpoint_bronze: dict[str, BronzeRecord] = {}
        # Wall-clock times (seconds, via `clock`) of getInfo calls made by *this*
        # instance, used to self-throttle proactively rather than only reacting
        # to a 429. A fresh run per process is a deliberately conservative
        # approximation: it cannot see calls made by a previous, separate
        # process, so it never risks under-counting the tenant's real budget.
        self._getinfo_call_times: list[float] = []

    def collect(self) -> CollectionResult:
        self._load_checkpoint()
        result = CollectionResult(
            inventory=empty_inventory(self.config.tenant_id),
            bronze=list(self._checkpoint_bronze.values()),
            mode=self.mode,
        )
        settings = self._request(result, "tenant-settings", "GET", f"{self.config.fabric_base_url}/admin/tenantsettings")
        if settings is not None:
            result.inventory["tenant"] = self.normalize_tenant(self.config.tenant_id, settings)

        groups = self._get_groups(result)
        capacities = self._get_capacities(result)
        workspace_ids = [
            item.get("id") or item.get("workspaceId")
            for item in groups
            if isinstance(item, dict) and (item.get("id") or item.get("workspaceId"))
        ]
        if self.config.workspace_allowlist:
            allowed = set(self.config.workspace_allowlist)
            workspace_ids = [workspace_id for workspace_id in workspace_ids if workspace_id in allowed]

        scans: list[dict[str, Any]] = []
        for index in range(0, len(workspace_ids), MAX_WORKSPACES_PER_SCAN):
            ids = workspace_ids[index : index + MAX_WORKSPACES_PER_SCAN]
            scans.extend(self._scan_batch(result, index // MAX_WORKSPACES_PER_SCAN, ids))

        if result.inventory.get("tenant"):
            result.inventory["tenant"].update(
                {
                    "capacities": [self.normalize_capacity(c) for c in capacities.values()],
                    "workspaces_total": len(workspace_ids),
                    "workspaces_scanned": len(scans),
                }
            )

        result.inventory["workspaces"] = [self.normalize_workspace(item, capacities) for item in scans]
        result.inventory["semantic_models"] = self._artifacts(scans, SEMANTIC_MODEL_KEYS, "semantic_model")
        result.inventory["reports"] = self._artifacts(scans, REPORT_KEYS, "report")
        result.inventory["data_agents"] = self._artifacts(scans, DATA_AGENT_KEYS, "data_agent")
        self._link_reports(result.inventory)
        return result.validate()

    @staticmethod
    def _link_reports(inventory: dict[str, Any]) -> None:
        """Resolve report -> semantic model reachability from the collected estate."""
        known = {model["id"] for model in inventory["semantic_models"] if model.get("id")}
        for report in inventory["reports"]:
            model_id = report.get("semantic_model_id")
            if model_id:
                report["semantic_model_reachable"] = model_id in known

    def _get_groups(self, result: CollectionResult) -> list[dict[str, Any]]:
        """Page /admin/groups with $top and $skip; the endpoint has no nextLink."""
        items: list[dict[str, Any]] = []
        for page in range(MAX_GROUP_PAGES):
            skip = page * MAX_GROUPS_PER_PAGE
            url = f"{self.config.scanner_base_url}/groups?$top={MAX_GROUPS_PER_PAGE}&$skip={skip}"
            payload = self._request(result, f"groups-{page}", "GET", url)
            if payload is None:
                break
            batch = self._items(payload)
            items.extend(batch)
            if len(batch) < MAX_GROUPS_PER_PAGE:
                break
        return items

    def _get_capacities(self, result: CollectionResult) -> dict[str, dict[str, Any]]:
        """Resolve capacity SKU, state and region; the Scanner only returns capacityId."""
        payload = self._request(
            result, "capacities", "GET", f"{self.config.scanner_base_url}/capacities"
        )
        if payload is None:
            return {}
        return {
            capacity["id"]: capacity
            for capacity in self._items(payload)
            if isinstance(capacity.get("id"), str)
        }

    def _throttle_getinfo_quota(self, key: str) -> None:
        """Self-limit getInfo calls to the documented hourly quota, proactively.

        A checkpointed key never reaches the network, so it must not consume
        quota or trigger a wait; only a call this instance is about to *make*
        counts. This keeps a 500-workspace scan (5 getInfo calls) well under
        the ceiling while still protecting a very large tenant from tripping
        the Admin API's real per-hour limit before the server ever has to
        return a 429.
        """
        if key in self._completed:
            return
        now = self.clock()
        window_start = now - 3600
        self._getinfo_call_times = [when for when in self._getinfo_call_times if when > window_start]
        if len(self._getinfo_call_times) >= MAX_GETINFO_CALLS_PER_HOUR:
            wait = self._getinfo_call_times[0] + 3600 - now
            if wait > 0:
                self.sleep(wait)
            now = self.clock()
            window_start = now - 3600
            self._getinfo_call_times = [when for when in self._getinfo_call_times if when > window_start]
        self._getinfo_call_times.append(now)

    def _scan_batch(
        self, result: CollectionResult, batch_index: int, workspace_ids: list[str]
    ) -> list[dict[str, Any]]:
        """Run one asynchronous Scanner cycle: getInfo, poll scanStatus, read scanResult."""
        options = dict(SCANNER_OPTIONS)
        options["getArtifactUsers"] = self.config.include_artifact_users
        query = "&".join(f"{name}={str(value)}" for name, value in options.items())
        get_info_key = f"get-info-{batch_index}"
        self._throttle_getinfo_quota(get_info_key)
        started = self._request(
            result,
            get_info_key,
            "POST",
            f"{self.config.scanner_base_url}/workspaces/getInfo?{query}",
            {"workspaces": workspace_ids},
        )
        scan_id = started.get("id") if isinstance(started, dict) else None
        if not scan_id:
            self.record_error(
                result,
                f"{self.config.scanner_base_url}/workspaces/getInfo",
                "scan did not return an id",
            )
            return []

        for attempt in range(SCAN_POLL_ATTEMPTS):
            status_payload = self._request(
                result,
                f"scan-status-{batch_index}-{attempt}",
                "GET",
                f"{self.config.scanner_base_url}/workspaces/scanStatus/{scan_id}",
            )
            status = status_payload.get("status") if isinstance(status_payload, dict) else None
            if status == "Succeeded":
                break
            if status in {"Failed", "Cancelled"}:
                self.record_error(result, f"scanStatus/{scan_id}", f"scan ended with status {status}")
                return []
            if status is None:
                return []
            self.sleep(SCAN_POLL_SECONDS)
        else:
            self.record_error(result, f"scanStatus/{scan_id}", "scan did not complete in time")
            return []

        scan_result = self._request(
            result,
            f"scan-result-{batch_index}",
            "GET",
            f"{self.config.scanner_base_url}/workspaces/scanResult/{scan_id}",
        )
        return self._items(scan_result, "workspaces") if scan_result is not None else []

    def _request(
        self, result: CollectionResult, key: str, method: str, url: str, body: dict[str, Any] | None = None
    ) -> Any:
        if key in self._completed:
            return self._completed[key]
        try:
            raw_response = self.transport(method, url, body)
            response = raw_response if isinstance(raw_response, HttpResponse) else HttpResponse(raw_response, 200)
            record = BronzeRecord(
                endpoint=url,
                status_code=response.status_code,
                duration_ms=response.duration_ms,
                correlation_id=response.headers.get("x-ms-request-id", response.headers.get("requestid", "")),
                identity="bearer_token",
                payload=response.payload,
            )
            result.bronze.append(record)
            self._checkpoint_bronze[key] = record
            if response.status_code >= 400:
                raise CollectionError(f"HTTP {response.status_code} from {url}")
            self._completed[key] = response.payload
            self._save_checkpoint()
            return response.payload
        except ThrottlingError:
            self._save_checkpoint()
            raise
        except CollectionError as exc:
            self.record_error(result, url, str(exc))
            self._save_checkpoint()
            return None

    @staticmethod
    def _items(payload: Any, preferred_key: str | None = None) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            keys = ((preferred_key,) if preferred_key else ()) + ("value", "workspaces", "data")
            for key in keys:
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
                # The Scanner returns a lone Fabric item as an object, not a list.
                if isinstance(value, dict):
                    return [value]
        return []

    def _load_checkpoint(self) -> None:
        if not self.config.checkpoint_path or not os.path.exists(self.config.checkpoint_path):
            return
        try:
            with open(self.config.checkpoint_path, encoding="utf-8") as handle:
                checkpoint = json.load(handle)
            if checkpoint.get("tenant_id") != self.config.tenant_id:
                raise CollectionError("checkpoint tenant does not match the configured tenant")
            self._completed = checkpoint.get("completed") or {}
            for key, record in (checkpoint.get("bronze") or {}).items():
                self._checkpoint_bronze[key] = BronzeRecord(
                    **{name: value for name, value in record.items() if name != "content_hash"}
                )
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise CollectionError(f"cannot read collection checkpoint: {exc}") from exc

    def _save_checkpoint(self) -> None:
        if not self.config.checkpoint_path:
            return
        directory = os.path.dirname(os.path.abspath(self.config.checkpoint_path))
        try:
            os.makedirs(directory, exist_ok=True)
            temporary = f"{self.config.checkpoint_path}.tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "tenant_id": self.config.tenant_id,
                        "completed": self._completed,
                        "bronze": {key: record.to_dict() for key, record in self._checkpoint_bronze.items()},
                    },
                    handle,
                    sort_keys=True,
                )
            os.replace(temporary, self.config.checkpoint_path)
        except OSError as exc:
            raise CollectionError(f"cannot write collection checkpoint: {exc}") from exc

    @staticmethod
    def _artifacts(
        workspaces: list[dict[str, Any]], keys: tuple[str, ...], object_type: str
    ) -> list[dict[str, Any]]:
        normalizer = {
            "semantic_model": FabricApiCollector.normalize_semantic_model,
            "report": FabricApiCollector.normalize_report,
            "data_agent": FabricApiCollector.normalize_data_agent,
        }[object_type]
        artifacts = []
        for workspace in workspaces:
            parent_id = workspace.get("id", workspace.get("workspaceId", ""))
            for key in keys:
                for artifact in FabricApiCollector._items({key: workspace.get(key)}, key):
                    artifacts.append(normalizer(artifact, parent_id))
        return artifacts

    @staticmethod
    def _identity(raw: dict[str, Any], parent_id: str, object_type: str) -> dict[str, Any]:
        return {
            "id": raw.get("id", raw.get("objectId", "")),
            "name": raw.get("name", raw.get("displayName", "")),
            "parent_id": parent_id,
            "object_type": object_type,
            "description": raw.get("description"),
        }

    @staticmethod
    def _flatten(tables: list[dict[str, Any]], key: str, mapper: Callable[[dict[str, Any], str], dict[str, Any]]) -> list[dict[str, Any]]:
        """Lift table-scoped children to the flat, model-level lists the rules read."""
        flattened = []
        for table in tables:
            table_name = table.get("name", "")
            for child in table.get(key) or []:
                if isinstance(child, dict):
                    flattened.append(mapper(child, table_name))
        return flattened

    @staticmethod
    def normalize_semantic_model(raw: dict[str, Any], parent_id: str) -> dict[str, Any]:
        """Map a Scanner dataset onto the canonical model shape.

        Anything the Scanner cannot observe stays ``None`` so the scoring engine
        records NOT_EVALUATED instead of inventing a pass. In particular the
        Scanner's ``relations`` key carries artefact lineage, not model
        relationships, so it is deliberately not mapped.
        """
        normalized = FabricApiCollector._identity(raw, parent_id, "semantic_model")
        tables_raw = raw.get("tables")
        schema_available = isinstance(tables_raw, list)
        tables = tables_raw if schema_available else []

        normalized["tables"] = (
            [
                {
                    "name": table.get("name", ""),
                    "description": table.get("description"),
                    "hidden": table.get("isHidden"),
                    "storage_mode": table.get("storageMode"),
                    "role": None,
                    "is_date_table": None,
                }
                for table in tables
            ]
            if schema_available
            else None
        )
        normalized["columns"] = (
            FabricApiCollector._flatten(
                tables,
                "columns",
                lambda column, table_name: {
                    "name": column.get("name", ""),
                    "table": table_name,
                    "description": column.get("description"),
                    "data_type": column.get("dataType"),
                    "hidden": column.get("isHidden"),
                    "column_type": column.get("columnType"),
                    "semantic_role": None,
                    "summarize_by": None,
                    "synonyms": None,
                },
            )
            if schema_available
            else None
        )
        normalized["measures"] = (
            FabricApiCollector._flatten(
                tables,
                "measures",
                lambda measure, table_name: {
                    "name": measure.get("name", ""),
                    "table": table_name,
                    "description": measure.get("description"),
                    "expression": measure.get("expression"),
                    "hidden": measure.get("isHidden"),
                    "synonyms": None,
                },
            )
            if schema_available
            else None
        )
        normalized["schema_retrieval_error"] = (
            "" if schema_available else "dataset schema not returned by the scanner"
        )

        roles = raw.get("roles")
        normalized["rls_required"] = raw.get("isEffectiveIdentityRequired")
        normalized["rls_roles"] = (
            [{"name": role.get("name", ""), "tested": None} for role in roles if isinstance(role, dict)]
            if isinstance(roles, list)
            else None
        )
        normalized["target_storage_mode"] = raw.get("targetStorageMode")
        normalized["owner"] = raw.get("configuredBy")

        # Out of scope for the Scanner: model relationships, Prep-for-AI metadata
        # and refresh history all require XMLA or the refresh APIs.
        for unavailable in (
            "relationships",
            "has_time_intelligence",
            "ai_data_schema",
            "ai_instructions",
            "verified_answers",
            "hours_since_refresh",
            "freshness_sla_hours",
        ):
            normalized[unavailable] = None
        return normalized

    @staticmethod
    def normalize_report(raw: dict[str, Any], parent_id: str) -> dict[str, Any]:
        """Map a Scanner report. Visual-level metadata needs the report definition API."""
        normalized = FabricApiCollector._identity(raw, parent_id, "report")
        normalized["semantic_model_id"] = raw.get("datasetId")
        normalized["report_type"] = raw.get("reportType")
        normalized["owner"] = raw.get("createdBy") or raw.get("modifiedBy")
        normalized["modified_at"] = raw.get("modifiedDateTime")
        for unavailable in (
            "semantic_model_reachable",
            "semantic_model_score",
            "visual_count",
            "broken_visuals",
            "untitled_visuals",
            "report_level_measures",
            "hidden_filters",
            "visuals_with_alt_text",
            "audience",
            "monthly_views",
            "verified_answer_candidates",
        ):
            normalized[unavailable] = None
        return normalized

    @staticmethod
    def normalize_data_agent(raw: dict[str, Any], parent_id: str) -> dict[str, Any]:
        """Map a Scanner data agent.

        The Scanner exposes the agent item but never its sources, instructions or
        evaluation results, so every behavioural field stays unobserved.
        """
        normalized = FabricApiCollector._identity(raw, parent_id, "data_agent")
        normalized["owner"] = raw.get("createdBy") or raw.get("modifiedBy")
        normalized["state"] = raw.get("state")
        normalized["modified_at"] = raw.get("lastUpdatedDate")
        for unavailable in (
            "data_sources",
            "source_scores",
            "instructions",
            "evaluation",
            "target_languages",
            "requires_write",
            "expects_bulk_export",
            "latency_sla_seconds",
            "preview_dependencies",
        ):
            normalized[unavailable] = None
        return normalized

    @staticmethod
    def normalize_tenant(tenant_id: str, settings: Any) -> dict[str, Any]:
        flags = {}
        for setting in FabricApiCollector._items(settings, "tenantSettings"):
            name = setting.get("settingName") or setting.get("name")
            if name:
                flags[name] = setting.get("enabled")
        normalized: dict[str, Any] = {"id": tenant_id, "name": tenant_id}
        for field_name, candidates in TENANT_SETTING_MAP.items():
            normalized[field_name] = next(
                (flags[name] for name in candidates if name in flags), None
            )
        return normalized

    @staticmethod
    def normalize_capacity(raw: dict[str, Any]) -> dict[str, Any]:
        """Project an /admin/capacities entry onto the tenant rule contract."""
        return {
            "id": raw.get("id"),
            "name": raw.get("displayName") or raw.get("name") or raw.get("id"),
            "sku": raw.get("sku"),
            "state": raw.get("state"),
            "region": raw.get("region"),
        }

    @staticmethod
    def normalize_workspace(
        raw: dict[str, Any], capacities: dict[str, dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        normalized = dict(raw)
        normalized.setdefault("id", raw.get("workspaceId", raw.get("objectId", "")))
        normalized.setdefault("name", raw.get("displayName", ""))
        normalized.setdefault(
            "items_total",
            sum(len(FabricApiCollector._items({key: raw.get(key)}, key)) for key in WORKSPACE_ITEM_KEYS),
        )
        capacity_id = raw.get("capacityId")
        capacity = (capacities or {}).get(capacity_id or "", {})
        if capacity_id:
            normalized["capacity_sku"] = capacity.get("sku")
            normalized["capacity_state"] = capacity.get("state")
        elif raw.get("isOnDedicatedCapacity") is False:
            # Proven absence of a capacity, not missing evidence.
            normalized["capacity_sku"] = ""
            normalized["capacity_state"] = None
        else:
            normalized["capacity_sku"] = None
            normalized["capacity_state"] = None
        normalized["region"] = capacity.get("region")
        normalized["role_assignments"] = FabricApiCollector._role_assignments(raw)
        return normalized

    @staticmethod
    def _role_assignments(raw: dict[str, Any]) -> list[dict[str, Any]] | None:
        """Project Scanner workspace users onto the role contract the rules read.

        Returns None when the Scanner returned no user container at all: that is an
        unobserved permission surface, not a workspace without assignments. An empty
        list is kept as an empty list, because that is a genuine observation.
        """
        users = raw.get("users")
        if users is None:
            return None
        if not isinstance(users, list):
            return None
        assignments: list[dict[str, Any]] = []
        for user in users:
            if not isinstance(user, dict):
                continue
            role = next((user[key] for key in WORKSPACE_ROLE_KEYS if user.get(key)), None)
            principal = (
                user.get("displayName")
                or user.get("emailAddress")
                or user.get("identifier")
                or user.get("graphId")
            )
            assignments.append(
                {
                    "role": role,
                    "principal": principal,
                    "principal_type": user.get("principalType"),
                }
            )
        return assignments

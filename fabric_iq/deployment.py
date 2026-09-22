"""Package the assessor as a deployable Fabric solution.

This module builds the item definitions under ``fabric/items`` into the payloads the
Fabric REST API expects, and drives the calls that create them.

Scope note: everything here writes into *our own* delivery workspace — a Lakehouse, a
Notebook and a Data Pipeline that we own. The read-only contract of this project covers
the *assessed* tenant, whose objects are never modified.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .errors import ConfigurationError, DeploymentError
from .powerbi import (
    build_definition_pbir_live,
    build_definition_pbism,
    build_model_bim_directlake,
    build_report_json,
)

FABRIC_API = "https://api.fabric.microsoft.com/v1"
ONELAKE_DFS = "https://onelake.dfs.fabric.microsoft.com"

LAKEHOUSE_ITEM = "FabricIQReadiness.Lakehouse"
NOTEBOOK_ITEM = "Fabric_IQ_Readiness_Assessment.Notebook"
PIPELINE_ITEM = "Fabric_IQ_Readiness_Orchestration.DataPipeline"
SEMANTIC_MODEL_ITEM = "IsFabricReadyForIQ.SemanticModel"
REPORT_ITEM = "IsFabricReadyForIQ.Report"

NOTEBOOK_SOURCE = "notebook-content.py"
PIPELINE_SOURCE = "pipeline-content.json"
PLATFORM_SOURCE = ".platform"
MODEL_BIM_SOURCE = "model.bim"
PBISM_SOURCE = "definition.pbism"
REPORT_JSON_SOURCE = "report.json"
PBIR_SOURCE = "definition.pbir"

#: Where deploy.py drops the package so the notebook can import it.
LIBRARY_PREFIX = "Files/lib"

#: Default schema the Lakehouse's SQL analytics endpoint exposes Delta tables under.
DIRECTLAKE_SCHEMA = "dbo"

MAX_LRO_SECONDS = 600
LRO_POLL_SECONDS = 5

#: Transient network resets (observed as WinError 10054 / connection-reset on
#: OneLake and Fabric REST calls) are retried a handful of times with a short
#: backoff before the call is reported as a failure.
NETWORK_RETRY_ATTEMPTS = 4
NETWORK_RETRY_BACKOFF_SECONDS = 3

#: How long to wait for the Lakehouse's SQL analytics endpoint to finish
#: provisioning before giving up. It is created asynchronously right after the
#: Lakehouse item itself, so it is routinely "Provisioning" for a few seconds.
MAX_SQL_ENDPOINT_SECONDS = 300
SQL_ENDPOINT_POLL_SECONDS = 5

_META_PREFIX = "# META"
_METADATA_MARKER = "# METADATA"


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class DeploymentConfig:
    """Where the solution goes and what it is called once it lands."""

    workspace_id: str
    lakehouse_name: str = "FabricIQReadiness"
    notebook_name: str = "Fabric_IQ_Readiness_Assessment"
    pipeline_name: str = "Fabric_IQ_Readiness_Orchestration"
    semantic_model_name: str = "IsFabricReadyForIQ"
    report_name: str = "IsFabricReadyForIQ"
    default_tenant_id: str = ""
    items_root: str = field(default_factory=lambda: os.path.join(_repo_root(), "fabric", "items"))
    package_root: str = field(default_factory=lambda: os.path.join(_repo_root(), "fabric_iq"))
    directlake_schema: str = DIRECTLAKE_SCHEMA

    def validate(self) -> "DeploymentConfig":
        if not self.workspace_id:
            raise ConfigurationError("workspace_id is required")
        names = (
            self.lakehouse_name,
            self.notebook_name,
            self.pipeline_name,
            self.semantic_model_name,
            self.report_name,
        )
        for name in names:
            if not name:
                raise ConfigurationError("item display names cannot be empty")
        if not os.path.isdir(self.items_root):
            raise ConfigurationError(f"items_root does not exist: {self.items_root}")
        if not os.path.isdir(self.package_root):
            raise ConfigurationError(f"package_root does not exist: {self.package_root}")
        return self


# --------------------------------------------------------------------------- payloads


def inline_part(path: str, text: str) -> dict[str, str]:
    """Wrap one file as an InlineBase64 definition part."""
    return {
        "path": path,
        "payload": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "payloadType": "InlineBase64",
    }


def read_item_file(items_root: str, item: str, filename: str) -> str:
    path = os.path.join(items_root, item, filename)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise DeploymentError(f"cannot read {path}: {exc}") from exc


def _header_bounds(lines: list[str]) -> tuple[int, int]:
    """Return the [start, end) slice holding the notebook's leading META block."""
    start = -1
    for index, line in enumerate(lines):
        if line.startswith(_METADATA_MARKER):
            start = index + 1
            break
    if start == -1:
        raise DeploymentError("notebook source has no METADATA block")
    end = start
    while end < len(lines) and not lines[end].strip():
        end += 1
    start = end
    while end < len(lines) and lines[end].startswith(_META_PREFIX):
        end += 1
    if end == start:
        raise DeploymentError("notebook METADATA block is empty")
    return start, end


def _decode_meta(lines: Iterable[str]) -> dict[str, Any]:
    body = "\n".join(line[len(_META_PREFIX) :].lstrip(" ") for line in lines)
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise DeploymentError(f"notebook METADATA block is not valid JSON: {exc}") from exc


def _encode_meta(meta: dict[str, Any]) -> list[str]:
    return [f"{_META_PREFIX} {line}".rstrip() for line in json.dumps(meta, indent=2).splitlines()]


def build_notebook_content(
    source: str,
    *,
    workspace_id: str,
    lakehouse_id: str,
    lakehouse_name: str,
    default_tenant_id: str = "",
) -> str:
    """Bind the notebook to its Lakehouse and, optionally, to a default tenant.

    Without the ``dependencies.lakehouse`` binding the notebook has no
    ``/lakehouse/default`` mount, so every path in it would fail at runtime.
    """
    lines = source.splitlines()
    start, end = _header_bounds(lines)
    meta = _decode_meta(lines[start:end])
    dependencies = meta.setdefault("dependencies", {})
    dependencies["lakehouse"] = {
        "default_lakehouse": lakehouse_id,
        "default_lakehouse_name": lakehouse_name,
        "default_lakehouse_workspace_id": workspace_id,
    }
    rebuilt = lines[:start] + _encode_meta(meta) + lines[end:]
    content = "\n".join(rebuilt) + "\n"

    if default_tenant_id:
        placeholder = 'tenant_id = ""'
        if placeholder not in content:
            raise DeploymentError("notebook parameters cell no longer declares tenant_id")
        content = content.replace(placeholder, f'tenant_id = "{default_tenant_id}"', 1)
    return content


def build_pipeline_content(
    source: str,
    *,
    workspace_id: str,
    notebook_id: str,
    default_tenant_id: str = "",
) -> str:
    """Point the pipeline's notebook activity at the notebook we just created."""
    try:
        document = json.loads(source)
    except json.JSONDecodeError as exc:
        raise DeploymentError(f"pipeline definition is not valid JSON: {exc}") from exc

    properties = document.get("properties") or {}
    activities = properties.get("activities") or []
    bound = 0
    for activity in activities:
        if not isinstance(activity, dict) or activity.get("type") != "TridentNotebook":
            continue
        type_properties = activity.setdefault("typeProperties", {})
        type_properties["notebookId"] = notebook_id
        type_properties["workspaceId"] = workspace_id
        bound += 1
    if bound == 0:
        raise DeploymentError("pipeline definition has no TridentNotebook activity to bind")

    if default_tenant_id:
        parameters = properties.get("parameters") or {}
        tenant = parameters.get("tenant_id")
        if isinstance(tenant, dict):
            tenant["defaultValue"] = default_tenant_id
    return json.dumps(document, indent=2) + "\n"


def library_files(package_root: str) -> list[tuple[str, bytes]]:
    """Every module the notebook needs, as (relative posix path, bytes).

    The assessor is stdlib-only, so shipping the sources is enough — no wheel, no
    ``%pip install``, no dependency resolution inside the Fabric runtime.
    """
    package = os.path.basename(os.path.normpath(package_root))
    collected: list[tuple[str, bytes]] = []
    for directory, dirnames, filenames in os.walk(package_root):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            absolute = os.path.join(directory, filename)
            relative = os.path.relpath(absolute, package_root).replace(os.sep, "/")
            try:
                with open(absolute, "rb") as handle:
                    collected.append((f"{package}/{relative}", handle.read()))
            except OSError as exc:
                raise DeploymentError(f"cannot read {absolute}: {exc}") from exc
    if not collected:
        raise DeploymentError(f"no modules found under {package_root}")
    return collected


def get_lakehouse_sql_endpoint(
    client: FabricRestClient,
    workspace_id: str,
    lakehouse_id: str,
    *,
    max_seconds: int = MAX_SQL_ENDPOINT_SECONDS,
    poll_seconds: float = SQL_ENDPOINT_POLL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, str]:
    """Poll the Lakehouse until its SQL analytics endpoint is ready.

    The endpoint is provisioned asynchronously right after the Lakehouse item
    itself, so it is routinely reported as ``"Provisioning"`` for the first
    few seconds. Returns ``(connection_string, sql_endpoint_id)`` -- the two
    values :func:`fabric_iq.powerbi.build_model_bim_directlake` needs to build
    the model's ``Sql.Database(...)`` expression.
    """
    deadline = time.monotonic() + max_seconds
    while True:
        _, _, payload = client.request("GET", f"workspaces/{workspace_id}/lakehouses/{lakehouse_id}")
        properties = (payload or {}).get("properties") or {}
        endpoint = properties.get("sqlEndpointProperties") or {}
        status = (endpoint.get("provisioningStatus") or "").lower()
        connection_string = endpoint.get("connectionString")
        sql_endpoint_id = endpoint.get("id")
        if status == "success" and connection_string and sql_endpoint_id:
            return connection_string, sql_endpoint_id
        if status == "failed":
            raise DeploymentError(f"lakehouse SQL analytics endpoint provisioning failed: {endpoint}")
        if time.monotonic() >= deadline:
            raise DeploymentError(
                f"lakehouse SQL analytics endpoint did not become ready within {max_seconds}s "
                f"(last status: {status or 'unknown'})"
            )
        sleep(poll_seconds)


def build_semantic_model_parts(
    items_root: str,
    *,
    sql_endpoint_connection_string: str,
    sql_endpoint_id: str,
    schema_name: str = DIRECTLAKE_SCHEMA,
) -> list[dict[str, str]]:
    """Assemble the SemanticModel definition parts: ``model.bim`` + ``definition.pbism`` + ``.platform``.

    The model's tables are ``directLake`` partitions reading the Gold marts
    straight from the Lakehouse's Delta tables via its SQL analytics endpoint
    (see :func:`fabric_iq.powerbi.build_model_bim_directlake`) -- no seed
    CSVs, no OneLake upload, no manual data-source-credentials step.
    """
    model_bim = json.dumps(
        build_model_bim_directlake(sql_endpoint_connection_string, sql_endpoint_id, schema_name),
        indent=2,
    )
    pbism = json.dumps(build_definition_pbism(), indent=2)
    return [
        inline_part(MODEL_BIM_SOURCE, model_bim),
        inline_part(PBISM_SOURCE, pbism),
        inline_part(PLATFORM_SOURCE, read_item_file(items_root, SEMANTIC_MODEL_ITEM, PLATFORM_SOURCE)),
    ]


def build_report_parts(items_root: str, *, semantic_model_id: str) -> list[dict[str, str]]:
    """Assemble the Report definition parts: ``report.json`` + ``definition.pbir`` + ``.platform``.

    Uses :func:`fabric_iq.powerbi.build_definition_pbir_live` (``byConnection``),
    not the ``byPath`` form used by the local PBIP project -- the Fabric REST API
    requires ``byConnection`` for reports created/updated through the API.
    ``report.config.json`` is intentionally excluded: it's a Desktop/PBIP-local
    file, not a recognised API definition part.
    """
    report_json = json.dumps(build_report_json(), indent=2)
    pbir = json.dumps(build_definition_pbir_live(semantic_model_id), indent=2)
    return [
        inline_part(REPORT_JSON_SOURCE, report_json),
        inline_part(PBIR_SOURCE, pbir),
        inline_part(PLATFORM_SOURCE, read_item_file(items_root, REPORT_ITEM, PLATFORM_SOURCE)),
    ]


# ------------------------------------------------------------------------------ REST


class FabricRestClient:
    """Minimal stdlib REST client with long-running-operation support."""

    def __init__(
        self,
        token_provider: Callable[[], str],
        *,
        base_url: str = FABRIC_API,
        opener: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._token_provider = token_provider
        self._base_url = base_url.rstrip("/")
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleep

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | bytes | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], Any]:
        token = self._token_provider()
        if not token:
            raise DeploymentError("no bearer token available; check the token environment variable")

        url = path if path.startswith("http") else f"{self._base_url}/{path.lstrip('/')}"
        payload: bytes | None = None
        request_headers = {"Authorization": f"Bearer {token}"}
        if isinstance(body, bytes):
            payload = body
            request_headers["Content-Type"] = "application/octet-stream"
        elif body is not None:
            payload = json.dumps(body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})

        request = urllib.request.Request(url, data=payload, method=method, headers=request_headers)
        last_reason: Any = None
        for attempt in range(NETWORK_RETRY_ATTEMPTS):
            try:
                with self._opener(request) as response:
                    raw = response.read()
                    response_headers = {k.lower(): v for k, v in dict(response.headers).items()}
                    return response.status, response_headers, _maybe_json(raw)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                raise DeploymentError(f"{method} {url} failed with HTTP {exc.code}: {detail}") from exc
            except (urllib.error.URLError, ConnectionError, OSError) as exc:
                last_reason = getattr(exc, "reason", exc)
                if attempt == NETWORK_RETRY_ATTEMPTS - 1:
                    break
                self._sleep(NETWORK_RETRY_BACKOFF_SECONDS * (attempt + 1))
        raise DeploymentError(f"{method} {url} failed: {last_reason}")

    def wait_for_operation(self, headers: dict[str, str]) -> Any:
        """Poll a 202 Accepted operation until it settles, then return its result."""
        location = headers.get("location")
        if not location:
            raise DeploymentError("long-running operation did not return a Location header")
        deadline = time.monotonic() + MAX_LRO_SECONDS
        delay = max(float(headers.get("retry-after", LRO_POLL_SECONDS)), 1.0)
        while time.monotonic() < deadline:
            self._sleep(delay)
            status, operation_headers, payload = self.request("GET", location)
            state = (payload or {}).get("status", "").lower() if isinstance(payload, dict) else ""
            if status == 200 and state in {"succeeded", "completed"}:
                result_url = operation_headers.get("location") or f"{location}/result"
                try:
                    _, _, result = self.request("GET", result_url)
                except DeploymentError as exc:
                    # Some long-running operations (e.g. LRO-backed item updates)
                    # succeed without producing a fetchable result body; Fabric
                    # signals this with errorCode "OperationHasNoResult" on the
                    # /result endpoint. That is a successful no-op, not a failure.
                    if "OperationHasNoResult" in str(exc):
                        return None
                    raise
                return result
            if state == "failed":
                raise DeploymentError(f"operation failed: {json.dumps(payload)[:500]}")
            delay = max(float(operation_headers.get("retry-after", delay)), 1.0)
        raise DeploymentError(f"operation did not complete within {MAX_LRO_SECONDS}s")


def _maybe_json(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


# ------------------------------------------------------------------------- deployment


def find_item(client: FabricRestClient, workspace_id: str, item_type: str, name: str) -> str | None:
    """Return the id of an existing item so a redeploy updates instead of duplicating."""
    _, _, payload = client.request("GET", f"workspaces/{workspace_id}/items?type={item_type}")
    for item in (payload or {}).get("value") or []:
        if item.get("displayName") == name:
            return item.get("id")
    return None


def _create_item(
    client: FabricRestClient,
    workspace_id: str,
    body: dict[str, Any],
) -> str:
    status, headers, payload = client.request("POST", f"workspaces/{workspace_id}/items", body)
    if status == 202:
        payload = client.wait_for_operation(headers)
    item_id = (payload or {}).get("id") if isinstance(payload, dict) else None
    if not item_id:
        raise DeploymentError(f"item creation returned no id: {json.dumps(payload)[:300]}")
    return item_id


def upsert_item(
    client: FabricRestClient,
    workspace_id: str,
    *,
    item_type: str,
    display_name: str,
    description: str = "",
    parts: list[dict[str, str]] | None = None,
) -> tuple[str, str]:
    """Create the item, or replace its definition when it already exists.

    Returns ``(item_id, "created" | "updated")``.
    """
    existing = find_item(client, workspace_id, item_type, display_name)
    if existing and parts:
        status, headers, _ = client.request(
            "POST",
            f"workspaces/{workspace_id}/items/{existing}/updateDefinition?updateMetadata=True",
            {"definition": {"parts": parts}},
        )
        if status == 202:
            client.wait_for_operation(headers)
        return existing, "updated"
    if existing:
        return existing, "updated"

    body: dict[str, Any] = {"displayName": display_name, "type": item_type}
    if description:
        body["description"] = description
    if parts:
        body["definition"] = {"parts": parts}
    return _create_item(client, workspace_id, body), "created"


def upload_library(
    client: FabricRestClient,
    workspace_id: str,
    lakehouse_id: str,
    files: list[tuple[str, bytes]],
    *,
    prefix: str = LIBRARY_PREFIX,
) -> list[str]:
    """Push the package into OneLake so the notebook can import it from Files.

    Uses the DFS create/append/flush sequence; the client must hold a storage-scoped
    token (``https://storage.azure.com/.default``), not the Fabric API token.

    The OneLake path segment after the workspace GUID must itself be a GUID (the
    item's id) unless the tenant has friendly-name support enabled for OneLake --
    which is off by default (``FriendlyNameSupportDisabled``). Do not pass a
    display name here.
    """
    written: list[str] = []
    for relative, payload in files:
        path = f"{workspace_id}/{lakehouse_id}/{prefix}/{relative}"
        client.request("PUT", f"{ONELAKE_DFS}/{path}?resource=file")
        if payload:
            client.request("PATCH", f"{ONELAKE_DFS}/{path}?action=append&position=0", payload)
        client.request("PATCH", f"{ONELAKE_DFS}/{path}?action=flush&position={len(payload)}")
        written.append(path)
    return written


def deploy(
    config: DeploymentConfig,
    fabric_client: FabricRestClient,
    onelake_client: FabricRestClient,
) -> dict[str, Any]:
    """Create or refresh the whole solution and report what happened."""
    config.validate()
    workspace_id = config.workspace_id

    lakehouse_id, lakehouse_state = upsert_item(
        fabric_client,
        workspace_id,
        item_type="Lakehouse",
        display_name=config.lakehouse_name,
        description="Bronze/Silver/Gold store for Fabric IQ readiness runs.",
    )

    files = library_files(config.package_root)
    uploaded = upload_library(onelake_client, workspace_id, lakehouse_id, files)

    notebook_content = build_notebook_content(
        read_item_file(config.items_root, NOTEBOOK_ITEM, NOTEBOOK_SOURCE),
        workspace_id=workspace_id,
        lakehouse_id=lakehouse_id,
        lakehouse_name=config.lakehouse_name,
        default_tenant_id=config.default_tenant_id,
    )
    notebook_id, notebook_state = upsert_item(
        fabric_client,
        workspace_id,
        item_type="Notebook",
        display_name=config.notebook_name,
        parts=[
            inline_part(NOTEBOOK_SOURCE, notebook_content),
            inline_part(PLATFORM_SOURCE, read_item_file(config.items_root, NOTEBOOK_ITEM, PLATFORM_SOURCE)),
        ],
    )

    pipeline_content = build_pipeline_content(
        read_item_file(config.items_root, PIPELINE_ITEM, PIPELINE_SOURCE),
        workspace_id=workspace_id,
        notebook_id=notebook_id,
        default_tenant_id=config.default_tenant_id,
    )
    pipeline_id, pipeline_state = upsert_item(
        fabric_client,
        workspace_id,
        item_type="DataPipeline",
        display_name=config.pipeline_name,
        parts=[
            inline_part(PIPELINE_SOURCE, pipeline_content),
            inline_part(PLATFORM_SOURCE, read_item_file(config.items_root, PIPELINE_ITEM, PLATFORM_SOURCE)),
        ],
    )

    # DirectLake reads the Gold marts straight off the Lakehouse's SQL analytics
    # endpoint -- no seed CSVs to upload. The endpoint is provisioned
    # asynchronously right after the Lakehouse item, so wait for it here.
    connection_string, sql_endpoint_id = get_lakehouse_sql_endpoint(fabric_client, workspace_id, lakehouse_id)

    # The Report's definition.pbir must reference the SemanticModel's *actual*
    # item id (byConnection/semanticmodelid=...), so the model has to be created
    # -- and its id known -- before the Report's parts can be built.
    semantic_model_parts = build_semantic_model_parts(
        config.items_root,
        sql_endpoint_connection_string=connection_string,
        sql_endpoint_id=sql_endpoint_id,
        schema_name=config.directlake_schema,
    )
    semantic_model_id, semantic_model_state = upsert_item(
        fabric_client,
        workspace_id,
        item_type="SemanticModel",
        display_name=config.semantic_model_name,
        description="Fabric IQ Readiness scorecards, findings and remediation backlog.",
        parts=semantic_model_parts,
    )

    report_parts = build_report_parts(config.items_root, semantic_model_id=semantic_model_id)
    report_id, report_state = upsert_item(
        fabric_client,
        workspace_id,
        item_type="Report",
        display_name=config.report_name,
        description="Fabric IQ Readiness dashboard.",
        parts=report_parts,
    )

    return {
        "workspace_id": workspace_id,
        "lakehouse": {"id": lakehouse_id, "name": config.lakehouse_name, "state": lakehouse_state},
        "notebook": {"id": notebook_id, "name": config.notebook_name, "state": notebook_state},
        "pipeline": {"id": pipeline_id, "name": config.pipeline_name, "state": pipeline_state},
        "semantic_model": {
            "id": semantic_model_id,
            "name": config.semantic_model_name,
            "state": semantic_model_state,
        },
        "report": {"id": report_id, "name": config.report_name, "state": report_state},
        "library_files": len(uploaded),
        "sql_endpoint_id": sql_endpoint_id,
    }

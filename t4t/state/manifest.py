"""
Run manifest schema and conversion from executor result dicts.
"""

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal

SCHEMA_VERSION = 1

NodeStatus = Literal["success", "failed", "skipped"]
FuncStatus = Literal["success", "failed"]


def _t4t_version() -> str:
    try:
        return version("t4t")
    except PackageNotFoundError:
        return "0.0.0"


def _stable_json_hash(obj: Any) -> str | None:
    if obj is None:
        return None
    try:
        payload = json.dumps(obj, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class NodeResult:
    name: str
    status: NodeStatus
    error: str | None = None
    row_count: int | None = None
    materialization: str | None = None
    skip_reason: str | None = None


@dataclass
class FunctionResult:
    name: str
    status: FuncStatus
    error: str | None = None


@dataclass
class RunManifest:
    schema_version: int
    t4t_version: str
    run_id: str
    command: Literal["run", "build"]
    started_at: str
    finished_at: str
    project_root: str
    config_hash: str | None
    vars_hash: str | None
    execution_order: list[str]
    nodes: list[NodeResult]
    functions: list[FunctionResult]
    cli_args: dict[str, Any] | None = None


def manifest_to_dict(manifest: RunManifest) -> dict[str, Any]:
    d = asdict(manifest)
    return d


def manifest_from_dict(d: dict[str, Any]) -> RunManifest:
    nodes = [NodeResult(**n) for n in d.get("nodes", [])]
    functions = [FunctionResult(**f) for f in d.get("functions", [])]
    return RunManifest(
        schema_version=int(d["schema_version"]),
        t4t_version=str(d["t4t_version"]),
        run_id=str(d["run_id"]),
        command=d["command"],  # type: ignore[arg-type]
        started_at=str(d["started_at"]),
        finished_at=str(d["finished_at"]),
        project_root=str(d["project_root"]),
        config_hash=d.get("config_hash"),
        vars_hash=d.get("vars_hash"),
        execution_order=list(d.get("execution_order", [])),
        nodes=nodes,
        functions=functions,
        cli_args=d.get("cli_args"),
    )


def _normalize_skipped_tables(raw: Any) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if not raw:
        return out
    for item in raw:
        if isinstance(item, str):
            out.append((item, "upstream_failed:unknown"))
        elif isinstance(item, dict):
            t = str(item.get("table", ""))
            r = str(item.get("reason", ""))
            out.append((t, r or "upstream_failed:unknown"))
    return out


def results_to_manifest(
    results: dict[str, Any],
    command: Literal["run", "build"],
    project_root: str,
    started_at: str,
    finished_at: str,
    *,
    project_config: dict[str, Any] | None = None,
    variables: dict[str, Any] | None = None,
    cli_args: dict[str, Any] | None = None,
    function_names: set[str] | None = None,
) -> RunManifest:
    """Normalize execute_models or build_models result dicts into a RunManifest."""
    analysis = results.get("analysis") or {}
    execution_order: list[str] = list(analysis.get("execution_order") or [])
    graph = analysis.get("dependency_graph") or {}
    nodes_out: list[NodeResult] = []

    executed = set(results.get("executed_tables") or [])
    failed_map = {f["table"]: f.get("error", "") for f in (results.get("failed_tables") or [])}

    table_info: dict[str, Any] = results.get("table_info") or {}

    if command == "build":
        skipped_pairs = _normalize_skipped_tables(results.get("skipped_tables"))
        skipped_reason: dict[str, str] = {t: r for t, r in skipped_pairs if t}
        for name in execution_order:
            if function_names and name in function_names:
                continue
            if name.startswith("test:"):
                continue
            if name in failed_map:
                nodes_out.append(
                    NodeResult(
                        name=name,
                        status="failed",
                        error=str(failed_map[name]),
                        row_count=(table_info.get(name) or {}).get("row_count"),
                        materialization=(table_info.get(name) or {}).get("materialization"),
                    )
                )
            elif name in skipped_reason:
                nodes_out.append(
                    NodeResult(
                        name=name,
                        status="skipped",
                        skip_reason=skipped_reason[name],
                    )
                )
            elif name in executed:
                ti = table_info.get(name) or {}
                nodes_out.append(
                    NodeResult(
                        name=name,
                        status="success",
                        row_count=ti.get("row_count"),
                        materialization=ti.get("materialization"),
                    )
                )
    else:
        # run: derive skipped as order minus executed minus failed (downstream of failure)
        failed_names = set(failed_map.keys())
        for name in execution_order:
            if function_names and name in function_names:
                continue
            if name.startswith("test:"):
                continue
            if name in failed_map:
                nodes_out.append(
                    NodeResult(
                        name=name,
                        status="failed",
                        error=str(failed_map[name]),
                        row_count=(table_info.get(name) or {}).get("row_count"),
                        materialization=(table_info.get(name) or {}).get("materialization"),
                    )
                )
            elif name in executed:
                ti = table_info.get(name) or {}
                nodes_out.append(
                    NodeResult(
                        name=name,
                        status="success",
                        row_count=ti.get("row_count"),
                        materialization=ti.get("materialization"),
                    )
                )
            else:
                deps = (graph.get("dependencies") or {}).get(name, [])
                upstream_failed = any(
                    d in failed_names for d in deps if not str(d).startswith("test:")
                )
                reason = (
                    "not_run:downstream_of_failure"
                    if upstream_failed
                    else "not_run:not_reached"
                )
                nodes_out.append(NodeResult(name=name, status="skipped", skip_reason=reason))

    func_out: list[FunctionResult] = []
    for fn in results.get("executed_functions") or []:
        fn_name = fn if isinstance(fn, str) else str(fn)
        func_out.append(FunctionResult(name=fn_name, status="success"))
    for ff in results.get("failed_functions") or []:
        if isinstance(ff, dict):
            func_out.append(
                FunctionResult(
                    name=str(ff.get("function", "")),
                    status="failed",
                    error=str(ff.get("error", "")),
                )
            )

    return RunManifest(
        schema_version=SCHEMA_VERSION,
        t4t_version=_t4t_version(),
        run_id=str(uuid.uuid4()),
        command=command,
        started_at=started_at,
        finished_at=finished_at,
        project_root=str(project_root),
        config_hash=_stable_json_hash(project_config),
        vars_hash=_stable_json_hash(variables),
        execution_order=execution_order,
        nodes=nodes_out,
        functions=func_out,
        cli_args=cli_args,
    )


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()

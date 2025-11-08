"""Console entry point for the QCS dual-clock bridge daemon."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Optional

_MODULE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _MODULE_DIR.parent
_REPO_ROOT = _PROJECT_ROOT.parent
_DEFAULT_CONFIG = Path("configs/lab_snsdp.yaml")


def _resolve_config(path: Path) -> Path:
    """Resolve *path* against common repository roots."""

    candidates = [path] if path.is_absolute() else [Path.cwd() / path,
                                                   _PROJECT_ROOT / path,
                                                   _REPO_ROOT / path]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"config file not found: {path}")


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the QCS dual-clock bridge daemon",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=_DEFAULT_CONFIG,
        help="Path to the bridge YAML configuration (default: %(default)s)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging output",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        config_path = _resolve_config(args.config)
    except FileNotFoundError as exc:  # pragma: no cover - argparse exits
        parser.error(str(exc))

    try:
        run_bridge = _import_run_bridge()
    except ModuleNotFoundError as exc:  # pragma: no cover - argparse exits
        parser.error(_format_missing_dependency(exc))

    run_bridge(config_path, verbose=args.verbose)
    return 0


def _import_run_bridge():
    """Import ``run_bridge`` while surfacing clearer dependency errors."""

    # Import lazily so ``qcsd --help`` works even if optional dependencies are
    # not installed yet.
    from bridge.qcs_dcq_bridge import run_bridge

    return run_bridge


def _format_missing_dependency(error: ModuleNotFoundError) -> str:
    missing = error.name or str(error)
    hints = {
        "grpc": "Install gRPC runtime tooling: python -m pip install grpcio",
        "grpcio": "Install gRPC runtime tooling: python -m pip install grpcio",
        "qcs_control_pb2": (
            "Generate the QCS control protobuf stubs (see README 'Generate protobuf stubs')."
        ),
        "qcs_control_pb2_grpc": (
            "Generate the QCS control protobuf stubs (see README 'Generate protobuf stubs')."
        ),
        "dcq_plugin_pb2": (
            "Generate the shared dcq.v1 protobuf stubs with grpc_tools.protoc."
        ),
        "dcq_plugin_pb2_grpc": (
            "Generate the shared dcq.v1 protobuf stubs with grpc_tools.protoc."
        ),
        "yaml": "Install PyYAML: python -m pip install pyyaml",
    }

    hint = hints.get(missing, "Install the bridge runtime dependencies and regenerate protobuf stubs.")
    return f"Missing dependency '{missing}'. {hint}"


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())

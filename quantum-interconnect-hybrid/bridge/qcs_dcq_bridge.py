"""Reference dcq bridge control loop.

This module wires a Quantum Communications Sensor (QCS) controller
with a DualClock planning plugin using the dcq.v1 protobuf contract.
It consumes the repository's bridge configuration (for example,
``configs/lab_snsdp.yaml``) and shows how to enforce the guard rails
defined by the hardware spec while applying the plugin's plan outputs.
"""
from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import sys


_DEPENDENCY_HINTS = {
    "grpc": "Install gRPC runtime tooling: python -m pip install grpcio",
    "grpcio": "Install gRPC runtime tooling: python -m pip install grpcio",
    "grpc_tools": "Install the gRPC tools package: python -m pip install grpcio-tools",
    "yaml": "Install PyYAML: python -m pip install pyyaml",
    "dcq_plugin_pb2": "Generate the dcq.v1 protobuf stubs with grpc_tools.protoc.",
    "dcq_plugin_pb2_grpc": "Generate the dcq.v1 protobuf stubs with grpc_tools.protoc.",
    "qcs_control_pb2": "Generate the QCS control protobuf stubs (see README 'Generate protobuf stubs').",
    "qcs_control_pb2_grpc": "Generate the QCS control protobuf stubs (see README 'Generate protobuf stubs').",
}


def _dependency_hint(name: Optional[str]) -> str:
    """Return a remediation hint for a missing dependency name."""

    if not name:
        return "Install the bridge runtime dependencies and regenerate protobuf stubs."
    return _DEPENDENCY_HINTS.get(
        name,
        "Install the bridge runtime dependencies and regenerate protobuf stubs.",
    )


def _handle_missing_dependency(error: ModuleNotFoundError) -> None:
    """Emit a friendlier message when executed as a script."""

    if __name__ != "__main__":
        raise error

    missing = error.name or str(error)
    hint = _dependency_hint(error.name)
    print(f"Missing dependency '{missing}'. {hint}", file=sys.stderr)
    raise SystemExit(1) from error


try:  # pragma: no cover - import guard
    import grpc
except ModuleNotFoundError as exc:  # pragma: no cover - import guard
    _handle_missing_dependency(exc)

try:  # pragma: no cover - import guard
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - import guard
    _handle_missing_dependency(exc)

# --- import generated stubs (adjust PYTHONPATH for your environment) ---
try:  # pragma: no cover - import guard
    import qcs_control_pb2 as qcs  # type: ignore
    import qcs_control_pb2_grpc as qcs_rpc  # type: ignore
except ModuleNotFoundError as exc:  # pragma: no cover - import guard
    _handle_missing_dependency(exc)

try:  # pragma: no cover - import guard
    import dcq_plugin_pb2 as dcq  # type: ignore
    import dcq_plugin_pb2_grpc as dcq_rpc  # type: ignore
except ModuleNotFoundError as exc:  # pragma: no cover - import guard
    _handle_missing_dependency(exc)


_LOG = logging.getLogger("dcq.bridge")


def clamp(value: float, bounds: Tuple[float, float]) -> float:
    """Clamp *value* to the inclusive *bounds* tuple."""
    lo, hi = bounds
    if lo > hi:
        raise ValueError(f"invalid clamp bounds: {bounds}")
    return max(lo, min(hi, value))


@dataclass
class TLSConfig:
    enable: bool = False
    ca: Optional[Path] = None
    cert: Optional[Path] = None
    key: Optional[Path] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TLSConfig":
        return cls(
            enable=bool(data.get("enable", False)),
            ca=Path(data["ca"]) if data.get("ca") else None,
            cert=Path(data["cert"]) if data.get("cert") else None,
            key=Path(data["key"]) if data.get("key") else None,
        )

    def credentials(self) -> Optional[grpc.ChannelCredentials]:
        if not self.enable:
            return None
        if not (self.ca and self.ca.exists()):
            raise FileNotFoundError(f"TLS CA file missing: {self.ca}")
        root_certificates = self.ca.read_bytes()
        private_key = self.key.read_bytes() if self.key else None
        certificate_chain = self.cert.read_bytes() if self.cert else None
        return grpc.ssl_channel_credentials(
            root_certificates=root_certificates,
            private_key=private_key,
            certificate_chain=certificate_chain,
        )


@dataclass
class SafetyLimits:
    mu_range: Tuple[float, float]
    rep_rate_hz_range: Tuple[float, float]
    amzi_phase_deg_limit: float
    qber_hard_ceiling_pct: float
    shutter_guard: bool

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SafetyLimits":
        return cls(
            mu_range=tuple(data.get("mu_range", (0.0, 1.0)))[:2],
            rep_rate_hz_range=tuple(data.get("rep_rate_hz_range", (0.0, 0.0)))[:2],
            amzi_phase_deg_limit=float(data.get("amzi_phase_deg_limit", 0.0)),
            qber_hard_ceiling_pct=float(data.get("qber_hard_ceiling_pct", 0.0)),
            shutter_guard=bool(data.get("shutter_guard", True)),
        )

    @property
    def mu_bounds(self) -> Tuple[float, float]:
        return self.mu_range

    @property
    def rep_bounds(self) -> Tuple[float, float]:
        return self.rep_rate_hz_range


@dataclass
class DomainMapping:
    urlcc_dscp: Optional[int] = None
    embb_dscp: Optional[int] = None
    srv6_bsid_urlcc: Optional[str] = None
    srv6_bsid_embb: Optional[str] = None
    mlo_prefer_6ghz: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DomainMapping":
        return cls(
            urlcc_dscp=data.get("urlcc_dscp"),
            embb_dscp=data.get("embb_dscp"),
            srv6_bsid_urlcc=data.get("srv6_bsid_urlcc"),
            srv6_bsid_embb=data.get("srv6_bsid_embb"),
            mlo_prefer_6ghz=bool(data.get("mlo_prefer_6ghz", False)),
        )


def _extract_endpoint_tls(
    tls_section: Dict[str, Any], endpoint_key: str
) -> Dict[str, Any]:
    """Return per-endpoint TLS settings merged with shared defaults."""

    if not isinstance(tls_section, dict):
        return {}

    overrides = tls_section.get(endpoint_key, {})
    if not isinstance(overrides, dict):
        overrides = {}

    defaults = {
        key: value
        for key, value in tls_section.items()
        if key not in {"qcs", "plugin"}
    }
    merged: Dict[str, Any] = {**defaults, **overrides}
    return merged


@dataclass
class BridgeConfig:
    qcs_endpoint: str
    plugin_endpoint: str
    cycle_period_ms: int
    telemetry_period_ms: int
    qcs_tls: TLSConfig
    plugin_tls: TLSConfig
    safety: SafetyLimits
    mapping: DomainMapping
    listen: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BridgeConfig":
        bridge = data.get("bridge", {})
        tls_section = bridge.get("tls", {})
        return cls(
            qcs_endpoint=str(bridge.get("qcs_endpoint")),
            plugin_endpoint=str(bridge.get("plugin_endpoint")),
            cycle_period_ms=int(bridge.get("cycle_period_ms", 500)),
            telemetry_period_ms=int(bridge.get("telemetry_period_ms", 250)),
            qcs_tls=TLSConfig.from_dict(_extract_endpoint_tls(tls_section, "qcs")),
            plugin_tls=TLSConfig.from_dict(
                _extract_endpoint_tls(tls_section, "plugin")
            ),
            safety=SafetyLimits.from_dict(bridge.get("safety", {})),
            mapping=DomainMapping.from_dict(bridge.get("mapping", {})),
            listen=bridge.get("listen"),
        )


class BridgeRuntime:
    """Runs the closed-loop plan/apply cycle."""

    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self._qcs_channel: Optional[grpc.Channel] = None
        self._plugin_channel: Optional[grpc.Channel] = None
        self._qcs: Optional[qcs_rpc.QchsControlStub] = None
        self._plugin: Optional[dcq_rpc.DualClockPluginStub] = None
        self._session_id: Optional[str] = None
        self._running = False

    # ------------------------------------------------------------------
    # Channel / session helpers
    # ------------------------------------------------------------------
    def _open_channel(self, endpoint: str, tls: TLSConfig) -> grpc.Channel:
        creds = tls.credentials()
        if creds is None:
            return grpc.insecure_channel(endpoint)
        return grpc.secure_channel(endpoint, creds)

    def connect(self) -> None:
        """Establish controller and plugin channels."""
        _LOG.info("connecting to QCS controller at %s", self.config.qcs_endpoint)
        self._qcs_channel = self._open_channel(
            self.config.qcs_endpoint, self.config.qcs_tls
        )
        self._qcs = qcs_rpc.QchsControlStub(self._qcs_channel)

        _LOG.info("connecting to dcq plugin at %s", self.config.plugin_endpoint)
        self._plugin_channel = self._open_channel(
            self.config.plugin_endpoint, self.config.plugin_tls
        )
        self._plugin = dcq_rpc.DualClockPluginStub(self._plugin_channel)

    def close(self) -> None:
        for channel in filter(None, (self._qcs_channel, self._plugin_channel)):
            channel.close()

    # ------------------------------------------------------------------
    # QCS helpers
    # ------------------------------------------------------------------
    def ensure_session(self) -> str:
        if self._session_id:
            return self._session_id
        if not self._qcs:
            raise RuntimeError("QCS stub is not connected")

        symbol_rate_mhz = self._initial_symbol_rate_mhz()
        _LOG.info("issuing Configure request at %.3f MHz", symbol_rate_mhz)
        response = self._qcs.Configure(
            qcs.ConfigureRequest(
                mode="BB84_TIME_BIN",
                wavelength_nm=1550.0,
                symbol_rate_MHz=symbol_rate_mhz,
                divergence_urad=100.0,
                use_spad=False,
                ptp_enable=True,
            )
        )
        self._session_id = response.session_id

        _LOG.info("starting QKD session %s", self._session_id)
        self._qcs.StartQkd(qcs.StartRequest(session_id=self._session_id))
        self._running = True
        return self._session_id

    def _initial_symbol_rate_mhz(self) -> float:
        lo, hi = self.config.safety.rep_bounds
        if hi <= 0:
            return 100.0
        # pick midpoint of allowed range
        return (lo + hi) / 2.0 / 1e6

    # ------------------------------------------------------------------
    # Plan helpers
    # ------------------------------------------------------------------
    def _status_to_telemetry(self, status: qcs.StatusResponse) -> dcq.Telemetry:
        qber_pct = status.qber_pct if hasattr(status, "qber_pct") else 0.0
        sifted_rate = status.sifted_rate_cps if hasattr(status, "sifted_rate_cps") else 0.0
        secure_rate = status.secure_rate_cps if hasattr(status, "secure_rate_cps") else 0.0
        jitter_ps = status.jitter_ps if hasattr(status, "jitter_ps") else 0.0
        atm_loss = status.atm_loss_db_per_km if hasattr(status, "atm_loss_db_per_km") else 0.0
        return dcq.Telemetry(
            t_unix_ms=int(time.time() * 1000),
            qber_pct=qber_pct,
            sifted_rate_cps=sifted_rate,
            secure_rate_bps=secure_rate,
            jitter_ps=jitter_ps,
            atm_loss_db_per_km=atm_loss,
            dark_cps=getattr(status, "dark_counts_cps", 0.0),
            det_eff=getattr(status, "det_efficiency", 0.0),
            temperature_c=getattr(status, "temperature_c", 0.0),
            site=getattr(status, "site", "unknown"),
            active_domain=dcq.Domain.FSO,
            scintillation_idx=getattr(status, "scintillation_idx", 0.0),
        )

    def _send_clock_model(self) -> None:
        if not self._plugin:
            raise RuntimeError("dcq plugin stub is not connected")
        clock = dcq.ClockModel(coarse_ppb=0.0, fine_hz=0.0, tdc_bin_ps=10.0, gate_ns=1.0)
        _LOG.debug("pushing baseline clock model: %s", clock)
        self._plugin.SetClockModel(clock)

    def _plan_constraints(self) -> dcq.Constraints:
        safety = self.config.safety
        return dcq.Constraints(
            mu_min=safety.mu_bounds[0],
            mu_max=safety.mu_bounds[1],
            rep_rate_min_hz=safety.rep_bounds[0],
            rep_rate_max_hz=safety.rep_bounds[1],
            qber_hard_ceiling_pct=safety.qber_hard_ceiling_pct,
        )

    def _default_slo(self) -> dcq.Slo:
        return dcq.Slo(cls=dcq.SloClass.URLLC, jitter_ps_target=50.0, key_rate_min_bps=5e4)

    # ------------------------------------------------------------------
    # Apply helpers
    # ------------------------------------------------------------------
    def _clamp_decoys(self, decoys: dcq.DecoyProfile) -> dcq.DecoyProfile:
        safety = self.config.safety
        mu_sig = clamp(decoys.mu_signal or 0.0, safety.mu_bounds)
        mu_dec = clamp(decoys.mu_decoy or 0.0, (safety.mu_bounds[0] / 10.0, safety.mu_bounds[1]))
        vac_prob = clamp(decoys.vac_prob or 0.0, (0.0, 1.0))
        sig_prob = clamp(decoys.sig_prob or 0.0, (0.0, 1.0))
        decoy_prob = clamp(decoys.decoy_prob or 0.0, (0.0, 1.0))
        return dcq.DecoyProfile(
            mu_signal=mu_sig,
            mu_decoy=mu_dec,
            vac_prob=vac_prob,
            sig_prob=sig_prob,
            decoy_prob=decoy_prob,
        )

    def _apply_plan(self, plan: dcq.PlanResponse) -> None:
        if not self._qcs or not self._session_id:
            raise RuntimeError("QCS session not established")

        if plan.HasField("tx") and plan.tx.HasField("decoys"):
            decoys = self._clamp_decoys(plan.tx.decoys)
            _LOG.debug("applying decoy profile: %s", decoys)
            self._qcs.SetDecoyProfile(
                qcs.DecoyProfile(
                    session_id=self._session_id,
                    mu_signal=decoys.mu_signal,
                    mu_decoy=decoys.mu_decoy,
                    vacuum_prob=decoys.vac_prob,
                )
            )

        if plan.HasField("tx") and plan.tx.rep_rate_hz:
            rep_rate = clamp(plan.tx.rep_rate_hz, self.config.safety.rep_bounds)
            symbol_rate_mhz = rep_rate / 1e6
            _LOG.debug("nudging symbol rate to %.3f MHz", symbol_rate_mhz)
            self._qcs.Configure(
                qcs.ConfigureRequest(
                    mode="BB84_TIME_BIN",
                    wavelength_nm=1550.0,
                    symbol_rate_MHz=symbol_rate_mhz,
                    divergence_urad=100.0,
                    use_spad=False,
                    ptp_enable=True,
                )
            )

        if plan.HasField("phase") and abs(plan.phase.amzi_phase_deg) > 0.1:
            phase_delta = clamp(
                plan.phase.amzi_phase_deg,
                (-self.config.safety.amzi_phase_deg_limit, self.config.safety.amzi_phase_deg_limit),
            )
            _LOG.debug("requesting MZI phase calibration %.2f deg", phase_delta)
            self._qcs.Calibrate(
                qcs.CalibrationRequest(type="MZI_PHASE")
            )

        if plan.HasField("domain"):
            self._publish_domain_policy(plan.domain)

    def _publish_domain_policy(self, domain: dcq.DomainPolicy) -> None:
        mapping = self.config.mapping
        if domain.preferred == dcq.Domain.FSO:
            _LOG.debug("domain preference: FSO")
        elif domain.preferred == dcq.Domain.MMWAVE:
            _LOG.debug("domain preference: mmWave")
        elif domain.preferred == dcq.Domain.LEO:
            _LOG.debug("domain preference: LEO")
        elif domain.preferred == dcq.Domain.WIFI7:
            _LOG.debug("domain preference: Wi-Fi 7")
        elif domain.preferred == dcq.Domain.FR3_6G:
            _LOG.debug("domain preference: FR3/6G")

        if domain.dscp:
            _LOG.debug("set DSCP %s", domain.dscp)
        if domain.srv6_bsid:
            _LOG.debug("target SRv6 BSID %s", domain.srv6_bsid)
        if mapping.mlo_prefer_6ghz or domain.mlo_prefer_6ghz:
            _LOG.debug("prefer Wi-Fi 7 6 GHz MLO leg")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def run(self) -> None:
        if not self._qcs or not self._plugin:
            raise RuntimeError("connect() must be called before run()")

        self.ensure_session()
        self._send_clock_model()

        hello = self._plugin.Hello(dcq.HelloReq(plugin_name="dcq-bridge", version="0.1", git_sha="local"))
        _LOG.info("plugin hello: %s", hello)
        caps = self._plugin.Describe(dcq.Empty())
        _LOG.info("plugin capabilities: %s", caps)

        constraints = self._plan_constraints()
        slo = self._default_slo()

        _LOG.info(
            "starting control loop (cycle=%d ms, qber ceiling=%.2f%%)",
            self.config.cycle_period_ms,
            self.config.safety.qber_hard_ceiling_pct,
        )

        try:
            while True:
                status = self._qcs.GetStatus(qcs.StatusRequest())
                telemetry = self._status_to_telemetry(status)
                _LOG.debug("telemetry snapshot: %s", telemetry)

                if telemetry.qber_pct >= self.config.safety.qber_hard_ceiling_pct:
                    if self._running:
                        _LOG.warning(
                            "QBER %.2f%% exceeds ceiling %.2f%% – parking shutter",
                            telemetry.qber_pct,
                            self.config.safety.qber_hard_ceiling_pct,
                        )
                        self._qcs.Shutter(qcs.ShutterRequest(open=False))
                        self._qcs.StopQkd(qcs.StopRequest(session_id=self._session_id))
                        self._running = False
                    time.sleep(self.config.cycle_period_ms / 1000.0)
                    continue

                if not self._running:
                    _LOG.info("restarting QKD session %s", self._session_id)
                    self._qcs.Shutter(qcs.ShutterRequest(open=True))
                    self._qcs.StartQkd(qcs.StartRequest(session_id=self._session_id))
                    self._running = True

                plan = self._plugin.PlanCycle(
                    dcq.PlanRequest(
                        clock=dcq.ClockModel(coarse_ppb=0.0, fine_hz=0.0, tdc_bin_ps=10.0, gate_ns=1.0),
                        tel=telemetry,
                        limits=constraints,
                        slo=slo,
                    )
                )
                _LOG.debug("received plan: %s", plan)
                self._apply_plan(plan)

                time.sleep(self.config.cycle_period_ms / 1000.0)
        except KeyboardInterrupt:
            _LOG.info("bridge interrupted, stopping")
        finally:
            if self._running and self._session_id:
                self._qcs.StopQkd(qcs.StopRequest(session_id=self._session_id))
            if self.config.safety.shutter_guard:
                try:
                    self._qcs.Shutter(qcs.ShutterRequest(open=False))
                except Exception:  # pragma: no cover - best effort shutdown
                    _LOG.exception("failed to close shutter during shutdown")
            self.close()


def load_config(path: Path) -> BridgeConfig:
    """Parse a YAML bridge configuration into a :class:`BridgeConfig`."""

    data = yaml.safe_load(path.read_text())
    return BridgeConfig.from_dict(data)


def configure_logging(verbose: bool) -> None:
    """Initialize module logging with an optional verbose level."""

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def run_bridge(config_path: Path, *, verbose: bool = False) -> None:
    """Entry point for launching the bridge runtime."""

    configure_logging(verbose)

    config = load_config(config_path)
    runtime = BridgeRuntime(config)
    runtime.connect()
    runtime.run()


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the dcq bridge reference loop")
    parser.add_argument("config", type=Path, help="Path to bridge YAML configuration")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args(list(argv) if argv is not None else None)

    run_bridge(args.config, verbose=args.verbose)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

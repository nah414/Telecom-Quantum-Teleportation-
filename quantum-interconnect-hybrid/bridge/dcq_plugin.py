"""Sample dcq DualClock plugin implementation.

This module provides a minimal gRPC server that implements the
``DualClockPlugin`` service defined in ``proto/dcq_plugin.proto``.
It is intentionally lightweight so the reference bridge loop can be exercised
without a full planning engine.  The behaviour mirrors the review feedback by
adapting repetition rate, decoy profile, and phase trims based on the
telemetry that the bridge forwards each cycle.
"""

from __future__ import annotations

import argparse
import logging
from concurrent import futures
from typing import Iterable, Optional

import grpc

import dcq_plugin_pb2 as dcq  # type: ignore
import dcq_plugin_pb2_grpc as rpc  # type: ignore


_LOG = logging.getLogger("dcq.plugin")


class Plugin(rpc.DualClockPluginServicer):
    """Simple planning heuristic for exercising the bridge."""

    def __init__(self) -> None:
        self._clock = dcq.ClockModel(coarse_ppb=0.0, fine_hz=0.0, tdc_bin_ps=10.0, gate_ns=1.0)

    # ------------------------------------------------------------------
    # Lifecycle RPCs
    # ------------------------------------------------------------------
    def Hello(self, request: dcq.HelloReq, context: grpc.ServicerContext) -> dcq.HelloResp:  # type: ignore[override]
        _LOG.info("hello from bridge: %s", request)
        return dcq.HelloResp(
            bridge_version="any",
            qcs_firmware="unknown",
            features=["dual-clock", "domain-policy"],
        )

    def Describe(self, request: dcq.Empty, context: grpc.ServicerContext) -> dcq.Capabilities:  # type: ignore[override]
        return dcq.Capabilities(
            can_plan_tx_schedule=True,
            can_phase_dither=True,
            can_clock_align=True,
            can_domain_policy=True,
            requires_raw_counts=False,
        )

    def SetClockModel(self, model: dcq.ClockModel, context: grpc.ServicerContext) -> dcq.Ack:  # type: ignore[override]
        _LOG.debug("clock model updated: %s", model)
        self._clock = model
        return dcq.Ack(ok=True, msg="clock accepted")

    # ------------------------------------------------------------------
    # Planning logic
    # ------------------------------------------------------------------
    def PlanCycle(self, request: dcq.PlanRequest, context: grpc.ServicerContext) -> dcq.PlanResponse:  # type: ignore[override]
        telemetry = request.tel
        limits = request.limits

        # Start with the midpoint repetition rate unless the constraints are
        # degenerate, then walk it down when loss or QBER climb.
        rep_floor = max(limits.rep_rate_min_hz, 1.0e6)
        rep_ceiling = limits.rep_rate_max_hz or 1.0e9
        rep_rate = max(rep_floor, min(1.0e8, rep_ceiling))

        if telemetry.atm_loss_db_per_km > 10 or telemetry.qber_pct > 3:
            rep_rate = max(rep_floor, rep_rate / 2.0)
        if telemetry.atm_loss_db_per_km > 20 or telemetry.qber_pct > 5:
            rep_rate = max(rep_floor, rep_rate / 4.0)

        # Convert fine frequency error to a gate shift.  Clamp so we do not
        # request excursions outside the bridge guard rails.
        gate_shift_ps = (self._clock.fine_hz / rep_rate) * 1e12
        gate_shift_ps = max(min(gate_shift_ps, 150.0), -150.0)

        # Adaptive decoy profile mirroring the guidance from the review: lower
        # signal mean photon number and increase vacuum/decoy probability in
        # harsher channels to stabilise QBER.
        mu_signal = 0.50
        mu_decoy = 0.08
        vac_prob = 0.10
        sig_prob = 0.75
        dec_prob = 0.15

        if telemetry.atm_loss_db_per_km > 10 or telemetry.qber_pct > 3:
            mu_signal = 0.40
            mu_decoy = 0.06
            vac_prob = 0.15
            sig_prob = 0.65
            dec_prob = 0.20
        if telemetry.atm_loss_db_per_km > 20 or telemetry.qber_pct > 5:
            mu_signal = 0.30
            mu_decoy = 0.05
            vac_prob = 0.20
            sig_prob = 0.60
            dec_prob = 0.20

        # Mild phase dither during scintillation events to keep interference
        # visibility from collapsing.
        phase_deg = 0.0
        if telemetry.scintillation_idx > 0.3:
            phase_deg = max(min((telemetry.scintillation_idx - 0.3) * 20.0, 8.0), -8.0)

        # Cross-domain hint: nudge away from FSO when the fog proxy (loss or
        # QBER) indicates significant degradation.
        preferred = dcq.Domain.FSO
        dscp = 46
        bsid = "FC00::A"
        if telemetry.atm_loss_db_per_km > 20 or telemetry.qber_pct > 5:
            preferred = dcq.Domain.MMWAVE
            dscp = 46
            bsid = "FC00::A"

        rationale = (
            f"loss={telemetry.atm_loss_db_per_km:.1f}dB/km "
            f"qber={telemetry.qber_pct:.2f}% -> rep={rep_rate/1e6:.0f}MHz "
            f"mu={mu_signal:.2f} shift={gate_shift_ps:.0f}ps"
        )

        return dcq.PlanResponse(
            tx=dcq.TxOverrides(
                rep_rate_hz=rep_rate,
                pulse_width_ps=100.0,
                decoys=dcq.DecoyProfile(
                    mu_signal=mu_signal,
                    mu_decoy=mu_decoy,
                    vac_prob=vac_prob,
                    sig_prob=sig_prob,
                    decoy_prob=dec_prob,
                ),
                gate_shift_ps=gate_shift_ps,
            ),
            phase=dcq.PhaseOverrides(amzi_phase_deg=phase_deg, eom_bias_v_delta=0.0),
            domain=dcq.DomainPolicy(
                preferred=preferred,
                srv6_bsid=bsid,
                dscp=dscp,
                mlo_prefer_6ghz=True,
            ),
            next_cycle_ms=500,
            rationale=rationale,
        )

    def Events(self, request_iterator: Iterable[dcq.Telemetry], context: grpc.ServicerContext) -> dcq.Ack:  # type: ignore[override]
        for telemetry in request_iterator:
            _LOG.debug("event stream update: %s", telemetry)
        return dcq.Ack(ok=True, msg="event stream closed")


def serve(listen: str) -> None:
    """Start the sample plugin server."""

    _LOG.info("starting sample plugin on %s", listen)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    rpc.add_DualClockPluginServicer_to_server(Plugin(), server)
    server.add_insecure_port(listen)
    server.start()
    server.wait_for_termination()


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the sample dcq planning plugin")
    parser.add_argument("--listen", default="0.0.0.0:7700", help="Listen address for the gRPC server")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args(list(argv) if argv is not None else None)

    _configure_logging(args.verbose)
    serve(args.listen)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

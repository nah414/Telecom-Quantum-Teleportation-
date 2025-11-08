# Dual-Clocking-Qubits (DCQ) Integration with QCS

The dual-clock domain coordination (DCQ) plugin captures the closed-loop policy between the Quantum Communications Hardware Sensor (QCHS) control stack and the hybrid backhaul fabric (FSO, mmWave, Wi-Fi 7, FR3/6G, and LEO). The gRPC contract is extracted into `proto/dcq_plugin.proto` for CI-friendly code generation.

## Overview

- **Objective**: provide deterministic micro-cycle planning that respects the QCHS finite-key/QBER guard bands while maximizing secure key throughput across multiple domains.
- **Interfaces**: the bridge runs as a plugin that exchanges telemetry snapshots and plan overrides with the controller using the `DualClockPlugin` service.
- **Clock model**: dual (coarse GNSS/PTP, fine optical pilot). The plugin updates the controller with drift estimates, gate width, and TDC quantization.

## Components

- `proto/dcq_plugin.proto` — DualClockPlugin service definition shared across languages.
- `bridge/dcq_plugin.py` — Example Python plugin implementing the service.
- `bridge/qcs_dcq_bridge.py` — Safety-gated adapter that brokers plans between QCS and the plugin.
- `configs/lab_snsdp.yaml` — Reference bridge configuration (limits, SRv6/DSCP mapping, cadence).

## Build

1. Install the gRPC tooling alongside the runtime dependencies (example with `python -m pip`):

   ```bash
   python -m pip install grpcio grpcio-tools protobuf pyyaml
   ```

2. Generate Python stubs for the shared DCQ contract:

   ```bash
   python -m grpc_tools.protoc \
     --proto_path=proto \
     --python_out=. \
     --grpc_python_out=. \
     proto/dcq_plugin.proto
   ```

3. Generate stubs for your QCS control service definition. The repository does not include the
   controller schema, so point `--proto_path` to the location of your `qcs_control.proto` (or
   equivalent) to produce `qcs_control_pb2.py` and `qcs_control_pb2_grpc.py` for the bridge module.

## Service contract

```protobuf
syntax = "proto3";
package dcq.v1;

option go_package = "dcq.dev/api/dcqv1";
option java_multiple_files = true;

message Empty {}
message Ack { bool ok = 1; string msg = 2; }

enum Domain { DOMAIN_UNKNOWN=0; FSO=1; MMWAVE=2; LEO=3; WIFI7=4; FR3_6G=5; }
enum SloClass { SLO_UNKNOWN=0; URLLC=1; EMBB=2; BESTEFFORT=3; }

message HelloReq  { string plugin_name = 1; string version = 2; string git_sha = 3; }
message HelloResp { string bridge_version = 1; string qcs_firmware = 2; repeated string features = 3; }

message Capabilities {
  bool can_plan_tx_schedule = 1;
  bool can_phase_dither     = 2;
  bool can_clock_align      = 3;
  bool can_domain_policy    = 4;
  bool requires_raw_counts  = 5;
}

message ClockModel {
  double coarse_ppb = 1;
  double fine_hz    = 2;
  double tdc_bin_ps = 3;
  double gate_ns    = 4;
}

message Telemetry {
  int64  t_unix_ms = 1;
  double qber_pct  = 2;
  double sifted_rate_cps = 3;
  double secure_rate_bps = 4;
  double jitter_ps = 5;
  double atm_loss_db_per_km = 6;
  double dark_cps = 7;
  double det_eff = 8;
  double temperature_c = 9;
  string site = 10;
  Domain active_domain = 11;
  double scintillation_idx = 12;
}

message Constraints {
  double mu_min = 1; double mu_max = 2;
  double rep_rate_min_hz = 3; double rep_rate_max_hz = 4;
  double qber_hard_ceiling_pct = 5;
}

message Slo {
  SloClass cls = 1;
  double   jitter_ps_target = 2;
  double   key_rate_min_bps = 3;
}

message PlanRequest {
  ClockModel clock = 1;
  Telemetry  tel   = 2;
  Constraints limits = 3;
  Slo        slo     = 4;
}

message DecoyProfile {
  double mu_signal = 1;
  double mu_decoy  = 2;
  double vac_prob  = 3;
  double sig_prob  = 4;
  double decoy_prob= 5;
}

message TxOverrides {
  double rep_rate_hz = 1;
  double pulse_width_ps = 2;
  DecoyProfile decoys = 3;
  double gate_shift_ps = 4;
}

message PhaseOverrides {
  double amzi_phase_deg = 1;
  double eom_bias_v_delta = 2;
}

message DomainPolicy {
  Domain preferred = 1;
  string srv6_bsid = 2;
  int32  dscp = 3;
  bool   mlo_prefer_6ghz = 4;
}

message PlanResponse {
  TxOverrides tx = 1;
  PhaseOverrides phase = 2;
  DomainPolicy domain = 3;
  uint32 next_cycle_ms = 4;
  string rationale = 5;
}

service DualClockPlugin {
  rpc Hello(HelloReq) returns (HelloResp);
  rpc Describe(Empty) returns (Capabilities);
  rpc SetClockModel(ClockModel) returns (Ack);
  rpc PlanCycle(PlanRequest) returns (PlanResponse);
  rpc Events(stream Telemetry) returns (Ack);
}
```

## Implementation notes

- **Planning cadence**: `next_cycle_ms` is capped by fog/autonomous failover timing (<2 s) and can be tightened during scintillation spikes.
- **Decoy enforcement**: `Constraints.qber_hard_ceiling_pct` mirrors the 11% hard stop in the QCHS spec; the plugin must never request overrides that would violate it.
- **Domain steering**: the optional `DomainPolicy` tuple allows SRv6 steering for metro fiber/LEO backhaul while also nudging Wi-Fi 7 MLO preferences for rooftop deployments.
- **Event streaming**: the controller may stream real-time telemetry via `Events` to keep the plugin synchronized even when planning is paused (e.g., shutter closed).

## Bridge reference configuration

The repository includes `configs/lab_snsdp.yaml`, a starter configuration for standing up the dcq bridge alongside a lab QCHS instance. It wires the controller (`qcs_endpoint`) and plugin (`plugin_endpoint`) over mutually-authenticated TLS and enforces the safety guard rails defined by the hardware spec:

```yaml
bridge:
  listen: 127.0.0.1:7600
  qcs_endpoint: 127.0.0.1:7443   # QCS device service gRPC
  plugin_endpoint: 127.0.0.1:7700
  tls:
    enable: true
    ca: /etc/qcs/ca.pem
    cert: /etc/qcs/bridge.pem
    key: /etc/qcs/bridge.key
  safety:
    mu_range: [0.05, 0.8]
    rep_rate_hz_range: [5.0e6, 2.5e8]
    amzi_phase_deg_limit: 10
    qber_hard_ceiling_pct: 11.0
    shutter_guard: true
  mapping:
    urlcc_dscp: 46
    embb_dscp: 10
    srv6_bsid_urlcc: "FC00::A"
    srv6_bsid_embb:  "FC00::B"
  telemetry_period_ms: 250
  cycle_period_ms: 500
```

- **Safety block**: clamps requested decoy means, repetition rate, and interferometer nudges to the same bounds called out in the QCHS specification.
- **Mapping block**: pre-binds DSCP values and SRv6 BSIDs for URLLC and eMBB slices so `DomainPolicy` hints can be translated directly into forwarding actions.
- **Timing**: defaults to 250 ms telemetry streaming and 500 ms planning cadence, matching the fog/LEO failover envelope.

## Reference control loop implementation

The repository ships a Python implementation of the bridge in `bridge/qcs_dcq_bridge.py`. It loads the YAML configuration, performs the gRPC handshakes (TLS if enabled), clamps the plugin's proposals to the published μ, repetition-rate, and phase limits, and then applies them via the QCS control RPCs. The loop also enforces the 11% QBER hard ceiling by parking the shutter and pausing keying until conditions recover.

Run the reference loop with the sample configuration after placing the generated protobuf stubs on the `PYTHONPATH` (execute the
commands inside `quantum-interconnect-hybrid/`):

```bash
python -m qcsd --config configs/lab_snsdp.yaml --verbose
```

Install the repository in editable mode from `quantum-interconnect-hybrid/` (`python -m pip install -e .`) to expose the `qcsd`
console entry point and run:

```bash
qcsd --config configs/lab_snsdp.yaml --verbose
```

Use this as a baseline for production bridges; swap in your telemetry pipelines, hardened credential storage, and orchestration hooks as required.

## Sample planning plugin

To aid local testing, `bridge/dcq_plugin.py` implements a heuristic planner that tracks the review guidance: μ and repetition rate are reduced as atmospheric loss or QBER rise, gate alignment compensates for dual-clock drift, and domain hints fall back to mmWave when free-space conditions deteriorate. Launch it alongside the bridge:

```bash
python -m bridge.dcq_plugin --listen 0.0.0.0:7700 --verbose
```

Swap this module with your production-grade plugin once the deterministic planning logic is available.

## How this maximizes performance across domains

- **Dual-clock alignment**: The plugin feeds coarse/fine drift estimates into the bridge so gate shifts stay bounded, cutting effective timing jitter and suppressing afterpulsing penalties—this preserves sifted and secure key throughput even as the optical pilot walks.
- **Adaptive decoy/μ policy**: The reference heuristics lower μ and bias toward higher vacuum/decoy probability whenever turbulence or loss rises. That keeps QBER within the 3 % operational target, protecting finite-key efficiency while avoiding needless shutter trips.
- **Cross-domain hints**: Domain policies map directly onto the SRv6/DSCP tuples in `configs/lab_snsdp.yaml`, letting the control plane stay deterministic (FSO in clear air, mmWave/LEO in fog) so key generation resumes promptly after fades.
- **Safety gates**: All overrides are clamped by the bridge against the specification guard rails, ensuring experiments cannot leave the secure envelope even if a plugin bug proposes an out-of-band value.

## Drop-in checklist

1. Add `proto/dcq_plugin.proto` to your DCQ repository (or vendored interface module) and generate stubs for the languages you support.
2. Replace `bridge/dcq_plugin.py` with your production `DualClockPlugin` implementation so the bridge exercises your algorithms instead of the heuristic starter.
3. Vendor the bridge runtime into the **Advanced Communications** infrastructure as a sidecar to the QCS device service, wiring telemetry and control endpoints per your deployment topology.
4. Plumb observability into your metrics stack and dashboard the key four signals: `qber`, `key_rate_bps`, `rep_rate_hz`, and `gate_shift_ps`.

With those pieces in place the kit remains “boring reliable”: bounded inputs, bounded outputs, and explicit ownership of safety. A natural follow-on is publishing a hardened container image (SBOM + signatures) and automating lab-trace replays in CI to catch DCQ regression risk.


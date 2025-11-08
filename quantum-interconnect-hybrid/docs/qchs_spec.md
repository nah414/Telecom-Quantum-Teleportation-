# Quantum Communications Hardware Sensor (QCHS) Specification

## Meta
- **Project**: Advanced Communications
- **Module**: Quantum Communications Hardware Sensor (QCHS)
- **Version**: 0.2b
- **Pilot City**: Chicago
- **License**: Proprietary (eVision)
- **Last Updated**: 2025-11-08
- **Summary**: Factory-ready specification for a rooftop/rack deployable quantum communications sensor enabling DV-QKD (decoy BB84), time-/frequency-bin experiments, and entanglement pilots over free-space optical links. Includes hardware, firmware, APIs, register map, test plans, safety and compliance, Wi-Fi 7 & 6G integration hooks, and sanity-checked budgets.

## Use Cases & Requirements
### Supported Use Cases
- DV-QKD with decoy-state BB84
- Time-bin QKD
- Frequency-bin experiments
- Entanglement pilot via SPDC
- Quantum telemetry export

### Operating Ranges
| Parameter | Range |
| --- | --- |
| Metro rooftop clear-air link | 1–5 km |
| Extended corridor link | 5–15 km |
| Symbol rate | 100–250 MHz |
| Timing jitter (max) | 50 ps |

**Environmental envelope**
- Temperature: −20 °C to +50 °C
- Optical head ingress: IP65
- Wind gusts: up to 20 m/s

### Safety & Interlocks
- Laser classification: IEC 60825-1 Class 1M
- Hardware shutters with ≤1 µs kill time
- Interlocks trigger on: mispoint >2 mrad, beacon loss, power anomalies, enclosure open, over-temperature

### Security
- Control plane: TLS 1.3 hybrid PQC (Kyber + X25519)
- Device identity: TPM 2.0 attestation with secure boot
- Key storage: Onboard or network HSM
- Finite-key analysis tooling embedded in post-processing pipeline (configurable block sizes)

### Compatibility & Performance Targets
- Wi-Fi 7, 6G-ready, and SRv6 integrations
- Typical secure key rate (3 km clear): 50–100 kb/s
- Operational QBER target: 3%; hard ceiling: 11% (hard interlock halts emission)

## Hardware Architecture
### Wavelength Plan
- Primary quantum channel: 1550 nm
- Beacon channels: 850–940 nm

### Transmitter Subsystem
- Ultra-stable DFB or ECL laser with PDH cavity lock (linewidth ≤1 kHz)
- LiNbO3 phase and intensity modulators plus VOA and fast AOM kill path
- Encoding profiles:
  - Decoy BB84: μ_signal 0.4–0.6, μ_decoy 0.05–0.1, vacuum decoy enabled
  - Time-bin: Δt 0.5–2.0 ns
  - Frequency-bin: 25–50 GHz spacing with AWG or microring filters (RX)
  - Optional polarization support for short hops
- Beam characteristics: 50–150 µrad divergence, 50–120 mm aperture

### Pointing, Acquisition, and Tracking (PAT)
- Two-axis gimbal (±45° travel, 50 µrad repeatability)
- Fast steering mirror: ±2 mrad range, 500–2000 Hz control bandwidth
- Sensors: global-shutter star camera and quad-cell detector
- Sensor fusion via EKF (IMU + beacon + stars), acquisition within 1 s
- Fog detection workflow: backscatter monitor on beacon channel + local meteorological feed fusion, triggers shutter park within 100 ms and initiates failover orchestration

### Receiver Subsystem
- Aperture: 120–200 mm with 0.5–1.0 nm spectral filters and single-mode/LMA fiber coupling
- Time-bin decoder: unbalanced MZI (ΔL = 0.20 m for 1 ns) with piezo phase lock (≥95% visibility)
- Frequency-bin decoder: AWG or microring with thermo-optic or PZT tuning
- Optional polarization analyzer: PBS with waveplates
- 2% power-monitor tap for safety telemetry

### Detectors
- Primary: SNSPD module, 70–85% system efficiency, ≤100 cps dark counts, 15–30 ps jitter, ≤50 Mcps, closed-cycle PT/GM cryo at 2.5–3.0 K, 180–260 W system draw
- Alternate: Gated SPAD (20–35% efficiency, 1–10 kcps dark counts, 100–200 ps jitter) with Peltier cooling for lower-power builds (90–140 W)

### Timing & Frequency Reference
- GNSS-disciplined OCXO with IEEE 1588 Profile A/B support
- TDC resolution: 10 ps, frequency reference via micro-comb or cavity

### Compute, I/O, and Power
- FPGA: TDC capture and deterministic schedulers
- SoC: Real-time Linux control plane
- Data ports: dual 10 GbE + optional 25 GbE; dedicated OOB management
- Power: 48 VDC input, recommend ≥500 Wh UPS
- Edge failover fabric: 60 GHz mmWave MIMO radio pair (4×4, 2.5 GbE bridge) with optional LEO terminal control via gRPC hooks

### Enclosure & Mechanics
- Optical head (IP65 + purge): 300 × 300 × 250 mm
- Rack unit: 4–6U electronics bay

## Firmware & Software Stack
- RT-Linux base OS with gRPC over QUIC control API
- TX pipeline: QRNG → basis pattern → decoy schedule → EOM/AOM drive → safety checks → emit
- RX pipeline: TDC events → basis sort → QBER estimation → sifting → LDPC/CASCADE error correction → privacy amplification → key confirmation
- QRNG: vacuum or beam-splitter shot-noise with min-entropy, IID, and bias health tests
- PQC: TLS 1.3 hybrid (Kyber + X25519) with PQC MAC support
- Observability: OpenTelemetry metrics exporting photon counts, QBER, sifted/secure rates, jitter, frequency drift, atmospheric loss, PAT and interlock state
- Failover orchestration microservice monitors fog telemetry, mmWave link KPIs, and LEO terminal status; commands shutter park, mmWave switch-over, and optional LEO routing advertisement via SRv6 within 2 s

### Dual-clock domain coordination plugin (`dcq.v1`)
- Bridge exposes `DualClockPlugin` gRPC service (see `proto/dcq_plugin.proto`) for deterministic scheduling between the QCHS controller and multi-bearer backhaul fabric.
- Negotiates coarse/fine clock models, adaptive decoy/rep-rate overrides, and SRv6/DSCP policy hints to align URLLC vs. eMBB service levels across FSO, mmWave, Wi-Fi 7, FR3, and LEO domains.
- Telemetry payload extends atmospheric loss, jitter, scintillation, detector efficiency, and domain selection inputs for closed-loop planning while enforcing the 11% QBER hard ceiling via constraint sharing with the bridge.
- Reference bridge configuration (`configs/lab_snsdp.yaml`) clamps μ, repetition rate, interferometer phase offsets, and shutter guards to these limits while mapping DSCP/BSID pairs for URLLC and eMBB slices.
- Reference bridge runtime (`bridge/qcs_dcq_bridge.py`) consumes the configuration, enforces the guard rails in software, and halts keying + parks the shutter if the QBER ceiling (11%) is breached while awaiting recovery telemetry.

## Control Proto API (v1)
```protobuf
syntax = "proto3";
package qchs.v1;

service QchsControl {
  rpc Configure(ConfigureRequest) returns (ConfigureResponse);
  rpc StartQkd(StartRequest) returns (StartResponse);
  rpc StopQkd(StopRequest) returns (StopResponse);
  rpc GetStatus(StatusRequest) returns (StatusResponse);
  rpc StreamTelemetry(TelemetryRequest) returns (stream Telemetry);
  rpc GetKeys(KeysRequest) returns (KeysResponse);
  rpc SetDecoyProfile(DecoyProfile) returns (Ack);
  rpc Calibrate(CalibrationRequest) returns (CalibrationResult);
  rpc Shutter(ShutterRequest) returns (Ack);
  rpc FirmwareUpdate(FirmwareChunk) returns (Ack);
}

message ConfigureRequest {
  string mode = 1; // "BB84_TIME_BIN", "FREQ_BIN", "ENT_PILOT"
  double wavelength_nm = 2; // default 1550.0
  double symbol_rate_MHz = 3; // 100–250
  double divergence_urad = 4;
  bool use_spad = 5; // if false, SNSPD
  bool ptp_enable = 6;
}
message ConfigureResponse { string session_id = 1; }

message StartRequest { string session_id = 1; }
message StartResponse { bool started = 1; string msg = 2; }
message StopRequest { string session_id = 1; }
message StopResponse { bool stopped = 1; }

message StatusRequest {}
message StatusResponse {
  string lock_state = 1; // UNLOCKED, COARSE, FINE, LOCKED
  double qber_pct = 2;
  double sifted_rate_cps = 3;
  double secure_rate_cps = 4;
  double jitter_ps = 5;
  double atm_loss_db_per_km = 6;
  string pat_state = 7;
  string interlock_state = 8;
  bool shutter_open = 9;
  bool fog_failover_active = 10;
  bool leo_backup_active = 11;
}

message TelemetryRequest { int32 period_ms = 1; }
message Telemetry {
  uint64 ts_unix_ns = 1;
  double photon_counts_cps = 2;
  double qber_pct = 3;
  double sifted_rate_cps = 4;
  double secure_rate_cps = 5;
  double jitter_ps = 6;
  double frequency_drift_Hz = 7;
  double atm_loss_db_per_km = 8;
  string pat_state = 9;
  string interlock_state = 10;
  double temperature_c = 11;
  double fog_optical_depth = 12;
  double mmwave_link_margin_db = 13;
  double leo_rtt_ms = 14;
}

message KeysRequest { string session_id = 1; int32 max_bytes = 2; }
message KeysResponse { bytes key_material = 1; uint64 lifetime_s = 2; }

message DecoyProfile {
  string session_id = 1;
  double mu_signal = 2;  // 0.4–0.6
  double mu_decoy = 3;   // 0.05–0.1
  double vacuum_prob = 4; // 0.05–0.2
}
message CalibrationRequest { string type = 1; }
message CalibrationResult { bool ok = 1; string report = 2; }

message ShutterRequest { bool open = 1; }
message FirmwareChunk { bytes data = 1; bool last = 2; }
message Ack { bool ok = 1; string msg = 2; }
```

## QBER Guard Bands

| Metric | Threshold | Action |
| --- | --- | --- |
| QBER ≤3% | Nominal | Continue secure key extraction |
| 3% < QBER ≤5% | Investigate | Tighten PAT loop, verify alignment and background suppression |
| 5% < QBER ≤11% | Degraded | Reduce key release rate, run enhanced finite-key estimation |
| QBER >11% | Hard stop | Trigger shutter close, alert NOC, require manual override |

## Register Map
| Address | Name | Access | Description |
| --- | --- | --- | --- |
| 0x00 | SYS_ID | RO | Build identifier and version |
| 0x04 | SYS_STATUS | RO | Bitfield: lock state, PTP, shutter, interlock, alarm |
| 0x10 | TDC_CTRL | R/W | Enable, bin-size select (10/20 ps), channel mask |
| 0x14 | TDC_FIFO | RO | Event timestamp readout pointer |
| 0x20 | MOD_CTRL | R/W | EOM/MZM bias, phase setpoints, symbol rate divider |
| 0x24 | DECOY_CTRL | R/W | μ_signal, μ_decoy, vacuum probability (scaled ints) |
| 0x30 | QRNG_STAT | RO | Entropy estimator and health flags |
| 0x40 | DET_BIAS | R/W | SNSPD/SPAD bias DACs with guard rails |
| 0x44 | PWR_MON | RO | Optical power taps and thresholds |
| 0x50 | SHUTTER_CMD | R/W | 0 = close, 1 = open (requires interlock OK) |
| 0x60 | FSM_CTRL | R/W | FSM loop gains, offsets, range limits |
| 0x64 | GIMBAL_CTRL | R/W | Az/El setpoints and rates |
| 0x70 | TEMP_CTRL | R/W | TEC setpoints, fans, heaters |
| 0x7C | ALARM_MASK | R/W | Enable/disable specific trips for testing |

## Manufacturing Bill of Materials (BOM)
- Optics: 80 mm TX telescope (100 µrad divergence), 150 mm RX telescope, FSM (±2 mrad, 1 kHz), 2-axis gimbal (50 µrad repeatability), dual 1550 nm filters (0.7 nm FWHM, OD6), dichroics (1000 nm split), heated AR window
- Photonics: Ultra-stable ECL/DFB laser (≤1 kHz linewidth), LiNbO3 phase and MZM modulators, VOA, 1 µs AOM kill, 0.20 m MZI, 5-channel 25 GHz AWG/microring
- Detection: SNSPD (80% efficiency, 20 ps jitter, ≤100 cps dark), optional SPAD module (30% efficiency, 150 ps jitter, 5 kcps dark)
- Timing: GNSS OCXO (PTP Profile A/B), 4-channel 10 ps TDC
- Compute & Security: Mid-range FPGA with SERDES, 8-core SoC (16 GB RAM), QRNG (vacuum or BS shot-noise), TPM 2.0, HSM
- Power & Mechanics: 500 W 48 VDC PSU, 500 Wh UPS, IP65 optical head, 6U rack chassis

## Factory Test Plan
**Fixtures**: Beam collimator with phase plate, fog/rain chamber (0–40 dB), VOA (up to 50 dB), vibration table, −20 to +50 °C thermal chamber.

| Test ID | Description | Pass Criteria |
| --- | --- | --- |
| T01_laser_lock | PDH sweep; verify lock ≤90 s with linewidth ≤1 kHz | Lock ≤90 s, linewidth ≤1 kHz |
| T02_modulator_characterization | Measure Vπ vs. temperature; map phase bias | Visibility ≥95% |
| T03_detector_characterization | Measure PDE, jitter, DCR; gate SPAD; cool SNSPD | SNSPD PDE ≥70%, jitter ≤30 ps, DCR ≤100 cps |
| T04_tdc_linearity | INL/DNL with pulse generator | INL ≤10 ps, DNL ≤5 ps |
| T05_pat_acquire_track | Acquire from 100 µrad offset; track 30 min | Acquire ≤1 s, RMS ≤3 µrad |
| T06_qkd_emulation_25db | 25 dB path loss; run decoy BB84 @250 MHz | QBER ≤3%, secure ≥80 kb/s |
| T07_fog_failover | 20 dB/km equivalent; check shutter park + mmWave failover + LEO heartbeat | Shutter ≤100 ms, failover notify ≤2 s, LEO RTT telemetry <80 ms |
| T08_eye_safety | Verify IEC 60825-1 Class 1M; interlock trips | Class 1M, mispoint trip true |
| T09_burn_in | 72 h drift log | QBER drift ≤1%, zero lock drops |

## Site Acceptance Test
1. Rooftop survey and mount
2. Boresight using visible beacon
3. Auto-tune FSM
4. Time-bin phase lock
5. Frequency reference trim
6. QKD trial with 15 dB path (QBER ≤3%)
7. Telemetry export to SRv6
8. Safety interlock verification

**Acceptance metrics**: QBER ≤3%, sifted rate ≥100 kcps, secure rate ≥50 kb/s, jitter ≤50 ps

## Calibration Playbook
- **Daily**: Quick time-bin phase sweep, PAT model refinement
- **Weekly**: Frequency reference trim, detector bias map
- **Monthly**: QRNG entropy audit, safety interlock test

## Math Sanity Checks
- **Link budget example**: 3.2 km FSO, total loss 19.6 dB (1.6 dB atmospheric + 4.0 dB optics coupling + 4.0 dB pointing + 10 dB fade margin)
- **Secure key rate example**: 250 MHz, μ=0.5, 25 dB channel loss, 0.8 detector efficiency, 0.7 coupling ⇒ detection probability 8.85×10⁻⁴, raw clicks 2.213×10⁵ cps, sifted 1.106×10⁵ cps, QBER 2%, secure ≈79 kb/s
- **Timing budget**: SNSPD 20 ps, TDC 10 ps, clock skew 15 ps ⇒ combined RMS 27 ps

## Security Policies
- Decoy states and finite-key analysis mandatory
- Classical authentication via PQC MAC or pre-shared keys
- MDI hub operation allowed
- Detector blinding defenses: watchdogs, power monitors, randomized attenuator
- Trojan-horse mitigation: input isolators, power taps, alarms
- Telemetry and firmware must be cryptographically signed

## Wi-Fi 7 & 6G Integration Profile
- Wi-Fi 7: multi-link operation backhaul, automated frequency coordination, optional TSN bridge, DSCP preservation for quantum metadata
- 6G: FR3 support, optional sub-THz short hops, NTN handover, IAB small-cell backhaul, optional RIS panels, JCAS hooks, timing via PTP 1588 + IEEE 802.1Qbv

## Compliance Targets
- Laser: IEC 60825-1 Class 1M
- Safety: IEC 61010 or 62368
- EMC: CISPR 32/35
- Environmental: HALT/HASS subset plus MIL-STD-810-like regimen

## Risks & Mitigations
- Cryocooler vibration driving phase noise → mechanical isolation + control notch filters
- Interferometer thermal drift → athermal spools, active phase lock, temperature feed-forward
- Urban background light → narrow filters, small FoV, time gating
- Modulator/detector supply chain → dual sourcing and SPAD fallback BOM

## Deliverables
- Codex YAML spec
- Embedded proto API
- Register map
- Manufacturing BOM
- Factory test plan
- Site acceptance test
- Calibration playbook
- Security policies
- Wi-Fi 7 / 6G profile

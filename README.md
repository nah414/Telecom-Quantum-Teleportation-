Quantum Communications
# Quantum Communications Hardware Sensor (QCHS)
**Version:** 0.2b — Chicago Pilot  
**Project:** Advanced Communications — Fiber‑Free, Quantum‑Ready

This repository contains a complete, factory‑oriented specification for a rooftop/rack‑deployable quantum communications sensor capable of DV‑QKD (decoy BB84), time/frequency bin experiments, and entanglement pilots over free‑space optical (FSO) links. It integrates with Wi‑Fi 7 and is forward‑compatible with 6G (FR3/NTN/IAB).

---

## Contents

- `qchs_spec.yaml` — **Primary Spec**: hardware, firmware/software, APIs, register map, BOM, test plans, calibration, security, Wi‑Fi 7/6G profile, sanity checks.
- Embedded `.proto` API — gRPC control surface (see `proto_api` section of YAML).
- Register map & offsets for FPGA/TDC/modulator control (see `register_map`).
- Factory Test Plan and Site Acceptance Test templates.

---

## Quick Start (Engineering)

1. **Import the spec**  
   Load `qchs_spec.yaml` into your build/config tools. The file is structured for programmatic parsing (YAML parsers) and human review.

2. **Spin the control surface**  
   Extract the `proto_api` section into `proto/qchs/v1/qchs.proto`, then:
   ```bash
   protoc --go_out=. --go-grpc_out=. proto/qchs/v1/qchs.proto
   # or
   protoc --python_out=. --grpc_python_out=. proto/qchs/v1/qchs.proto


# Quantum Interconnect – DCQ Bridge Starter

This repository bundles the Quantum Communications Hardware Sensor (QCHS) specification with a
reference Dual-Clocking-Qubits (DCQ) bridge loop. The bridge enforces the published guard rails for
μ, repetition rate, phase trims, and QBER while coordinating with a planning plugin over gRPC. Use
these assets as a lab/CI baseline before wiring the production controller, telemetry, and
orchestration stack.

## What's inside

- `docs/qchs_spec.md` – factory-ready hardware/firmware/API specification for the rooftop/rack
  QCHS unit.
- `proto/dcq_plugin.proto` – shared DCQ planning service contract.
- `bridge/dcq_plugin.py` – heuristic plugin that exercises the contract without a full planner.
- `bridge/qcs_dcq_bridge.py` – safety-gated adapter between the QCHS controller and a DCQ plugin.
- `configs/lab_snsdp.yaml` – reference configuration (TLS, guard rails, SRv6/DSCP hints).
- `mkdocs.yml` & `docs/` – source for the published documentation set.

## Requirements

- Python 3.10 or newer.
- `grpcio`, `grpcio-tools`, `protobuf`, and `PyYAML` for the reference runtime.

Create and activate a virtual environment, then install the runtime dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install grpcio grpcio-tools protobuf pyyaml
```

## Generate protobuf stubs

The bridge and sample plugin expect the generated Python stubs to live on `PYTHONPATH`.

1. Compile the bundled DCQ service definition:

   ```bash
   python -m grpc_tools.protoc \
     --proto_path=proto \
     --python_out=. \
     --grpc_python_out=. \
     proto/dcq_plugin.proto
   ```

2. Compile the QCS control schema used by your hardware controller. The repository only ships the
   DCQ contract; point `--proto_path` at the location where your `qcs_control.proto` (or equivalent)
   resides so the bridge can import `qcs_control_pb2` and `qcs_control_pb2_grpc`.

Place the generated modules somewhere on the bridge's import path (e.g., the repository root or an
installed package).

## Run the sample loop

Launch the heuristic planner and the bridge in separate terminals after generating the stubs (commands should be executed inside
`quantum-interconnect-hybrid/`):

```bash
# Terminal 1 – start the sample DCQ planner
python -m bridge.dcq_plugin --listen 0.0.0.0:7700 --verbose

# Terminal 2 – run the bridge daemon against the sample configuration
python -m qcsd --config configs/lab_snsdp.yaml --verbose

# (Optional) install in editable mode from ``quantum-interconnect-hybrid/``
# to expose the ``qcsd`` console command on PATH
python -m pip install -e .
qcsd --config configs/lab_snsdp.yaml --verbose
```

The bridge continuously pulls telemetry from the QCHS controller, calls `PlanCycle` on the planner,
clamps the overrides to the configured guard rails, and applies them through the QCHS API. If the
observed QBER crosses the 11 % hard ceiling the bridge halts keying and parks the shutter until the
channel recovers.

## Documentation

The MkDocs site includes the full QCHS specification, the DCQ bridge guide, and supporting
references. To preview locally:

```bash
python -m pip install mkdocs mkdocs-material
mkdocs serve
```

## Repository layout

```
quantum-interconnect-hybrid/
├─ bridge/
│  ├─ __init__.py
│  ├─ dcq_plugin.py
│  └─ qcs_dcq_bridge.py
├─ configs/
│  └─ lab_snsdp.yaml
├─ docs/
│  ├─ dcq_plugin.md
│  ├─ qchs_spec.md
│  └─ REFERENCES.md
├─ mkdocs.yml
├─ pyproject.toml
├─ proto/
│  └─ dcq_plugin.proto
└─ README.md
```

Use this scaffold as a starting point for integrating the DCQ planning loop with your production
QCHS deployment.

# thermal/

Thermal respiratory sensing proof of concept (contactless breathing monitor for NICU infants).
Simulation-first and hardware-ready: the whole pipeline is validated on a physics-based synthetic
thermal video and runs unchanged on a recorded `.npz` or a real Lepton once a camera exists.

**Read `THERMAL_SPEC.md` first.** It is the living spec and session log (status, decisions, open issues).
Everything here is SYNTHETIC until real hardware recordings exist.

## Run the demo (one command)

```bash
pip install -e ".[dev]"          # Python 3.11+
python scripts/run_synthetic_demo.py
```

About 10 seconds. Produces, all labeled synthetic:

- `figures/demo_summary.png`: raw signal, filtered signal, estimated vs true rate, apnea flags vs truth, control ROI
- `figures/demo_report.md`: the numbers, plus the spec's Section 9 acceptance checklist
- `data/demo_processed.npz` (gitignored): the Section 7 processed output for the fusion/CNN teammates;
  read it with `thermal.pipeline.load_processed`

```bash
python -m pytest                 # all tests
```

Other scripts: `scripts/sweep_ambient.py` (incubator temperature study), `scripts/phase3_report.py`,
`scripts/phase4_report.py` (accuracy studies). Raw recordings of real people go in `data/` only
(gitignored, never commit them).

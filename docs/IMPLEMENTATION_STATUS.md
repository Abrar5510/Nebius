# Implementation status

Last updated: **2026-10-30** · version `0.1.0`

This document exists so judges, collaborators and future maintainers can tell the
difference between a working stage, a wired-but-unexercised live adapter, and a
placeholder. The project is currently a **Phase 1** implementation of
[BUILD_PLAN.md](BUILD_PLAN.md).

Legend:

- **Mock** — runs locally with synthetic data and produces production-shaped artifacts.
- **Wired** — real client or boundary exists, but needs credentials, a GPU, a mesh or an
  external extractor; it fails explicitly if the dependency is missing.
- **Planned** — contract or manifest exists, but the compute/model is not implemented.

---

## Phase matrix

| Phase | Build-plan scope | Status | Evidence |
|---|---|---|---|
| 1 | Infra, orchestrator, dummy capture through all stages | **Complete** | `showitonce demo`, 10/10 stages, SQLite, local/S3 storage, CLI, dashboard, tests |
| 2 | [A] Understand + [C] Extract on real captures | **Partial** | live Parakeet/Cosmos/Token Factory clients; external FoundationPose boundary; no GPU extractor or phone capture app |
| 3 | [B] Reconstruct with NuRec + SAM 2 | **Mock + boundary** | USDA/JSON twin, physics priors, live mesh import; no NuRec/SAM 2 job |
| 4 | [D] gripper retarget + [E] verify | **Mock** | analytic SO-101/Franka retargeter, twin checks, velocity/joint limits; no Isaac Lab replay or optimizer |
| 5 | [F] Mimic → [G] train → [H] evaluate | **Mock** | manifest counts, LeRobot-shaped dataset contract, empty safetensors adapter, ablation table; no GPU generation/training |
| 6 | Dreams + Transfer + Reason filter | **Mock** | complete manifests and counts; no Cosmos rendering, no real Reason filtering |
| 7 | Deploy to SO-101 + safety layers | **Mock** | four safety layers, dry-run report, `deployed: false`; no Jetson, drivers or arm |
| 8 | Capture app + dashboard | **Dashboard only** | responsive zero-dependency web UI; no iOS app |
| 9 | [J] Correction loop | **Planned** | no retraining or DAgger path |
| 10 | Five household tasks | **Planned** | demo is the cup place task |
| 11 | Dex-hand + SONIC humanoid | **Planned** | SO-101 and Franka only |
| 12 | [K] Skill library + adapt-on-install | **Mock library** | versioned package, privacy manifest, adapt-on-install declaration; no install-time fine-tune |

---

## Stage matrix

| Stage | Handler | Default (`mock`) | Live (`live`) | Real model / hardware |
|---|---|---|---|---|
| [A] Understand | `stages/understand.py` | Deterministic task compiler from capture metadata | Parakeet → Cosmos Reason 2 → Nemotron Ultra | Clients written; not called in this build |
| [B] Reconstruct | `stages/reconstruct.py` | USD scene + physics priors | Imports `capture.files.mesh` as USDZ | NuRec/SAM 2 not implemented |
| [C] Extract | `stages/extract.py` | Synthetic object-centric NPZ | Consumes external FoundationPose/HaMeR NPZ + JSON | GPU extractor not implemented |
| [D] Retarget | `stages/retarget.py` | Analytic object-path retargeter | Same, with live-derived demo | Isaac Lab IK/optimizer planned |
| [E] Verify | `stages/verify.py` | Analytic twin checks (success, upright, release, limits) | Same contract | Isaac Lab replay planned |
| [F] Multiply | `stages/multiply.py` | 2,042-clip manifest (Mimic/Dreams/Transfer/Reason) | Explicit error: GPU generation not implemented | GPU generation planned |
| [G] Train | `stages/train.py` | Loss curve + valid empty safetensors | Explicit error: no training image/checkpoint | GR00T training not implemented |
| [H] Evaluate | `stages/evaluate.py` | Synthetic ablation rows | Explicit error: no Isaac Lab-Arena results | Isaac Lab-Arena + real robot planned |
| [I] Deploy | `stages/deploy.py` | Safety package, `deployed: false` | Same | Jetson/runtime/drivers planned |
| [K] Library | `stages/library.py` | Versioned package + index | Same | Adapt-on-install fine-tune planned |

---

## Artifact reality check

| Artifact | Real format? | Synthetic? | Notes |
|---|---|---|---|
| `capture.json` | Yes | Yes | Same schema a phone capture will use |
| `task_spec.json` | Yes | Yes | Validated against `TASK_SPEC_SCHEMA` |
| `demo_object_centric.npz` | Yes | Yes | `(120, N, 7)` object poses, `(120, 2, 21, 3)` hands, contacts |
| `demo_so101.hdf5` | Yes | Yes | HDF5 datasets: joint positions, actions, object poses, timestamps |
| `scene.usda` | Yes | Yes | Parseable USDA scene, not an Isaac Sim render |
| `lora_so101.safetensors` | Yes | **Empty** | Zero tensors; metadata says `mock: true`. Not a trained adapter. |
| `eval.json` | Yes | Yes | Numbers are illustrative and marked synthetic |
| `skill.json` package | Yes | Yes | Checksums, privacy manifest, versioning |

---

## What is tested

`pytest -q` covers:

- every contract validator and stage ordering
- local storage round-trips, missing objects, invalid JSON and path traversal
- SQLite job creation, claiming, stage transitions, events, metadata and listing
- the full 10-stage mock DAG, artifact shapes, library version bump, idempotent reruns
- explicit failure for an unknown robot and missing live mesh
- live extract consuming an external object-centric demo
- live multiply/train/evaluate refusing to fabricate results
- Nebius Serverless Job spec, CLI command, dry run, missing CLI and config validation
- dashboard health, static files, demo POST, job polling, events, artifacts and library API
- retargeter joint/velocity bounds and safetensors header validity

`ruff check showitonce tests` is clean.

---

## Known gaps and honest risks

1. **No paid live call has been made from this repository.** Live clients are implemented
   but not verified against a real Token Factory, Cosmos or Parakeet endpoint here.
2. **No GPU stage has run.** Reconstruction, extraction, Mimic, Dreams, Transfer, GR00T
   training and Isaac evaluation are contracts and boundaries, not working model jobs.
3. **The demo evaluation table is synthetic.** It demonstrates the product surface; it is
   not evidence that a policy works.
4. **No real robot exists in this repo.** The safety package is a design artifact.
5. **Postgres is SQL-translated but only SQLite is tested locally.** A real DevPod/Postgres
   run is required before claiming cloud readiness.
6. **Automatic cloud dispatch is not wired.** `NebiusJobs` can build and submit a stage;
   the worker still executes stages locally.
7. **There is no phone app.** Capture is represented by a synthetic JSON/NPZ contract and
   a documented file layout.

The next real milestone is Phase 2: use a phone capture, run live [A] and [C], and compare
the object-centric overlay to the video. Phase 4 is the first defensible hardware claim.

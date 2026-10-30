# Show It Once

> Film yourself doing a task once on your phone. Any robot learns it.

**Track:** 4, Physical AI — real hardware footage plus simulation
**Built for:** the [Nebius x NVIDIA Global AI Hackathon](https://nebiusglobalaihackathon.devpost.com/)
**License:** Apache 2.0 (see [LICENSE](LICENSE))

Show It Once turns a single phone demonstration into a deployable robot skill. The
capture is understood, the room becomes a digital twin, the motion is extracted in an
object-centric form, retargeted to a robot, verified in simulation, multiplied into
thousands of training clips, used to train a GR00T N1.6 LoRA, evaluated, and published
to a skill library — without recording a second human demonstration.

---

## Status: Phase 1 is complete and runnable

This repository currently implements **Phase 1 of [the build plan](docs/BUILD_PLAN.md)**:
a credential-free dummy capture flows through all ten stages and produces real
artifact formats.

- **Implemented and tested locally:** the full stage DAG, SQLite/Postgres-compatible
  job store, local and S3-compatible artifact storage, orchestrator with retries and an
  append-only event stream, CLI, dashboard, skill versioning, Nebius Serverless Job
  command builder, and 55 tests.
- **Live adapters written, not exercised in this build:** Parakeet, Cosmos Reason 2 and
  Nebius Token Factory HTTP clients. They fail explicitly when configuration is missing.
- **Not implemented yet:** the iPhone capture app, GPU reconstruction/tracking jobs,
  Isaac Sim replay, real model training, real-robot deployment, and the correction loop.
  Mock mode never pretends otherwise: every synthetic artifact carries `"synthetic": true`.

See [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) for the honest
phase-by-phase matrix.

---

## What it does

1. **Capture once.** A 10-second room scan plus one narrated RGB-D demonstration.
2. **Compile the task.** Parakeet transcribes the narration; Cosmos Reason 2 reads the
   video; Nemotron Ultra emits a machine-checkable task spec.
3. **Rebuild the room.** The phone mesh becomes a USD twin with per-object physics priors.
4. **Extract what happened to the objects.** Not human joint angles: object poses,
   hand keypoints, contact events and grasp/release times.
5. **Retarget to a robot.** SO-101 and Franka profiles turn the object path into joint
   trajectories and gripper commands.
6. **Verify before training.** The twin checks success predicates, velocity limits and
   joint limits; nothing moves on without passing.
7. **Multiply one demo.** Isaac Lab Mimic, Cosmos Predict 2.5 (GR00T-Dreams), Cosmos
   Transfer 2.5 and a Cosmos Reason 2 filter produce 2,042 training clips in the mock run.
8. **Train a per-skill LoRA.** GR00T N1.6 is the base policy; each skill is a small,
   swappable adapter.
9. **Evaluate every data addition.** Held-out pose, instance, lighting and scene axes feed
   the ablation table. Real-robot trials remain explicitly pending.
10. **Publish safely.** The skill package ships with four safety layers, a twin dry run,
    and physical deployment still gated on a human and an e-stop.

---

## Quick start (no credentials, no GPU)

Requires Python 3.11+.

```bash
git clone https://github.com/Abrar5510/Nebius.git
cd Nebius

python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

showitonce demo          # seed a synthetic capture, run all 10 stages
showitonce serve         # dashboard at http://127.0.0.1:8765
```

`showitonce demo` completes in well under a second and publishes `place-cup` `0.1.0`.
The dashboard adds a small pause between mock stages so the timeline is visible; pass
`--pace 0.4` to the CLI for the same effect. Both poll the same SQLite job store and
artifact API.

Run the checks:

```bash
pytest -q
ruff check showitonce tests
showitonce check
```

---

## Commands

| Command | What it does |
|---|---|
| `showitonce demo [--robot so101] [--pace 0.4] [--no-run] [--json]` | Seed a synthetic capture and run the whole DAG |
| `showitonce submit CAPTURE_ID [--run]` | Queue an existing capture |
| `showitonce run JOB_ID [--stage NAME]` | Run a queued job, or exactly one stage |
| `showitonce status JOB_ID [--json]` | Print the stage table and summaries |
| `showitonce events JOB_ID [--after N]` | Read the append-only event stream |
| `showitonce jobs` / `showitonce captures` | List recent work |
| `showitonce library [--json]` | Show published skills and versions |
| `showitonce worker [--once] [--poll 2]` | Poll the queue and execute jobs |
| `showitonce stage NAME --job JOB_ID` | Serverless Jobs entrypoint for one stage |
| `showitonce serve [--host H] [--port 8765]` | Start the dashboard |
| `showitonce check` | Print mode, storage, database and stage health |

Global overrides: `--data-dir PATH`, `--mode mock|live|auto`.

---

## Architecture

```
phone capture ──► [A] Understand ──► [B] Reconstruct ──► [C] Extract motion
                       │                    │                    │
                       └──────────► [D] Retarget per robot ◄─────┘
                                            │
                                     [E] Verify in twin
                                            │
                          ┌─────────────────┴─────────────────┐
                          ▼                                   ▼
                  [F] Multiply 1 → 2,042            [H] Evaluate / ablation
                          │                                   ▲
                  [G] Train GR00T LoRA ───────────────────────┘
                          │
                  [I] Deploy + 4 safety layers
                          │
                  [K] Versioned skill library
```

Every stage reads and writes through the same storage interface. Locally that is a
directory; on Nebius it is S3-compatible Object Storage. Job state is a Postgres-compatible
schema, backed by SQLite for development. The orchestrator can run in-process, as a
polling worker, or expose a single stage as a Serverless Job entrypoint.

### Repository layout

```
showitonce/
  contracts.py       versioned schemas + stage definitions (A–K)
  orchestrator.py    stage DAG, retries, events, worker
  jobs.py            SQLite/Postgres job store
  storage.py         local filesystem + Nebius S3 storage
  artifacts.py       NPZ / HDF5 / safetensors / USDA writers
  robots.py          SO-101 and Franka profiles + analytic retargeter
  stages/            one module per build-plan stage
  clients/           Parakeet, Cosmos Reason 2, Token Factory HTTP clients
  nebius.py          Serverless Job spec, submit and status
  web/               zero-dependency dashboard + JSON API
tests/               55 tests across contracts, storage, jobs, DAG and HTTP API
docs/BUILD_PLAN.md   the product and build-order source of truth
```

### Artifacts are real formats

Mock mode is not a slideshow. A run writes:

- `demo_object_centric.npz` — object poses `(T, N, 7)`, 21-keypoint hands, contacts, times
- `demo_{robot}.hdf5` — joint positions, actions, object poses and timestamps
- `lora_{robot}.safetensors` — a **valid but empty** adapter file whose metadata says
  `mock: true`; it is packaging plumbing, not a trained model
- `scene.usda` — a USD scene with the room, table and tracked objects
- `task_spec.json`, `verification.json`, `eval.json`, ablation Markdown, safety report
- `library/{skill}/{version}/skill.json` plus the packaged demo, LoRA, verification,
  evaluation and deployment artifacts

The synthetic evaluation numbers are illustrative. They are marked
`"synthetic": true` and must never be presented as measured robot performance.

---

## NVIDIA models and Nebius services

| Model / service | Code path | Role in the product | This build |
|---|---|---|---|
| **Nebius Token Factory — Nemotron Ultra** | `stages/understand.py` | Compile narration + video analysis into a task spec | Live client; not called without a key |
| **Nebius Token Factory — Nemotron Nano/Super** | `clients.status_line()` | One warm status line per stage | Live client; mock uses the stage summary |
| **NVIDIA Parakeet** | `clients/ParakeetClient` | Transcribe the phone narration | Live client |
| **NVIDIA Cosmos Reason 2** | `clients/CosmosReasonClient` | Video understanding, physics priors, clip filtering, runtime safety monitor | Client + stage boundary; mock emits the same manifests |
| **NVIDIA Cosmos Predict 2.5 (GR00T-Dreams)** | `stages/multiply.py` | Generate new behaviours and environments | Manifest + counts; GPU generation is future work |
| **NVIDIA Cosmos Transfer 2.5** | `stages/multiply.py` | Photoreal sim-to-real variants | Manifest + counts; GPU rendering is future work |
| **NVIDIA GR00T N1.6** | `stages/train.py` | Base policy for a per-skill LoRA | Training contract + empty adapter; real training is future work |
| **NVIDIA Isaac Lab / Lab-Arena** | `stages/verify.py`, `evaluate.py` | Twin replay, held-out evaluation | Analytic mock checks with the production report shape |
| **Nebius Serverless Jobs** | `nebius.py`, `showitonce stage` | Run each GPU stage as a container | Command builder, submit, status, dry run |
| **Nebius Object Storage** | `storage.S3Storage` | Artifacts shared by phone, jobs and dashboard | S3-compatible client |
| **Nebius AI Cloud (Postgres/DevPod)** | `jobs.SqlJobStore` | Durable job state and orchestration | Postgres-compatible SQL, SQLite locally |

**Model routing:** the hard reasoning call (task compilation) goes to Nemotron Ultra,
while high-volume status lines go to Nano/Super. Cosmos owns anything that requires
physical-world video understanding; GR00T owns the robot policy. Switching tiers is a
one-word change because every model is behind one OpenAI-compatible client.

**Where Token Factory accelerated development:** it removes the need to host or tune a
reasoning model during iteration. The live path resolves Nemotron model IDs from the
Token Factory catalog at runtime, so no model ID is hard-coded. The current Phase 1
build does not make a paid live call by default; set a key and `SHOWITONCE_MODE=live`
to exercise it.

---

## Live mode and Nebius setup

```bash
cp .env.example .env
# fill in NEBIUS_API_KEY, COSMOS_REASON_URL, PARAKEET_URL, S3 settings
SHOWITONCE_MODE=live showitonce demo
```

`auto` mode selects live only when `NEBIUS_API_KEY` or `COSMOS_REASON_URL` is present.
`SHOWITONCE_EXECUTION=nebius` additionally requires `SHOWITONCE_JOB_IMAGE` and
`NEBIUS_SUBNET_ID`; `showitonce.nebius.NebiusJobs` can build, dry-run, submit and poll
a stage container. Automatic per-stage cloud dispatch is deliberately not wired into the
local worker yet — the stage entrypoint (`python -m showitonce stage ...`) is ready for it.

Storage moves from the local filesystem to Nebius Object Storage with:

```bash
SHOWITONCE_STORAGE=s3
NEBIUS_S3_BUCKET=...
NEBIUS_S3_ENDPOINT=https://storage.eu-north1.nebius.cloud
```

No secret is committed. `.env` is gitignored.

---

## Safety and privacy

- Raw video never enters a skill package. The package contains the object-centric demo,
  task spec, adapter, verification, evaluation and deploy report.
- The deploy stage refuses to mark a skill deployed. It records `"deployed": false` and
  requires a human-confirmed physical e-stop before any real motion.
- The dashboard and API bind to `127.0.0.1` by default and only serve artifact keys under
  `jobs/`, `captures/` and `library/`.
- Live failures are explicit: a missing mesh, missing extractor output or missing GPU
  job raises a stage error rather than fabricating a result.

---

## What is intentionally not here

This is an honest Phase 1, not a recorded hardware demo:

- no Swift/ARKit capture app
- no NuRec/SAM 2/FoundationPose/HaMeR GPU jobs
- no Isaac Sim replay or trajectory optimizer
- no real Cosmos, GR00T or Parakeet calls in the default path
- no trained LoRA, no real robot, no measured success rate
- no correction loop [J]

The next milestone in the build plan is Phase 2: run [A] and [C] on a real phone
capture and check the object-centric overlay against the video. Phase 4 — a verified
SO-101 demo from a phone video — is the core technical breakthrough.

---

## Documentation

- [Build plan](docs/BUILD_PLAN.md) — product, architecture, stages, risks
- [Implementation status](docs/IMPLEMENTATION_STATUS.md) — what is mock, live or missing
- [Hackathon guide](docs/HACKATHON_GUIDE.md) — rules and submission checklist
- [Submission draft](docs/SUBMISSION.md) — Devpost form copy

Built during the submission period, Aug 26 – Oct 30, 2026.

# Devpost submission draft

> **Status:** Phase 1 software demo, 2026-10-30. Fill the URLs below and record the video
> before submitting. Track 4 requires **at least one minute of real hardware operating**
> (or, if no hardware, the key software modules in action); the current repository has no
> hardware footage. Do not submit a video that implies a real robot ran when it did not.

Deadline: **Fri Oct 30, 2026, 10:00 AM PT = 10:00 PM PKT.** Submit, don't just save a draft.

---

## Form fields

**Project name:** Show It Once

**Track:** Physical AI (Track 4)

**Demo URL:** _TODO — run `showitonce serve` on a public host. Not required for Physical AI._

**YouTube video URL:** _TODO — public, under 3:00._

**Repository URL:** _TODO — public GitHub repo; Apache-2.0 visible in About._

**Description (what, why, how):**

Show It Once turns one phone demonstration into a deployable robot skill. Robot learning
today starts with hundreds of teleoperated demonstrations and a lab setup. Show It Once
starts with a person doing the task once, narrating as they go.

A phone captures a 10-second room scan and one RGB-D video. The pipeline then:

1. **Understands** the task with Parakeet ASR, Cosmos Reason 2 video understanding and
   Nemotron Ultra on Nebius Token Factory. The result is a machine-checkable `task_spec.json`.
2. **Reconstructs** the room as a USD digital twin with per-object physics priors.
3. **Extracts** an object-centric demo: 6-DoF object poses, hand keypoints, contacts and
   grasp/release events — not human joint angles. This is what makes the demo portable
   across robots.
4. **Retargets** the object path to an SO-101 or Franka trajectory and verifies it against
   the task's success predicates inside the twin.
5. **Multiplies** the verified demo with Isaac Lab Mimic, Cosmos Predict 2.5 (GR00T-Dreams),
   Cosmos Transfer 2.5 and a Cosmos Reason 2 filter. The mock run produces 2,042 clips.
6. **Trains** a per-skill GR00T N1.6 LoRA, **evaluates** every data addition on held-out
   pose/instance/lighting/scene axes, and **publishes** a versioned skill package.
7. **Deploys** with four safety layers: a hard motion envelope, a Cosmos Reason 2 runtime
   monitor, a twin dry run, and a physical e-stop. The package reports `deployed: false`
   until a human confirms the e-stop.

The current submission is a **Phase 1** implementation: all ten stages run end to end in
credential-free mock mode and write real NPZ, HDF5, USDA, safetensors, JSON and Markdown
artifacts. The dashboard shows the live stage timeline, event stream, metrics, ablation
table and skill library. Live NVIDIA clients and the Nebius Serverless Job seam are
implemented but not exercised with paid credentials or GPUs in this build.

**Who it's for:** a robotics developer or small lab that owns an arm but cannot afford a
teleoperation lab, and later a home user who wants to teach a household robot by showing
it a task once.

**What's next:** run Phase 2 on a real phone capture (live [A] and [C]), then Phase 4 —
a verified SO-101 demo from a phone video — and finally the real-robot safety pilot.

**Testing instructions:** No login. Run locally with no credentials:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
showitonce demo
showitonce serve   # http://127.0.0.1:8765
```

The mock run is deterministic and needs no API key. `showitonce check` prints configuration
health. `pytest -q` runs the test suite.

**Existed before Aug 26, 2026?** No.

**City (Builders & Brews):** none

---

## About the project (Devpost story)

> Paste this into Devpost's **About the project** field. Markdown and LaTeX are supported.

# Show It Once

> **Film yourself doing a task once on your phone. Any robot learns it.**

**Track 4: Physical AI** · Built for the NVIDIA × Nebius Global AI Hackathon

## Inspiration

The moment that started this project was not a robot demo. It was watching someone teach a friend to fold a fitted sheet: one attempt, a bit of narration, a correction, done. No teleoperation rig, no motion-capture lab, no dataset. That is how humans transfer manipulation skill — and it is nothing like how robots learn today.

The robotics stack has the opposite shape. To teach one arm one task you need a lab, a rig, a trained operator, and hours of setup. The output is a few seconds of joint trajectories that belong to that arm and no other. The bottleneck is not model capacity; it is demonstrations. And demonstrations are expensive precisely because they are recorded in the wrong coordinate system: the robot's joints.

A phone sees something different. It sees objects moving in a room. If the demonstration is recorded as object poses, contacts, and grasp/release events, the data stops being about a human hand and starts being about the task. That representation can be retargeted to any embodiment. The phone in every pocket becomes the data collection rig, and the object becomes the interface between human and robot.

The timing made it possible for one person to attempt: NVIDIA's Cosmos models can imagine and filter physical outcomes, GR00T provides a robot foundation policy to adapt, and Nebius provides Token Factory and serverless GPU capacity without owning a cluster.

## What it does

Show It Once turns a single phone demonstration into a deployable robot skill:

1. **Capture** — a ten-second room sweep plus one narrated demonstration: RGB-D, ARKit poses, LiDAR mesh, audio.
2. **Understand** — narration and video become a machine-checkable task spec: objects, subtasks, constraints, success predicates.
3. **Extract** — hands and objects are tracked in 3D; the demo is stored object-centrically, not as human joint angles.
4. **Retarget and verify** — the object path is converted to the target robot's kinematics and replayed in a digital twin of the user's room. A demo that fails the twin never reaches training.
5. **Multiply and train** — one verified demo becomes thousands of Mimic, Cosmos Predict, and Cosmos Transfer variations, then a GR00T N1.6 LoRA.
6. **Deploy, correct, share** — the skill runs on a Jetson behind four safety layers, improves from filmed corrections, and can be published to a library that adapts to another user's room.

The same capture can target an SO-101 arm, a Franka, or a humanoid; only the retargeting stage changes.

## How I built it

Show It Once is a stage DAG, not a monolithic script. Ten stages — Understand, Reconstruct, Extract, Retarget, Verify, Multiply, Train, Evaluate, Deploy, Library — each read artifacts from storage and write new artifacts back. A stage never reaches into another stage's memory. That boundary lets the GPU-heavy steps run as independent Nebius Serverless Jobs and lets a failed job resume where it stopped.

The contracts came first. `contracts.py` defines and validates the capture, task spec, object-centric demo, and every stage output. A task is

$$\mathcal{T} = (\mathcal{O}, \mathcal{S}, \Phi, \mathcal{C})$$

— objects, subtasks, success predicates, and physical constraints. The demonstration is not a trajectory of human joints; it is a set of object poses over time,

$$\mathcal{D} = \left\{\left(T_t^{o} \in SE(3),\, \kappa_t^{o}\right)\right\}_{o \in \mathcal{O},\, t=1..T}$$

where $\kappa_t^o$ marks hand–object contact. Everything downstream consumes $\mathcal{D}$, which is why the embodiment can change without re-recording.

Retargeting solves for joint trajectories that put the robot's gripper where the object was:

$$q_{1:T}^{\star} = \arg\min_{q_{1:T}} \sum_{t=1}^{T} \left\| \mathrm{FK}(q_t) - T_t^{\star} \right\|_F^2 + \lambda \sum_{t=1}^{T-1} \left\| q_{t+1} - q_t \right\|_2^2$$

subject to joint, velocity, and force limits. The verifier is a hard gate rather than a score:

$$\text{pass} \iff \bigwedge_{\phi \in \Phi} \phi\!\left(\mathrm{rollout}_{\text{twin}}(q_{1:T}^{\star})\right).$$

Only after that gate does the multiplier run. Training adds a low-rank adapter per skill instead of rewriting the policy:

$$W' = W + \frac{\alpha}{r}BA, \qquad B \in \mathbb{R}^{d \times r},\; A \in \mathbb{R}^{r \times k},\; r \ll \min(d,k).$$

Evaluation is designed as an ablation, not a single number. For each axis $k$ — pose, instance, lighting, scene — with $N$ trials,

$$\hat{p}_k = \frac{1}{N}\sum_{i=1}^{N}\mathbf{1}[s_{k,i}], \qquad \Delta_k = \hat{p}_k - \hat{p}_{k-1},$$

so every data source has to earn its place.

On the live path, Nemotron Nano writes the one-line stage statuses the app shows, Nemotron Ultra compiles the task spec and parses spoken corrections, Parakeet transcribes narration, Cosmos Reason 2 judges physical plausibility and runtime safety, Cosmos Predict 2.5 and Transfer 2.5 generate and photorealize variations, and GR00T N1.6 supplies the policy that the LoRA adapts. Token Factory model IDs are resolved at runtime from `/v1/models`, so a version bump does not break the app.

Two engineering choices made this buildable in the time available. First, every stage has a deterministic mock implementation, so the full ten-stage pipeline, CLI, job store, and dashboard API run with no GPU and no credentials. That is not a demo shortcut; it forced the contracts to be precise, and the repository now has a 43-test suite covering the pipeline, API, storage, job state, and Nebius command construction. Second, live mode never fabricates: when a GPU artifact is missing, the stage fails with the exact missing path instead of inventing arrays. The mock is explicit and the seam is honest.

The orchestration layer is deliberately boring: a Postgres-compatible job table (SQLite locally), append-only events the phone or dashboard can poll, per-stage retries, and idempotent resume. A zero-dependency HTTP service exposes the job, capture, and library APIs, so the pipeline can be inspected while the GPU work runs elsewhere.

## What I learned

**The representation is the product.** The hard problem was not tracking hands; it was deciding what to throw away. Human joint angles are a dead end because they encode the demonstrator, not the task. Object-relative motion survived every embodiment change.

**Verification is what makes multiplication safe.** A data multiplier is neutral: it amplifies whatever it is given. Putting the twin gate before Mimic, Predict, and Transfer is the difference between scaling a skill and scaling a mistake.

**Mock mode is a design tool.** Writing deterministic fakes before the models existed exposed every ambiguous field in the contracts. If a fake cannot satisfy the schema, the schema is underspecified.

**Model routing is an architecture decision.** Nano belongs in the UI loop, Ultra at the rare hard reasoning steps, Cosmos Reason where physical judgment is required, and GR00T in the control loop. Putting a reasoning model in the inner loop is too slow; putting a small model on task decomposition is wrong.

**Safety belongs below the policy.** A learned policy cannot be trusted to respect a workspace boundary. The motion envelope, the Cosmos monitor, the twin dry run, and the physical e-stop are layers the policy cannot override.

## Challenges

**The embodiment gap.** A human hand is not a gripper. Copying finger motion fails immediately. The fix was to copy what happened to the object, sample grasps the target gripper can actually achieve, and let IK and the trajectory optimizer absorb the difference.

**Depth noise and scale.** Phone LiDAR is noisy at object scale. Tracking objects rather than hands, anchoring scale with depth, and allowing centimeter-level repair in the verifier turned a fragile 3D reconstruction into a usable path.

**Generative video can invent physics.** Cosmos clips sometimes warp objects or produce motion that looks right and is mechanically impossible. Strong depth and segmentation conditioning plus a Cosmos Reason 2 filter that rejects bad clips is better than averaging them into the training set.

**Sim-to-real.** A twin is never the room. Room-matched Transfer styles, domain randomization, and a correction loop that retrains on the states where the policy actually failed are the mitigation; the ablation table exists to show which one matters.

**Long-running heterogeneous jobs.** A ten-stage pipeline spanning CPU, GPU, and a robot is a distributed-systems problem disguised as a machine-learning problem. Idempotent stages, artifact contracts, and resumable job state mattered as much as any model.

**Scope.** The temptation was to build twelve embodiments and twenty tasks. I built one task — place a mug on a coaster — through every stage first, because a pipeline that finishes one task end to end teaches more than a dozen stages that almost work.

## What's next

The immediate next step is real-robot trials on the SO-101 across held-out object layouts, filling in the ablation table with success judged by Cosmos Reason 2 and confirmed by a human. After that: the native iOS capture app, dexterous-hand and humanoid retargeting through SONIC, and the skill library's adapt-on-install path, where a skill trained in one home is fine-tuned in another from a ten-second room scan.

The long-term goal is simple to state and hard to do: **make teaching a robot as casual as showing a person.**

---

## Feedback on Nebius and NVIDIA

Be specific: what you tried, what happened, what would fix it. Replace these prompts with
real observations before submitting; do not invent feedback.

- **Token Factory:** one OpenAI-compatible endpoint for every Nemotron size is the right
  shape. Model IDs are resolved from `/v1/models` at runtime, so no ID goes stale. _TODO:
  add a real call result, latency, and any friction._
- **Nebius AI Cloud (Serverless Endpoints/Jobs):** the Serverless Job CLI contract is
  captured in `showitonce/nebius.py`; the stage entrypoint is `python -m showitonce stage`.
  _TODO: add a real job submission, GPU availability notes and cost._
- **Nemotron models:** Nano/Super for status lines, Ultra for task compilation. _TODO: add
  observed quality/latency._
- **Other NVIDIA tools:** Cosmos Reason 2 for video/physics, Cosmos Predict/Transfer for
  data multiplication, GR00T N1.6 for the policy, Isaac Lab/Lab-Arena for verification and
  evaluation. _TODO: add what ran, what did not, and what would unblock it._

---

## Video outline (keep under 3:00)

The Physical AI track requires at least one minute of real hardware operating. If hardware
is not available, show the key software modules in action and say clearly that the robot
footage is simulated.

1. **0:00–0:20** Hook: teaching a robot usually takes a lab and hundreds of demos. Show one
   person filming a cup task once.
2. **0:20–1:30** Live dashboard: capture → task spec → object-centric demo → retarget →
   twin verification. Point at the real artifact files.
3. **1:30–2:20** One minute of hardware (or a clearly labelled software-only walkthrough):
   SO-101 attempting the task, safety monitor, e-stop.
4. **2:20–2:40** Ablation table: zero-shot → one demo → Mimic → Dreams → Transfer. State
   that the current numbers are synthetic if no real evaluation has run.
5. **2:40–3:00** Model routing: Token Factory Ultra/Nano, Cosmos Reason, GR00T, Nebius Jobs.
   Close on the product line: film once, any robot learns it.

No copyrighted music or third-party trademarks without permission.

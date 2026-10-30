# Show It Once: complete build plan

> Film yourself doing a task once on your phone. Any robot learns it.

**Track:** 4, Physical AI (real hardware footage plus simulation).
**Runs on:** Nebius AI Cloud (Serverless Jobs, Serverless Endpoints, DevPods, Object Storage) and Nebius Token Factory.
**NVIDIA models and tools:** Nemotron (Nano / Super / Ultra), Cosmos Reason 2, Cosmos Predict 2.5, Cosmos Transfer 2.5, GR00T N1.6, SONIC (humanoid whole-body control), FoundationPose, Parakeet ASR, Isaac Sim / Isaac Lab / Isaac Lab Mimic / Isaac Lab-Arena, Omniverse NuRec, Jetson.

---

## 1. The product

1. **Capture.** Open the phone app, sweep the room for 10 seconds (it builds a 3D scan), then do the task once while saying what you're doing.
2. **Watch it learn.** The app shows each stage live: your hand tracked, a "ghost" robot copying you, your room rebuilt in 3D, hundreds of practice runs in simulation, Cosmos variants in other rooms and lighting, training progress, and the success rate.
3. **Run it.** The skill installs on your robot (a $100-class SO-101 arm, a Franka, or a humanoid). It runs on-device on a Jetson, with a safety monitor watching.
4. **Correct it.** If the robot fumbles, film the fix or just say "grab it by the handle." It retrains on the correction.
5. **Share it.** Skills go into a library. Someone else's "fold a towel" downloads to your robot and adapts to *your* towel and *your* table.

---

## 2. System architecture

```
 PHONE APP (iOS, LiDAR)                     NEBIUS AI CLOUD                                      ROBOT
 ─────────────────────        ───────────────────────────────────────────────────────        ──────────────
 room scan (mesh+poses) ──┐   [A] Understand ── [B] Reconstruct ── [C] Extract motion         Jetson Orin/Thor
 RGB-D task video  ───────┼─►      │                  │                   │                  GR00T policy +
 narration audio ─────────┘        └──────────► [D] Retarget per robot ◄──┘                  skill LoRA
                                                      │                                       │
                                               [E] Verify in sim (digital twin)               │ telemetry,
                                                      │                                       │ failures
                                               [F] Multiply (Mimic + Dreams + Transfer)       │
                                                      │                                       ▼
                                               [G] Train (GR00T N1.6 + skill LoRA) ──────► [I] Deploy + safety
                                                      │                                       │
                                               [H] Evaluate (Isaac Lab-Arena)                 │
                                                      ▲                                       │
                                               [J] Correction loop ◄──────────────────────────┘
                                               [K] Skill library (shared, versioned)
```

Each stage is a **Serverless Job** that reads and writes **Nebius Object Storage**. One orchestrator (a Postgres `jobs` table plus a worker) moves a capture through the stages, and the app subscribes to stage updates.

---

## 3. Stages in detail

### [A] Understand: what is the task?
| Input | Model | Output |
|---|---|---|
| Narration audio | **Parakeet** (NVIDIA ASR) | transcript |
| Video + transcript | **Cosmos Reason 2** | objects, step boundaries (reach / grasp / transport / place / release), physical constraints ("keep cup upright"), visual success condition |
| All of the above | **Nemotron Ultra** (Token Factory) | `task_spec.json`: subtasks, preconditions, success predicates for sim, failure modes to watch |
| Stage events | **Nemotron Nano** | one-line human-readable status per stage for the app |

### [B] Reconstruct: build a digital twin of the room
- **Scene:** the phone's LiDAR mesh plus ARKit camera poses go through **Omniverse NuRec** (3D Gaussian reconstruction) into a USD scene for Isaac Sim, so the sim is *your* table and *your* room.
- **Objects:** **SAM 2** segments each object across frames, image-to-3D gives a mesh per object, and the mesh is scaled with LiDAR depth.
- **Physics:** Cosmos Reason 2 proposes material class (ceramic, cloth, plastic) and maps it to mass and friction priors. Sim checks these values against the observed motion and corrects them.

### [C] Extract motion: what did the human actually do?
- **Hands:** **HaMeR / WiLoR** give 3D hand meshes per frame for both hands, fused with LiDAR depth for metric scale.
- **Objects:** **FoundationPose** (NVIDIA) gives 6-DoF pose tracking for each object mesh from RGB-D.
- **Contacts:** hand-object distance plus mesh penetration tells which hand holds which object, and when.
- **Output: an object-centric demo.** The demo is recorded as object poses over time plus grasp and release events and approach directions, *not* joint angles. Because it describes what happened to the objects rather than how the human's joints moved, any robot can use it.

### [D] Retarget: turn the human demo into each robot's motion
| Robot | Method |
|---|---|
| 2-finger gripper (SO-101, Franka) | grasp pose from hand-object contact plus a gripper grasp sampler; trajectory from object path; IK |
| Dexterous hands (humanoid hands) | `dex-retargeting` from MANO hand keypoints to robot finger joints |
| Humanoid whole body (Unitree G1, Fourier GR-1) | human body pose (from the video) into **SONIC** whole-body controller for balance and locomotion, with upper-body targets from [C] |

### [E] Verify in sim: does the copied motion actually work?
- Replay the retargeted motion in the twin (Isaac Lab), checking the `task_spec` success predicates.
- If it fails, run a **local trajectory optimizer** that adjusts grasp pose and approach within a few cm and degrees of the human's motion until it succeeds.
- Output: one **verified robot demo** per embodiment. This is the gate: nothing moves on without it.

### [F] Multiply: turn 1 demo into thousands
1. **Isaac Lab Mimic / SkillGen:** randomize object poses, instances and distractors, re-plan the demo relative to each object, and keep only runs that succeed. This produces thousands of sim demos with real actions.
2. **Cosmos Predict 2.5 (GR00T-Dreams):** post-trained on your robot, it generates *new behaviors and environments* from a single image ("same task, different kitchen"). An inverse-dynamics model extracts the actions from those videos.
3. **Cosmos Transfer 2.5:** re-renders every sim demo from its depth, segmentation and edge maps into photoreal video across lighting, textures and backgrounds, including a style matched to your real room so the sim-to-real gap shrinks.
4. **Cosmos Reason 2 filter:** rejects clips with impossible physics, object warping or task failure.

### [G] Train
- **Base:** GR00T N1.6 (3B), already post-trained for the target robot.
- **Per skill:** a **LoRA adapter**, which is small, cheap to train and swappable at runtime. A robot holds many skills, and the right adapter is loaded per command.
- **Data mix:** verified demo (upweighted) plus Mimic, Dreams and Transfer data, in **LeRobot v2** format (cameras `front` and `wrist`).
- **Compute:** a Serverless Job on an 80 GB GPU for full fine-tunes, and smaller GPUs for LoRA.

### [H] Evaluate
- **Isaac Lab-Arena** runs closed-loop tests on held-out variations along separate axes: object pose, object instance, lighting, scene, and distractors.
- **Ablation table** (this is the scientific proof):

| Policy | Data | Pose | Instance | Lighting | Scene |
|---|---|---|---|---|---|
| GR00T zero-shot | none | | | | |
| + 1 verified demo | 1 | | | | |
| + Mimic | ~1k sim | | | | |
| + Dreams | + neural trajectories | | | | |
| + Transfer | + photoreal variants | | | | |
| **Real robot** | full mix | | | | |

- **Real-robot protocol:** 20 trials × 5 fixed object layouts, filmed, with success judged by Cosmos Reason 2 and confirmed by a human.

### [I] Deploy + safety
- **Runtime:** a GR00T policy plus skill LoRA on **Jetson AGX Orin / Thor**, with a **Nebius Serverless Endpoint** as cloud fallback for robots without a Jetson.
- **Robot drivers:** LeRobot (SO-101), with ROS 2 bridges for Franka and humanoids.
- **Safety layers:**
  1. Hard workspace box and joint, speed and force limits in the driver.
  2. A **Cosmos Reason 2 monitor** on the robot camera that halts the robot on a person entering the workspace, a dropped object or an unexpected state.
  3. A first-run "dry run" in the twin before the real arm moves.
  4. A physical e-stop.

### [J] Correction loop
- When a real run fails, the robot's telemetry and video are uploaded automatically.
- The user can re-film just the failing part, or say a correction. Nemotron Ultra turns spoken corrections into a constraint ("grasp at handle") applied in [D].
- Corrections are added DAgger-style (training on the states where the policy went wrong) and the skill LoRA retrains incrementally.

### [K] Skill library
- A skill package is `task_spec.json` + object-centric demo + LoRA per embodiment + eval report.
- **Adapt on install:** the new user does a 10-second room scan. [E] and [F] re-run in *their* twin and the LoRA is fine-tuned briefly. Their robot gets the skill without anyone demonstrating it again.
- **Privacy:** faces and bystanders are blurred at capture (on the phone), and raw video stays private. Only the object-centric demo and LoRA are shared, and only if the user opts in.

---

## 4. Data contracts

| Artifact | Format |
|---|---|
| Capture | `capture/{id}/rgb.mp4`, `depth/*.png`, `poses.json` (ARKit), `mesh.usdz`, `audio.wav` |
| Task spec | `task_spec.json`: objects, subtasks, success predicates, constraints |
| Human demo | `demo_object_centric.npz`: object poses (T×N×7), hand poses, contacts, events |
| Robot demo | `demo_{robot}.hdf5` (Isaac Lab format) |
| Training set | LeRobot v2 dataset |
| Skill | `skill/{name}/{version}/`: spec, demo, `lora_{robot}.safetensors`, `eval.json` |

---

## 5. Repository layout

```
showitonce/
  app/ios/            capture app (Swift, ARKit, LiDAR, Vision hand pose for live overlay)
  app/web/            dashboard: live stage timeline, skill library, robot console
  orchestrator/       jobs table, worker, stage DAG, Nebius job submission
  stages/
    understand/       Parakeet, Cosmos Reason 2, Nemotron calls
    reconstruct/      NuRec, SAM 2, object meshes, physics priors
    extract/          HaMeR/WiLoR, FoundationPose, contacts → object-centric demo
    retarget/         gripper, dex-hand, SONIC humanoid
    verify/           Isaac Lab twin replay + trajectory optimizer
    multiply/         Mimic/SkillGen, GR00T-Dreams, Cosmos Transfer, Reason filter
    train/            GR00T N1.6 + LoRA, LeRobot conversion
    evaluate/         Isaac Lab-Arena suites, ablations, real-robot protocol
  runtime/            Jetson deploy, LeRobot/ROS 2 drivers, safety monitor
  library/            skill packaging, versioning, adapt-on-install
  tests/              one check per stage: golden capture → expected artifact
```

---

## 6. Build order (by dependency)

| Phase | Build | Exit criterion |
|---|---|---|
| 1 | Nebius infra: DevPod, Object Storage, Serverless Jobs submission, orchestrator skeleton | A dummy capture flows through all stages as no-ops |
| 2 | [A] Understand + [C] Extract on your own captures | Object-centric demo matches the video (overlay check) |
| 3 | [B] Reconstruct | Isaac Sim twin visually matches the room, objects at the right poses |
| 4 | [D] gripper retarget + [E] Verify | **Verified SO-101 demo from a phone video** (the core breakthrough) |
| 5 | [F] Mimic → [G] Train → [H] Evaluate in sim | Trained policy beats zero-shot on held-out poses |
| 6 | [F] Dreams + Transfer + Reason filter | Each addition moves the ablation table |
| 7 | [I] Deploy to a real SO-101 on Jetson + safety layers | Real arm completes the task on a new layout |
| 8 | Capture app + web dashboard | Phone → robot with no terminal |
| 9 | [J] Correction loop | One failure fixed by a correction, then measured again |
| 10 | Multi-task: 5 household tasks (place, stack, pour, wipe, fold) | Ablation table for each |
| 11 | [D] dex-hand + SONIC humanoid retarget, humanoid in sim | Same phone video drives an arm *and* a humanoid |
| 12 | [K] Skill library + adapt-on-install | User B's robot runs User A's skill in User B's room |

---

## 7. Hardware

- iPhone Pro (LiDAR) for capture.
- SO-101 arm (leader + follower kit) with front and wrist cameras.
- Jetson AGX Orin (or Thor) for on-robot inference.
- Optional: Franka, or a humanoid. The Unitree G1 is covered in sim via SONIC.

---

## 8. Model routing (judges score this)

| Job | Model | Why this one |
|---|---|---|
| Stage status lines, UI chat | Nemotron Nano | high volume, low latency |
| Task spec, correction parsing, long-horizon decomposition | Nemotron Ultra | the hard reasoning, called rarely |
| Video understanding, physics plausibility, success judging, runtime safety | Cosmos Reason 2 | physical-world reasoning on video |
| New behaviors and environments | Cosmos Predict 2.5 (GR00T-Dreams) | world model as a data generator |
| Photoreal variety from sim | Cosmos Transfer 2.5 | controlled sim-to-real rendering |
| Robot policy | GR00T N1.6 + LoRA | open robot foundation model |
| Humanoid balance / whole body | SONIC | whole-body control |
| Object tracking | FoundationPose | 6-DoF from RGB-D |
| Speech | Parakeet | NVIDIA ASR |

---

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Phone depth noise corrupts the 3D path | LiDAR + ARKit poses, FoundationPose tracks objects (more stable than hands), and the trajectory optimizer in [E] absorbs cm-level error |
| Human hand ≠ robot gripper | Object-centric demos plus a grasp sampler: copy *what happened to the object*, not the fingers |
| Twin physics differs from reality | Physics priors corrected against observed motion, domain randomization in Mimic, real-robot correction loop |
| Cosmos clips warp objects | High depth/segmentation control weights plus the Reason filter |
| Policy works in sim, not real | Room-matched Transfer style, real-robot DAgger corrections, ablation by axis to find the gap |
| Unsafe motion at home | Four safety layers in [I]; never skip the twin dry run |

---

## 10. Prior work and what's new

- **Phantom, Masquerade** (Stanford): human video → robot data by painting a robot over the hand. They need lab capture setups and fixed robots, with no simulation multiplier and no product.
- **DreamGen / GR00T-Dreams** (NVIDIA): multiplies robot data with Cosmos, but **starts from teleoperation**.
- **Show It Once is new in combining all of it:**
  - a phone video from anyone as the *only* input
  - object-centric demos that work on any robot
  - a digital twin built from the user's own room
  - sim-verified retargeting
  - a three-way multiplier (Mimic, Dreams, Transfer)
  - per-skill LoRAs
  - a correction loop
  - a skill library that adapts to each new room

---

## 11. Demo video (3:00)

| Time | Shot |
|---|---|
| 0:00–0:15 | "Teaching a robot takes a lab. Watch me do it with my phone." Film the cup task once. |
| 0:15–0:50 | Live timeline: hand tracked → **ghost robot copying me** → my room rebuilt in 3D |
| 0:50–1:20 | Thousands of sim runs, then a 4×4 grid of Cosmos variants in 16 kitchens |
| 1:20–2:20 | **Real SO-101 doing the task on a layout it never saw** (the 1 minute of hardware Track 4 requires) |
| 2:20–2:40 | Same video → humanoid in sim. Ablation table. |
| 2:40–3:00 | Model routing slide (Token Factory, Nebius Jobs/Endpoints, every NVIDIA model), then the closing line |

---

## 12. Verify before Phase 1

- [ ] Nebius GPU types available for Serverless Jobs (need RTX-class or data-center GPU with rendering for Isaac Sim, and 80 GB for full GR00T fine-tunes)
- [ ] Which models Token Factory hosts (Nemotron tiers; is Cosmos Reason 2 there, or self-host on an Endpoint?)
- [ ] GR00T N1.6 SO-101 example fine-tunes on its sample dataset
- [ ] Cosmos Transfer 2.5 and Predict 2.5 checkpoints run on the chosen GPU
- [ ] NuRec → Isaac Sim import works on a phone LiDAR scan
- [ ] Licenses of HaMeR/WiLoR, FoundationPose, SAM 2 permit this use

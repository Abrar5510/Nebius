# Near Miss

**Hazard-perception training generated from your own streets.**

Record ten seconds of the road you drive every day. Near Miss uses NVIDIA Cosmos to imagine what could go wrong there next (a child running out from behind a parked rickshaw, a motorbike cutting across from a side lane), then tests whether you spot it in time.

Built for the NVIDIA x Nebius Global AI Hackathon, Track 2: Best Apps and Agents. License: Apache-2.0.

## Why

Road crashes kill about 1.19 million people a year, and 92% of those deaths are in low- and middle-income countries ([WHO, 2023](https://www.who.int/publications/i/item/9789240086517)). Countries like the UK and Australia test hazard perception before issuing a licence. In a New South Wales cohort of 20,822 novice drivers, those who failed that test at least twice had about 1.8x the crash risk of those who passed first time ([DRIVE study](https://research-repository.uwa.edu.au/en/publications/attempts-at-the-practical-on-road-driving-test-and-the-hazard-per/)).

Most of the countries with the deadliest roads have no such test. The clips that do exist are filmed on British roads, not on streets full of rickshaws, donkey carts and motorbikes coming the wrong way. Filming real near misses for every city isn't possible, but generating them now is.

## How it works

| Step | Model | Runs on | What it does |
|---|---|---|---|
| Read the street | **Nemotron 3 Nano Omni** | Nebius Token Factory | Reads keyframes of the real footage: what hides people (parked vehicles, stalls), side openings, who uses the road. |
| Plan hazards | **Nemotron 3 Ultra** + **Tavily** | Token Factory | Searches for the city's real crash causes, then writes hazards that fit *this* street and *this* city, each with the first visible clue. |
| Render hazards | **Cosmos Predict 2.5** (video2world) | Nebius Serverless Job, 1 GPU | Continues the real footage from its last frames, so the hazard grows out of the real street. |
| Answer key + QA | **Cosmos Reason 2** | Nebius Serverless Endpoint (vLLM) | Watches each stitched clip and writes when the clue appears and when the driver must react. Rejects renders that are physically implausible or where the hazard never shows. |
| Coach | **Nemotron 3 Super** | Token Factory, called live from the app | Reads your clicks across the test and explains your pattern and the one habit to fix. |

The test itself follows the UK DVSA format. The scoring window opens at the first clue and is split into five bands, scored 5 to 1. More than 8 clicks in a clip scores zero.

Model ids are resolved at runtime from Token Factory's `/v1/models` catalog, so nothing breaks when a model version changes.

## Run it

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), ffmpeg, the [Nebius CLI](https://docs.nebius.com/cli), and Node 20+ for the tests.

```bash
export NEBIUS_API_KEY=...      # Nebius Token Factory
export TAVILY_API_KEY=...
export HF_TOKEN=...            # Hugging Face, with the NVIDIA Open Model License accepted for Cosmos
uv sync
```

1. **Footage.** Put 10-second phone clips in `footage/`, filmed from a fixed dashboard or handlebar mount at normal speed.
2. **Plan.** `uv run nearmiss plan footage/*.mp4 --city Karachi`
3. **Prepare Cosmos inputs.** `uv run nearmiss prep footage/*.mp4 --cut 5` writes `out/cosmos/`.
4. **Render.** Upload `out/cosmos/` to a Nebius Object Storage bucket, then run `jobs/submit.sh <input-bucket> <output-bucket>` and download the generated clips to `out/gen/`.
5. **Label.** Run `jobs/reason_endpoint.sh` once, then `export COSMOS_REASON_URL=http://<endpoint>:8000` and run `uv run nearmiss label out/gen`.
6. **Build the pack.** `uv run nearmiss build --name karachi --title "Karachi school run" --city Karachi`
7. **Play.** `python3 -m http.server 8765 --directory web`, then open http://localhost:8765

To deploy the demo, run `vercel deploy` with `NEBIUS_API_KEY` set in the Vercel project environment, so the coach can call Token Factory.

To run the tests: `node --test tests/score.test.js`

## Nebius and NVIDIA usage

- **Nebius Token Factory**: Nemotron 3 Nano Omni (vision scene reading), Nemotron 3 Ultra (hazard planning), and Nemotron 3 Super (live coaching from the deployed app).
- **Nebius Serverless Jobs**: batch Cosmos Predict 2.5 rendering on a single GPU, with model weights cached in the output bucket so re-runs skip the download.
- **Nebius Serverless Endpoints**: Cosmos Reason 2 8B served with vLLM as an OpenAI-compatible API.
- **Tavily**: grounds every hazard in the city's real crash causes, and each hazard shows its source in the app.

Cosmos guardrails stay on, as the NVIDIA Open Model License requires.

## Repository

```
nearmiss/   pipeline CLI: media.py (ffmpeg), models.py (all model calls), pack.py (commands)
jobs/       Nebius Serverless Job and Endpoint scripts
web/        static player: index.html, app.js, score.js, style.css, packs/
api/        coach.js, a Vercel function that calls Token Factory
tests/      scoring tests
```

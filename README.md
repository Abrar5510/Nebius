# PROJECT NAME

> One sentence: **who** has **what problem**, and **what this does about it**.

**Track:** Best Apps and Agents *(or: Coding and Agentic Engineering / Personal AI / Physical AI)*
**Live demo:** https://YOUR-DEMO-URL
**Video (under 3 min):** https://youtube.com/watch?v=YOUR-VIDEO
**License:** Apache 2.0 (see [LICENSE](LICENSE))

Built for the [Nebius x NVIDIA Global AI Hackathon](https://nebiusglobalaihackathon.devpost.com/).
The full rules, requirements and checklist are in [docs/HACKATHON_GUIDE.md](docs/HACKATHON_GUIDE.md).

---

## What it does

- Feature 1
- Feature 2
- Feature 3

## Why

The real user, the real pain, and one number that shows it matters.

## How it works

```
user -> [your app] -> Nebius Token Factory -> Nemotron Nano/Super (fast calls)
                                           -> Nemotron Ultra (reasoning step)
```

Describe each step in one line.

---

## NVIDIA models and Nebius services used

| Model / service | Where | What it does in this project |
|---|---|---|
| NVIDIA Nemotron (Nano or Super) via **Nebius Token Factory** | `app.py` `ask()` | Fast, frequent calls |
| NVIDIA Nemotron Ultra via **Nebius Token Factory** | `app.py` `ask(..., REASON)` | Heavy reasoning step |
| *(optional)* Nebius Serverless Endpoint / Job | | Hosting / background work |
| *(optional)* Tavily API | | Live web grounding |

**Where Token Factory accelerated the work:** one OpenAI-compatible endpoint for every Nemotron
size, so switching between the fast and reasoning tiers is a one-word change, with no GPUs to run.
*(Replace with your real experience.)*

---

## Setup

Requires Python 3.11+.

```bash
git clone https://github.com/YOUR-USER/YOUR-REPO.git
cd YOUR-REPO
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then put your Token Factory key in NEBIUS_API_KEY
```

Get a key: Nebius console -> Token Factory -> API keys.

## Run

```bash
python app.py check              # proves the Token Factory call works
python app.py models             # NVIDIA models available to your key
python app.py ask "question"     # fast tier (Nemotron Nano/Super)
python app.py think "question"   # reasoning tier (Nemotron Ultra)
```

## Testing instructions for judges

Open the live demo above. No login needed. *(If there is a login, give test credentials here.)*

---

## Built during the Submission Period

All code in this repository was written between Aug 26 and Oct 30, 2026.

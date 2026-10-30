# Nebius x NVIDIA Global AI Hackathon: the complete guide

Everything from the event page, resources page and Official Rules, rewritten as what you
must build, what you must submit, and how you get judged. Source: nebiusglobalaihackathon.devpost.com
and its [Official Rules](https://nebiusglobalaihackathon.devpost.com/rules). If this guide and the
Rules ever disagree, **the Rules win**.

---

## 1. Key dates

| What | When (Pacific Time) | When (Karachi, PKT) |
|---|---|---|
| Submission Period opens | Wed Aug 26, 2026, 9:00 AM | Wed Aug 26, 9:00 PM |
| **Submission deadline** | **Fri Oct 30, 2026, 10:00 AM** | **Fri Oct 30, 10:00 PM** |
| Judging Period | Dec 9, 2026 9:00 AM to Dec 23, 2026 12:00 PM | |
| Winners announced | on or around Mon Jan 25, 2027, 12:00 PM | |

- After the deadline you **cannot edit** the submission. You can save drafts on Devpost before then.
- Your demo and repo must stay **free, public and working until Dec 23, 2026** (end of judging).

---

## 2. Can you enter?

**Yes, if you are:** an individual at the age of majority where you live, a team of such
individuals, or an existing organization. You can enter solo and also be on teams.

**No, if you are:**
- a resident of Brazil, Quebec, Russia, Crimea, Cuba, Iran, North Korea, or any country under
  comprehensive US OFAC sanctions (Pakistan is not on this list);
- an employee, agent or family/household member of Nebius, Devpost, or anyone running the event;
- a judge, or employed by a company that employs a judge;
- a project that got money, a contract, or a commercial license from Nebius or Devpost.

Teams appoint one **Representative** who submits and receives any prize.

---

## 3. The one hard technical rule

> Your project must **run on Nebius Token Factory or Nebius AI Cloud** and **use at least one
> NVIDIA open source model.**

"Runs on Nebius" is defined precisely. You need at least one of:

1. **A runtime call to the Token Factory inference API** (the app calls it while running), or
2. **Deployment on Nebius AI Cloud compute**: Serverless Jobs, Serverless Endpoints, or DevPods.

"NVIDIA open source model" means Nemotron (Nano / Super / Ultra / Omni), Cosmos (Predict,
Reason, Transfer), GR00T, Sonic, and other NVIDIA open models.

Stage One of judging is **pass/fail** on exactly this: does it fit the track, and does it
really use the required APIs/models. Fail here and nothing else is scored.

---

## 4. Tracks (pick exactly one)

### Track 1: Coding and Agentic Engineering
Coding agents and developer tools: agents that **write, run and test code** using Token Factory.

### Track 2: Best Apps and Agents
Any app or agent a real person would use: productivity tool, copilot, self-running workflow.
- Power it with **Nemotron on Token Factory**.
- Use **Nemotron 3 Ultra** for heavy reasoning; **Nano or Super** for fast everyday calls
  (keeps the app responsive and saves credits). Judges will notice this tiering.
- Encouraged, not required: deploy on **Nebius Serverless Endpoints**, run background work
  on **Nebius Serverless Jobs**.

### Track 3: Personal AI
An always-on, **private** assistant that keeps your data under your control.
- Needs **persistent memory**, **reusable skills**, access to tools/data you choose, and
  the ability to carry out tasks across daily workflows.
- At least one NVIDIA open model. Suggested tools: **NVIDIA NemoClaw, OpenShell, Hermes
  Agent, Nebius Serverless**.

### Track 4: Physical AI
Embodied and edge agents that sense and act in the real world: robotics, IoT, on-device AI.
- Powered by **Nemotron, GR00T, Cosmos, Sonic**, coordinated through an agent runtime.
- Use **Serverless Jobs** for simulation, synthetic data, policy evaluation or sensor
  processing at scale; **Serverless Endpoints** for real-time inference.
- **Demo URL not required**, but the video must include **at least 1 minute of the real
  hardware/robot operating** (or, with no hardware, the key software modules in action).
- Nebius may ask for **physical access** to non-standard hardware.

A project that is a "superficial rebrand of an unrelated idea" fails Stage One. Pick the track
your project genuinely attacks.

---

## 5. What you must submit (Devpost form)

Every item below is required unless marked.

| # | Item | Rules that apply |
|---|---|---|
| 1 | **Working project** | Installs and runs consistently; works as shown in the video and described in text. |
| 2 | **Track** | One of the four above. |
| 3 | **Project description** | What you built, why, how it works, its features. English. |
| 4 | **Demo URL** | Working hosted app, demo, or test build. Not required for Physical AI. If login is needed, put **test credentials** in the testing instructions. Free and unrestricted until judging ends. |
| 5 | **Demo video** | **Under 3 minutes** (judges stop at 3:00). **Public on YouTube.** Shows the project working on its target device, and **how you used Token Factory and the NVIDIA models**. No copyrighted music or third-party trademarks without permission. Physical AI: 1+ min of hardware footage. |
| 6 | **Public code repo** | GitHub, GitLab or Bitbucket. All source, assets and instructions needed to run it. |
| 7 | **Open source license** | Apache 2.0, MIT, MPL 2.0 or similar, in a `LICENSE` file so it is **detected and shown in the repo's About section**. |
| 8 | **README** | Setup instructions, how to run it, and a clear section on **which NVIDIA models you used, where Token Factory accelerated your work, and any other Nebius services**. |
| 9 | **Feedback** | On Token Factory, AI Cloud and every NVIDIA tool/model you used. (Also enters you for "Most Valuable Feedback".) |
| 10 | **"What changed" note** | Only if the project existed before Aug 26, 2026: what was significantly updated during the Submission Period. |
| 11 | **City** (optional) | Only if you attended a Builders & Brews event in a participating city. |

You may submit **more than one project**, but each must be substantially different.

---

## 6. How you are judged

**Stage One (pass/fail):** fits the track as a genuine attempt, and reasonably uses the
required Nebius API/compute and NVIDIA models.

**Stage Two:** four criteria, **equally weighted**:

| Criterion | The question judges ask | How to score high |
|---|---|---|
| **Technological Implementation** | How well is it built, and how effectively does it use Token Factory / AI Cloud and NVIDIA models? | Models used for real work, right model for each job (Nano/Super fast, Ultra for reasoning), clean code, it actually runs. |
| **Design** | Is it a complete, coherent product, not a tech proof of concept? | A real UI and flow a user can finish end to end; polish; no dead buttons. |
| **Potential Impact** | A credible, specific case for a real problem for a real audience, and does what's shown solve it? | Name the user, the pain, a number; show the demo solving exactly that. |
| **Quality of the Idea** | Creative, non-obvious use of the models, and real understanding of the problem space? | Something only these models make possible; show domain insight. |

**Ties** are broken by Technological Implementation first, then Design, Impact, Idea, then a
judges' vote. Judges **may not run your project** and can score from the description, images and
video alone. The video and README carry the most weight in practice.

---

## 7. Prizes

| Prize | Award | Who can win |
|---|---|---|
| Grand Prize | $20,000 | All |
| 2nd Place | $10,000 | All |
| 3rd Place | $6,000 | All |
| Track Winner (x4, one per track) | NVIDIA Jetson Orin Nano | Entries in that track |
| Best Use of Tavily | $3,000 | Entries with a **functional runtime call to the Tavily API** |
| City Winner (x20) | $500 | Attendees of a Builders & Brews city event* |
| Most Valuable Feedback (x10) | $100 + NVIDIA swag | Entries that complete the feedback section |

\*Cities: Tokyo, Da Nang, Seoul, Kuala Lumpur, Singapore, Taipei, Tel Aviv, London, Copenhagen,
Stockholm, Warsaw, Amsterdam, Berlin, Paris, Mexico City, New York City, Toronto, Boston,
San Francisco, Los Angeles.

**Stacking rule:** a project can win **one Overall Award OR one Track Award, plus one Bonus
Award**. So adding a real Tavily call is a free second shot.

Winners must pass identity/role verification and return forms (W-9 / W-8BEN for non-US) within
10 business days. Winners pay their own taxes and transfer fees.

---

## 8. Credits and resources

- **$25 Token Factory credits:** [promo form](https://nebius.com/promo-code?utm_promo_event_code=2026-devpost-global-ai-hack&utm_promo_code_type=Token_Factory&utm_promo_activation_code=NEBIUS-DEVPOST-GLOBAL26), activation code **`NEBIUS-DEVPOST-GLOBAL26`**.
- **Another $25 credits** (plus Tavily, Nebius Academy, office hours): join the [Nebius Builders Program](https://dev.nebius.com/builders).
- Docs: [Nebius for AI Builders](https://dev.nebius.com/) · Help: [Nebius Discord](https://discord.gg/eXYTGhgnhK)
- In-person: [Builders & Brews](https://luma.com/builderandbrews?k=c) (optional; extra credits for attendees).

---

## 9. How to build it, step by step

1. **Register** on the Devpost page ("Join Hackathon").
2. **Claim credits** (section 8) and create a **Token Factory API key** in the Nebius console.
3. **Pick a track** (section 4) and write one sentence: *who* has *what problem*, and *what
   the app does about it*.
4. **Wire Token Factory first.** It is OpenAI-compatible:
   `base_url = https://api.tokenfactory.nebius.com/v1/`, `api_key = <your key>`.
   This repo's `showitonce/clients` does this and resolves Nemotron model ids from the live catalog, so ids
   never go stale. Run `showitonce check` to prove the API call works.
5. **Tier your models:** Nano/Super for fast, frequent calls; Ultra for the hard reasoning step.
   Say so in the README and video.
6. **Optional extras that score:** Tavily runtime call (bonus prize), Nebius Serverless
   Endpoint/Job for deployment or background work (Tech score), Cosmos/GR00T for Physical AI.
7. **Build a real UI** someone can use end to end (Design score).
8. **Deploy** to a public URL that will stay up until Dec 23, 2026. Nebius Serverless Endpoint
   is encouraged; any host works as long as it calls Token Factory at runtime.
9. **Fill in the README** (template already in this repo) and keep the `LICENSE` file.
10. **Make the repo public** and confirm GitHub shows the license in the About sidebar.
11. **Record the video** (under 3:00, public YouTube): problem, live demo, then show the
    Token Factory calls and name each NVIDIA model.
12. **Fill `docs/SUBMISSION.md`**, paste it into Devpost, **submit before the deadline.**

---

## 10. Final pre-submit checklist

- [ ] App makes a **runtime call to Token Factory** (or runs on Nebius AI Cloud)
- [ ] At least one **NVIDIA open model** (Nemotron etc.) used for real work
- [ ] Fits the chosen track as a genuine attempt
- [ ] **Demo URL** works in a private browser window (skip for Physical AI)
- [ ] Test login credentials included, if any login exists
- [ ] Video **under 3:00**, **public** on YouTube, shows Token Factory + NVIDIA models, no copyrighted music
- [ ] Physical AI only: 1+ minute of hardware operating
- [ ] Repo **public**, `LICENSE` present, license visible in **About**
- [ ] README: setup, run steps, NVIDIA models used, where Token Factory helped, other Nebius services
- [ ] Feedback section filled in with specifics
- [ ] "What changed" note, if the project predates Aug 26, 2026
- [ ] No API keys committed (`.env` is gitignored)
- [ ] All materials in English
- [ ] Submitted (not just drafted) **before Oct 30, 10:00 AM PT / 10:00 PM PKT**

---

## 11. Rules that can disqualify you

- Missing any required item, or the demo/video not matching what the project actually does.
- Code you do not own or are not licensed to use; open source is fine if you comply with its
  license **and build meaningfully on top of it**.
- Third-party APIs/data used against their terms.
- Copyrighted music or trademarks in the video without permission.
- Viruses, malware or malicious code.
- Tampering, unsportsmanlike conduct, or a conflict of interest (Sponsor's sole discretion).

By submitting you grant Nebius a non-exclusive license to use the entry **for judging**, and let
Nebius and Devpost use your name, likeness and project for promotion for three years. You keep
ownership of your IP. Disputes go to individual AAA arbitration under New York law.

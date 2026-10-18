# Submission kit

Due **Fri Oct 30, 2026, 10:00 AM PT** (10:00 PM in Karachi). Aim to submit Oct 29.

## Devpost checklist

- [ ] Track: **Best Apps and Agents**
- [ ] Demo URL (from `vercel deploy`)
- [ ] Public YouTube video, 3 min max, with narration covering Token Factory and the NVIDIA models
- [ ] Repo public, with Apache-2.0 shown in the GitHub About section
- [ ] Feedback section filled in (see the draft below)
- [ ] Bonus: Best Use of Tavily. Tavily makes a runtime call in `nearmiss plan`.

## Video script (about 2:50)

**0:00–0:15. Hook.** Phone footage of your own street. *"This is the road outside my house in Karachi. Nothing happened here today."* Cut to the Cosmos version: a boy runs out from behind the rickshaw. *"This is what NVIDIA Cosmos thinks could happen tomorrow."*

**0:15–0:40. Problem.** WHO: 1.19 million road deaths a year, 92% in low- and middle-income countries. The UK and Australia test whether new drivers can spot hazards, and drivers who fail it crash about 1.8x more. Pakistan has no such test, and every existing training clip is a British road.

**0:40–1:30. Demo.** Play two clips live. Click on one early and one late. Show the review screen: the clue line, the five scoring bands, *"the first clue was the ball, 1.4 s before the boy."* Show the results screen and read out the Nemotron coach's paragraph.

**1:30–2:30. How it's built.** Screen-record the pipeline as each model is named:
1. Nemotron 3 Nano Omni on Token Factory reads the street from four frames.
2. Nemotron 3 Ultra and Tavily plan hazards from Karachi's real crash causes. Show the source link in the app.
3. Cosmos Predict 2.5 on a Nebius Serverless Job continues the real footage. Show the job logs.
4. Cosmos Reason 2 on a Nebius Serverless Endpoint writes the answer key and rejects bad renders. Show one rejected clip and why.
5. Nemotron 3 Super coaches live from the deployed app.

**2:30–2:50. Close.** *"Any street, any city, ten seconds of footage. Driving schools and delivery fleets can make a test for the roads their drivers actually use."*

## Feedback draft

Only include points you actually ran into. These two came up while building:

- **Model catalog discoverability.** Public pages redirect to the logged-in console, so exact model ids couldn't be found before signing up. We ended up resolving ids at runtime from `/v1/models`. A public, versioned model list with ids, context lengths and modalities would help.
- **Cosmos on Serverless.** There's no ready-made Cosmos Predict image or template, so every job installs the repo and downloads about 20 GB of weights. A prebuilt image, or Cosmos served on Token Factory, would cut minutes from every run.
- *(Add anything from the actual GPU runs: cold-start times, quota issues, logs.)*

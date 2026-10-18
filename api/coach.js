// Vercel serverless function: turns a learner's clicks into coaching with Nemotron on Nebius Token Factory.
// The API key stays server-side (NEBIUS_API_KEY in the Vercel project env).
const BASE = "https://api.tokenfactory.nebius.com/v1";
let modelId;

async function tf(path, body) {
  const r = await fetch(BASE + path, {
    method: body ? "POST" : "GET",
    headers: { Authorization: `Bearer ${process.env.NEBIUS_API_KEY}`, "Content-Type": "application/json" },
    body: body && JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`Token Factory ${r.status}: ${await r.text()}`);
  return r.json();
}

async function pickModel() {
  if (modelId) return modelId;
  const ids = (await tf("/models")).data.map((m) => m.id);
  const hits = ids.filter((id) => /nemotron/i.test(id) && /super/i.test(id));
  if (!hits.length) throw new Error("no Nemotron Super model on Token Factory");
  return (modelId = hits.sort((a, b) => a.length - b.length)[0]);
}

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).end();
  const { city = "", clips = [] } = req.body || {};
  if (!Array.isArray(clips) || clips.length > 30) return res.status(400).json({ error: "bad clips" });
  try {
    const out = await tf("/chat/completions", {
      model: await pickModel(),
      temperature: 0.5,
      max_tokens: 900,
      messages: [
        {
          role: "system",
          content:
            "You are a calm, direct driving instructor reviewing a hazard-perception test. Times are seconds into each clip. " +
            "clue_s is when a skilled driver first sees the hazard developing; onset_s is when they must react. " +
            "Write 3 short paragraphs, plain text, no lists or headings: the learner's pattern (early, late, missed, over-clicking), " +
            "the one habit that would most improve it with a concrete example from their clips, and what to watch for on real roads" +
            (city ? ` in ${city}` : "") + ". Under 140 words. Never invent clips or numbers.",
        },
        { role: "user", content: JSON.stringify(clips) },
      ],
    });
    const text = out.choices[0].message.content.replace(/<think>[\s\S]*?<\/think>/g, "").trim();
    res.status(200).json({ text, model: modelId });
  } catch (e) {
    res.status(502).json({ error: String(e.message || e) });
  }
}

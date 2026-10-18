import { scoreClip, windowFor, MAX_PER_CLIP } from "./score.js";

const $ = (id) => document.getElementById(id);
const show = (id) => {
  for (const s of document.querySelectorAll(".screen")) s.hidden = s.id !== id;
  window.scrollTo(0, 0);
};

let pack, base, i, taps, results;

async function home() {
  show("home");
  const list = $("packs");
  try {
    const packs = await (await fetch("packs/index.json")).json();
    list.innerHTML = "";
    for (const p of packs) {
      const b = document.createElement("button");
      b.className = "pack";
      b.innerHTML = `<div><b></b><span></span></div><div class="arrow">→</div>`;
      b.querySelector("b").textContent = p.title;
      b.querySelector("span").textContent = `${p.city} · ${p.n} clips`;
      b.onclick = () => start(p.id);
      list.append(b);
    }
  } catch {
    list.innerHTML = `<p class="empty">No packs yet. Build one with <code>nearmiss build</code>.</p>`;
  }
}

async function start(id) {
  base = `packs/${id}/`;
  pack = await (await fetch(base + "pack.json")).json();
  i = 0;
  results = [];
  brief();
}

function brief() {
  $("brief-count").textContent = `Clip ${i + 1} of ${pack.clips.length}`;
  show("brief");
  $("go").focus();
}

function drawTrack(el, clip, duration, clicks, reveal, hit) {
  el.innerHTML = "";
  const pct = (t) => `${(100 * t) / duration}%`;
  const add = (cls, css) => {
    const d = document.createElement("div");
    d.className = cls;
    Object.assign(d.style, css);
    el.append(d);
    return d;
  };
  if (reveal) {
    const w = windowFor(clip);
    for (let k = 0; k < 5; k++) {
      add("band", { left: pct(w.start + k * w.band), width: pct(w.band), opacity: 1 - k * 0.17 });
    }
    add("clue", { left: pct(clip.clue_s) });
  }
  for (const t of clicks) add("tap" + (t === hit ? " hit" : ""), { left: pct(t) });
}

function play() {
  const clip = pack.clips[i];
  const v = $("video");
  taps = [];
  show("play");
  v.src = base + clip.src;
  const track = $("play-track");
  const progress = () => {
    drawTrack(track, clip, v.duration || 10, taps, false);
    const p = document.createElement("div");
    p.className = "progress";
    p.style.width = `${(100 * v.currentTime) / (v.duration || 10)}%`;
    track.prepend(p);
  };
  let done = false;
  const end = () => {
    if (done) return;
    done = true;
    stopListening();
    review(clip, v.duration);
  };
  // `ended` can fail to fire when a tab is throttled or the last frame stalls; the time check is the backstop.
  v.ontimeupdate = () => (v.duration && v.currentTime >= v.duration - 0.05 ? end() : progress());
  v.onended = end;
  v.play();
  listen(() => {
    if (v.ended || v.paused) return;
    taps.push(v.currentTime);
    const f = $("flash");
    f.classList.add("on");
    requestAnimationFrame(() => requestAnimationFrame(() => f.classList.remove("on")));
    progress();
  });
}

let onKey, onClick;
function listen(fn) {
  onKey = (e) => {
    if (e.code === "Space") {
      e.preventDefault();
      fn();
    }
  };
  onClick = (e) => {
    if (e.target.closest("#play")) fn();
  };
  addEventListener("keydown", onKey);
  addEventListener("pointerdown", onClick);
}
function stopListening() {
  removeEventListener("keydown", onKey);
  removeEventListener("pointerdown", onClick);
}

function review(clip, duration) {
  const r = scoreClip(clip, taps);
  results.push({ clip, taps, ...r });
  $("review-count").textContent = `Clip ${i + 1} of ${pack.clips.length}`;
  $("review-score").textContent = r.score;
  const v = $("review-video");
  v.src = base + clip.src;
  v.currentTime = 0;
  drawTrack($("review-track"), clip, duration, taps, true, r.tap);
  $("review-hazard").textContent = cap(clip.hazard_type);
  const clueAt = clip.clue_s.toFixed(1);
  $("review-text").textContent = r.spam
    ? `Too many clicks (${taps.length}). In a real test this pattern scores zero, because nobody can tell whether you saw the hazard.`
    : r.score
      ? `You clicked at ${r.tap.toFixed(1)} s. The first clue was at ${clueAt} s: ${clip.clue}. ${r.score >= 4 ? "Well spotted." : `That's ${(r.tap - clip.clue_s).toFixed(1)} s after the clue appeared.`}`
      : `No click in the scoring window. The first clue was at ${clueAt} s: ${clip.clue}.`;
  const why = $("review-why");
  why.textContent = clip.why_here || "";
  if (clip.sources?.length) {
    why.append(" Source: ");
    const a = Object.assign(document.createElement("a"), { href: clip.sources[0], target: "_blank", rel: "noopener" });
    a.textContent = new URL(clip.sources[0]).hostname;
    why.append(a);
  }
  $("next").textContent = i + 1 < pack.clips.length ? "Next clip" : "See your result";
  show("review");
  $("next").focus();
}

const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");

async function finish() {
  const total = results.reduce((s, r) => s + r.score, 0);
  const max = results.length * MAX_PER_CLIP;
  $("total").textContent = total;
  $("total-max").textContent = `/${max}`;
  const pctScore = total / max;
  $("verdict").textContent =
    pctScore >= 0.7 ? "You read the road like an experienced driver." :
    pctScore >= 0.45 ? "You see most hazards, but late. Those seconds are your stopping distance." :
    "Most hazards reached you before you reacted. That gap is where crashes happen.";
  $("breakdown").innerHTML = "";
  for (const r of results) {
    const li = document.createElement("li");
    li.innerHTML = `<span></span><span class="pts"></span>`;
    li.firstChild.textContent = cap(r.clip.hazard_type);
    li.lastChild.textContent = `${r.score}/5`;
    $("breakdown").append(li);
  }
  show("results");
  const coach = $("coach-text");
  coach.textContent = "Thinking about your clicks…";
  try {
    const res = await fetch("/api/coach", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        city: pack.city,
        clips: results.map((r) => ({
          hazard: r.clip.hazard_type, clue: r.clip.clue, clue_s: r.clip.clue_s, onset_s: r.clip.onset_s,
          clicks: r.taps.map((t) => +t.toFixed(2)), score: r.score, spam: r.spam,
        })),
      }),
    });
    if (!res.ok) throw new Error(res.status);
    coach.textContent = (await res.json()).text;
  } catch {
    coach.textContent = "Coach is offline right now. Your per-clip feedback above still shows where each clue appeared.";
  }
}

$("go").onclick = play;
$("next").onclick = () => (++i < pack.clips.length ? brief() : finish());
$("again").onclick = home;
home();

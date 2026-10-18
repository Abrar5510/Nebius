// Hazard-perception scoring, modelled on the UK DVSA test.
// The window opens at the first visible clue and closes 1.5 s after the moment the driver must react.
// It is cut into five equal bands: a click in the first band scores 5, the last band 1.
export const MAX_PER_CLIP = 5;
export const SPAM_CLICKS = 8; // more clicks than this in one clip scores 0, as in the real test

export function windowFor(clip) {
  const start = clip.clue_s;
  const end = Math.max(clip.onset_s + 1.5, start + 2.5);
  return { start, end, band: (end - start) / 5 };
}

export function scoreClip(clip, taps) {
  if (taps.length > SPAM_CLICKS) return { score: 0, tap: null, spam: true };
  const w = windowFor(clip);
  let best = { score: 0, tap: null, spam: false };
  for (const t of taps) {
    if (t < w.start || t > w.end) continue;
    const score = 5 - Math.min(4, Math.floor((t - w.start) / w.band));
    if (score > best.score) best = { score, tap: t, spam: false };
  }
  return best;
}

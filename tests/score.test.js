import { test } from "node:test";
import assert from "node:assert/strict";
import { scoreClip, windowFor } from "../web/score.js";

const clip = { clue_s: 5, onset_s: 6.5 }; // window 5..8, bands of 0.6 s

test("window", () => assert.deepEqual(windowFor(clip), { start: 5, end: 8, band: 0.6 }));
test("early click scores 5", () => assert.equal(scoreClip(clip, [5.1]).score, 5));
test("late click scores 1", () => assert.equal(scoreClip(clip, [7.9]).score, 1));
test("before window scores 0", () => assert.equal(scoreClip(clip, [4.9]).score, 0));
test("after window scores 0", () => assert.equal(scoreClip(clip, [8.1]).score, 0));
test("best click counts", () => assert.equal(scoreClip(clip, [2, 6.3, 5.7]).score, 4));
test("end of window is band 1, not 0", () => assert.equal(scoreClip(clip, [8]).score, 1));
test("spam scores 0", () => {
  const r = scoreClip(clip, [1, 2, 3, 4, 5.1, 6, 7, 7.5, 7.8]);
  assert.equal(r.score, 0);
  assert.equal(r.spam, true);
});
test("short gap gets a 2.5 s minimum window", () => assert.equal(windowFor({ clue_s: 5, onset_s: 5.2 }).end, 7.5));

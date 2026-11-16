import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { TUTORIALS, formatVideoTime } from "../src/lib/tutorials.js";
test("tutorials are ordered sky, agent, application with local playable assets", () => {
  assert.deepEqual(TUTORIALS.map(t => t.id), ["your-sky", "cortex", "explore"]);
  for (const t of TUTORIALS) {
    const video = readFileSync(new URL(`../public${t.video}`, import.meta.url));
    const poster = readFileSync(new URL(`../public${t.poster}`, import.meta.url));
    assert.equal(video.toString("ascii", 4, 8), "ftyp");
    assert.equal(poster.readUInt16BE(0), 0xffd8);
    assert.ok(video.length > 100000 && t.duration > 0);
  }
});
test("video timeline formatting handles loading, seconds and long durations", () => {
  assert.equal(formatVideoTime(NaN), "0:00");
  assert.equal(formatVideoTime(Infinity), "0:00");
  assert.equal(formatVideoTime(-1), "0:00");
  assert.equal(formatVideoTime(15.04), "0:15");
  assert.equal(formatVideoTime(125.9), "2:05");
});

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { combineValues, valuesToRGBA } from "../src/lib/combine.js";
import { availableEpochs, frameFor } from "../src/lib/manifest.js";
import { parseCoordinates, pixelToSky } from "../src/lib/coords.js";
const manifest = (id) =>
  JSON.parse(
    readFileSync(
      new URL(`../public/static/fields/${id}/manifest.json`, import.meta.url),
    ),
  );
test("94 frames, 16 epochs, no missing file URLs", () => {
  let frames = 0,
    epochs = 0;
  for (const id of ["barnard", "epsindib", "wise0855", "rwaur", "rdra"]) {
    const m = manifest(id);
    epochs += m.epochs.length;
    for (const e of m.epochs)
      for (const f of e.frames) {
        frames++;
        for (const k of ["image_url", "data_url", "flags_url"]) {
          const b = readFileSync(new URL("../public" + f[k], import.meta.url));
          if (k === "data_url") assert.equal(b.byteLength, 3844);
        }
      }
  }
  assert.equal(frames, 94);
  assert.equal(epochs, 16);
});
test("Epsilon Indi e4 missing D1/D4, D5 available all four dates", () => {
  const m = manifest("epsindib");
  assert.equal(frameFor(m, 3, 1), undefined);
  assert.equal(frameFor(m, 3, 4), undefined);
  assert.deepEqual(availableEpochs(m, 1), [0, 1, 2]);
  assert.deepEqual(availableEpochs(m, 5), [0, 1, 2, 3]);
});
test("raw arithmetic B-A and A+B preserves NaN", () => {
  const a = new Float32Array([1, NaN, 3]),
    b = new Float32Array([4, 2, NaN]);
  assert.deepEqual([...combineValues(a, b, "diff")], [3, NaN, NaN]);
  assert.deepEqual([...combineValues(a, b, "sum")], [5, NaN, NaN]);
  assert.deepEqual(
    [...valuesToRGBA(new Float32Array([NaN]), "diff")],
    [58, 42, 74, 255],
  );
});
test("p99 difference ignores NaN and handles all-missing frames", () => {
  const pixels = valuesToRGBA(new Float32Array([-1, 0, 1, NaN]), "diff");
  assert.deepEqual([...pixels.slice(0, 4)], [0, 0, 0, 255]);
  assert.deepEqual([...pixels.slice(4, 8)], [128, 128, 128, 255]);
  assert.deepEqual([...pixels.slice(8, 12)], [255, 255, 255, 255]);
});
test("coordinate parsing and east-left orientation", () => {
  assert.deepEqual(
    parseCoordinates("133.75945 -7.24286"),
    [133.75945, -7.24286],
  );
  assert.equal(parseCoordinates("400 91"), null);
  assert.ok(parseCoordinates("08h55m10.8s -07d14m42s"));
  const m = manifest("wise0855");
  assert.equal(pixelToSky(15, 15, m).dec, m.center.dec);
  assert.ok(pixelToSky(16, 15, m).ra < m.center.ra);
  assert.ok(pixelToSky(15, 14, m).dec > m.center.dec);
});
test("measured manifest positions remain distinct across epochs", () => {
  const m = manifest("wise0855");
  assert.ok(
    m.epochs[2].expected_position.x - m.epochs[0].expected_position.x > 1.2,
  );
  assert.equal(m.epochs[0].frames.find((f) => f.detector === 5).n_exposures, 8);
});

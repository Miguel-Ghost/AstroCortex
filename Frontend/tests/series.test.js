import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { readSeries, readSeriesDocument, seriesPoints, isSaturatedSeries } from "../src/lib/series.js";
import { drawPlot } from "../src/lib/plot.js";
const load = (id, kind) => readSeriesDocument(readFileSync(new URL(`../public/static/fields/${id}/${kind}.json`, import.meta.url), "utf8"));
test("all manifest measurement URLs resolve to finite measured data", () => {
  for (const id of ["barnard", "epsindib", "wise0855", "rwaur", "rdra"]) {
    const m = JSON.parse(readFileSync(new URL(`../public/static/fields/${id}/manifest.json`, import.meta.url)));
    for (const kind of ["spectrum", "lightcurve"]) {
      const series = readSeriesDocument(readFileSync(new URL(`../public${m[kind + "_url"]}`, import.meta.url), "utf8"));
      assert.equal(series.target_id, id);
      assert.ok(seriesPoints(series, kind === "spectrum").length > 0);
      assert.ok(series.data.every(p => Number.isFinite(p.flux_err) && p.flux_err >= 0));
    }
  }
});
test("warnings and units survive parsing, detector selection never falls back to aggregate", () => {
  const s = load("epsindib", "lightcurve");
  assert.match(s.warning, /detectors disagree/i);
  assert.match(s.flux_unit, /relative/);
  assert.deepEqual(seriesPoints(s, false, 5), s.by_detector["5"]);
  assert.deepEqual(seriesPoints(s, false, 99), []);
  assert.equal(load("barnard", "spectrum").flux_unit, "mJy");
  assert.ok(isSaturatedSeries(load("rdra", "lightcurve")));
  assert.equal(isSaturatedSeries(load("wise0855", "lightcurve")), false);
});
test("legacy arrays and CSV remain readable", () => {
  assert.deepEqual(readSeries('[{"flux":2}]'), [{ flux: 2 }]);
  assert.deepEqual(readSeriesDocument('mjd,flux\n60000,1').data, [{ mjd: 60000, flux: 1 }]);
  assert.throws(() => readSeriesDocument('{"data":{}}'), /Invalid/);
});
test("plots stay finite with a single point, zero errors and high DPI", () => {
  const numbers = [], labels = [];
  const ctx = new Proxy({}, { set(o,k,v) { o[k]=v; return true; }, get(o,k) {
    if (k === "fillText") return text => labels.push(text);
    if (k in o) return o[k];
    return (...args) => numbers.push(...args.filter(x => typeof x === "number"));
  }});
  drawPlot(ctx, { width: 800, height: 500 }, [{ mjd: 60000, flux: 1, flux_err: 0 }], false, { pixelRatio: 2 });
  assert.ok(numbers.every(Number.isFinite));
  assert.ok(labels.includes("Relative flux"));
  assert.ok(labels.includes("MJD"));
});

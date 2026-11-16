import test from 'node:test';
import assert from 'node:assert/strict';
import { FULL_VIEW, zoomView, panView, plotAnchor } from '../src/lib/plotView.js';
test('zoom preserves cursor data coordinates and inverse zoom restores ranges', () => {
  const a = { x: 0.8, y: 0.2 }, v = zoomView(FULL_VIEW, 0.5, a);
  assert.ok(Math.abs(v.x0 + (v.x1 - v.x0) * a.x - a.x) < 1e-10);
  assert.ok(Math.abs(v.y0 + (v.y1 - v.y0) * a.y - a.y) < 1e-10);
  const full = zoomView(v, 2, a);
  for (const k of Object.keys(full)) assert.ok(Math.abs(full[k] - FULL_VIEW[k]) < 1e-10);
});
test('pan moves both axes by the visible span', () => {
  const actual = panView({x0:0.2,x1:0.6,y0:0,y1:0.5}, 0.5, -0.5);
  const expected = {x0:0.4,x1:0.8,y0:-0.25,y1:0.25};
  for (const key of Object.keys(expected)) assert.ok(Math.abs(actual[key] - expected[key]) < 1e-10);
});
test('zoom limits keep ranges finite under repeated zoom operations', () => {
  let v=FULL_VIEW;
  for(let i=0;i<500;i++) v=zoomView(v,0.5);
  assert.equal(v.x1-v.x0,1/128);
  for(let i=0;i<500;i++) v=zoomView(v,2);
  assert.equal(v.x1-v.x0,4);
});
test('pointer conversion uses CSS pixels and inverts screen Y', () => {
  assert.deepEqual(plotAnchor(200,150,{left:100,top:100},{L:0,R:200,T:0,B:100}),{x:0.5,y:0.5});
});

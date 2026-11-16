export const FULL_VIEW = { x0: 0, x1: 1, y0: 0, y1: 1 };

// Coordinates are fractions of the full data range, with Y increasing upward.
export function zoomView(view, factor, anchor = { x: 0.5, y: 0.5 }) {
  const result = {};
  for (const axis of ['x', 'y']) {
    const lo = view[axis + '0'], hi = view[axis + '1'];
    const span = Math.max(1 / 128, Math.min(4, (hi - lo) * factor));
    const a = Math.max(0, Math.min(1, anchor[axis]));
    const fixed = lo + (hi - lo) * a;
    result[axis + '0'] = fixed - span * a;
    result[axis + '1'] = fixed + span * (1 - a);
  }
  return result;
}

export function panView(view, dx, dy) {
  const x = dx * (view.x1 - view.x0), y = dy * (view.y1 - view.y0);
  return { x0: view.x0 + x, x1: view.x1 + x, y0: view.y0 + y, y1: view.y1 + y };
}

export function plotAnchor(clientX, clientY, rect, plot) {
  return {
    x: Math.max(0, Math.min(1, (clientX - rect.left - plot.L) / (plot.R - plot.L))),
    y: Math.max(0, Math.min(1, (plot.B - clientY + rect.top) / (plot.B - plot.T))),
  };
}

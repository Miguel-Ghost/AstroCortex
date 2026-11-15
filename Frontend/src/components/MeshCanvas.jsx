import { useEffect } from "react";
import { useElementSize } from "../hooks/useElementSize";
export function MeshCanvas() {
  const [ref, size] = useElementSize();
  useEffect(() => {
    const mesh = ref.current,
      mc = mesh.getContext("2d");
    mesh.width = size.width;
    mesh.height = size.height;
    let mouse = { x: -1000, y: -1000 },
      id;
    function draw() {
      const w = mesh.width,
        h = mesh.height;
      mc.clearRect(0, 0, w, h);
      const warp = (x, y) => {
        const dx = x - mouse.x,
          dy = y - mouse.y,
          f = 0.16 * Math.exp(-(dx * dx + dy * dy) / 33000);
        return [x - dx * f, y - dy * f];
      };
      mc.lineWidth = 0.8;
      mc.strokeStyle = "#b2d4ec28";
      for (let a = 0; a < w; a += 34) {
        mc.beginPath();
        for (let b = 0; b <= h; b += 9) {
          const p = warp(a, b);
          b ? mc.lineTo(...p) : mc.moveTo(...p);
        }
        mc.stroke();
      }
      for (let b = 0; b < h; b += 34) {
        mc.beginPath();
        for (let a = 0; a <= w; a += 9) {
          const p = warp(a, b);
          a ? mc.lineTo(...p) : mc.moveTo(...p);
        }
        mc.stroke();
      }
    }
    const parent = mesh.parentElement;
    function move(e) {
      const r = parent.getBoundingClientRect();
      mouse = { x: e.clientX - r.left, y: e.clientY - r.top };
      cancelAnimationFrame(id);
      id = requestAnimationFrame(draw);
    }
    function leave() {
      mouse = { x: -1000, y: -1000 };
      draw();
    }
    draw();
    parent.addEventListener("pointermove", move);
    parent.addEventListener("pointerleave", leave);
    return () => {
      cancelAnimationFrame(id);
      parent.removeEventListener("pointermove", move);
      parent.removeEventListener("pointerleave", leave);
    };
  }, [size.width, size.height]);
  return <canvas id="mesh" ref={ref} />;
}

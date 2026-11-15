export function startOrb(orbCanvas, busy) {
  const oc = orbCanvas.getContext("2d");
  orbCanvas.width = orbCanvas.height = 192;
  let lastOrb = 0;
  const orbPoints = Array.from({ length: 94 }, (_, i) => {
    const z = 1 - (2 * (i + 0.5)) / 94,
      a = i * 2.3999632297,
      r = Math.sqrt(1 - z * z);
    return {
      x: Math.cos(a) * r,
      y: z,
      z: Math.sin(a) * r,
      size: 0.8 + (((i * 37) % 17) / 17) * 1.35,
      phase: i * 1.73,
    };
  });
  function drawOrb(t) {
    if (t - lastOrb < 32) return;
    lastOrb = t;
    const working = busy();
    const C = 96,
      R = 67,
      phase = t * (working ? 0.0008 : 0.00021);
    oc.clearRect(0, 0, 192, 192);
    const bg = oc.createRadialGradient(C, C, R * 0.4, C, C, R * 1.4);
    bg.addColorStop(0, "rgba(30,83,145,.28)");
    bg.addColorStop(0.58, "rgba(36,106,185,.16)");
    bg.addColorStop(1, "rgba(30,83,145,0)");
    oc.fillStyle = bg;
    oc.fillRect(0, 0, 192, 192);
    const projected = orbPoints
      .map((p) => {
        const angle = phase + Math.sin(t * 0.00027) * 0.18,
          xx = p.x * Math.cos(angle) + p.z * Math.sin(angle),
          zz = -p.x * Math.sin(angle) + p.z * Math.cos(angle),
          tilt = 0.28 + Math.sin(t * 0.00031) * 0.12,
          yy = p.y * Math.cos(tilt) - zz * Math.sin(tilt),
          depth = p.y * Math.sin(tilt) + zz * Math.cos(tilt),
          swarm = working
            ? 1 + 0.035 * Math.sin(t * 0.002 + p.phase)
            : 1 + 0.012 * Math.sin(t * 0.001 + p.phase);
        return {
          x: C + xx * R * swarm,
          y: C + yy * R * swarm,
          z: depth,
          size: p.size,
          phase: p.phase,
        };
      })
      .sort((a, b) => a.z - b.z);
    oc.strokeStyle = "rgba(154,208,255,.40)";
    oc.lineWidth = 0.65;
    oc.beginPath();
    oc.arc(C, C, R, 0, Math.PI * 2);
    oc.stroke();
    for (const q of projected) {
      const front = (q.z + 1) * 0.5,
        twinkle = 0.84 + 0.16 * Math.sin(t * 0.0017 + q.phase),
        alpha =
          (0.46 + 0.54 * Math.pow(front, 0.75)) *
          (0.93 + 0.07 * Math.sin(t * 0.0017 + q.phase)),
        size = (0.5 + front * 0.85) * q.size;
      if (front > 0.83) {
        const glow = oc.createRadialGradient(q.x, q.y, 0, q.x, q.y, size * 3.4);
        glow.addColorStop(0, "rgba(109,190,255," + alpha * 0.48 + ")");
        glow.addColorStop(1, "rgba(109,190,255,0)");
        oc.fillStyle = glow;
        oc.fillRect(q.x - size * 3.4, q.y - size * 3.4, size * 6.8, size * 6.8);
      }
      oc.fillStyle =
        "rgba(" +
        (front > 0.65 ? "227,244,255" : "109,184,255") +
        "," +
        alpha +
        ")";
      oc.beginPath();
      oc.arc(q.x, q.y, size, 0, Math.PI * 2);
      oc.fill();
    }
  }

  let id;
  function tick(t) {
    drawOrb(t);
    id = requestAnimationFrame(tick);
  }
  id = requestAnimationFrame(tick);
  return () => cancelAnimationFrame(id);
}

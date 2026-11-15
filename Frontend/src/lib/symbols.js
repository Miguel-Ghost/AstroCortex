const symbols = new Map();
export function bodySymbol(label) {
  if (symbols.has(label)) return symbols.get(label);
  const c = document.createElement("canvas");
  c.width = c.height = 40;
  const x = c.getContext("2d");
  if (label === "asteroid_comet") {
    x.save();
    x.translate(20, 20);
    x.rotate(-0.3);
    const g = x.createLinearGradient(-12, -13, 12, 13);
    g.addColorStop(0, "#d9d0bc");
    g.addColorStop(0.4, "#a69c88");
    g.addColorStop(1, "#373c45");
    x.fillStyle = g;
    x.beginPath();
    [
      [-13, -6],
      [-6, -14],
      [5, -13],
      [13, -5],
      [12, 8],
      [3, 13],
      [-9, 10],
      [-15, 2],
    ].forEach((p, i) => (i ? x.lineTo(...p) : x.moveTo(...p)));
    x.closePath();
    x.fill();
    x.strokeStyle = "#e1ded655";
    x.stroke();
    for (const [a, b, r] of [
      [-5, -5, 4],
      [6, 2, 3],
      [-4, 7, 2],
    ]) {
      x.fillStyle = "#30313980";
      x.beginPath();
      x.ellipse(a, b, r, r * 0.75, -0.4, 0, 7);
      x.fill();
      x.strokeStyle = "#e6debc50";
      x.beginPath();
      x.arc(a - 0.5, b + 0.5, r, 0.4, 2.8);
      x.stroke();
    }
    x.restore();
  } else if (label === "galaxy") {
    x.save();
    x.translate(20, 20);
    x.rotate(-0.5);
    const g = x.createRadialGradient(0, 0, 0, 0, 0, 18);
    g.addColorStop(0, "#fff8e5");
    g.addColorStop(0.2, "#e8dacdcc");
    g.addColorStop(0.55, "#a7b6dd66");
    g.addColorStop(1, "#668acc00");
    x.scale(1, 0.42);
    x.fillStyle = g;
    x.fillRect(-20, -20, 40, 40);
    x.strokeStyle = "#c2cbec88";
    for (let a = 0; a < 2; a++) {
      x.beginPath();
      for (let i = 0; i < 60; i++) {
        const t = i / 14 + a * Math.PI,
          r = 1 + i * 0.23;
        const px = Math.cos(t) * r,
          py = Math.sin(t) * r;
        i ? x.lineTo(px, py) : x.moveTo(px, py);
      }
      x.stroke();
    }
    x.restore();
  } else if (label === "cold_brown_dwarf") {
    const halo = x.createRadialGradient(20, 20, 8, 20, 20, 19);
    halo.addColorStop(0, "#c0734b66");
    halo.addColorStop(1, "#b6734900");
    x.fillStyle = halo;
    x.fillRect(0, 0, 40, 40);
    x.save();
    x.beginPath();
    x.arc(20, 20, 12, 0, 7);
    x.clip();
    const g = x.createRadialGradient(15, 14, 2, 24, 24, 19);
    g.addColorStop(0, "#d5ac82");
    g.addColorStop(0.5, "#96664d");
    g.addColorStop(1, "#1e2733");
    x.fillStyle = g;
    x.fillRect(7, 7, 26, 26);
    x.strokeStyle = "#3b293453";
    x.lineWidth = 2;
    for (let i = 0; i < 5; i++) {
      x.beginPath();
      x.ellipse(20, 12 + i * 4, 14, 2.1, 0.1, 0, Math.PI);
      x.stroke();
    }
    x.restore();
  } else if (label === "star") {
    const g = x.createRadialGradient(20, 20, 0, 20, 20, 18);
    g.addColorStop(0, "#fffdf1");
    g.addColorStop(0.16, "#fff8dd");
    g.addColorStop(0.35, "#dbe6ff88");
    g.addColorStop(1, "#8ab8ff00");
    x.fillStyle = g;
    x.fillRect(0, 0, 40, 40);
    x.strokeStyle = "#e5efff88";
    x.lineWidth = 0.8;
    x.beginPath();
    x.moveTo(20, 3);
    x.lineTo(20, 37);
    x.moveTo(3, 20);
    x.lineTo(37, 20);
    x.stroke();
  } else {
    x.strokeStyle = "#bad2ed";
    x.lineWidth = 1.2;
    x.beginPath();
    x.moveTo(20, 7);
    x.lineTo(33, 20);
    x.lineTo(20, 33);
    x.lineTo(7, 20);
    x.closePath();
    x.stroke();
    x.fillStyle = "#bad2ed";
    x.beginPath();
    x.arc(20, 20, 2, 0, 7);
    x.fill();
  }
  symbols.set(label, c);
  return c;
}

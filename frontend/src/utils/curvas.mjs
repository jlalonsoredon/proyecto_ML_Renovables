// Curvas para los dibujos SVG del diseño (spec 017). Funciones puras.

/** Trazo suave (Catmull-Rom a Bézier) por una lista de puntos [x, y]; `null` corta el trazo. */
export function smoothPath(points, k = 0.18) {
  const tramos = [];
  let actual = [];
  for (const p of [...points, null]) {
    if (p === null) {
      if (actual.length) tramos.push(actual);
      actual = [];
    } else {
      actual.push(p);
    }
  }
  const f = (v) => v.toFixed(1);
  return tramos.map((t) => {
    if (t.length === 1) return `M${f(t[0][0])},${f(t[0][1])}`;
    let d = `M${f(t[0][0])},${f(t[0][1])}`;
    for (let i = 0; i < t.length - 1; i++) {
      const p0 = t[i - 1] ?? t[i];
      const p1 = t[i];
      const p2 = t[i + 1];
      const p3 = t[i + 2] ?? t[i + 1];
      d += ` C${f(p1[0] + (p2[0] - p0[0]) * k)},${f(p1[1] + (p2[1] - p0[1]) * k)} ${f(p2[0] - (p3[0] - p1[0]) * k)},${f(p2[1] - (p3[1] - p1[1]) * k)} ${f(p2[0])},${f(p2[1])}`;
    }
    return d;
  }).join(" ");
}

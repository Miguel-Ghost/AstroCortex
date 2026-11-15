import { useEffect } from "react";
import { useStore } from "../store";
import { TARGETS } from "../targets";
function read() {
  const p = new URLSearchParams(location.search);
  return {
    targetId: TARGETS.some((t) => t.target_id === p.get("target"))
      ? p.get("target")
      : null,
    ra: Number(p.get("ra")),
    dec: Number(p.get("dec")),
    hasCoords: p.has("ra") && p.has("dec"),
    restore: {
      detector: p.has("det") ? +p.get("det") : undefined,
      epochIndex: +p.get("t") || 0,
      mode: p.get("mode"),
      grid: p.get("grid") === "1",
      pairA: +p.get("a") || 0,
      pairB: p.has("b") ? +p.get("b") : undefined,
      fps: p.has("fps") ? +p.get("fps") : 2,
      selectedSourceId: p.get("src"),
    },
  };
}
export function useUrlSync() {
  useEffect(() => {
    let restoring = false;
    async function restore() {
      restoring = true;
      const v = read();
      await useStore
        .getState()
        .openField(
          v.targetId
            ? { targetId: v.targetId }
            : v.hasCoords
              ? { ra: v.ra, dec: v.dec }
              : { targetId: "wise0855" },
          v.restore,
        );
      restoring = false;
      const s = useStore.getState();
      if (s.field && s.status === "ready") {
        const p = new URLSearchParams({
          target: s.targetId || "",
          ra: s.field.center.ra,
          dec: s.field.center.dec,
          det: s.detector,
          t: s.epochIndex,
          mode: s.mode,
          grid: s.grid ? "1" : "0",
          a: s.pairA,
          b: s.pairB,
          fps: s.fps,
        });
        if (s.selectedSourceId) p.set("src", s.selectedSourceId);
        history.replaceState(null, "", location.pathname + "?" + p);
      }
    }
    restore();
    const off = useStore.subscribe((s, old) => {
      if (restoring || !s.field || s.status !== "ready") return;
      const keys = [
        "field",
        "detector",
        "epochIndex",
        "mode",
        "grid",
        "pairA",
        "pairB",
        "fps",
        "selectedSourceId",
      ];
      if (keys.every((k) => s[k] === old[k])) return;
      const p = new URLSearchParams({
        target: s.targetId || "",
        ra: s.field.center.ra,
        dec: s.field.center.dec,
        det: s.detector,
        t: s.epochIndex,
        mode: s.mode,
        grid: s.grid ? "1" : "0",
        a: s.pairA,
        b: s.pairB,
        fps: s.fps,
      });
      if (s.selectedSourceId) p.set("src", s.selectedSourceId);
      const next = location.pathname + "?" + p;
      const current = location.pathname + location.search;
      if (next !== current) {
        if (s.field !== old.field) history.pushState(null, "", next);
        else history.replaceState(null, "", next);
      }
    });
    window.addEventListener("popstate", restore);
    return () => {
      off();
      window.removeEventListener("popstate", restore);
    };
  }, []);
}

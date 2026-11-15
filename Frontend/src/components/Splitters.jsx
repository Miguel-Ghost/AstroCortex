import { useRef } from "react";
import { useStore } from "../store";
export function Splitters() {
  const s = useStore(),
    drag = useRef();
  function resize(kind, value) {
    const r = document.getElementById("app").getBoundingClientRect();
    s.patch(
      kind === "side"
        ? { sideWidth: Math.max(265, Math.min(r.width - 240, value)) }
        : { bottomHeight: Math.max(100, Math.min(r.height - 190, value)) },
    );
  }
  return (
    <>
      {["side", "bottom"].map((kind) => (
        <div
          key={kind}
          id={kind + "Splitter"}
          className={
            "splitter " + (kind === "side" ? "vertical" : "horizontal")
          }
          role="separator"
          tabIndex="0"
          aria-label={"Resize " + kind + " panel"}
          aria-orientation={kind === "side" ? "vertical" : "horizontal"}
          aria-valuenow={kind === "side" ? s.sideWidth : s.bottomHeight}
          style={
            kind === "side"
              ? {
                  right: s.sideWidth + 4,
                  top: 8,
                  bottom: s.bottomHeight + 16,
                  display: s.expanded ? "none" : undefined,
                }
              : { bottom: s.bottomHeight + 3, left: 8, right: 8 }
          }
          onPointerDown={(e) => {
            drag.current = kind;
            e.currentTarget.setPointerCapture(e.pointerId);
          }}
          onPointerMove={(e) => {
            if (drag.current !== kind) return;
            const r = document.getElementById("app").getBoundingClientRect();
            resize(
              kind,
              kind === "side"
                ? r.right - e.clientX - 8
                : r.bottom - e.clientY - 8,
            );
          }}
          onPointerUp={() => {
            drag.current = null;
          }}
          onPointerCancel={() => {
            drag.current = null;
          }}
          onDoubleClick={() => resize(kind, kind === "side" ? 410 : 185)}
          onKeyDown={(e) => {
            const keys =
              kind === "side"
                ? ["ArrowLeft", "ArrowRight"]
                : ["ArrowUp", "ArrowDown"];
            if (keys.includes(e.key)) {
              e.preventDefault();
              resize(
                kind,
                (kind === "side" ? s.sideWidth : s.bottomHeight) +
                  (e.key === keys[0] ? 16 : -16),
              );
            }
          }}
        />
      ))}
    </>
  );
}

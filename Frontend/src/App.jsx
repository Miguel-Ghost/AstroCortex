import { useEffect, useState, useCallback } from "react";
import { useStore } from "./store";
import { useFlipbookPlayer } from "./hooks/useFlipbookPlayer";
import { useUrlSync } from "./hooks/useUrlSync";
import { Intro } from "./components/Intro";
import { Header } from "./components/Header";
import { SkyView } from "./components/SkyView";
import { FieldPanel } from "./components/FieldPanel";
import { ClassificationPanel } from "./components/ClassificationPanel";
import { Agent } from "./components/Agent";
import { Splitters } from "./components/Splitters";
export default function App() {
  const s = useStore(),
    [introDone, setIntroDone] = useState(false),
    complete = useCallback(() => setIntroDone(true), []);
  useUrlSync();
  useFlipbookPlayer();
  useEffect(() => {
    document.body.classList.toggle("field-panel-only", s.expanded);
  }, [s.expanded]);
  useEffect(() => {
    const handler = (e) => {
      if (
        ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(e.target.tagName) ||
        document.querySelector("dialog[open]")
      )
        return;
      const s = useStore.getState();
      if (e.code === "Space") {
        e.preventDefault();
        s.togglePlay();
      }
      if (e.key === "ArrowRight") s.field && s.step(1);
      if (e.key === "ArrowLeft") s.field && s.step(-1);
      if (e.key === "Escape") s.patch({ chatOpen: false, expanded: false });
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  return (
    <>
      <Intro onComplete={complete} />
      <Header />
      <main
        onPointerDownCapture={() => {
          const st = useStore.getState();
          if (st.tour.auto) st.patch({ tour: { ...st.tour, auto: false } });
        }}
        id="app"
        style={{
          "--side-width": s.sideWidth + "px",
          "--bottom-height": s.bottomHeight + "px",
        }}
      >
        <SkyView ready={introDone} />
        <FieldPanel />
        <ClassificationPanel />
        <Splitters />
      </main>
      <Agent />
      <div id="status" role="status">
        {s.toast}
      </div>
      {s.expanded && (
        <button
          className="collapse-field"
          onClick={() => s.patch({ expanded: false })}
        >
          Back to sky
        </button>
      )}
    </>
  );
}

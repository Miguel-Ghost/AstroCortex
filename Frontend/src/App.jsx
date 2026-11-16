import { useEffect, useState, useCallback, useRef } from "react";
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
import { TutorialGuide } from "./components/TutorialGuide";
export default function App() {
  const s = useStore(),
    returnView = useRef(null),
    [introDone, setIntroDone] = useState(false),
    complete = useCallback(() => setIntroDone(true), []);
  const openTutorials = useCallback(() => {
    const current = useStore.getState();
    if (current.tutorialOpen) return;
    returnView.current = { expanded: current.expanded, chatOpen: current.chatOpen };
    current.patch({ tutorialOpen: true, expanded: false, chatOpen: false, playing: false,
      tour: { ...current.tour, auto: false } });
  }, []);
  const closeTutorials = useCallback(() => {
    useStore.getState().patch({ tutorialOpen: false, ...(returnView.current || {}) });
    requestAnimationFrame(() => document.getElementById("guideBtn")?.focus());
  }, []);
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
      if (s.tutorialOpen) return;
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
      <Header onGuide={openTutorials} />
      <main
        onPointerDownCapture={() => {
          const st = useStore.getState();
          if (st.tour.auto) st.patch({ tour: { ...st.tour, auto: false } });
        }}
        id="app"
        className={s.tutorialOpen ? "tutorials-open" : ""}
        style={{
          "--side-width": s.sideWidth + "px",
          "--bottom-height": s.bottomHeight + "px",
        }}
      >
        <SkyView ready={introDone} />
        <div className="tutorial-side-shell" inert={s.tutorialOpen || undefined}><FieldPanel /></div>
        <div className="tutorial-bottom-shell" inert={s.tutorialOpen || undefined}><ClassificationPanel /></div>
        {!s.tutorialOpen && <Splitters />}
        {s.tutorialOpen && <TutorialGuide onClose={closeTutorials} />}
      </main>
      <div style={s.tutorialOpen ? { display: "none" } : undefined}><Agent /></div>
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

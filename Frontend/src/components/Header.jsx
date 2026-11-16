import { useRef, useEffect, useState } from "react";
import { useStore } from "../store";
import { TARGETS } from "../targets";
export function Header({ onGuide }) {
  const s = useStore(),
    dialog = useRef(),
    [guideUnread, setGuideUnread] = useState(() => {
      try { return localStorage.getItem("astrocortex-guide-seen-v1") !== "1"; }
      catch { return true; }
    });
  function showGuide() {
    setGuideUnread(false);
    try { localStorage.setItem("astrocortex-guide-seen-v1", "1"); } catch { /* Session-only when storage is unavailable. */ }
    onGuide();
  }
  useEffect(() => {
    s.loadTargetStats();
  }, []);
  const stats = Object.values(s.targetStats).filter(Boolean),
    total = stats.reduce((n, t) => n + t.frames, 0);
  return (
    <>
      <header>
        <svg
          className="wordmark"
          viewBox="0 0 1200 300"
          aria-label="AstroCortex"
        >
          <use href="#wordmark" />
        </svg>
        <form
          className="search"
          id="searchForm"
          onSubmit={(e) => {
            e.preventDefault();
            s.search(new FormData(e.currentTarget).get("search"));
          }}
        >
          <input
            id="search"
            name="search"
            aria-label="Name or RA Dec"
            placeholder="Name or RA / Dec"
          />
        </form>
        <div className="quick">
          {TARGETS.map((t) => (
            <button
              key={t.target_id}
              className={s.targetId === t.target_id ? "active" : ""}
              onClick={() => s.selectTarget(t.target_id)}
            >
              {t.short}
            </button>
          ))}
        </div>
        <button id="targetsBtn" onClick={() => dialog.current.showModal()}>
          Targets{total ? ` · ${total}` : ""}
        </button>
        <label className="fov">
          FOV{" "}
          <select disabled value="3.2" aria-label="Field of view">
            <option value="3.2">3.2′</option>
          </select>
        </label>
        <div className="spacer" />
        <button id="guideBtn" className={guideUnread ? "guide-unread" : undefined} aria-expanded={s.tutorialOpen} onClick={showGuide}>
          Guide me
          {guideUnread && <span className="guide-notification" aria-hidden="true" />}
        </button>
        <button
          id="share"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(location.href);
              s.notify("View link copied");
            } catch {
              s.notify("Copy the page URL to share this view.");
            }
          }}
        >
          Share
        </button>
      </header>
      <dialog id="targetDialog" ref={dialog}>
        <h2>Targets · {total} frames</h2>
        <p>
          Coadded images across observing dates and detectors. Select a target,
          then use Play or 6 panels.
        </p>
        <div id="targetList">
          {TARGETS.map((t) => (
            <button
              key={t.target_id}
              onClick={() => {
                s.selectTarget(t.target_id);
                dialog.current.close();
              }}
            >
              {t.name}
              {s.targetStats[t.target_id] && (
                <small
                  style={{ display: "block", color: "#aaa", marginTop: 4 }}
                >
                  {s.targetStats[t.target_id].epochs} dates ·{" "}
                  {s.targetStats[t.target_id].frames} frames
                </small>
              )}
            </button>
          ))}
        </div>
        <div className="row">
          <button onClick={() => dialog.current.close()}>Close</button>
        </div>
      </dialog>
    </>
  );
}

import { useCallback, useEffect, useRef, useState } from "react";
import { TUTORIALS, formatVideoTime } from "../lib/tutorials";

function PlayIcon() {
  return <svg viewBox="0 0 18 18" width="15" height="15" fill="currentColor" aria-hidden="true"><path d="M5 3 15 9 5 15Z" /></svg>;
}
function BackArrow() {
  return <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m14 6-6 6 6 6M8 12h12" /></svg>;
}

function TutorialPlayer({ tutorial, onBack }) {
  const video = useRef(null), timer = useRef(null), controls = useRef(null), back = useRef(null), keyboard = useRef(false);
  const [playing, setPlaying] = useState(false), [time, setTime] = useState(0),
    [duration, setDuration] = useState(tutorial.duration), [visible, setVisible] = useState(true),
    [error, setError] = useState("");
  const reveal = useCallback(() => {
    setVisible(true);
    clearTimeout(timer.current);
    if (video.current && !video.current.paused) timer.current = setTimeout(() => {
      if (!keyboard.current || (!controls.current?.contains(document.activeElement) && document.activeElement !== back.current))
        setVisible(false);
    }, 2200);
  }, []);
  useEffect(() => {
    const v = video.current;
    v.play().catch(() => setVisible(true));
    return () => { clearTimeout(timer.current); v.pause(); };
  }, []);
  function togglePlay() {
    const v = video.current;
    if (v.paused) v.play().catch(() => setError("Playback could not start. Please try again."));
    else v.pause();
    reveal();
  }
  return <div className={`tutorial-player ${visible || !playing || error ? "controls-visible" : "controls-hidden"}`}
    onPointerMove={reveal} onPointerDownCapture={() => { keyboard.current = false; }} onPointerDown={reveal} onFocusCapture={reveal}
    onKeyDown={event => {
      keyboard.current = true; reveal();
      if (event.key === " " && !["INPUT", "BUTTON"].includes(event.target.tagName)) {
        event.preventDefault(); event.stopPropagation(); togglePlay();
      }
    }}>
    <video ref={video} src={tutorial.video} poster={tutorial.poster} preload="metadata" playsInline
      tabIndex="0" aria-label={tutorial.title}
      onClick={togglePlay} onTimeUpdate={() => setTime(video.current.currentTime)}
      onLoadedMetadata={() => setDuration(video.current.duration)}
      onPlay={() => { setError(""); setPlaying(true); reveal(); }}
      onPause={() => { setPlaying(false); setVisible(true); clearTimeout(timer.current); }}
      onEnded={() => { setPlaying(false); setVisible(true); }}
      onError={() => { setError("This video could not be loaded. Return to tutorials and try again."); setVisible(true); }} />
    <div className="tutorial-player-top tutorial-chrome">
      <button ref={back} className="tutorial-back" aria-label="Back to tutorials" onClick={onBack}><BackArrow /></button>
      <span>{tutorial.title}</span>
    </div>
    {!playing && !error && <button className="tutorial-big-play" aria-label={`Play ${tutorial.title}`} onClick={togglePlay}><PlayIcon /></button>}
    {error && <p className="tutorial-video-error" role="alert">{error}</p>}
    <div className="tutorial-player-controls tutorial-chrome" ref={controls}>
      <button aria-label={playing ? "Pause tutorial" : "Play tutorial"} onClick={togglePlay}>{playing ? "Ⅱ" : <PlayIcon />}</button>
      <span className="tutorial-time">{formatVideoTime(time)}</span>
      <input type="range" aria-label="Video progress" min="0" max={Number.isFinite(duration) ? duration : 0} step="0.05"
        value={Math.min(time, duration || 0)} onChange={event => {
          const next = Number(event.target.value);
          video.current.currentTime = next; setTime(next); reveal();
        }} />
      <span className="tutorial-time">{formatVideoTime(duration)}</span>
    </div>
  </div>;
}

export function TutorialGuide({ onClose }) {
  const [selected, setSelected] = useState(null), [enter, setEnter] = useState(false);
  const region = useRef(null), galleryFocus = useRef(null);
  const back = useCallback(() => selected ? setSelected(null) : onClose(), [selected, onClose]);
  useEffect(() => {
    const id = requestAnimationFrame(() => setEnter(true));
    return () => cancelAnimationFrame(id);
  }, []);
  useEffect(() => {
    const key = event => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); back(); }
    };
    window.addEventListener("keydown", key, true);
    return () => window.removeEventListener("keydown", key, true);
  }, [back]);
  useEffect(() => {
    if (selected) region.current?.querySelector("video")?.focus({ preventScroll: true });
    else (region.current?.querySelector(`[data-tutorial="${galleryFocus.current}"]`) || region.current?.querySelector(".tutorial-back"))?.focus({ preventScroll: true });
  }, [selected]);
  return <section ref={region} className={`tutorial-guide ${enter ? "tutorial-entered" : ""}`}
    role="region" aria-label="AstroCortex tutorials"
    onPointerDown={event => event.stopPropagation()} onWheel={event => event.stopPropagation()}>
    {selected ? <TutorialPlayer key={selected.id} tutorial={selected} onBack={() => setSelected(null)} /> : <>
      <div className="tutorial-heading">
        <button className="tutorial-back" aria-label="Back to sky" onClick={onClose}><BackArrow /></button>
        <div><p>GUIDE ME</p><h1>A closer look.</h1><span>Three short films. Choose where to begin.</span></div>
      </div>
      <div className="tutorial-films">
        {TUTORIALS.map((tutorial, i) => <button key={tutorial.id} className="tutorial-film"
          data-tutorial={tutorial.id} aria-label={`Watch ${tutorial.title}`} onClick={() => { galleryFocus.current = tutorial.id; setSelected(tutorial); }}>
          <div className="tutorial-poster"><img src={tutorial.poster} alt="" draggable="false" />
            <span className="tutorial-number">0{i + 1}</span><span className="tutorial-film-play" aria-hidden="true"><PlayIcon /></span>
            <span className="tutorial-duration">{formatVideoTime(tutorial.duration)}</span>
          </div>
          <strong>{tutorial.title}</strong><span className="tutorial-description">{tutorial.description}</span>
        </button>)}
      </div>
    </>}
  </section>;
}

import { useEffect, useRef, useState } from "react";
import { useStore } from "../store";
import { startOrb } from "../lib/orb";
import { runAction } from "../lib/actions";
export function Agent() {
  const s = useStore(),
    canvas = useRef(),
    drag = useRef(),
    [position, setPosition] = useState(null),
    [question, setQuestion] = useState(""),
    recognition = useRef(),
    [listening, setListening] = useState(false);
  useEffect(
    () => startOrb(canvas.current, () => useStore.getState().agentBusy),
    [],
  );
  useEffect(() => () => recognition.current?.abort(), []);
  async function step(i) {
    const next = s.tour.steps[i];
    if (!next) return;
    s.patch({ tour: { ...s.tour, index: i } });
    for (const action of next.actions || [])
      if (!(await runAction(action)))
        s.notify("Skipped an unsupported guide action.");
  }
  useEffect(() => {
    if (!s.tour.auto) return;
    const t = setTimeout(() => {
      if (s.tour.index < s.tour.steps.length - 1) step(s.tour.index + 1);
      else s.patch({ tour: { ...s.tour, auto: false } });
    }, 6500);
    return () => clearTimeout(t);
  }, [s.tour]);
  function send() {
    s.askAgent(question);
    setQuestion("");
  }
  function voice() {
    const C = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!C) {
      s.notify(
        "Voice input is not available in this browser. Type your question.",
      );
      return;
    }
    if (recognition.current) {
      recognition.current.stop();
      return;
    }
    const r = new C();
    recognition.current = r;
    r.lang = "en-US";
    r.onstart = () => setListening(true);
    r.onresult = (e) =>
      setQuestion(
        Array.from(e.results)
          .map((x) => x[0].transcript)
          .join(" "),
      );
    r.onerror = () => s.notify("Voice input unavailable.");
    r.onend = () => {
      recognition.current = null;
      setListening(false);
    };
    r.start();
  }
  return (
    <>
      <button
        id="agentOrb"
        className={s.agentBusy ? "working" : ""}
        style={
          position
            ? {
                left: position.x,
                top: position.y,
                right: "auto",
                bottom: "auto",
              }
            : {
                right: s.expanded ? 24 : s.sideWidth + 96,
                bottom: s.bottomHeight + 25,
              }
        }
        aria-label="Open Cortex"
        aria-expanded={s.chatOpen}
        onPointerDown={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          drag.current = {
            sx: e.clientX,
            sy: e.clientY,
            dx: e.clientX - r.left,
            dy: e.clientY - r.top,
            moved: false,
          };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          const d = drag.current;
          if (!d) return;
          if (Math.hypot(e.clientX - d.sx, e.clientY - d.sy) > 5)
            d.moved = true;
          if (d.moved)
            setPosition({
              x: Math.max(0, Math.min(innerWidth - 116, e.clientX - d.dx)),
              y: Math.max(52, Math.min(innerHeight - 116, e.clientY - d.dy)),
            });
        }}
        onPointerUp={() => {
          if (drag.current && !drag.current.moved)
            s.patch({ chatOpen: !s.chatOpen });
          drag.current = null;
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
        onKeyDown={(e) => {
          if (["Enter", " "].includes(e.key)) {
            e.preventDefault();
            s.patch({ chatOpen: !s.chatOpen });
          }
        }}
      >
        <canvas id="orb" ref={canvas} />
      </button>
      {s.chatOpen && (
        <aside
          id="chat"
          aria-label="Cortex guide"
          style={
            position
              ? {
                  left: Math.max(
                    10,
                    Math.min(innerWidth - 354, position.x - 220),
                  ),
                  top: Math.max(60, position.y - 330),
                  right: "auto",
                  bottom: "auto",
                }
              : {
                  right: Math.min(
                    innerWidth - 354,
                    s.expanded ? 30 : s.sideWidth + 24,
                  ),
                  bottom: s.bottomHeight + 145,
                }
          }
        >
          <header>
            <strong>Cortex</strong>
            <button
              id="chatClose"
              aria-label="Close chat"
              onClick={() => s.patch({ chatOpen: false })}
            >
              ×
            </button>
          </header>
          <div id="messages" role="log" aria-live="polite">
            {s.messages.map((m, i) => (
              <p key={i} className={m.role === "user" ? "question" : "reply"}>
                {m.content}
              </p>
            ))}
          </div>
          {s.tour.steps.length > 0 && (
            <div className="tour">
              <p>{s.tour.steps[s.tour.index]?.say}</p>
              <div className="tour-controls">
                <button
                  disabled={!s.tour.index}
                  onClick={() => step(s.tour.index - 1)}
                >
                  Back
                </button>
                <button
                  onClick={() =>
                    step(Math.min(s.tour.steps.length - 1, s.tour.index + 1))
                  }
                >
                  Next
                </button>
                <button
                  onClick={() =>
                    s.patch({ tour: { ...s.tour, auto: !s.tour.auto } })
                  }
                >
                  Auto
                </button>
                <button
                  onClick={() =>
                    s.patch({ tour: { steps: [], index: 0, auto: false } })
                  }
                >
                  Stop
                </button>
              </div>
            </div>
          )}
          <form
            id="askForm"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <textarea
              id="ask"
              aria-label="Question"
              placeholder="Ask about this field…"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button
              type="button"
              id="voice"
              aria-label="Speak your question"
              className={listening ? "listening" : ""}
              onClick={voice}
            >
              <svg
                viewBox="0 0 24 24"
                width="19"
                height="19"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
              >
                <rect x="9" y="3" width="6" height="11" rx="3" />
                <path d="M6 11v1a6 6 0 0 0 12 0v-1M12 18v3M9 21h6" />
              </svg>
            </button>
            <button id="send" disabled={s.agentBusy} aria-label="Send">
              ↑
            </button>
          </form>
        </aside>
      )}
    </>
  );
}

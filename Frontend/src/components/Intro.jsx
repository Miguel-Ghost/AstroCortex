import { useEffect, useRef } from "react";
import { branding } from "../branding";
// Original visible SVG paths are kept, rather than animating paths inside <symbol>.
export function Intro({ onComplete }) {
  const ref = useRef();
  useEffect(() => {
    let id1, id2, timer;
    id1 = requestAnimationFrame(() => {
      id2 = requestAnimationFrame(() => {
        document.body.classList.add("intro-running");
        timer = setTimeout(() => {
          const intro = ref.current?.querySelector("#intro");
          if (intro) intro.hidden = true;
          document.body.classList.remove("intro-running");
          onComplete();
        }, 1550);
      });
    });
    return () => {
      cancelAnimationFrame(id1);
      cancelAnimationFrame(id2);
      clearTimeout(timer);
      document.body.classList.remove("intro-running");
    };
  }, [onComplete]);
  return <div ref={ref} dangerouslySetInnerHTML={{ __html: branding }} />;
}

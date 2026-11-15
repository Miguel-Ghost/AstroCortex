import { useRef, useState, useLayoutEffect } from "react";
export function useElementSize() {
  const ref = useRef(null),
    [size, set] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    if (!ref.current) return;
    const o = new ResizeObserver(([e]) =>
      set({ width: e.contentRect.width, height: e.contentRect.height }),
    );
    o.observe(ref.current);
    return () => o.disconnect();
  }, []);
  return [ref, size];
}

import { useEffect } from "react";
import { useStore } from "../store";
import { availableEpochs } from "../lib/manifest";
export function useFlipbookPlayer() {
  const {
    tutorialOpen,
    field,
    playing,
    mode,
    preloaded,
    fps,
    epochIndex,
    pairA,
    pairB,
    detector,
    grid,
  } = useStore();
  useEffect(() => {
    if (tutorialOpen || !field || !preloaded || !(playing || mode === "blink")) return;
    const a = availableEpochs(field, detector, grid),
      delay =
        mode === "blink"
          ? 500
          : (1000 / fps) * (epochIndex === a.at(-1) ? 2 : 1);
    const timer = setTimeout(() => {
      useStore.setState({
        epochIndex:
          mode === "blink"
            ? epochIndex === pairA
              ? pairB
              : pairA
            : (a[(a.indexOf(epochIndex) + 1) % a.length] ?? 0),
      });
    }, delay);
    return () => clearTimeout(timer);
  }, [
    tutorialOpen,
    field,
    playing,
    mode,
    preloaded,
    fps,
    epochIndex,
    pairA,
    pairB,
    detector,
    grid,
  ]);
}

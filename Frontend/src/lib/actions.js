import { useStore } from "../store";
import { TARGETS } from "../targets";
export async function runAction(a) {
  const s = useStore.getState();
  if (!a || typeof a.type !== "string") return false;
  switch (a.type) {
    case "select_target":
      if (!TARGETS.some((t) => t.target_id === a.target_id)) return false;
      await s.selectTarget(a.target_id);
      return true;
    case "set_detector":
      if (!Number.isInteger(a.detector) || a.detector < 1 || a.detector > 6)
        return false;
      s.setDetector(a.detector);
      return true;
    case "set_epoch": {
      const i = s.field?.epochs.findIndex((e) => e.epoch_id === a.epoch_id);
      if (!(i >= 0)) return false;
      s.setEpoch(i);
      return true;
    }
    case "open_tab":
      if (!["flipbook", "spectrum", "lightcurve", "catalogs"].includes(a.tab))
        return false;
      s.patch({ tab: a.tab });
      return true;
    case "play_flipbook":
      if (a.fps !== undefined && ![0.5, 1, 2, 4, 8].includes(a.fps))
        return false;
      s.patch({ playing: s.preloaded, mode: "flip", fps: a.fps || s.fps });
      return true;
    case "pause":
      s.patch({ playing: false, mode: "flip" });
      return true;
    case "show_detector_grid":
      s.patch({ grid: true, tab: "flipbook" });
      return true;
    case "select_source":
      if (!s.sources?.sources?.some((x) => x.source_id === a.source_id))
        return false;
      s.selectSource(a.source_id);
      return true;
    case "toggle_layer":
      if (!(a.layer in s.layers) || typeof a.on !== "boolean") return false;
      s.patch({ layers: { ...s.layers, [a.layer]: a.on } });
      return true;
    case "blink":
    case "show_difference": {
      const aa = s.field?.epochs.findIndex((e) => e.epoch_id === a.epoch_a),
        bb = s.field?.epochs.findIndex((e) => e.epoch_id === a.epoch_b);
      if (!(aa >= 0 && bb >= 0)) return false;
      s.patch({
        pairA: aa,
        pairB: bb,
        mode: a.type === "blink" ? "blink" : "diff",
        playing: false,
        tab: "flipbook",
      });
      return true;
    }
    default:
      return false;
  }
}

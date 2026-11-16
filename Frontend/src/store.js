import { create } from "zustand";
import { TARGETS, findTargetByName } from "./targets";
import { fetchJSON, apiPath, preload } from "./lib/api";
import { API_BASE } from "./config";
import { validateManifest, availableEpochs } from "./lib/manifest";
import { parseCoordinates } from "./lib/coords";
let controller,
  request = 0,
  toastTimer;
export const useStore = create((set, get) => ({
  field: null,
  targetId: null,
  targetStats: {},
  loadTargetStats: async () => {
    const entries = await Promise.all(
      TARGETS.map(async (t) => {
        try {
          const m = await fetchJSON(
            `/static/fields/${t.target_id}/manifest.json`,
          );
          return [
            t.target_id,
            {
              name: m.name,
              center: m.center,
              epochs: m.epochs.length,
              frames: m.epochs.reduce((n, e) => n + e.frames.length, 0),
            },
          ];
        } catch {
          return [t.target_id, null];
        }
      }),
    );
    set({ targetStats: Object.fromEntries(entries) });
  },
  status: "idle",
  error: null,
  preloaded: false,
  progress: "",
  detector: 5,
  epochIndex: 0,
  mode: "flip",
  grid: false,
  pairA: 0,
  pairB: 0,
  fps: 2,
  playing: false,
  tab: "flipbook",
  layers: {
    flags: false,
    reticle: true,
    track: true,
    sources: true,
    gaia: false,
    wise: false,
  },
  sources: null,
  catalogs: null,
  relatedError: "",
  selectedSourceId: null,
  tracking: false,
  reviewTab: "needs_review",
  classFilter: "all",
  movingOnly: false,
  tutorialOpen: false,
  chatOpen: false,
  messages: [],
  agentBusy: false,
  tour: { steps: [], index: 0, auto: false },
  toast: "",
  expanded: location.pathname.replace(/\/$/, "") === "/embed",
  sideWidth: 410,
  bottomHeight: 185,
  patch: (patch) => set(patch),
  notify: (text) => {
    set({ toast: text });
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => set({ toast: "" }), 5000);
  },
  openField: async ({ targetId, ra, dec }, restore = {}) => {
    controller?.abort();
    controller = new AbortController();
    const signal = controller.signal,
      id = ++request;
    set({
      status: "loading",
      field: null,
      error: null,
      playing: false,
      preloaded: false,
      progress: "Loading field…",
      sources: null,
      catalogs: null,
      relatedError: "",
      selectedSourceId: null,
      tracking: false,
    });
    try {
      const path = targetId
        ? `/static/fields/${targetId}/manifest.json`
        : apiPath(`/api/field?ra=${ra}&dec=${dec}&fov_arcmin=3.2`);
      const field = validateManifest(await fetchJSON(path, { signal }));
      if (id !== request) return;
      const detector =
        restore.detector ||
        TARGETS.find((t) => t.target_id === field.target_id)
          ?.default_detector ||
        5;
      const n = field.epochs.length;
      set({
        field,
        targetId: field.target_id,
        status: "ready",
        detector,
        epochIndex: 0,
        mode: "flip",
        grid: false,
        pairA: 0,
        pairB: n - 1,
        ...sanitize(restore, field),
      });
      preload(field, (done, total) => {
        if (id === request)
          set({ progress: `Loading frames ${done}/${total}…` });
      })
        .then(() => {
          if (id === request) set({ preloaded: true, progress: "" });
        })
        .catch((e) => {
          if (id === request) set({ progress: e.message });
        });
      if (API_BASE) {
        const result = await Promise.allSettled([
          fetchJSON(
            apiPath(
              `/api/sources?field_id=${encodeURIComponent(field.field_id)}`,
            ),
            { signal },
          ),
          fetchJSON(
            apiPath(
              `/api/catalogs?field_id=${encodeURIComponent(field.field_id)}`,
            ),
            { signal },
          ),
        ]);
        if (id !== request) return;
        set({
          sources: result[0].status === "fulfilled" ? result[0].value : null,
          catalogs: result[1].status === "fulfilled" ? result[1].value : null,
          relatedError: result
            .filter((r) => r.status === "rejected")
            .map((r) => r.reason.message)
            .join(" · "),
        });
      }
    } catch (e) {
      if (id === request && e.name !== "AbortError")
        set({
          status: "error",
          error: targetId
            ? e.message
            : "No SPHEREx images cover this position yet.",
          progress: "",
        });
    }
  },
  selectTarget: (id) => get().openField({ targetId: id }),
  search: (q) => {
    const t = findTargetByName(q);
    if (t) return get().selectTarget(t.target_id);
    const c = parseCoordinates(q);
    if (c) return get().openField({ ra: c[0], dec: c[1] });
    get().notify("Enter a test target name or valid RA / Dec coordinates.");
  },
  setDetector: (detector) =>
    set((s) => {
      const a = availableEpochs(s.field, detector);
      return {
        detector,
        grid: false,
        playing: false,
        mode: "flip",
        epochIndex: a.includes(s.epochIndex) ? s.epochIndex : a[0] || 0,
        pairA: a[0] || 0,
        pairB: a.at(-1) || 0,
      };
    }),
  setEpoch: (i) =>
    set((s) => ({
      epochIndex: Math.max(0, Math.min(s.field.epochs.length - 1, i)),
      playing: false,
    })),
  step: (delta) =>
    set((s) => {
      const a = availableEpochs(s.field, s.detector, s.grid);
      return {
        epochIndex:
          a[
            (Math.max(0, a.indexOf(s.epochIndex)) + delta + a.length) % a.length
          ] || 0,
        playing: false,
        mode: "flip",
      };
    }),
  togglePlay: () =>
    set((s) => ({
      playing: s.preloaded ? !s.playing : false,
      mode: "flip",
      tab: "flipbook",
    })),
  setMode: (mode) =>
    set((s) => ({
      mode: s.mode === mode ? "flip" : mode,
      playing: false,
      epochIndex: mode === "blink" ? s.pairA : s.epochIndex,
      tab: "flipbook",
    })),
  setLayer: (key) =>
    set((s) => ({ layers: { ...s.layers, [key]: !s.layers[key] } })),
  selectSource: (id) =>
    set((s) => ({
      selectedSourceId: id,
      tab: "flipbook",
      playing: false,
      mode: "blink",
      pairA: 0,
      pairB: (s.field?.epochs.length || 1) - 1,
    })),
  askAgent: async (message) => {
    if (!message.trim() || get().agentBusy) return;
    const snapshot = get();
    set({
      chatOpen: true,
      agentBusy: true,
      messages: [...snapshot.messages, { role: "user", content: message }],
    });
    try {
      const state = {
        ra: snapshot.field?.center.ra,
        dec: snapshot.field?.center.dec,
        fov_arcmin: snapshot.field?.fov_arcmin,
        field_id: snapshot.field?.field_id,
        target_id: snapshot.targetId,
        detector: snapshot.detector,
        epoch_id: snapshot.field?.epochs[snapshot.epochIndex]?.epoch_id,
        mode: snapshot.mode,
        selected_source_id: snapshot.selectedSourceId,
      };
      let r;
      if (API_BASE)
        r = await fetchJSON(apiPath("/api/agent"), {
          method: "POST",
          body: {
            message,
            view_state: state,
            history: snapshot.messages.slice(-12),
          },
        });
      else r = await fetchJSON(`/static/agent/${snapshot.targetId}.json`);
      if (snapshot.field !== get().field)
        throw Error("The field changed. Ask again for the current view.");
      const reply = r.reply || r.answer;
      if (typeof reply !== "string") throw Error("Invalid guide response.");
      set((s) => ({
        messages: [...s.messages, { role: "assistant", content: reply }],
        tour: {
          steps: Array.isArray(r.steps) ? r.steps : [],
          index: 0,
          auto: false,
        },
      }));
    } catch {
      set((s) => ({
        messages: [
          ...s.messages,
          {
            role: "assistant",
            content:
              "The guide is not available right now. You can keep exploring with the controls.",
          },
        ],
      }));
    } finally {
      set({ agentBusy: false });
    }
  },
  vote: async (label) => {
    try {
      await fetchJSON(apiPath("/api/marks"), {
        method: "POST",
        body: {
          field_id: get().field.field_id,
          source_id: get().selectedSourceId,
          ra: get().sources?.sources?.find(
            (x) => x.source_id === get().selectedSourceId,
          )?.ra,
          dec: get().sources?.sources?.find(
            (x) => x.source_id === get().selectedSourceId,
          )?.dec,
          epoch_mjd: get().field.epochs[get().epochIndex].mjd_avg,
          user_label: label,
          comment: "",
          client_id: clientId(),
        },
      });
      get().notify("Vote saved");
    } catch (e) {
      get().notify(e.message);
    }
  },
}));
export function sanitize(v, m) {
  const n = m.epochs.length,
    ix = (x) => (Number.isInteger(+x) ? Math.max(0, Math.min(n - 1, +x)) : 0);
  return {
    detector: [1, 2, 3, 4, 5, 6].includes(+v.detector)
      ? +v.detector
      : TARGETS.find((t) => t.target_id === m.target_id)?.default_detector || 5,
    epochIndex: ix(v.epochIndex),
    pairA: ix(v.pairA ?? 0),
    pairB: ix(v.pairB ?? n - 1),
    mode: ["flip", "blink", "diff", "sum"].includes(v.mode) ? v.mode : "flip",
    grid: v.grid === true,
    fps: [0.5, 1, 2, 4, 8].includes(+v.fps) ? +v.fps : 2,
    selectedSourceId: v.selectedSourceId || null,
  };
}

function clientId() {
  try {
    let id = localStorage.getItem("astrocortex-client");
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem("astrocortex-client", id);
    }
    return id;
  } catch {
    return crypto.randomUUID();
  }
}

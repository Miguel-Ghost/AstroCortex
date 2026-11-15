import { useStore } from "../store";
import { API_BASE } from "../config";
export function ClassificationPanel() {
  const s = useStore(),
    rows = s.sources?.sources || [],
    filtered = rows.filter(
      (r) =>
        (s.classFilter === "all" || r.label === s.classFilter) &&
        (!s.movingOnly || (r.evidence?.motion_px || 0) > 0) &&
        (s.reviewTab === "all" ||
          (r.review_status || "needs_review") === s.reviewTab),
    ),
    selected = rows.find((r) => r.source_id === s.selectedSourceId);
  return (
    <section className="classification" id="classification">
      <div className="classification-head">
        <strong>Source classification</strong>
        <select
          aria-label="Review status"
          value={s.reviewTab}
          onChange={(e) => s.patch({ reviewTab: e.target.value })}
        >
          <option value="needs_review">Needs review</option>
          <option value="all">All review states</option>
          <option value="reviewed">Reviewed</option>
        </select>
        <select
          id="classFilter"
          aria-label="Source class"
          value={s.classFilter}
          onChange={(e) => s.patch({ classFilter: e.target.value })}
        >
          {[
            "all",
            "cold_brown_dwarf",
            "unknown",
            "star",
            "galaxy",
            "asteroid_comet",
          ].map((k) => (
            <option key={k} value={k}>
              {k === "all" ? "All classes" : k.replaceAll("_", " ")}
            </option>
          ))}
        </select>
        <label>
          <input
            id="movingOnly"
            type="checkbox"
            checked={s.movingOnly}
            onChange={(e) => s.patch({ movingOnly: e.target.checked })}
          />
          Only moving
        </label>
        <div className="spacer" />
        <span className="muted">
          {s.sources?.method === "model"
            ? "Model"
            : s.sources?.method
              ? "Rule-based"
              : "Awaiting catalog"}
        </span>
      </div>
      <div className="table-scroll">
        {filtered.length ? (
          <table>
            <thead>
              <tr>
                {[
                  "Source",
                  "Candidate class",
                  s.sources?.calibrated ? "Calibrated score" : "Priority",
                  "Moves (px)",
                  "Review",
                ].map((k) => (
                  <th key={k}>{k}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((src) => (
                <tr
                  key={src.source_id}
                  data-source={src.source_id}
                  onClick={() => s.selectSource(src.source_id)}
                  className={
                    src.source_id === s.selectedSourceId ? "selected" : ""
                  }
                >
                  <td>{src.display_name || src.source_id}</td>
                  <td>{src.label || "unknown"}</td>
                  <td>
                    {s.sources?.calibrated &&
                    Number.isFinite(src.class_probs?.[src.label])
                      ? `${(src.class_probs[src.label] * 100).toFixed(1)}%`
                      : (src.priority ?? "—")}
                  </td>
                  <td>{src.evidence?.motion_px ?? "—"}</td>
                  <td>{src.review_status || "Needs review"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div id="sourcesEmpty" className="empty">
            {s.relatedError ||
              (!API_BASE
                ? "The team API is not configured. Classification is not available yet."
                : "No sources match this view.")}
          </div>
        )}
      </div>
      {selected && (
        <div id="sourceDetail">
          <strong>{selected.source_id}</strong>
          <span>{selected.summary || "Needs review"}</span>
          <div className="evidence">
            {selected.review_reasons?.map((x) => (
              <span className="chip" key={x}>
                {x}
              </span>
            ))}
          </div>
          <button
            className={s.tracking ? "active" : ""}
            onClick={() => s.patch({ tracking: !s.tracking })}
          >
            Track
          </button>
          <div className="votes">
            {["real", "artifact", "not_sure"].map((label) => (
              <button key={label} onClick={() => s.vote(label)}>
                {label.replaceAll("_", " ")}
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

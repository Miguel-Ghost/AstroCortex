"""Business rules of AstroCortex, with stable IDs.

Each rule is cited by its ID next to the code that enforces it and in the test that proves it
(`tests/test_rules.py` fails if a rule loses either). The human-readable table lives in
`docs/business-rules.md`.
"""

RULES: dict[str, str] = {
    # Fields and flipbook ---------------------------------------------------------------
    "BR-FIELD-01": "The grid of a field has a fixed centre (target propagated to the median date); "
    "per-date positions only go into the crosshair.",
    "BR-FIELD-02": "All epochs of one detector share one stretch, so brightness changes are real.",
    "BR-FIELD-03": "Data built from synthetic exposures always says synthetic: true.",
    "BR-FIELD-04": "An epoch may miss detectors; the gap is shown, never filled.",
    "BR-FIELD-05": "Positions are propagated to each date. A position opens a field when it is within 1 arcmin "
    "(true angular separation) of the field centre or of the target's proper-motion track between 1990 and 2030, "
    "so catalog coordinates of any epoch (the challenge's 2010 coordinate of WISE 0855 included) find the field "
    "where the target is now; the response says which way it matched.",
    "BR-FIELD-06": "A field is named by its manifest field_id; target ids, folder names and aliases resolve to it, "
    "and responses and stored votes always carry the canonical field_id.",
    # Image pipeline -------------------------------------------------------------------
    "BR-PIPE-01": "SOURCE and OUTLIER flags are never excluded from a coadd (moving objects carry them).",
    "BR-PIPE-02": "Exposures are capped per epoch and detector, never globally.",
    "BR-PIPE-03": "Keys under qr2/ are never read.",
    # Classification engine ------------------------------------------------------------
    "BR-CLS-01": "Every classification declares its method (rule or model) and version.",
    "BR-CLS-02": "A catalog type is never an input of the model.",
    "BR-CLS-03": "Uncalibrated scores are flagged calibrated: false and are not shown as probabilities.",
    "BR-CLS-04": "Methane-like colour without motion goes to review, never to cold_brown_dwarf.",
    "BR-CLS-05": "Review status: known if the catalog type agrees; needs_review if no class passes its "
    "threshold, the catalog disagrees, the source moves without catalog motion, a cold dwarf is not "
    "known, it appears in one epoch, it has no counterpart or most pixels are flagged; otherwise "
    "classified. Order: needs_review, classified, known. needs_review is a candidate, not a discovery.",
    "BR-CLS-06": "A published field always answers /api/sources: with its measured list, or, if that list is "
    "missing, with its target from the catalog (method rule); a field without catalog cross-match says "
    "catalog not_checked, never uncatalogued.",
    "BR-CLS-07": "Source evidence is measured on the published coadds (forced PSF photometry at catalog "
    "positions per date); a motion is reported only above 3 sigma and only for sources not dominated by a "
    "neighbour.",
    # Live fields ----------------------------------------------------------------------
    "BR-JOB-01": "No request waits on a live field longer than LIVE_TIMEOUT_S (60 s); the build continues and "
    "fills the disk cache, and a field folder is published atomically, never half-written.",
    "BR-JOB-02": "IRSA unavailable (503/429 after retries, timeouts) answers 503 upstream_unavailable; a position "
    "without exposures answers 404 no_coverage and is remembered for an hour.",
    # Agent ----------------------------------------------------------------------------
    "BR-AGENT-01": "The agent only emits actions from the closed vocabulary; invalid actions are dropped.",
    "BR-AGENT-02": "The live agent only uses facts returned by this API; actions that reference unknown "
    "ids are dropped; every response declares its mode and the endpoints it used.",
    "BR-AGENT-03": "If the language model fails, the response falls back to the recorded tour and says why.",
    "BR-AGENT-04": "/api/agent refuses more than AGENT_RPM_PER_IP requests a minute per client (429); the "
    "language model has a per-client and a global daily budget, beyond which the rule-based guide answers.",
    "BR-AGENT-05": "The language model only chooses the intent and writes the reply; steps come from the "
    "rule-based guide, and a reply with a number that is not in the API data is replaced by the guide's text.",
    # Marks ----------------------------------------------------------------------------
    "BR-MARK-01": "One vote per client and source; a new vote replaces the previous one.",
    "BR-MARK-02": "Responses declare where votes are stored and whether they survive a restart.",
    # Errors ---------------------------------------------------------------------------
    "BR-ERR-01": 'Every error leaves as {"error": {"code", "message", "details"}}; an unexpected error '
    "returns 500 with the request id and no stack trace.",
}

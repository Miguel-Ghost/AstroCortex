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
    "BR-FIELD-05": "Positions are propagated to each date; the challenge's 2010 coordinate of WISE 0855 "
    "is accepted as a lookup, never used as a centre.",
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
    # Live fields ----------------------------------------------------------------------
    "BR-JOB-01": "No live-field job stays running: time limit, final safety net and expiry on read.",
    "BR-JOB-02": "A provider failure ends in technical_error; a field without exposures ends in no_data.",
    # Agent ----------------------------------------------------------------------------
    "BR-AGENT-01": "The agent only emits actions from the closed vocabulary; invalid actions are dropped.",
    "BR-AGENT-02": "The live agent only uses facts returned by this API; actions that reference unknown "
    "ids are dropped; every response declares its mode and the endpoints it used.",
    "BR-AGENT-03": "If the language model fails, the response falls back to the recorded tour and says why.",
    # Marks ----------------------------------------------------------------------------
    "BR-MARK-01": "One vote per client and source; a new vote replaces the previous one.",
    "BR-MARK-02": "Responses declare where votes are stored and whether they survive a restart.",
    # Errors ---------------------------------------------------------------------------
    "BR-ERR-01": 'Every error leaves as {"error": {"code", "message", "details"}}; an unexpected error '
    "returns 500 with the request id and no stack trace.",
}

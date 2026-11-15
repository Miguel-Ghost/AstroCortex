"""Closed vocabularies of the domain.

StrEnum values travel as plain text in the API and in files, so the frontend and the data
files see strings while the code gets typo-proof names.
"""

from enum import StrEnum


class SourceClass(StrEnum):
    STAR = "star"
    GALAXY = "galaxy"
    ASTEROID_COMET = "asteroid_comet"
    COLD_BROWN_DWARF = "cold_brown_dwarf"
    UNKNOWN = "unknown"


class ClassifierMethod(StrEnum):
    RULE = "rule"
    MODEL = "model"


class Behavior(StrEnum):
    MOVES = "moves"
    VARIES = "varies"


class CatalogStatus(StrEnum):
    KNOWN_TYPED = "known_typed"  # SIMBAD / UltracoolSheet type or JPL name
    CATALOGUED_UNTYPED = "catalogued_untyped"  # in Gaia or CatWISE, no type
    UNCATALOGUED = "uncatalogued"  # catalogs checked, no counterpart
    NOT_CHECKED = "not_checked"  # no catalog cross-match for this field: never read as "no counterpart"


class Agreement(StrEnum):
    AGREES = "agrees"
    DISAGREES = "disagrees"
    NO_REFERENCE = "no_reference"


class ReviewStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    CLASSIFIED = "classified"
    KNOWN = "known"


class ReviewReason(StrEnum):
    """Closed list; the UI turns each code into an English chip."""

    BELOW_THRESHOLD = "low_confidence"
    INSUFFICIENT_DATA = "insufficient_data"
    METHANE_WITHOUT_MOTION = "methane_without_motion"
    METHANE_INDEX_HIGH_NOT_KNOWN = "methane_index_high_not_known"
    MOVES_WITHOUT_CATALOG_MOTION = "moves_without_catalog_motion"
    DISAGREES_WITH_CATALOG = "disagrees_with_catalog"
    ONLY_IN_ONE_EPOCH = "only_one_epoch"
    UNCATALOGUED = "uncatalogued"
    HIGH_FLAGGED_FRACTION = "high_flagged_fraction"
    # informative only: does not send a source to review by itself (many galaxies lack Gaia)
    NO_GAIA_COUNTERPART = "no_gaia_counterpart"


# English chip text for each review reason (served by /api/meta so the UI never hard-codes it)
REVIEW_REASON_TEXT: dict[str, str] = {
    ReviewReason.BELOW_THRESHOLD: "Low confidence",
    ReviewReason.INSUFFICIENT_DATA: "Not enough data to classify",
    ReviewReason.METHANE_WITHOUT_MOTION: "Methane-like colour, no motion",
    ReviewReason.METHANE_INDEX_HIGH_NOT_KNOWN: "High methane index, not a known dwarf",
    ReviewReason.MOVES_WITHOUT_CATALOG_MOTION: "Moves, no catalog motion",
    ReviewReason.DISAGREES_WITH_CATALOG: "Disagrees with catalog",
    ReviewReason.ONLY_IN_ONE_EPOCH: "Only in one date",
    ReviewReason.UNCATALOGUED: "Not in Gaia or CatWISE",
    ReviewReason.HIGH_FLAGGED_FRACTION: "Mostly flagged pixels",
    ReviewReason.NO_GAIA_COUNTERPART: "No Gaia counterpart",
}


class JobState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    NO_DATA = "no_data"  # the archive has no exposure of the field: not a failure of the service
    TECHNICAL_ERROR = "technical_error"  # provider or infrastructure failure: can be retried


class UserLabel(StrEnum):
    REAL = "real"
    ARTIFACT = "artifact"
    NOT_SURE = "not_sure"


class AgentMode(StrEnum):
    LIVE = "live"  # language model over this API's data
    RULE = "rule"  # deterministic planner over this API's data (no key needed)
    RECORDED = "recorded"  # a tour written to disk


class MarksStorage(StrEnum):
    MEMORY = "memory"  # lost when the instance restarts or sleeps
    POSTGRES = "postgres"

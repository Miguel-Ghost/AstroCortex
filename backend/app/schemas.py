"""API contracts. They mirror section 7 of the frontend guide; change both together."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.vocab import Agreement, CatalogStatus, ReviewReason, ReviewStatus, SourceClass

ClassName = Literal["star", "galaxy", "asteroid_comet", "cold_brown_dwarf", "unknown"]
CLASSES: tuple[str, ...] = tuple(c.value for c in SourceClass)


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    commit: str
    model_version: str
    classifier_method: str
    checks: dict[str, bool]
    static_fields: int


class Meta(BaseModel):
    """Declares which engines produce what the API returns (BR-CLS-01, BR-MARK-02)."""

    app: str
    version: str
    commit: str
    data_release: str
    classifier: dict
    marks: dict


# 7.1 -------------------------------------------------------------------------
class Sky(BaseModel):
    ra: float
    dec: float


class Target(BaseModel):
    target_id: str
    name: str
    short: str
    motion_arcsec_yr: float
    default_detector: int = Field(ge=1, le=6)
    aliases: list[str]
    approx_center: Sky
    static_manifest_url: str


# 7.2 -------------------------------------------------------------------------
class Stretch(BaseModel):
    type: Literal["asinh", "linear"] = "asinh"
    vmin: float
    vmax: float


class DetectorInfo(BaseModel):
    detector: int = Field(ge=1, le=6)
    lambda_min_um: float
    lambda_max_um: float
    stretch: Stretch


class Frame(BaseModel):
    detector: int = Field(ge=1, le=6)
    image_url: str
    data_url: str | None = None
    flags_url: str | None = None
    n_exposures: int
    flagged_frac: float


class ExpectedPosition(BaseModel):
    ra: float
    dec: float
    x: float
    y: float


class Epoch(BaseModel):
    epoch_id: str
    mjd_avg: float
    date_iso: str
    frames: list[Frame]
    expected_position: ExpectedPosition | None = None


class FieldManifest(BaseModel):
    field_id: str
    target_id: str | None = None
    center: Sky
    center_mjd: float | None = None
    fov_arcmin: float
    pixscale_arcsec: float
    nx: int
    ny: int
    orientation: Literal["north_up_east_left"] = "north_up_east_left"
    data_release: str
    pipeline_commit: str
    synthetic: bool = False
    flux_unit: str
    detectors: list[DetectorInfo]
    epochs: list[Epoch]
    spectrum_url: str | None = None
    autotype_url: str | None = None
    lightcurve_url: str | None = None
    sources_url: str
    catalogs_url: str


# 7.3 -------------------------------------------------------------------------
class ProperMotion(BaseModel):
    pmra: float
    pmdec: float


class Evidence(BaseModel):
    model_config = ConfigDict(extra="allow")  # extra features pass through to the model
    motion_px: float | None = None  # displacement seen within SPHEREx data (flipbook)
    pm_mas_yr: ProperMotion | None = None  # catalog / WISE->SPHEREx proper motion
    methane_index: float | None = None  # F(3.83-4.41 um) / F(3.20-3.45 um)
    in_gaia: bool | None = None
    in_catwise: bool | None = None
    jpl_match: str | None = None
    extended: bool | None = None
    variable: bool | None = None
    flagged_frac: float | None = None
    n_epochs_detected: int | None = None


class CatalogInfo(BaseModel):
    """What the catalogs say about a source. Never a model input (BR-CLS-02)."""

    status: CatalogStatus
    known_label: SourceClass | None = None
    known_source: str | None = None  # e.g. "SIMBAD", "UltracoolSheet", "JPL"
    simbad_type: str | None = None
    gaia_id: str | None = None
    catwise_id: str | None = None
    jpl_name: str | None = None


class Source(BaseModel):
    source_id: str
    ra: float
    dec: float
    x: float
    y: float
    label: ClassName
    class_probs: dict[str, float]
    evidence: Evidence
    catalog: CatalogInfo
    agreement: Agreement
    review_status: ReviewStatus
    review_reasons: list[ReviewReason]
    obs_ids: list[str] = []
    epoch_mjd: float | None = None


class SourcesSummary(BaseModel):
    n_sources: int
    needs_review: int
    classified: int
    known: int


class SourcesResponse(BaseModel):
    field_id: str
    method: Literal["model", "rule"]
    model_version: str
    pipeline_commit: str
    data_release: str
    synthetic: bool = False
    calibrated: bool
    classes: list[str]
    thresholds: dict[str, float]
    rule_params: dict[str, float] | None = None
    summary: SourcesSummary
    sources: list[Source]


# 7.4 -------------------------------------------------------------------------
class GaiaRow(BaseModel):
    model_config = ConfigDict(extra="allow")
    source_id: str
    ra: float
    dec: float
    g_mag: float | None = None
    pmra: float | None = None
    pmdec: float | None = None


class WiseRow(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    ra: float
    dec: float
    w1: float | None = None
    w2: float | None = None


class CatalogsResponse(BaseModel):
    field_id: str
    epoch_mjd: float | None = None
    synthetic: bool = False
    gaia: list[GaiaRow] = []
    wise: list[WiseRow] = []


# 7.7 -------------------------------------------------------------------------
class MarkIn(BaseModel):
    field_id: str = Field(max_length=100)
    source_id: str | None = Field(default=None, max_length=100)
    ra: float = Field(ge=0, lt=360)
    dec: float = Field(ge=-90, le=90)
    epoch_mjd: float | None = None
    user_label: Literal["real", "artifact", "not_sure"]
    comment: str = Field(default="", max_length=500)
    client_id: str = Field(default="anonymous", max_length=64)


class MarkOut(MarkIn):
    mark_id: int
    created_at: str


# Agent (section 9) -----------------------------------------------------------
ActionType = Literal[
    "goto",
    "select_target",
    "set_fov",
    "set_detector",
    "show_detector_grid",
    "set_epoch",
    "play_flipbook",
    "pause",
    "blink",
    "show_difference",
    "toggle_layer",
    "highlight",
    "select_source",
    "open_tab",
    "ask_vote",
]


class AgentAction(BaseModel):
    model_config = ConfigDict(extra="allow")  # parameters depend on the type (see the guide, 9.3)
    type: ActionType


class AgentStep(BaseModel):
    say: str
    actions: list[AgentAction] = []


class ViewState(BaseModel):
    ra: float | None = None
    dec: float | None = None
    fov_arcmin: float | None = None
    target_id: str | None = None
    detector: int | None = None
    epoch_id: str | None = None
    selected_source_id: str | None = None


class AgentRequest(BaseModel):
    message: str = Field(max_length=2000)
    view_state: ViewState = ViewState()
    history: list[dict] = []


class AgentResponse(BaseModel):
    reply: str
    steps: list[AgentStep]
    sources_used: list[str] = []
    recorded: bool = False


class ErrorBody(BaseModel):
    code: str
    message: str

"""Unit tests of the rules that training and serving depend on (fast, no network, no trained model)."""
import numpy as np
import pandas as pd

from motor import modelos as M
from motor.e4_preprocesamiento import duplicados_posicion
from motor.e5_modelos import umbral_fria
from motor.spherex_io import detector_number, filas_sia, key_from_url, propagate, s3_key

VOTABLE = b"""<?xml version="1.0"?><VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3"><RESOURCE type="results"><TABLE>
<FIELD ID="col1" name="access_url" datatype="char" arraysize="*"/>
<FIELD ID="col2" name="cloud_access" datatype="char" arraysize="*"/>
<FIELD ID="col3" name="t_min" datatype="double"/>
<FIELD ID="col4" name="energy_bandpassname" datatype="char" arraysize="*"/>
<DATA><TABLEDATA><TR><TD>https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/a/b.fits</TD><TD></TD>
<TD>60800.1</TD><TD>SPHEREx-D3</TD></TR></TABLEDATA></DATA></TABLE></RESOURCE></VOTABLE>"""


def test_sia_uses_column_names_not_ids():
    # IRSA fills the VOTable FIELD ID with col1, col2...; the parser must read the name attribute
    rows = filas_sia(VOTABLE)
    assert rows[0]["access_url"].endswith("b.fits")
    assert rows[0]["t_min"] == 60800.1
    assert detector_number(rows[0]["energy_bandpassname"]) == 3


def test_s3_key_from_cloud_access_or_url():
    assert s3_key('{"aws": {"key": "dr1/x.fits"}}') == "dr1/x.fits"
    assert s3_key(pd.NA) is None and s3_key(None) is None and s3_key("") is None
    url = "https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/a/b.fits"
    assert key_from_url(url) == "dr1/level2/a/b.fits"


def test_propagate_proper_motion():
    ra, dec = propagate(10.0, 0.0, 0.0, 3600.0, 2000.0, 2010.0)  # 3.6"/yr north for 10 yr = 36"
    assert abs(dec - 0.01) < 1e-9 and abs(ra - 10.0) < 1e-12


def test_positional_duplicates_grouped():
    obj = pd.DataFrame({"ra": [10.0, 10.0 + 1.0 / 3600, 50.0], "dec": [0.0, 0.0, 0.0],
                        "pmra": [0.0, 0.0, 0.0], "pmdec": [0.0, 0.0, 0.0], "epoch": [2016.0] * 3})
    groups = duplicados_posicion(obj, radius=2.0, epoch=2016.0)
    assert groups == [[0, 1]]


def test_fold_imputation_uses_training_median():
    X = np.array([[1.0, np.nan], [3.0, 4.0], [np.nan, 6.0]])
    med = M.medianas(X)
    assert med.tolist() == [2.0, 5.0]
    assert not np.isnan(M.imputar(X, med)).any()


def test_class_weights_power():
    y = np.array([0] * 90 + [1] * 10)
    w1, w0 = M.pesos_clase(y, 2, 1.0), M.pesos_clase(y, 2, 0.0)
    assert w1[1] > w1[0] and np.allclose(w0, 1.0)


def test_unknown_threshold_is_at_least_half():
    y = np.array([1] * 50 + [0] * 50)
    p = np.c_[1 - np.linspace(0, 1, 100), np.linspace(0, 1, 100)][::-1]
    tau, _ = umbral_fria(y, p, ["star", "cold_brown_dwarf"], "cold_brown_dwarf", 0.9)
    assert 0.5 <= tau <= 0.95

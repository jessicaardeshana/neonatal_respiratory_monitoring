"""Demo app backend: scenario mapping, API, frames, results (SIMULATED data; no camera is touched)."""

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from thermal.app.results import LIMITS, load_results, parse_md_tables
from thermal.app.scenarios import SCHEMA, ScenarioParams, choose_profile, to_apnea, to_synthetic
from thermal.app.server import create_app
from thermal.config import ADULT, NEONATE


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


@pytest.fixture(scope="module")
def story(client):
    return client.post("/api/run", json={}).json()


# ---- scenario mapping --------------------------------------------------------
def test_default_params_are_the_guided_tour_story():
    p = ScenarioParams()
    cfg = to_synthetic(p)
    assert cfg.rate_bpm == 14.0 and cfg.rate_steps == ((75.0, 24.0),)
    assert cfg.apnea_events == ((95.0, 25.0),) and cfg.ffc and cfg.noise
    assert to_apnea(p).min_duration_s == 20.0


def test_slider_mapping_head_noise_ambient():
    cfg = to_synthetic(ScenarioParams(head="off", noise_x=0, ambient_c=34.0, rate_change=False, apnea=False))
    assert not cfg.head_jitter and not cfg.noise and cfg.ambient_c == 34.0
    assert cfg.rate_steps == () and cfg.apnea_events == ()
    assert to_synthetic(ScenarioParams(head="large")).head_jitter_prob > to_synthetic(ScenarioParams(head="small")).head_jitter_prob
    assert to_synthetic(ScenarioParams(noise_x=2)).noise_sigma_c == pytest.approx(0.10)


def test_profile_choice_and_mixed_range_warning():
    assert choose_profile(ScenarioParams())[0] is ADULT
    p, w = choose_profile(ScenarioParams(rate_bpm=60, rate_change=False))
    assert p is NEONATE and w is None
    assert choose_profile(ScenarioParams(rate_bpm=14, rate_change=True, rate_after_bpm=60))[1] is not None


@pytest.mark.parametrize("bad", [{"rate_bpm": 3}, {"ambient_c": 50}, {"head": "wild"}, {"apnea_len_s": 500},
                                 {"apnea_start_s": 170, "apnea_len_s": 30}, {"rate_change_time_s": 190}])
def test_invalid_parameters_are_rejected(client, bad):
    assert client.post("/api/run", json=bad).status_code == 422


def test_schema_covers_every_control_and_defaults(client):
    s = client.get("/api/schema").json()
    keys = {c["key"] for c in s["controls"]}
    assert keys == {c["key"] for c in SCHEMA} and keys <= set(s["defaults"])
    ranged = {c["key"]: c for c in s["controls"] if c["kind"] == "range"}
    for k, c in ranged.items():
        assert c["min"] <= s["defaults"][k] <= c["max"]


# ---- run payload -----------------------------------------------------------------
def test_health_says_simulation(client):
    h = client.get("/api/health").json()
    assert h["ok"] and h["mode"] == "simulation"


def test_story_payload_is_labeled_simulated_and_complete(story):
    assert story["source"] == {"kind": "simulation", "label": "SIMULATED DATA"}
    assert {"run_id", "params", "meta", "frame_times", "rois", "grid_t", "stages", "truth", "summary"} <= set(story)
    assert {"raw", "ffc", "clean", "filtered", "rate", "apnea", "control_rate"} <= set(story["stages"])
    assert story["truth"]["label"] == "simulation ground truth"
    assert story["meta"]["frame_shape"] == [60, 80] and story["meta"]["profile"] == "adult"


def test_stage_arrays_are_aligned(story):
    n = len(story["grid_t"])
    st = story["stages"]
    assert len(st["raw"]["nostril"]) == len(st["raw"]["control"]) == len(st["clean"]) == n
    assert len(st["filtered"]["nostril"]) == len(st["filtered"]["control"]) == n
    assert len(st["apnea"]["envelope"]) == len(st["apnea"]["baseline"]) == len(st["apnea"]["threshold"]) == n
    r = st["rate"]
    assert len(r["t_end"]) == len(r["spectral"]) == len(r["time"]) == len(r["quality"]) == len(r["snr_db"])
    assert len(story["frame_times"]) == story["meta"]["n_frames"]
    assert all(b > a for a, b in zip(story["frame_times"], story["frame_times"][1:]))


def test_story_tells_the_intended_story(story):
    ev = story["stages"]["apnea"]["events"]
    assert len(ev) == 1 and ev[0]["kind"] == "apnea"
    assert abs(ev[0]["start"] - 95) < 3 and abs(ev[0]["end"] - 120) < 3 and ev[0]["declared_at"] < ev[0]["end"]
    s = story["summary"]
    assert s["pauses_found"] == 1 and s["false_events"] == 0 and s["rate_mae_time"] < 0.5
    assert s["ffc_injected"] == 2 and s["ffc_detected"] == 2
    assert len(story["stages"]["ffc"]["repaired"]) >= 1


def test_payload_is_valid_json_with_nulls_not_nan(client):
    text = client.post("/api/run", json={}).text
    assert "NaN" not in text and "Infinity" not in text


def test_same_parameters_hit_the_cache(client, story):
    again = client.post("/api/run", json={}).json()
    assert again["run_id"] == story["run_id"]
    other = client.post("/api/run", json={"rate_bpm": 18}).json()
    assert other["run_id"] != story["run_id"]


# ---- slider extremes degrade honestly -----------------------------------------------
def test_hot_incubator_loses_the_signal_and_says_so(client):
    r = client.post("/api/run", json={"ambient_c": 35.5, "apnea": False, "rate_change": False}).json()
    assert r["truth"]["breath_swing_c"] == 0.0
    assert r["summary"]["signal_lost_fraction"] > 0.4
    kinds = {e["kind"] for e in r["stages"]["apnea"]["events"]}
    assert kinds == {"signal_lost"}


def test_no_pause_means_no_events_in_a_clean_story(client):
    r = client.post("/api/run", json={"apnea": False}).json()
    assert r["stages"]["apnea"]["events"] == [] and r["truth"]["pauses"] == []


def test_newborn_rates_switch_profile_and_still_track(client):
    r = client.post("/api/run", json={"rate_bpm": 60, "rate_change": False, "apnea": False}).json()
    assert r["meta"]["profile"] == "neonate" and r["summary"]["rate_mae_time"] < 2.0


# ---- frames --------------------------------------------------------------------------
def test_frame_chunks_decode_to_plausible_temperatures(client, story):
    res = client.get("/api/frames", params={"run": story["run_id"], "start": 10, "count": 5})
    assert res.status_code == 200 and res.headers["X-Frame-Count"] == "5"
    a = np.frombuffer(res.content, dtype="<i2").reshape(5, 60, 80) * 0.01
    assert 22.0 < a.min() and a.max() < 36.0
    r0, r1, c0, c1 = story["rois"]["nostril"]
    assert a[:, r0:r1, c0:c1].mean() > a[:, 0:5, 0:5].mean() + 5  # warm face vs cool background


def test_frame_chunk_errors(client, story):
    assert client.get("/api/frames", params={"run": "nope"}).status_code == 404
    assert client.get("/api/frames", params={"run": story["run_id"], "start": 10**6}).status_code == 416
    big = client.get("/api/frames", params={"run": story["run_id"], "count": 10_000})
    assert int(big.headers["X-Frame-Count"]) == 256  # capped


# ---- results ---------------------------------------------------------------------------
def test_markdown_table_parser():
    t = parse_md_tables("intro\n\n| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n\ntext\n| x |\n|---|\n| y |\n")
    assert t == [{"header": ["a", "b"], "rows": [["1", "2"], ["3", "4"]]}, {"header": ["x"], "rows": [["y"]]}]


def test_results_endpoint_reads_real_reports_and_always_lists_limits(client):
    r = client.get("/api/results").json()
    assert len(r["limits"]) == len(LIMITS) >= 7
    assert any("simulated" in x["title"].lower() for x in r["limits"])
    assert "not a medical device" in r["disclaimer"].lower()
    assert {"demo", "rate", "apnea", "incubator"} <= set(r["reports"])
    assert all(rep["tables"] for rep in r["reports"].values())
    assert load_results()["reports"]["demo"]["file"] == "demo_report.md"


def test_server_only_serves_ui_from_static(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/../server.py").status_code in (404, 400)


# ---- static UI wiring -----------------------------------------------------------------
def test_every_script_and_stylesheet_the_page_loads_exists_and_is_served(client):
    import re
    from pathlib import Path

    static = Path(__import__("thermal.app.server", fromlist=["STATIC"]).STATIC)
    html = client.get("/").text
    assert "Thermal Respiratory Sensing" in html and "SIMULATED" in html.upper()
    refs = re.findall(r'(?:src|href)="(/static/[^"]+)"', html)
    assert refs, "page references no static assets"
    for ref in refs:
        assert client.get(ref).status_code == 200, ref
        assert (static / ref.removeprefix("/static/")).exists()
    # every relative ES-module import resolves to a real file
    for js in (static / "js").glob("*.js"):
        for target in re.findall(r'from\s+"\./([^"]+)"', js.read_text()):
            assert (static / "js" / target).exists(), f"{js.name} imports missing {target}"


def test_ui_never_hides_that_data_is_simulated():
    from pathlib import Path

    static = Path(__import__("thermal.app.server", fromlist=["STATIC"]).STATIC)
    js = (static / "js" / "monitor.js").read_text() + (static / "js" / "main.js").read_text()
    assert "SIMULATED" in js.upper() and "source.label" in js


# ---- Pipeline view data -----------------------------------------------------------------
def test_payload_carries_every_stage_the_pipeline_view_draws(story):
    st = story["stages"]
    n = len(story["grid_t"])
    assert len(st["raw"]["reference"]) == len(st["repaired"]["nostril"]) == len(st["repaired"]["reference"]) == n
    assert len(st["ffc"]["step_sizes"]) == len(st["ffc"]["step_times"]) == 2
    assert 1 <= len(st["ffc"]["frozen_times"]) <= 4
    assert all(0.1 <= abs(x) <= 0.3 for x in st["ffc"]["step_sizes"])  # the modeled FFC step size range
    # background has no breathing: it should be far quieter than the nose
    ref = np.array(st["raw"]["reference"], dtype=float)
    nos = np.array(st["raw"]["nostril"], dtype=float)
    assert np.ptp(ref[100:400]) < 0.2 * np.ptp(nos[100:400])


def test_repair_keeps_the_ffc_step_but_background_subtraction_removes_it(story):
    """Uses the LAST glitch (24 breaths/min): ~3 whole breaths on each side average the breathing wiggle away."""
    st, t = story["stages"], np.array(story["grid_t"])
    k = int(np.argmin(np.abs(t - st["ffc"]["step_times"][-1])))
    before, after = slice(k - 70, k - 3), slice(k + 3, k + 70)
    rep = np.array(st["repaired"]["nostril"], dtype=float)
    clean = np.array(st["clean"], dtype=float)
    jump_repaired = abs(rep[after].mean() - rep[before].mean())
    jump_clean = abs(clean[after].mean() - clean[before].mean())
    assert jump_repaired > 0.15   # frozen frames are repaired, but the level jump is still in the signal...
    assert jump_clean < 0.05      # ...until the background patch (which sees the same jump) is subtracted


def test_spectrum_peaks_at_the_true_rate_and_band_pass_removes_slow_drift(client, story):
    sp = client.get("/api/spectrum", params={"run": story["run_id"], "t0": 20, "t1": 70}).json()
    bpm = np.array(sp["bpm"])
    clean = np.nan_to_num(np.array(sp["clean"], dtype=float))
    filt = np.nan_to_num(np.array(sp["filtered"], dtype=float))
    assert abs(bpm[filt.argmax()] - 14) <= 1.0 and abs(bpm[clean.argmax()] - 14) <= 1.0
    lo, hi = sp["band_bpm"]
    assert (lo, hi) == (6.0, 42.0)
    outside = (bpm < lo * 0.6) | (bpm > hi * 1.4)  # far from the passband
    assert filt[outside].max() < 0.5 * clean[outside].max() + 1e-9


def test_window_endpoint_explains_the_estimate(client, story):
    w = client.get("/api/window", params={"run": story["run_id"], "t_end": 60}).json()
    assert w["window_s"] == 30 and abs(w["spectral_bpm"] - 14) < 1.0 and abs(w["time_bpm"] - 14) < 1.0
    assert 5 <= len(w["peaks_t"]) <= 8 and w["quality"] >= 0.5 and w["shown_time"] is not None
    assert w["resolution_bpm"] == 2.0 and len(w["signal_t"]) == len(w["signal"])
    assert abs(w["peak_bpm"] - w["spectral_bpm"]) < 0.01
    # matches what the pipeline itself reported for that window
    rate = story["stages"]["rate"]
    i = int(np.argmin(np.abs(np.array(rate["t_end"]) - w["t1"])))
    assert abs(rate["spectral"][i] - w["spectral_bpm"]) < 0.5


def test_window_during_a_pause_withholds_the_rate(client, story):
    w = client.get("/api/window", params={"run": story["run_id"], "t_end": 124}).json()
    assert w["quality"] < 0.5 and w["shown_spectral"] is None and w["shown_time"] is None


def test_analysis_endpoints_reject_bad_requests(client, story):
    rid = story["run_id"]
    assert client.get("/api/window", params={"run": rid, "t_end": 10}).status_code == 400  # window not full yet
    assert client.get("/api/spectrum", params={"run": rid, "t0": 0, "t1": 3}).status_code == 400
    assert client.get("/api/window", params={"run": "nope", "t_end": 60}).status_code == 404
    assert client.get("/api/spectrum", params={"run": "nope", "t0": 0, "t1": 60}).status_code == 404

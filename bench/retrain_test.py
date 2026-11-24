# Tests for the checks that decide whether a candidate detector is promoted. Plain asserts, no test dependency.
# Usage: ~/.cache/humanize/venv/bin/python retrain_test.py
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import retrain as R  # noqa: E402
import fit as F  # noqa: E402  (retrain puts the skill's scripts/ on the path, so it has to come first)


def source(flagged, humans):
    return {"flagged": flagged, "humans": humans}


def held(flagged, docs=275):
    return {"docs": docs, "flagged": flagged, "sections": flagged * 0.8}


def metrics(**kw):
    # modelled on the Hacker News promotion of 2026-11-10, which the gate passed
    base = {"auroc": 0.940, "human_flagged": 0.133, "ai_caught": 0.837,
            "new_ai_caught": None, "new_human_flagged": 0.120, "new_right": 0.880,
            "new_human_by_source": {"hn": source(0.120, 260)}, "holdout": held(0.105)}
    return base | kw


def row(src, label, group, prob=0.1, words=200):
    return {"source": src, "label": label, "group": group, "split": "train", "prob": prob,
            "features": {"n_words": words, "mattr": 0.5}}


def run_paired(rows, is_new, current=None, candidate=None, predict=None):
    # the fitting is stubbed out: paired() is under test for its bookkeeping, not for the model
    kept = (F.resplit, F.fit, F.predict)
    F.resplit = lambda rs, seed: (rs, rs)
    F.fit = lambda rs, names, c, clamp: (None, None)
    F.predict = predict or (lambda s, m, rs, names: np.array([r["prob"] for r in rs]))
    try:
        return R.paired("prose", rows, current or {"features": ["mattr"], "c": 1.0},
                        candidate or {"features": ["mattr"], "c": 1.0}, is_new)
    finally:
        F.resplit, F.fit, F.predict = kept


def mixed_pool():
    # one clean new source, one flagged new source, one whose rows are all too short to judge,
    # and AI rows inside the new sources the way a paired batch carries them
    return ([row("old", 0, f"o{i}") for i in range(4)] + [row("old", 1, f"a{i}", prob=0.9) for i in range(4)]
            + [row("clean", 0, f"c{i}", prob=0.1) for i in range(3)]
            + [row("clean", 0, f"cs{i}", prob=0.9, words=60) for i in range(2)]
            + [row("clean", 1, f"ca{i}", prob=0.9) for i in range(2)]
            + [row("dirty", 0, f"d{i}", prob=0.9) for i in range(3)]
            + [row("short", 0, f"s{i}", prob=0.9, words=60) for i in range(3)])


NEW = {"clean", "dirty", "short"}


def test_a_batch_flagged_like_the_rest_is_promoted():
    assert R.reasons_to_keep(metrics(), metrics()) == []


def test_a_batch_whose_own_humans_flag_well_above_the_pool_is_kept():
    cand = metrics(new_human_by_source={"newbatch": source(0.200, 300)})
    reasons = R.reasons_to_keep(metrics(), cand)
    assert len(reasons) == 1, reasons
    assert "newbatch" in reasons[0] and "0.200 against 0.133" in reasons[0] and "300 rows" in reasons[0], reasons[0]


def test_the_bar_is_the_candidates_own_pooled_rate_not_the_currents():
    # the current detector never trained on the new rows, so its rate says how new the register is, not how clean
    cur = metrics(human_flagged=0.300, new_right=0.880)
    cand = metrics(human_flagged=0.100, new_human_by_source={"newbatch": source(0.150, 300)})
    reasons = R.reasons_to_keep(cur, cand)
    assert len(reasons) == 1, reasons
    assert "0.150 against 0.100" in reasons[0], reasons[0]


def test_a_rate_exactly_on_the_line_still_promotes():
    cand = metrics(human_flagged=0.100, new_human_by_source={"newbatch": source(0.130, 300)})
    assert R.reasons_to_keep(metrics(human_flagged=0.100), cand) == []


def test_a_hair_over_the_line_is_kept():
    cand = metrics(human_flagged=0.100, new_human_by_source={"newbatch": source(0.1301, 300)})
    assert len(R.reasons_to_keep(metrics(human_flagged=0.100), cand)) == 1


def test_a_source_with_too_few_humans_is_not_judged():
    # 249 judgeable rows of clean prose cross this line 6% of the time on noise alone
    cand = metrics(new_human_by_source={"thin": source(0.900, 249)})
    assert R.reasons_to_keep(metrics(), cand) == []


def test_a_source_right_on_the_row_floor_is_judged():
    cand = metrics(new_human_by_source={"thin": source(0.900, 250)})
    assert len(R.reasons_to_keep(metrics(), cand)) == 1


def test_a_source_with_no_judgeable_rows_is_not_judged():
    cand = metrics(new_human_by_source={"allshort": source(None, 0)})
    assert R.reasons_to_keep(metrics(), cand) == []


def test_one_bad_source_beside_a_bigger_clean_one_still_fires():
    # the masking case: averaged over both sources this batch reads clean, so the check must never average
    cand = metrics(new_human_by_source={"clean": source(0.120, 2000), "dirty": source(0.300, 300)})
    reasons = R.reasons_to_keep(metrics(), cand)
    assert len(reasons) == 1, reasons
    assert "dirty" in reasons[0] and "clean" not in reasons[0], reasons[0]


def test_every_bad_source_gets_its_own_reason():
    cand = metrics(new_human_by_source={"one": source(0.300, 300), "two": source(0.400, 300)})
    assert len(R.reasons_to_keep(metrics(), cand)) == 2


def test_an_ai_only_batch_is_not_judged_on_human_rows():
    # three logged runs had new_human_flagged null; reading it as a number crashes the gate
    cand = metrics(new_human_flagged=None, new_ai_caught=0.65, new_right=0.65, new_human_by_source={})
    assert R.reasons_to_keep(metrics(new_human_flagged=None, new_ai_caught=0.60, new_right=0.60), cand) == []


def test_a_report_from_before_this_check_still_decides():
    old = {k: v for k, v in metrics().items() if k != "new_human_by_source"}
    assert R.reasons_to_keep(old, dict(old)) == []
    assert R.decide({"current": old, "candidate": dict(old)}) == ([], [])


def test_no_reason_can_be_mistaken_for_the_no_new_data_note():
    # main() compares why_not[genre] to the literal ["no new data"], and a match would promote in silence
    cand = metrics(auroc=0.800, human_flagged=0.500, ai_caught=0.500, new_right=0.100,
                   new_human_by_source={"newbatch": source(0.900, 300)})
    reasons = R.reasons_to_keep(metrics(), cand)
    assert len(reasons) == 5, reasons
    assert "no new data" not in reasons


def test_a_genre_with_nothing_against_it_is_promoted():
    assert R.promote_list(["prose", "docs"], [], {}) == (["prose", "docs"], [])


def test_force_accepts_a_cost_the_gate_priced():
    promoted, declined = R.promote_list(["prose", "docs"], ["docs"], {"docs": ["human flagged rose 0.02"]})
    assert promoted == ["prose", "docs"], promoted
    assert declined == [], declined


def test_force_cannot_promote_a_genre_with_no_new_data():
    # the candidate was refit from rows the current detector already knows, so there is no measurement to
    # accept. --force all used to promote it anyway, with no report for it in the version log.
    promoted, declined = R.promote_list(["prose", "docs"], ["prose", "docs"], {"prose": list(R.NOT_JUDGED)})
    assert promoted == ["docs"], promoted
    assert declined == ["prose"], declined


def test_a_declined_force_is_handed_back_to_be_named():
    # main() skips the kept-detector note for a no-new-data genre, so if promote_list does not report the
    # refusal the run says nothing at all about a genre the user explicitly asked for
    assert R.promote_list(["prose"], ["prose"], {"prose": list(R.NOT_JUDGED)})[1] == ["prose"]


def test_forcing_one_genre_past_the_gate_leaves_an_unjudged_one_alone():
    promoted, declined = R.promote_list(["prose", "docs"], ["prose", "docs"],
                                        {"prose": list(R.NOT_JUDGED), "docs": ["held-out human docs flagged 0.127 against 0.091"]})
    assert promoted == ["docs"] and declined == ["prose"], (promoted, declined)


def test_the_four_older_checks_still_fire_on_their_own():
    base = metrics()
    assert "AUROC fell" in R.reasons_to_keep(base, metrics(auroc=0.930))[0]
    assert "more human text flagged" in R.reasons_to_keep(base, metrics(human_flagged=0.150))[0]
    assert "less AI caught" in R.reasons_to_keep(base, metrics(ai_caught=0.800))[0]
    assert "does worse on the new data" in R.reasons_to_keep(base, metrics(new_right=0.800))[0]


def test_a_candidate_that_flags_more_held_out_human_docs_is_refused():
    # the 41-doc promotion of 2026-11-11, which passed all five of the older checks
    reasons = R.reasons_to_keep(metrics(), metrics(holdout=held(0.127)))
    assert len(reasons) == 1, reasons
    assert "0.105 -> 0.127" in reasons[0] and "275" in reasons[0]


def test_a_rise_in_the_held_out_docs_inside_the_tolerance_promotes():
    assert R.reasons_to_keep(metrics(), metrics(holdout=held(0.114))) == []


def test_the_held_out_tolerance_is_a_point_and_the_line_itself_promotes():
    # literals, not R.MAX_HOLDOUT_RISE, or the test follows the constant wherever it is moved
    assert R.reasons_to_keep(metrics(), metrics(holdout=held(0.105 + 0.009))) == []
    assert len(R.reasons_to_keep(metrics(), metrics(holdout=held(0.105 + 0.011)))) == 1
    # the comparison is >, so a rise of exactly the tolerance promotes. Added the way the check adds it:
    # 0.105 + 0.01 is 0.11499999999999999 in binary and this should not turn on which side of 0.115 lands.
    assert R.reasons_to_keep(metrics(), metrics(holdout=held(0.105 + 0.01))) == []


def test_fewer_held_out_docs_than_the_floor_are_not_judged():
    assert R.reasons_to_keep(metrics(), metrics(holdout=held(0.400, docs=99))) == []
    assert len(R.reasons_to_keep(metrics(), metrics(holdout=held(0.400, docs=100)))) == 1


def test_a_thin_held_out_set_is_named_rather_than_passed_in_silence():
    thin, reasons = R.decide({"current": metrics(holdout=held(0.105, docs=40)),
                              "candidate": metrics(holdout=held(0.400, docs=40))})
    assert thin == ["the held-out human docs (40)"], thin
    assert reasons == []


def test_a_genre_with_no_held_out_docs_is_judged_on_the_rest():
    # prose has no set that never trains, so the sixth check has to sit out rather than refuse
    bare = metrics()
    del bare["holdout"]
    worse = metrics(ai_caught=0.700)
    del worse["holdout"]
    assert R.reasons_to_keep(bare, bare) == []
    assert len(R.reasons_to_keep(bare, worse)) == 1
    assert R.decide({"current": bare, "candidate": bare}) == ([], [])


def test_the_held_out_check_reads_the_setups_the_right_way_round():
    # a candidate that flags fewer of them is an improvement, not a reason to keep the current one
    assert R.reasons_to_keep(metrics(holdout=held(0.127)), metrics(holdout=held(0.105))) == []


def test_each_older_tolerance_is_where_it_was_set():
    # literals, not R.MAX_*, or the test follows the constant wherever it is moved
    base = metrics()
    assert R.reasons_to_keep(base, metrics(auroc=0.935)) == []
    assert len(R.reasons_to_keep(base, metrics(auroc=0.9349))) == 1
    assert R.reasons_to_keep(base, metrics(human_flagged=0.143)) == []
    assert len(R.reasons_to_keep(base, metrics(human_flagged=0.1431))) == 1
    assert R.reasons_to_keep(base, metrics(ai_caught=0.817)) == []
    assert len(R.reasons_to_keep(base, metrics(ai_caught=0.8169))) == 1


def test_new_right_is_skipped_when_the_current_setup_has_none():
    assert R.reasons_to_keep(metrics(new_right=None), metrics(new_right=0.100)) == []


def test_each_new_source_is_counted_on_its_own_rows():
    by_source = run_paired(mixed_pool(), lambda r: r["source"] in NEW)["candidate"]["new_human_by_source"]
    assert set(by_source) == NEW, by_source
    assert by_source["clean"]["flagged"] == 0.0, by_source["clean"]
    assert by_source["dirty"]["flagged"] == 1.0, by_source["dirty"]
    # pooled, the three sources read 0.5; per source they read 0.0 and 1.0
    report = run_paired(mixed_pool(), lambda r: r["source"] in NEW)["candidate"]
    assert abs(report["new_human_flagged"] - 0.5) < 1e-9, report["new_human_flagged"]


def test_the_row_floor_counts_only_human_rows():
    # a paired batch brings AI rows of its own; counting them would pad the floor with rows the rate never sees
    by_source = run_paired(mixed_pool(), lambda r: r["source"] in NEW)["candidate"]["new_human_by_source"]
    assert by_source["clean"]["humans"] == 3, by_source["clean"]


def test_the_flag_rate_counts_only_human_rows():
    # AI rows flag on purpose, so mixing them in would refuse every paired batch for contamination it does not have
    by_source = run_paired(mixed_pool(), lambda r: r["source"] in NEW)["candidate"]["new_human_by_source"]
    assert by_source["clean"]["flagged"] == 0.0, by_source["clean"]


def test_the_row_floor_counts_only_rows_long_enough_to_judge():
    # a batch of short rows is judged on fewer than it brings; the floor was calibrated on the judged ones
    by_source = run_paired(mixed_pool(), lambda r: r["source"] in NEW)["candidate"]["new_human_by_source"]
    assert by_source["clean"]["humans"] == 3, "the two 60-word rows must not count"


def test_a_source_with_nothing_long_enough_is_still_listed():
    # it would otherwise vanish from the report and pass in the silence the thin notice exists to stop
    report = run_paired(mixed_pool(), lambda r: r["source"] in NEW)["candidate"]
    assert report["new_human_by_source"]["short"] == {"flagged": None, "humans": 0}
    thin, reasons = R.decide(run_paired(mixed_pool(), lambda r: r["source"] in NEW))
    assert "short (0)" in thin, thin
    assert reasons == [], reasons


def test_only_the_label_groups_that_are_new_count_towards_the_floor():
    # feedback rows share one source name, and the ones already trained on must not pad the floor
    rows = ([row("old", 0, f"o{i}") for i in range(4)] + [row("old", 1, f"a{i}", prob=0.9) for i in range(4)]
            + [row("feedback", 0, f"feedback:new{i}", prob=0.9) for i in range(3)]
            + [row("feedback", 0, f"feedback:old{i}", prob=0.9) for i in range(2)])
    is_new = lambda r: r["group"].startswith("feedback:new")  # noqa: E731
    by_source = run_paired(rows, is_new)["candidate"]["new_human_by_source"]
    assert by_source == {"feedback": {"flagged": 1.0, "humans": 3}}, by_source


def test_each_setup_counts_its_own_decisions():
    # the two fits share nothing: a shared accumulator would blend them and halve the signal
    rows = ([row("old", 0, f"o{i}") for i in range(4)] + [row("old", 1, f"a{i}", prob=0.9) for i in range(4)]
            + [row("newbatch", 0, f"n{i}") for i in range(3)])
    # the candidate is told to use two features, so the stub can tell the two fits apart
    predict = lambda s, m, rs, names: np.array([0.9 if len(names) == 2 else 0.1] * len(rs))  # noqa: E731
    report = run_paired(rows, lambda r: r["source"] == "newbatch",
                        candidate={"features": ["mattr", "ttr"], "c": 1.0}, predict=predict)
    assert report["current"]["new_human_by_source"]["newbatch"]["flagged"] == 0.0
    assert report["candidate"]["new_human_by_source"]["newbatch"]["flagged"] == 1.0


def test_a_score_exactly_on_the_cut_counts_as_flagged():
    # the pooled rate uses >= 0.5, so the per-source rate has to split the boundary the same way
    rows = ([row("old", 0, f"o{i}") for i in range(4)] + [row("old", 1, f"a{i}", prob=0.9) for i in range(4)]
            + [row("newbatch", 0, "n0", prob=0.5)])
    by_source = run_paired(rows, lambda r: r["source"] == "newbatch")["candidate"]["new_human_by_source"]
    assert by_source["newbatch"]["flagged"] == 1.0, by_source


def test_a_big_source_with_no_scored_rows_does_not_crash_the_gate():
    # judgeable rows that never land in a test split across the 20 seeds: rare, and it must not raise
    cand = metrics(new_human_by_source={"unscored": source(None, 300)})
    assert R.reasons_to_keep(metrics(), cand) == []


def test_a_thin_source_is_named_rather_than_passed_over():
    cand = metrics(new_human_by_source={"thin": source(0.900, 10), "big": source(0.120, 400)})
    thin, reasons = R.decide({"current": metrics(), "candidate": cand})
    assert thin == ["thin (10)"], thin
    assert reasons == [], reasons


def test_the_verdict_reads_the_setups_the_right_way_round():
    # swapped, an improving candidate collects refusals and a bad batch promotes
    better = metrics(auroc=0.952, human_flagged=0.120, ai_caught=0.860,
                     new_human_by_source={"hn": source(0.120, 260)})
    assert R.decide({"current": metrics(), "candidate": better}) == ([], [])
    worse = metrics(new_human_by_source={"raid": source(0.199, 360)})
    thin, reasons = R.decide({"current": metrics(), "candidate": worse})
    assert len(reasons) == 1 and "raid" in reasons[0], reasons



def test_a_label_counts_as_seen_only_by_its_salted_digest():
    kept = F.SALT_FILE
    with tempfile.TemporaryDirectory() as tmp:
        try:
            F.SALT_FILE = os.path.join(tmp, "salt")
            label = {"source": "feedback", "group": "feedback:0123456789"}
            assert not R.unseen(label, {F.label_digest("0123456789")}, set())
            # a blend from before the salt lists raw ids; those labels count as new once, nothing worse
            assert R.unseen(label, {"0123456789"}, set())
            assert R.unseen({"source": "feedback", "group": "feedback:other"}, {F.label_digest("0123456789")}, set())
            assert not R.unseen({"source": "hn", "group": "hn:1"}, set(), {"hn"})
            assert R.unseen({"source": "wikipedia", "group": "wikipedia:1"}, set(), {"hn"})
        finally:
            F.SALT_FILE = kept


def test_retraining_without_the_corpus_stops_before_touching_anything():
    # a user who installed the skill has no training corpus; they should get a sentence, not a traceback,
    # and the running scorer must not be killed on the way out
    with tempfile.TemporaryDirectory() as tmp:
        bin_dir = os.path.join(tmp, "bin")
        os.mkdir(bin_dir)
        with open(os.path.join(bin_dir, "pkill"), "w") as f:
            f.write(f"#!/bin/sh\ntouch {os.path.join(tmp, 'pkill-ran')}\n")
        os.chmod(os.path.join(bin_dir, "pkill"), 0o755)
        env = os.environ | {"HOME": tmp, "PATH": bin_dir + os.pathsep + os.environ["PATH"]}
        done = subprocess.run([sys.executable, os.path.join(HERE, "retrain.py")], env=env, capture_output=True, text=True)
        assert done.returncode != 0
        assert "retraining needs the training corpus" in done.stderr and "raid.jsonl" in done.stderr, done.stderr
        assert "Traceback" not in done.stderr, done.stderr
        assert not os.path.exists(os.path.join(tmp, "pkill-ran")), "the scorer was killed before the check"

def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ok   {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"  FAIL {test.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

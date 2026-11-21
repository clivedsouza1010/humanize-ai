# Tests for the per-register cuts fit.py writes into blend.json. Plain asserts, no test dependency.
# Usage: ~/.cache/humanize/venv/bin/python fit_test.py
import hashlib
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fit as F  # noqa: E402

SEEDS = 5


def rows(domain, label, count, start=0):
    return [{"domain": domain, "label": label, "source": "x", "index": start + i} for i in range(count)]


def oof_for(train, score):
    # the same shape oof_probs() hands over: one row per seed, one column per training row
    return np.array([[score(r) for r in train] for _ in range(SEEDS)])


def test_a_cut_is_the_score_a_tenth_of_that_registers_writers_land_above():
    train = rows("news", 0, 100)
    # scores 0.00, 0.01 ... 0.99, so a tenth of them sit at 0.90 or above
    cuts = F.register_thresholds(train, oof_for(train, lambda r: r["index"] / 100))
    assert abs(cuts["news"]["threshold_ai"] - 0.891) < 0.002, cuts["news"]
    assert abs(cuts["news"]["threshold_human"] - 0.792) < 0.002, cuts["news"]


def test_the_bar_is_never_above_the_cut():
    train = rows("books", 0, 80)
    bars = F.register_thresholds(train, oof_for(train, lambda r: r["index"] / 80))["literary"]
    assert bars["threshold_human"] < bars["threshold_ai"], bars


def test_only_that_registers_own_writers_set_its_cut():
    train = rows("news", 0, 80) + rows("email", 0, 80, start=80)
    # news writers score low here, emailers high; a pooled cut would land between them
    cuts = F.register_thresholds(train, oof_for(train, lambda r: 0.1 if r["domain"] == "news" else 0.9))
    assert cuts["news"]["threshold_ai"] == 0.1, cuts["news"]
    assert cuts["email"]["threshold_ai"] == 0.9, cuts["email"]


def test_ai_rows_do_not_set_a_cut():
    train = rows("news", 0, 80) + rows("news", 1, 80, start=80)
    cuts = F.register_thresholds(train, oof_for(train, lambda r: 0.1 if r["label"] == 0 else 0.9))
    assert cuts["news"]["threshold_ai"] == 0.1, cuts["news"]
    assert cuts["news"]["humans"] == 80, cuts["news"]


def test_a_thin_register_keeps_the_pooled_cut():
    train = rows("news", 0, F.MIN_REGISTER_HUMANS - 1)
    assert F.register_thresholds(train, oof_for(train, lambda r: 0.5)) == {}


def test_a_register_right_on_the_minimum_gets_one():
    train = rows("news", 0, F.MIN_REGISTER_HUMANS)
    assert "news" in F.register_thresholds(train, oof_for(train, lambda r: 0.5))


def test_domains_that_mean_the_same_register_are_counted_together():
    # RAID's human books and Claude's fiction are both literary; neither has 60 rows alone
    train = rows("books", 0, 35) + rows("fiction", 0, 35, start=35)
    cuts = F.register_thresholds(train, oof_for(train, lambda r: 0.4))
    assert cuts["literary"]["humans"] == 70, cuts


def test_docs_get_no_register_cuts():
    # docs rows carry a register field of their own (guide, readme, changelog); it isn't this taxonomy,
    # and their bar is "where only 2% of AI sections fall", not a quantile of human scores
    train = [r | {"register": "guide"} for r in rows("docs", 0, 400)]
    assert F.register_thresholds(train, oof_for(train, lambda r: 0.3)) == {}


def test_a_register_with_no_human_writing_gets_no_cut():
    # blog posts, cover letters, talk abstracts and social posts are AI-only in this set
    train = rows("blog", 0, 200) + rows("cover", 0, 200, start=200)
    assert F.register_thresholds(train, oof_for(train, lambda r: 0.3)) == {}


def test_the_percentile_line_gets_a_reference_of_its_own():
    train = rows("news", 0, 100)
    bars = F.register_thresholds(train, oof_for(train, lambda r: r["index"] / 100))["news"]
    assert len(bars["human_reference"]) == 101, len(bars["human_reference"])
    assert bars["human_reference"] == sorted(bars["human_reference"])
    assert bars["human_reference"][0] == 0.0 and abs(bars["human_reference"][-1] - 0.99) < 1e-9


def test_every_folds_scores_count_not_just_the_first():
    # the pooled bar is a quantile over all five folds' scores, so a register's has to be too.
    # One fold put these writers at 0.1 and the other four at 0.9: 0.1 means only fold one was read,
    # 0.74 means the folds were averaged per row, and 0.9 is the quantile over all of them.
    train = rows("news", 0, 80)
    oof = oof_for(train, lambda r: 0.9)
    oof[0] = 0.1
    assert F.register_thresholds(train, oof)["news"]["threshold_ai"] == 0.9



def test_label_ids_are_salted_so_a_blend_cannot_be_matched_to_a_text():
    # a raw id is sha1(text)[:10], which anyone holding a public copy of the labelled text can recompute
    kept = F.SALT_FILE
    with tempfile.TemporaryDirectory() as tmp:
        try:
            F.SALT_FILE = os.path.join(tmp, "nested", "salt")
            first = F.label_digest("0123456789")
            assert os.stat(F.SALT_FILE).st_mode & 0o777 == 0o600, "the salt is readable by other users"
            assert first == F.label_digest("0123456789"), "the same label gave two digests"
            assert first not in ("0123456789", hashlib.sha1(b"0123456789").hexdigest()[:10]), "the digest is unsalted"
            assert first != F.label_digest("0123456788"), "two labels share a digest"
            rows = [{"source": "feedback", "group": "feedback:0123456789"}, {"source": "feedback", "group": "feedback:0123456789"},
                    {"source": "raid", "group": "raid:3"}]
            assert F.seen_labels(rows) == [first], F.seen_labels(rows)
            F.SALT_FILE = os.path.join(tmp, "another-machine")
            assert F.label_digest("0123456789") != first, "two salts gave the same digest"
        finally:
            F.SALT_FILE = kept



def test_a_salt_already_on_disk_is_the_one_used():
    # the maintainer's shipped blend was salted with the file that is already there; a new salt would orphan it
    kept = F.SALT_FILE
    with tempfile.TemporaryDirectory() as tmp:
        try:
            F.SALT_FILE = os.path.join(tmp, "existing")
            with open(F.SALT_FILE, "w") as f:
                f.write("0123abcd\n")
            assert F.label_digest("0123456789") == hashlib.sha1(b"0123abcd:0123456789").hexdigest()[:10]
            assert open(F.SALT_FILE).read() == "0123abcd\n", "the salt on disk was replaced"
        finally:
            F.SALT_FILE = kept


def test_an_empty_salt_stops_instead_of_salting_with_nothing():
    # an empty salt makes every digest sha1(":" + id), which anyone can recompute
    kept = F.SALT_FILE
    with tempfile.TemporaryDirectory() as tmp:
        try:
            F.SALT_FILE = os.path.join(tmp, "empty")
            open(F.SALT_FILE, "w").close()
            try:
                F.label_digest("0123456789")
            except SystemExit as stop:
                assert "is empty" in str(stop), stop
            else:
                raise AssertionError("an empty salt was used")
        finally:
            F.SALT_FILE = kept

def test_a_fit_without_labels_makes_no_salt():
    kept = F.SALT_FILE
    with tempfile.TemporaryDirectory() as tmp:
        try:
            F.SALT_FILE = os.path.join(tmp, "salt")
            assert F.seen_labels([{"source": "raid", "group": "raid:1"}]) == []
            assert not os.path.exists(F.SALT_FILE), "a user with no labels got a salt file"
        finally:
            F.SALT_FILE = kept

def test_fit_will_not_write_the_live_detector_without_being_told_where():
    # a bare `fit.py features.jsonl` used to default to scripts/blend.json and bench/metrics.md, which is
    # how the rerun recipe installed an ungated detector. The guard is in main(), so run it as the recipe did.
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl") as features:
        features.write("{}\n")
        features.flush()
        done = subprocess.run([sys.executable, os.path.join(HERE, "fit.py"), features.name],
                              capture_output=True, text=True)
    assert done.returncode != 0, done.stdout
    assert "retrain.py" in done.stderr, done.stderr
    # and the default itself is gone, so it cannot come back by someone dropping the argv check
    assert not hasattr(F, "BLEND_FILE") and not hasattr(F, "METRICS_FILE"), "the live-blend default is back"


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

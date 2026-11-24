# Tests for record.py. Plain asserts so there is no test dependency to install.
# Usage: python3 record_test.py
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.join(HERE, "..", "bench")
RECORD = os.path.join(HERE, "..", "plugin", "skills", "humanize-ai", "scripts", "record.py")


def run(store, *args):
    env = os.environ | {"HUMANIZE_RUNS": store}
    done = subprocess.run([sys.executable, RECORD, *args], capture_output=True, text=True, env=env)
    assert done.returncode == 0, f"{args} failed:\n{done.stderr}"
    return done.stdout


def rows(store):
    return [json.loads(line) for line in open(store)] if os.path.exists(store) else []


def add(store, draft, rewrite, **kw):
    args = ["add", "--draft", draft, "--rewrite", rewrite]
    for key, value in kw.items():
        args += [f"--{key.replace('_', '-')}", str(value)]
    return run(store, *args)


def write(directory, name, body):
    path = os.path.join(directory, name)
    open(path, "w").write(body)
    return path


DRAFT = "In today's fast-paced world, it is important to leverage robust solutions that drive outcomes.\n"
REWRITE = "Most teams just need the thing to work on Monday.\n"


def test_a_run_is_stored_unlabelled():
    with tempfile.TemporaryDirectory() as tmp:
        store = os.path.join(tmp, "runs.jsonl")
        add(store, write(tmp, "d.md", DRAFT), write(tmp, "r.md", REWRITE), genre="prose", before=0.81, after=0.04, rounds=3)

        [row] = rows(store)
        assert row["label"] is None, f"a run must never carry a label: {row['label']!r}"
        assert row["labelled_as"] is None
        assert row["before"] == 0.81 and row["after"] == 0.04


def test_draft_and_rewrite_are_stored_apart():
    with tempfile.TemporaryDirectory() as tmp:
        store = os.path.join(tmp, "runs.jsonl")
        add(store, write(tmp, "d.md", DRAFT), write(tmp, "r.md", REWRITE), genre="prose", before=0.81, after=0.04, rounds=1)

        [row] = rows(store)
        assert row["draft"] == DRAFT.strip()
        assert row["rewrite"] == REWRITE.strip()
        assert row["draft"] != row["rewrite"]


def test_queue_offers_the_draft_and_never_the_rewrite():
    with tempfile.TemporaryDirectory() as tmp:
        store = os.path.join(tmp, "runs.jsonl")
        add(store, write(tmp, "d.md", DRAFT), write(tmp, "r.md", REWRITE), genre="prose", before=0.81, after=0.04, rounds=1)

        out = run(store, "queue")
        assert "leverage robust solutions" in out, "the queue should show the draft, which has a real author"
        assert "Monday" not in out, "the queue must never offer a rewrite for labelling: the skill wrote it"


def test_an_identical_repeat_is_not_stored_twice():
    with tempfile.TemporaryDirectory() as tmp:
        store = os.path.join(tmp, "runs.jsonl")
        draft, rewrite = write(tmp, "d.md", DRAFT), write(tmp, "r.md", REWRITE)
        add(store, draft, rewrite, genre="prose", before=0.81, after=0.04, rounds=1)
        add(store, draft, rewrite, genre="prose", before=0.81, after=0.04, rounds=1)

        assert len(rows(store)) == 1, "the same run recorded twice should not double-count in the drift stats"


def test_rehumanising_the_same_draft_later_is_a_new_run():
    with tempfile.TemporaryDirectory() as tmp:
        store = os.path.join(tmp, "runs.jsonl")
        draft = write(tmp, "d.md", DRAFT)
        add(store, draft, write(tmp, "r1.md", REWRITE), genre="prose", before=0.81, after=0.04, rounds=1)
        add(store, draft, write(tmp, "r2.md", "A different ending entirely.\n"), genre="prose", before=0.81, after=0.11, rounds=2)

        assert len(rows(store)) == 2, "a second attempt on the same draft is evidence about the rewriter"


def test_stats_reports_drift_between_the_baseline_and_recent_runs():
    with tempfile.TemporaryDirectory() as tmp:
        store = os.path.join(tmp, "runs.jsonl")
        for i in range(6):
            add(store, write(tmp, f"d{i}.md", f"{DRAFT} draft {i}"), write(tmp, f"r{i}.md", f"{REWRITE} out {i}"),
                genre="docs", before=0.80, after=0.05, rounds=1, at=f"2026-0{i + 1}-01T00:00:00")
        for i in range(6):
            add(store, write(tmp, f"n{i}.md", f"{DRAFT} newer {i}"), write(tmp, f"m{i}.md", f"{REWRITE} newer {i}"),
                genre="docs", before=0.20, after=0.05, rounds=1, at=f"2026-1{i}-01T00:00:00")

        out = run(store, "stats")
        assert "docs" in out
        assert "drift" in out.lower(), "stats should name the drift it found"
        # the detector now scores incoming drafts far lower than it used to, which is what staleness looks like
        assert "0.80" in out and "0.20" in out


def test_stats_is_quiet_when_there_is_nothing_to_say():
    with tempfile.TemporaryDirectory() as tmp:
        store = os.path.join(tmp, "runs.jsonl")
        add(store, write(tmp, "d.md", DRAFT), write(tmp, "r.md", REWRITE), genre="prose", before=0.81, after=0.04, rounds=1)

        out = run(store, "stats")
        assert "not enough" in out.lower(), "one run is not a trend and should not be reported as one"


def test_run_evidence_is_never_read_as_training_data():
    # The rule this whole design exists to keep: a run is evidence, not a label. Training reads
    # feedback.jsonl, which only label.py writes, and only from something the user stated.
    # Static check, so it fails loudly the day someone wires the store into the training set.
    builders = [os.path.join(BENCH, f) for f in os.listdir(BENCH) if f.endswith(".py")]
    assert any(f.endswith("retrain.py") for f in builders)
    for path in builders:
        assert "runs.jsonl" not in open(path).read(), f"{os.path.basename(path)} reads the run store; it must not"

    assert "feedback.jsonl" not in open(RECORD).read(), "record.py must not be able to write a training label"


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

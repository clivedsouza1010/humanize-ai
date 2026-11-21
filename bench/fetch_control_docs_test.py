# Tests for where the control fetch writes and how it dates each snapshot. Plain asserts, no test dependency.
# Usage: ~/.cache/humanize/venv/bin/python fetch_control_docs_test.py
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch_control_docs as C  # noqa: E402


def policy_file(tmp, name, projects):
    path = os.path.join(tmp, name)
    with open(path, "w") as f:
        json.dump({"projects": [{"repo": repo, "effective": date, "kind": "disclosure"} for repo, date in projects]}, f)
    return path


def every_project(tmp, date="2026-01-01"):
    return [policy_file(tmp, "policies.json", [(repo, date) for repo, _ in C.DISCLOSURE])]


def test_the_output_goes_where_the_holdout_reads_it():
    # it wrote bench/control.jsonl, which nothing in the repo has ever read, so the file behind the gate's
    # held-out docs check could not be rebuilt by anything
    assert C.OUT == os.path.expanduser("~/.cache/humanize/data/github/pr-control.jsonl"), C.OUT
    holdouts = open(os.path.join(HERE, "holdouts.py")).read()
    assert os.path.basename(C.OUT) in holdouts, "holdouts.py does not read the file this writes"


def test_each_project_is_dated_from_its_own_policy_file():
    with tempfile.TemporaryDirectory() as tmp:
        files = [policy_file(tmp, "policies.json", [(repo, f"2025-01-{i + 1:02d}") for i, (repo, _) in enumerate(C.DISCLOSURE)])]
        dated = {repo: date for repo, date, _ in C.jobs(files) if date != "2022-11-01"}
    assert dated == {repo: f"2025-01-{i + 1:02d}" for i, (repo, _) in enumerate(C.DISCLOSURE)}, dated


def test_both_policy_files_are_read():
    # the nine projects are split across policies.json and policies-train.json
    with tempfile.TemporaryDirectory() as tmp:
        first, rest = C.DISCLOSURE[:4], C.DISCLOSURE[4:]
        files = [policy_file(tmp, "policies.json", [(r, "2025-05-05") for r, _ in first]),
                 policy_file(tmp, "policies-train.json", [(r, "2026-06-06") for r, _ in rest])]
        dated = {repo: date for repo, date, _ in C.jobs(files) if date != "2022-11-01"}
    assert {dated[r] for r, _ in first} == {"2025-05-05"}, dated
    assert {dated[r] for r, _ in rest} == {"2026-06-06"}, dated


def test_a_project_with_no_policy_date_stops_the_fetch():
    # dropping it would rebuild a smaller holdout and the sixth check would score it without complaint
    with tempfile.TemporaryDirectory() as tmp:
        files = [policy_file(tmp, "policies.json", [(repo, "2026-01-01") for repo, _ in C.DISCLOSURE[1:]])]
        try:
            C.jobs(files)
        except SystemExit as exc:
            assert C.DISCLOSURE[0][0] in str(exc), exc
        else:
            raise AssertionError("a missing policy date was accepted")


def test_a_missing_policy_file_is_not_silently_an_empty_one():
    try:
        C.jobs([os.path.join(tempfile.gettempdir(), "no-such-policies.json")])
    except SystemExit as exc:
        assert "fetch policies.json" in str(exc), exc
    else:
        raise AssertionError("no policy file at all was accepted")


def test_the_pre_chatgpt_snapshots_survive_and_only_three_projects_have_one():
    with tempfile.TemporaryDirectory() as tmp:
        built = C.jobs(every_project(tmp))
    old = [(repo, cap) for repo, date, cap in built if date == "2022-11-01"]
    assert old == [(repo, cap) for repo, _, cap in C.BEFORE_CHATGPT], old
    assert len(built) == len(C.DISCLOSURE) + len(C.BEFORE_CHATGPT) == 12, len(built)


def test_the_caps_add_up_to_the_holdout_that_was_measured():
    # 178 of cap against the 168 docs on disk: threat-dragon has only 4 that qualify
    with tempfile.TemporaryDirectory() as tmp:
        assert sum(cap for _, _, cap in C.jobs(every_project(tmp))) == 178


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

# Tests for the length bounds grade_evals.py applies per genre. Plain asserts, no test dependency.
# Usage: ~/.cache/humanize/venv/bin/python grade_evals_test.py
import contextlib
import glob
import io
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import grade_evals as G  # noqa: E402

DOCS_CASE = "docs-api-shapeparse-parse"
PROSE_CASE = "reddit-loan-advice"
DOCS_DRAFT = open(os.path.join(G.SKILL_DIR, "evals", DOCS_CASE, "files", "draft.txt")).read()
PROSE_DRAFT = open(os.path.join(G.SKILL_DIR, "evals", PROSE_CASE, "files", "draft.txt")).read()
LINKED_CASE = "docs-guide-nimblet"
# directories only: a .DS_Store in evals/ (which .gitignore expects) would otherwise crash the guard tests
CASES = sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(G.SKILL_DIR, "evals", "*", "")))
LINKED_DRAFT = open(os.path.join(G.SKILL_DIR, "evals", LINKED_CASE, "files", "draft.txt")).read()


def padded(draft, target):
    # pad with the draft's own short sentences, so it gets longer without gaining a fact
    sentences = [s.strip() + "." for s in draft.split(". ") if 6 < len(s.split()) < 15]
    final, i = draft, 0
    while G.detect.compare(draft, final)["length_ratio"] < target:
        final += "\n\n" + sentences[i % len(sentences)]
        i += 1
    return final


def grade_one(case, final_text, roberta=0.01, reads=None, drift=0.0, keep_score=False):
    # run main() over one fake run with the scorer stubbed out, and hand back the grading.json it wrote.
    # `reads` goes into the stubbed score() result, so a test can hand back a document shape; `drift` of
    # None drops voice_drift from compare() the way a blend with no docs ngram table would
    with tempfile.TemporaryDirectory() as tmp:
        run = os.path.join(tmp, case, "with_skill")
        os.makedirs(os.path.join(run, "outputs"))
        with open(os.path.join(run, "outputs", "final.txt"), "w") as f:
            f.write(final_text)
        real_score, real_argv, real_compare = G.score, sys.argv, G.detect.compare

        def fake_compare(a, b):
            out = dict(real_compare(a, b))
            if drift is None:
                out.pop("voice_drift", None)
            else:
                out["voice_drift"] = drift
            return out

        if not keep_score:
            G.score = lambda text, genre: {"verdict": "human", "genre": genre, "ai_probability": 0.01,
                                           **({} if roberta is None else {"heldout_roberta": roberta}), **(reads or {})}
        G.detect.compare = fake_compare
        sys.argv = ["grade_evals.py", tmp]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                G.main()
        finally:
            G.score, sys.argv, G.detect.compare = real_score, real_argv, real_compare
        with open(os.path.join(run, "grading.json")) as f:
            return json.load(f)


def grade_one_with_score(case, final_text):
    # grade with whatever G.score the caller has already put in place
    return grade_one(case, final_text, keep_score=True)


def length_check(grading):
    return next(e for e in grading["expectations"] if "the prose word count of draft.txt" in e["text"])


def test_a_docs_tagged_case_is_graded_as_docs():
    assert G.case_genre(DOCS_CASE, DOCS_DRAFT) == "docs"


def test_a_prose_case_is_graded_as_prose():
    assert G.case_genre(PROSE_CASE, PROSE_DRAFT) == "prose"


def test_a_case_with_no_prompt_file_falls_back_to_the_genre_detect_reads():
    # no evals/ folder of this name, so the draft itself has to decide
    assert G.case_genre("not-a-case", DOCS_DRAFT) == "docs"
    assert G.case_genre("not-a-case", PROSE_DRAFT) == "prose"


def test_every_genre_the_docs_blend_scores_gets_the_tight_bounds():
    assert G.length_bounds("docs") == (0.85, 1.15)
    assert G.length_bounds("both") == (0.85, 1.15)
    assert G.length_bounds("prose") == (0.7, 1.3)


def test_a_padded_docs_rewrite_fails_the_length_check():
    low, high = G.length_bounds("docs")
    assert not low <= 1.20 <= high
    assert low <= 1.06 <= high


def test_the_same_padding_still_passes_in_prose():
    low, high = G.length_bounds("prose")
    assert low <= 1.20 <= high


def test_the_grader_itself_fails_a_padded_docs_run():
    check = length_check(grade_one(DOCS_CASE, padded(DOCS_DRAFT, 1.16)))
    assert "0.85x-1.15x" in check["text"], check["text"]
    assert not check["passed"], check["evidence"]


def test_the_grader_itself_passes_the_same_padding_in_prose():
    check = length_check(grade_one(PROSE_CASE, padded(PROSE_DRAFT, 1.16)))
    assert "0.7x-1.3x" in check["text"], check["text"]
    assert check["passed"], check["evidence"]


def test_a_docs_rewrite_that_adds_a_link_fails_a_check():
    # a brand new URL already fails the added-facts check; linking one the draft has is the hole this closes
    url = re.search(r"https?://[^\s)\]]+", LINKED_DRAFT).group(0)
    grading = grade_one(LINKED_CASE, LINKED_DRAFT + f"\n\nSee [the guide]({url}).\n")
    links = [e for e in grading["expectations"] if "links" in e["text"]]
    assert links and not links[0]["passed"], grading["expectations"]
    assert not [e for e in grading["expectations"] if e["text"].startswith("no new numbers") and not e["passed"]]


def test_a_docs_rewrite_is_graded_on_eight_checks_whether_or_not_it_adds_links():
    # six base plus code blocks and links. The link check used to appear only when a link was added, so a
    # clean run recorded no link check at all and the denominator moved with the result.
    grading = grade_one(LINKED_CASE, LINKED_DRAFT)
    assert grading["summary"]["total"] == 8, grading["expectations"]
    assert grading["summary"]["failed"] == 0, grading["expectations"]
    url = re.search(r"https?://[^\s)\]]+", LINKED_DRAFT).group(0)
    added = grade_one(LINKED_CASE, LINKED_DRAFT + f"\n\nSee [the guide]({url}).\n")
    assert added["summary"]["total"] == 8, added["expectations"]


def second_opinion(grading):
    return [e for e in grading["expectations"] if "RoBERTa" in e["text"]]


def test_a_docs_rewrite_is_not_judged_on_the_second_opinion():
    # bench/metrics.md puts it below chance on docs, so a doc over the cut has shown nothing
    grading = grade_one(DOCS_CASE, DOCS_DRAFT, roberta=0.99)
    assert second_opinion(grading) == [], grading["expectations"]
    assert grading["summary"]["failed"] == 0, grading["expectations"]


def test_a_prose_rewrite_over_the_cut_still_fails_the_second_opinion():
    checks = second_opinion(grade_one(PROSE_CASE, PROSE_DRAFT, roberta=0.99))
    assert len(checks) == 1 and not checks[0]["passed"], checks
    assert "0.99" in checks[0]["evidence"], checks[0]["evidence"]


def test_a_prose_rewrite_under_the_cut_passes_it():
    checks = second_opinion(grade_one(PROSE_CASE, PROSE_DRAFT, roberta=0.01))
    assert len(checks) == 1 and checks[0]["passed"], checks


def test_the_prose_cut_sits_at_a_half():
    # 0.5 is a bare literal here, in SKILL.md and in the eight remaining grader files, so pin the line
    # itself: loosening it is otherwise invisible to a test that only tries 0.01 and 0.99
    assert second_opinion(grade_one(PROSE_CASE, PROSE_DRAFT, roberta=0.499))[0]["passed"]
    assert not second_opinion(grade_one(PROSE_CASE, PROSE_DRAFT, roberta=0.5))[0]["passed"]
    assert not second_opinion(grade_one(PROSE_CASE, PROSE_DRAFT, roberta=0.6))[0]["passed"]


def test_each_genre_gets_the_checks_its_graders_describe():
    # The python checks and the LLM grader files are two of the three statements of the same rule, and they
    # drifted apart without anything noticing. One count each, so adding to either side alone fails here.
    # Every case, because the drift this fixed was partly per case: one docs case missing a grader file
    # would pass a loop over two named cases.
    for case in CASES:
        draft = open(os.path.join(G.SKILL_DIR, "evals", case, "files", "draft.txt")).read()
        graders = len(glob.glob(os.path.join(G.SKILL_DIR, "evals", case, "graders", "*.md")))
        checks = grade_one(case, draft)["summary"]["total"]
        assert checks == graders, f"{case}: {checks} checks against {graders} grader files"
    # and the totals themselves, so both sides moving together still needs a deliberate edit here
    assert grade_one(PROSE_CASE, PROSE_DRAFT)["summary"]["total"] == 8
    assert grade_one(DOCS_CASE, DOCS_DRAFT)["summary"]["total"] == 8


def grader(case, name):
    return open(os.path.join(G.SKILL_DIR, "evals", case, "graders", name)).read()


def test_every_threshold_a_check_uses_is_the_one_its_grader_states():
    # The count guard compares how many, not what they say: grader 08 could say 0.25 against a code bound of
    # 0.22 and still pass it. Each number that appears in a check has to appear in that check's grader file.
    for case in CASES:
        draft = open(os.path.join(G.SKILL_DIR, "evals", case, "files", "draft.txt")).read()
        low, high = G.length_bounds(G.case_genre(case, draft))
        assert f"{low}x and {high}x" in grader(case, "05-length-close.md"), case
        assert f"under {G.MAX_VOICE_DRIFT}" in grader(case, "08-voice-close-to-draft.md"), case
        assert "one per 100 words" in grader(case, "06-no-tricks.md"), case
        if G.case_genre(case, draft) != "docs":
            assert "under 0.5" in grader(case, "02-heldout-roberta-passes.md"), case


def code_check(grading):
    return next(e for e in grading["expectations"] if "code block" in e["text"])


def test_a_prose_rewrite_that_adds_a_fenced_block_fails():
    # compare() keeps whatever is inside a block out of `added` and out of length_ratio, so this check is
    # the only one that sees a number invented inside a fence. Gating it on docs let this score clean.
    fenced = PROSE_DRAFT + "\n\n```python\nrate = 0.0742  # the lender quoted this\n```\n"
    grading = grade_one(PROSE_CASE, fenced)
    check = code_check(grading)
    assert not check["passed"] and "added 1" in check["evidence"], check
    assert not [e for e in grading["expectations"] if e["text"].startswith("no new numbers") and not e["passed"]], \
        "the facts check caught it after all, so this test no longer pins the hole"


def test_a_scorer_result_with_no_verdict_fails_rather_than_raising():
    # too little prose once code and markup are removed: detect returns a warning and nothing else
    real_score = G.score
    try:
        G.score = lambda text, genre: {"words": 40, "genre": genre,
                                       "warning": "too little prose to score once code and markup are removed"}
        grading = grade_one_with_score(DOCS_CASE, DOCS_DRAFT)
    finally:
        G.score = real_score
    check = verdict_check(grading)
    assert not check["passed"] and "too little prose" in check["evidence"], check
    # docs carries no second opinion, so the verdict is the only check that has nothing to read
    assert [e["text"] for e in grading["expectations"] if not e["passed"]] == [check["text"]], grading["expectations"]


def test_a_second_opinion_that_was_never_measured_is_not_a_pass():
    checks = second_opinion(grade_one(PROSE_CASE, PROSE_DRAFT, roberta=None))
    assert len(checks) == 1 and not checks[0]["passed"] and "not reported" in checks[0]["evidence"], checks


def test_a_both_case_takes_the_prose_rules_for_sections_and_the_docs_rules_for_links():
    # no `both` case exists in evals/ yet, so this checks the shape one would get
    real = G.case_genre
    G.case_genre = lambda case, draft: "both"
    try:
        stray = {"all_sections_human": True, "sections": [{"section": 0, "verdict": "human"},
                                                          {"section": 1, "verdict": "ai"}]}
        grading = grade_one(PROSE_CASE, PROSE_DRAFT, reads=stray)
    finally:
        G.case_genre = real
    texts = [e["text"] for e in grading["expectations"]]
    assert grading["summary"]["total"] == 9, texts
    assert any("RoBERTa" in t for t in texts) and any("links" in t for t in texts), texts
    assert "0.85x-1.15x" in length_check(grading)["text"], length_check(grading)
    assert not verdict_check(grading)["passed"], "a stray ai section passed a `both` case"


def verdict_check(grading):
    return next(e for e in grading["expectations"] if e["text"].startswith("final.txt gets verdict"))


def test_a_document_with_a_section_the_verdict_tolerates_still_fails_the_round():
    # detect.py lets `verdict` stay human with one stray section; SKILL.md step 6 does not, and this is
    # the clause the grader never checked
    grading = grade_one(DOCS_CASE, DOCS_DRAFT, reads={"all_sections_human": False})
    assert not verdict_check(grading)["passed"], grading["expectations"]
    assert "all_sections_human False" in verdict_check(grading)["evidence"]


def test_a_prose_section_reading_ai_fails_the_round_and_a_docs_one_does_not():
    stray = {"all_sections_human": True, "sections": [{"section": 0, "verdict": "human"},
                                                      {"section": 1, "verdict": "ai"}]}
    assert not verdict_check(grade_one(PROSE_CASE, PROSE_DRAFT, reads=stray))["passed"]
    # in docs a short AI-looking section is mostly a false alarm, so SKILL.md skips that part
    assert verdict_check(grade_one(DOCS_CASE, DOCS_DRAFT, reads=stray))["passed"]


def test_a_text_scored_in_one_piece_is_judged_on_its_verdict_alone():
    # no sections and no all_sections_human: every eval draft is this shape today
    check = verdict_check(grade_one(PROSE_CASE, PROSE_DRAFT))
    assert check["passed"] and "scored in one piece" in check["evidence"], check


def drift_check(grading):
    return next(e for e in grading["expectations"] if "voice_drift" in e["text"])


def test_a_rewrite_that_drifts_too_far_fails():
    assert drift_check(grade_one(PROSE_CASE, PROSE_DRAFT, drift=0.3))["passed"] is False
    assert drift_check(grade_one(PROSE_CASE, PROSE_DRAFT, drift=0.22))["passed"] is False
    assert drift_check(grade_one(PROSE_CASE, PROSE_DRAFT, drift=0.219))["passed"] is True


def test_drift_that_was_never_measured_is_not_a_pass():
    # compare() drops the field when blend.json carries no docs ngram table, which a rollback can do
    check = drift_check(grade_one(PROSE_CASE, PROSE_DRAFT, drift=None))
    assert not check["passed"], check
    assert "no docs ngram table" in check["evidence"], check


def tricks_check(grading):
    return next(e for e in grading["expectations"] if e["text"].startswith("no hidden characters"))


# nonsense, so no dictionary has them and nothing in a draft does
UNKNOWN = ["zorbleflux", "quintavex", "plimbrash"]


def test_a_hidden_character_or_a_look_alike_letter_fails():
    # this check had no test at all: replacing it with True passed the suite
    assert tricks_check(grade_one(PROSE_CASE, PROSE_DRAFT))["passed"]
    assert not tricks_check(grade_one(PROSE_CASE, PROSE_DRAFT + " zero\u200bwidth"))["passed"]
    # one Cyrillic letter standing in for a Latin a
    assert not tricks_check(grade_one(PROSE_CASE, PROSE_DRAFT.replace("a", "\u0430", 1)))["passed"]


def test_the_spelling_budget_is_one_word_per_100():
    # grader 06 states this budget exactly, so the code has to keep it. The prose draft is about 250 words,
    # so two words outside the dictionary pass and a third fails.
    words = len(PROSE_DRAFT.split())
    assert max(1, (words + 3) // 100) == 2, f"the draft is {words} words, so this test needs new numbers"
    assert tricks_check(grade_one(PROSE_CASE, PROSE_DRAFT + " " + " ".join(UNKNOWN[:2])))["passed"]
    assert not tricks_check(grade_one(PROSE_CASE, PROSE_DRAFT + " " + " ".join(UNKNOWN)))["passed"]


def test_a_short_rewrite_still_gets_one_word():
    # under 200 words the budget rounds down to zero or one; the floor keeps it at one
    short = " ".join(PROSE_DRAFT.split()[:90])
    assert tricks_check(grade_one(PROSE_CASE, short + " " + UNKNOWN[0]))["passed"]
    assert not tricks_check(grade_one(PROSE_CASE, short + " " + " ".join(UNKNOWN[:2])))["passed"]


def test_capitalised_words_and_the_drafts_own_words_do_not_count():
    # names, and vocabulary the author already used, are not misspellings
    named = PROSE_DRAFT + " " + " ".join(w.capitalize() for w in UNKNOWN)
    assert tricks_check(grade_one(PROSE_CASE, named))["passed"]
    # grade_one always grades against the case's real draft, so the draft rule is read off odd_words itself
    own = PROSE_DRAFT + " " + " ".join(UNKNOWN)
    assert G.odd_words(own, own + " " + " ".join(UNKNOWN)) == []
    assert G.odd_words(PROSE_DRAFT, own) == UNKNOWN


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

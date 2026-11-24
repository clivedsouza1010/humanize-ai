# Tests for build_set.py's normalisation and the artifact gate. Plain asserts, no test dependency.
# Usage: ~/.cache/humanize/venv/bin/python build_set_test.py
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_set as B  # noqa: E402

LONG = " ".join(["word"] * 70)


def gate():
    assert "space before punctuation" in B.ARTIFACTS, "the build has no alarm for the gap coming back"
    return B.ARTIFACTS["space before punctuation"]


def test_a_space_before_punctuation_is_closed():
    # every shape the gap took in the set, one per source it came from, in made-up words
    assert B.close_gaps("The soup was good . The bread was better .") \
        == "The soup was good. The bread was better."
    assert B.close_gaps("Acme Widgets Inc. , a small company") == "Acme Widgets Inc., a small company"
    assert B.close_gaps("write to us at help@example.com ; quote your order number") \
        == "write to us at help@example.com; quote your order number"
    assert B.close_gaps("is run by , mostly retired teachers") == "is run by, mostly retired teachers"
    assert B.close_gaps("a puzzle game like Falling Blocks . A slow turn based one") \
        == "a puzzle game like Falling Blocks. A slow turn based one"
    assert B.close_gaps(r"+ \dots . \] Another example") == r"+ \dots. \] Another example"
    # the quoted-printable soft wrap that left the comma on its own. Runs of spaces after it are
    # canon()'s job, not this rule's
    assert B.close_gaps("until the paint dries=   ,   until the floor is done") \
        == "until the paint dries=,   until the floor is done"


def test_the_rule_runs_on_the_ai_side_too():
    # the gap was one-sided, so a rule that only touched human rows would keep it that way
    ai = "The model achieves strong results , and generalises well ."
    assert B.close_gaps(ai) == "The model achieves strong results, and generalises well."


def test_a_punctuation_only_line_is_pulled_back():
    # AESLC splits one sentence per line, so a typed "..." arrives as bare dots on their own lines
    assert B.close_gaps("lots to sort out.\n.\n.\n.\nI have a list") \
        == "lots to sort out....\nI have a list"
    assert B.close_gaps("no change is planned.\n?\nIf the order volume") == "no change is planned.?\nIf the order volume"
    assert B.close_gaps("the long weekend.\n!\n!\nMon Jan5") == "the long weekend.!!\nMon Jan5"
    assert B.close_gaps("in the last round.\n, who joined late") == "in the last round., who joined late"


def test_a_dot_word_is_not_glued_to_the_word_before_it():
    assert B.close_gaps("copy the .env file") == "copy the .env file"
    assert B.close_gaps("listed in .gitignore already") == "listed in .gitignore already"


def test_a_decimal_keeps_its_point():
    assert B.close_gaps("Set a margin of .25  .") == "Set a margin of .25."


def test_a_split_clitic_is_rejoined():
    assert B.close_gaps("Churchill 's speech") == "Churchill's speech"
    assert B.close_gaps("they do n't know what it 's for") == "they don't know what it's for"


def test_paragraph_breaks_survive():
    # closing the gap must not weld lines together: layout is the one thing canon() already flattens
    assert B.close_gaps("One sentence.\n\nTwo sentences.") == "One sentence.\n\nTwo sentences."
    assert B.close_gaps("in town a couple of weeks ago .\nIt was pretty good.") \
        == "in town a couple of weeks ago.\nIt was pretty good."


def test_a_line_that_opens_on_a_colon_and_carries_text_is_left_alone():
    # doc_prose drops a bold label and leaves ": text" starting the paragraph, and AESLC breaks
    # after "P.S." the same way. Both labels have it, and pulling it back welds two sentences.
    for text in ("existing posts need no change.\n\n: With the changes in Next.js 12, the first render",
                 "I look forward to talking tomorrow.\nSam  \tP.S.\n:  Alex, I added you because",
                 # a whole paragraph of just punctuation stays too: a blank line is worth more than
                 # tidying a row the gate pattern does not read
                 "the first render.\n\n:\n\nWith the changes in Next.js 12"):
        assert B.close_gaps(text) == text, B.close_gaps(text)


def test_detokenize_still_joins_hc3_tokens():
    assert B.detokenize('he said " the end " to me') == 'he said "the end" to me'
    assert B.detokenize("it ( mostly ) works") == "it (mostly) works"
    assert B.detokenize("about 40 % of them") == "about 40% of them"
    assert B.detokenize("a well - known case") == "a well-known case"
    assert B.detokenize("see # 3 and $ 5") == "see #3 and $5"
    assert B.detokenize("you 're done , I think .") == "you're done, I think."


def test_the_gate_watches_for_the_shapes_the_rule_closes():
    # the gate is the alarm for this coming back, so it has to match what the rule exists to remove
    for text in ("this place . It was", "run by , mostly", "the end .", "questions.\n.\n.", "a pause ; then"):
        assert re.search(gate(), text), text
        assert not re.search(gate(), B.close_gaps(text)), B.close_gaps(text)
    assert not re.search(gate(), "copy the .env file")


def test_spaced_markup_reads_markup_and_not_cron():
    # the rows this pattern hits are cron lines, C comments and email dividers, written on both
    # labels. The gate is armed now, so a pattern that reads those halts the build over something
    # there is nothing to clean, and the only way out is editing the gate to pass the gate.
    pattern = B.ARTIFACTS["spaced markup"]
    # a truncated row can carry one side on its own, so there is a case for each half
    for text in ("a * *bold* * word", "a row cut off at * *bold", "a section ending on bold* *"):
        assert re.search(pattern, text), text
    for text in ("45 * * * * *", '"0 1 * * 0"', "cron: 0 */12 * * *", "15 9 * * 1-5",
                 "{/* */}", "/** */", "* * *   The newsletter presents", "**bold** text, as every doc writes it"):
        assert not re.search(pattern, text), text


def test_the_gate_fires_on_a_lopsided_split():
    # the split the old min == 0 test let through, and the one-label shapes it did catch
    assert B.one_sided([53, 2]), "a 53-to-2 split is the one that got through"
    assert B.one_sided([24, 0])
    assert B.one_sided([0, 48])
    assert B.one_sided([5, 0])
    # one past the line, so the line itself is pinned from both sides
    assert B.one_sided([11, 1])


def test_the_gate_stays_quiet_on_what_the_set_already_carries():
    # the five ARTIFACTS entries as the build read them on 2026-11-13 — three at 0/0, one AI-only
    # pair under the floor, one that hits rows — then the readings from before the set last grew,
    # and the 11-to-2 `[.,;:!?]` shape REPORT.md leaves in on purpose
    for counts in ([0, 0], [0, 2], [32, 12], [11, 2], [16, 9], [5, 2], [8, 2]):
        assert not B.one_sided(counts), counts
    # under five rows is noise either way, and exactly ten to one is the line itself
    assert not B.one_sided([4, 0])
    assert not B.one_sided([10, 1])


def raid_row(text, label):
    return {"text": text, "label": label, "source": "raid", "model": "human" if label == 0 else "chatgpt", "domain": "news"}


def fake_data_dir(tmp, raid=None):
    data = os.path.join(tmp, "data")
    os.mkdir(data)
    raid = raid or [raid_row("The battle ended in defeat , and the army withdrew .", 0),
                    raid_row("The model achieves strong results , and generalises well .", 1)]
    with open(os.path.join(data, "raid.jsonl"), "w") as f:
        for row in raid:
            f.write(json.dumps(row) + "\n")
    open(os.path.join(data, "reddit_eli5.jsonl"), "w").close()
    pq.write_table(pa.table({"email_body": [f"Full program details are now available at www.example.org . {LONG}"]}),
                   os.path.join(data, "aeslc-test.parquet"))
    return data


def fake_tree(tmp):
    # symlink the real modules so build_set.py runs as itself, with its words.txt landing in here
    for name in ("bench", os.path.join("plugin", "skills", "humanize-ai", "scripts")):
        os.makedirs(os.path.join(tmp, name))
        for entry in os.listdir(os.path.join(HERE, "..", name)):
            if entry in ("words.txt", "__pycache__"):
                continue
            os.symlink(os.path.join(HERE, "..", name, entry), os.path.join(tmp, name, entry))
    return os.path.join(tmp, "bench", "build_set.py")


def declared(rows):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return f.name


PROSE = " ".join(["the page explains how the setting works and what it changes"] * 12)


def doc(repo, provenance, path="docs/guide.md"):
    return {"repo": repo, "path": path, "provenance": provenance, "doc_type": "guide", "text": "# Guide\n\n" + PROSE}


def test_only_the_ai_side_of_a_provenance_source_trains():
    # the human side is one doc, so it is left out rather than taught as a label
    path = declared([doc("a/a", "ai"), doc("b/b", "human")])
    rows = B.github_rows(path, None, "gh-declared")
    assert {r["repo"]: r["label"] for r in rows} == {"a/a": 1}, rows
    assert {r["model"] for r in rows} == {"declared-ai"}


def test_a_held_back_project_never_trains():
    # nothing is in PR_HELD_BACK today; the mechanism is still what enforces a decision to hold one back
    path = declared([doc("a/a", "ai"), doc("held/back", "ai")])
    kept = B.PR_HELD_BACK
    B.PR_HELD_BACK = {"held/back"}
    try:
        assert {r["repo"] for r in B.github_rows(path, None, "gh-declared")} == {"a/a"}
    finally:
        B.PR_HELD_BACK = kept


def test_a_provenance_row_keeps_the_type_its_fetcher_gave_it():
    # OWASP keeps its docs in cheatsheets/, which the path rule does not recognise; the policy covers them
    path = declared([doc("a/a", "ai", path="cheatsheets/Authorization_Patterns_Cheat_Sheet.md")])
    assert [r["label"] for r in B.github_rows(path, None, "gh-declared")] == [1]


def test_a_fixed_label_source_still_goes_by_the_path():
    path = declared([{"repo": "a/a", "path": "cheatsheets/x.md", "doc_type": "guide", "text": "# X\n\n" + PROSE}])
    assert B.github_rows(path, 0, "gh-human") == []


def test_a_fixed_label_source_ignores_both():
    # the older files have no provenance field and no project is held back from them
    path = declared([{"repo": "held/back", "path": "docs/guide.md", "doc_type": "guide", "text": "# Guide\n\n" + PROSE}])
    kept = B.PR_HELD_BACK
    B.PR_HELD_BACK = {"held/back"}
    try:
        assert [r["label"] for r in B.github_rows(path, 0, "gh-human")] == [0]
    finally:
        B.PR_HELD_BACK = kept


def test_every_source_and_both_labels_go_through_the_same_rule():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.jsonl")
        done = subprocess.run([sys.executable, fake_tree(tmp), fake_data_dir(tmp), out], capture_output=True, text=True)
        assert done.returncode == 0, done.stderr

        rows = [json.loads(line) for line in open(out)]
        assert "artifact space before punctuation: human 0, ai 0" in done.stderr, done.stderr
        for row in rows:
            assert not re.search(gate(), row["text"]), (row["source"], row["label"], row["text"][:80])
        by_label = {row["label"]: row["text"] for row in rows if row["source"] == "raid"}
        assert by_label[0].startswith("The battle ended in defeat, and the army withdrew."), by_label[0]
        assert by_label[1].startswith("The model achieves strong results, and generalises well."), by_label[1]
        assert any(r["source"] == "aeslc" and "www.example.org." in r["text"] for r in rows), "aeslc row missing or untouched"



def test_a_retired_eval_draft_and_a_labelled_texts_words_stay_out():
    # an eval draft edited after it was written is still a row in the source data, so it stays out by hash;
    # a labelled text trains, but its own words must not ship in words.txt
    draft = f"A retired eval draft about frobnicators and their keepers. {LONG}"
    with tempfile.TemporaryDirectory() as tmp:
        build, data = fake_tree(tmp), fake_data_dir(tmp)
        retired = os.path.join(tmp, "bench", "retired-eval-drafts.txt")
        os.remove(retired)
        with open(retired, "w") as f:
            f.write(f"# a comment line\n{hashlib.sha1(B.canon(draft).encode()).hexdigest()} the test draft\n")
        with open(os.path.join(data, "claude-test.jsonl"), "w") as f:
            f.write(json.dumps({"text": draft, "label": 1, "source": "claude", "model": "claude", "domain": "essay"}) + "\n")
            f.write(json.dumps({"text": f"A kept draft about lighthouses. {LONG}", "label": 1, "source": "claude", "model": "claude", "domain": "essay"}) + "\n")
        with open(os.path.join(data, "feedback.jsonl"), "w") as f:
            f.write(json.dumps({"id": "abc", "text": f"zorblax zorblax zorblax keeps its name. {LONG} {LONG}", "label": 1, "domain": "prose"}) + "\n")
        out = os.path.join(tmp, "out.jsonl")
        done = subprocess.run([sys.executable, build, data, out], capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        rows = [json.loads(line) for line in open(out)]
        assert not any("frobnicators" in r["text"] for r in rows), "the retired draft got into the set"
        assert any("lighthouses" in r["text"] for r in rows), "a draft that isn't retired was dropped too"
        assert any(r["source"] == "feedback" and "zorblax" in r["text"] for r in rows), "the label didn't train"
        words = open(os.path.join(tmp, "plugin", "skills", "humanize-ai", "scripts", "words.txt")).read().split()
        assert "lighthouses" not in words and "word" in words, "words.txt wasn't built from the rows"
        assert "zorblax" not in words, "a labelled text's words shipped in words.txt"

def test_the_build_stops_on_a_lopsided_artifact():
    # 12 human rows against 1 AI row. The old min == 0 test waved a split like this through, so the
    # gate has to be wired to the ratio or a pattern that picks up a stray hit goes quiet again.
    raid = [raid_row(rf"Report {i} landed.\n {LONG}", 0) for i in range(12)]
    raid.append(raid_row(rf"One model card.\n {LONG}", 1))
    with tempfile.TemporaryDirectory() as tmp:
        done = subprocess.run([sys.executable, fake_tree(tmp), fake_data_dir(tmp, raid), os.path.join(tmp, "out.jsonl")],
                              capture_output=True, text=True)
        assert done.returncode != 0, done.stderr
        assert "artifact 'literal \\n' is one-sided (12 human, 1 ai)" in done.stderr, done.stderr


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

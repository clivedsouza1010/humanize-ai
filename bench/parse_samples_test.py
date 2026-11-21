# Tests for parse_samples.py. Plain asserts, no test dependency.
# Usage: python3 parse_samples_test.py
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PARSE = os.path.join(HERE, "parse_samples.py")
LONG = " ".join(["word"] * 80)


def run(out, *args, expect=0):
    done = subprocess.run([sys.executable, PARSE, out, *args], capture_output=True, text=True)
    assert done.returncode == expect, f"expected exit {expect}, got {done.returncode}:\n{done.stderr}{done.stdout}"
    return done.stdout


def report(tmp, body):
    path = os.path.join(tmp, "agent.txt")
    open(path, "w").write(body)
    return path


def piece(genre, text):
    return f"<<<PIECE genre={genre}>>>\n{text}\n<<<END>>>\n\n"


def test_pieces_become_items_the_importer_understands():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.json")
        run(out, "--model", "haiku", "--kind", "prose",
            report(tmp, piece("email", LONG) + piece("review", LONG)))

        [job] = json.load(open(out))["result"]
        assert job["model"] == "haiku" and job["kind"] == "prose"
        assert [i["genre"] for i in job["items"]] == ["email", "review"]
        assert job["items"][0]["text"].startswith("word word")


def test_commentary_outside_the_blocks_is_dropped():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.json")
        body = "Here are the 10 pieces you asked for:\n\n" + piece("email", LONG) + "\nLet me know if you want changes.\n"
        run(out, "--model", "sonnet", "--kind", "prose", report(tmp, body))

        [job] = json.load(open(out))["result"]
        assert len(job["items"]) == 1
        assert "Let me know" not in job["items"][0]["text"]
        assert "asked for" not in job["items"][0]["text"]


def test_docs_carry_a_register_the_importer_can_read():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.json")
        run(out, "--model", "opus", "--kind", "docs", "--register", "marketing",
            report(tmp, piece("readme", LONG)))

        [job] = json.load(open(out))["result"]
        # import_default_samples.py does key.split("-")[1] to find the register
        assert job["key"].split("-")[1] == "marketing", job["key"]
        assert job["items"][0]["doc_type"] == "readme"
        assert "genre" not in job["items"][0]


def test_a_piece_too_short_to_score_is_dropped():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.json")
        stdout = run(out, "--model", "haiku", "--kind", "prose",
                     report(tmp, piece("email", LONG) + piece("social", "too short to be worth scoring")))

        [job] = json.load(open(out))["result"]
        assert len(job["items"]) == 1, "a 6-word piece is noise in a set fitted on 120-220 word texts"
        assert "dropped" in stdout.lower()


def test_an_unclosed_block_is_not_emitted():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.json")
        body = piece("email", LONG) + f"<<<PIECE genre=review>>>\n{LONG}\n"
        run(out, "--model", "haiku", "--kind", "prose", report(tmp, body))

        [job] = json.load(open(out))["result"]
        assert [i["genre"] for i in job["items"]] == ["email"], "a truncated agent reply must not become a half-piece"


def test_a_two_bracket_terminator_is_accepted():
    # A real agent closed its last block with <<<END>> instead of <<<END>>>. Dropping the
    # piece over one angle bracket loses data for no reason; it is plainly the same token.
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.json")
        run(out, "--model", "sonnet", "--kind", "prose",
            report(tmp, piece("email", LONG) + f"<<<PIECE genre=talk>>>\n{LONG}\n<<<END>>\n"))

        [job] = json.load(open(out))["result"]
        assert [i["genre"] for i in job["items"]] == ["email", "talk"]


def test_a_second_call_appends_instead_of_overwriting():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.json")
        run(out, "--model", "haiku", "--kind", "prose", report(tmp, piece("email", LONG)))
        b = os.path.join(tmp, "b.txt")
        open(b, "w").write(piece("blog", LONG))
        run(out, "--model", "opus", "--kind", "prose", b)

        jobs = json.load(open(out))["result"]
        assert len(jobs) == 2, "each model is its own job; the second must not replace the first"
        assert [j["model"] for j in jobs] == ["haiku", "opus"]


def test_several_agent_reports_merge_into_one_file():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.json")
        a = report(tmp, piece("email", LONG))
        b = os.path.join(tmp, "b.txt")
        open(b, "w").write(piece("blog", LONG))
        run(out, "--model", "haiku", "--kind", "prose", a, b)

        [job] = json.load(open(out))["result"]
        assert [i["genre"] for i in job["items"]] == ["email", "blog"]


def test_it_refuses_to_write_an_empty_job():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.json")
        run(out, "--model", "haiku", "--kind", "prose", report(tmp, "I could not complete this task."), expect=1)
        assert not os.path.exists(out), "an empty job would silently shrink the training set"


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

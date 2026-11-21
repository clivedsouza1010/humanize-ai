# Tests for fetch_hn.py. Plain asserts, no test dependency.
# Usage: python3 fetch_hn_test.py
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch_hn as H

LONG = " ".join(["word"] * 110)


def test_paragraph_tags_become_blank_lines():
    assert H.to_text(f"one{LONG}<p>two") == f"one{LONG}\n\ntwo"


def test_italics_lose_the_tag_and_keep_the_words():
    assert H.to_text("he said <i>really</i> loudly") == "he said really loudly"


def test_entities_are_turned_back_into_characters():
    assert H.to_text("I&#x27;ve seen &quot;this&quot; &amp; that, a &gt; b") == 'I\'ve seen "this" & that, a > b'


def test_a_double_escaped_entity_is_not_resolved_twice():
    # HN writes a literal "&gt;" that someone typed as "&amp;gt;". Resolving &amp; first
    # would turn it into a quote marker.
    assert H.to_text("&amp;gt; is how you quote") == "&gt; is how you quote"


def test_a_comment_with_a_link_is_dropped():
    # A pasted URL is a provenance tell no model produces, and keeping it would let the
    # detector read the format instead of the voice.
    assert H.reject(f'<a href="https://x.com" rel="nofollow">x.com</a> {LONG}') == "link"
    assert H.reject(f"see https://example.com/thing {LONG}") == "link"
    assert H.reject(f"go to www.example.com {LONG}") == "link"


def test_a_slash_escaped_url_is_still_a_link():
    # HN writes '/' as &#x2F;. Checking the raw html let 33 of these through the first time,
    # because the text only looks like a url after the entities are resolved.
    assert H.reject(f"see https:&#x2F;&#x2F;example.com&#x2F;thing {LONG}") == "link"


def test_a_comment_with_code_is_dropped():
    assert H.reject(f"<pre><code>  npm install\n</code></pre> {LONG}") == "code"


def test_a_quoted_line_is_dropped():
    # '> ' quoting is a forum convention, not a way of writing. Same reason build_set.py
    # strips HC3's tokenizer residue.
    assert H.reject(f"&gt; you said this\nNo I didn&#x27;t. {LONG}") == "quote"


def test_markup_that_survived_cleaning_drops_the_row():
    assert H.reject(f"<blockquote>unexpected</blockquote> {LONG}") == "markup"
    assert H.reject(f"half an entity &nbsp; here {LONG}") == "markup", "an entity nobody anticipated must drop the row, not enter the data"


def test_text_outside_the_length_band_is_dropped():
    assert H.reject("too short to score") == "length"
    assert H.reject(" ".join(["word"] * 80)) == "length", "detect.py gives no verdict at 80 words"
    assert H.reject(" ".join(["word"] * 400)) == "length"
    assert H.reject(LONG) is None


def test_a_comment_that_says_a_model_wrote_it_is_dropped():
    assert H.reject(f"ChatGPT wrote the following for me: {LONG}") == "disclosed"
    assert H.reject(f"{LONG} (written with Claude)") == "disclosed"


def test_dead_and_empty_comments_are_dropped():
    assert H.reject("") == "length"
    assert H.reject(f"[flagged] {LONG}") == "dead"
    assert H.reject(f"[dead] {LONG}") == "dead"


def test_an_account_opened_after_chatgpt_is_not_trusted():
    # The whole provenance claim is that the person was writing here before a model could.
    assert H.account_ok(H.ACCOUNT_BEFORE - 1)
    assert not H.account_ok(H.ACCOUNT_BEFORE + 1)


def test_an_author_whose_account_cannot_be_read_is_not_trusted():
    # account_created hands back None when the lookup fails or the account is gone.
    # Reading that as 'old enough' would let anything in on a bad network.
    assert not H.account_ok(None)


def test_rows_carry_what_the_builder_and_the_split_need():
    row = H.row("Alice", "comment", LONG, 1700000000)
    assert row["label"] == 0 and row["source"] == "hn" and row["model"] == "human"
    assert row["domain"] == "forum", "prose is everything that is not docs, and the domain names the genre"
    assert row["group"] == "hn:alice", "one author stays on one side of the split, however they capitalise"
    assert row["date"].startswith("2023-11-"), row["date"]
    assert H.row("Alice", "ask", LONG, 1700000000)["domain"] == "ask"


def test_one_row_per_author():
    hits = [{"author": "alice", "comment_text": LONG, "created_at_i": 1700000000},
            {"author": "alice", "comment_text": LONG + " again", "created_at_i": 1700000001},
            {"author": "bob", "comment_text": LONG, "created_at_i": 1700000002}]
    rows, _ = H.collect(hits, "comment", lambda name: True)
    assert [r["author"] for r in rows] == ["alice", "bob"], "a prolific commenter would otherwise set the human voice"


def test_an_untrusted_author_costs_nothing_but_their_own_row():
    hits = [{"author": "new", "comment_text": LONG, "created_at_i": 1700000000},
            {"author": "old", "comment_text": LONG, "created_at_i": 1700000001}]
    rows, counts = H.collect(hits, "comment", lambda name: name == "old")
    assert [r["author"] for r in rows] == ["old"]
    assert counts["account"] == 1


def test_windows_spread_across_the_whole_range():
    # One walk back from today lands the whole sample in one week of one news cycle.
    spread = H.anchors(now=1000, floor=200, count=4)
    assert spread == [1000, 800, 600, 400], spread
    assert len(H.anchors(1000, 200, 8)) == 8
    assert all(a > 200 for a in H.anchors(1000, 200, 8))


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

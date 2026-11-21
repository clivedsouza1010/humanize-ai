# Tests for fetch_wikipedia.py. Plain asserts, no test dependency.
# Usage: python3 fetch_wikipedia_test.py
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch_wikipedia as W

LONG = " ".join(["word"] * 110)
OLD = "2010-04-01T00:00:00Z"


def user(**kw):
    base = {"name": "Hawkeye7", "registration": OLD, "editcount": 133956, "groups": ["autoconfirmed"]}
    return base | kw


def test_tenure_needs_a_pre_chatgpt_account():
    assert W.tenure_ok(user())
    assert not W.tenure_ok(user(registration="2023-04-01T00:00:00Z"))
    assert not W.tenure_ok(user(registration="2022-12-01T00:00:00Z"))


def test_tenure_needs_a_long_edit_history():
    assert not W.tenure_ok(user(editcount=19999))
    assert W.tenure_ok(user(editcount=20000))


def test_a_bot_is_not_a_person():
    assert not W.tenure_ok(user(groups=["bot", "autoconfirmed"]))


def test_a_blocked_editor_is_not_trusted():
    assert not W.tenure_ok(user(blockid=12345))


def test_an_account_with_no_registration_date_is_not_trusted():
    # the API omits registration for some very old accounts; absent must not read as old
    assert not W.tenure_ok(user(registration=None))
    assert not W.tenure_ok({"name": "X", "editcount": 50000, "groups": []})


def test_janitorial_summaries_are_rejected():
    for summary in ["Reverted good faith edits", "undo", "ce", "copyedit", "fix typo",
                    "merge from Foo", "HotCat: added", "clean up using AWB", "rm unsourced"]:
        assert W.janitorial(summary), summary


def test_a_summary_that_names_a_model_is_rejected():
    assert W.janitorial("expanded history section with ChatGPT help")
    assert W.janitorial("rewrite, drafted with Claude")


def test_a_creation_is_not_judged_on_tidying_words():
    # the tidying patterns are about whose prose it is. A new article has no earlier prose to
    # revert, merge or recategorise, so they say nothing - and they were rejecting 166 real
    # creations for saying "created page with infobox and categories".
    for summary in ["Reverted good faith edits", "Created page with infobox and categories",
                    "new article, refs and categories added", "ce"]:
        assert not W.janitorial(summary, created=True), summary
        assert W.janitorial(summary), summary


def test_a_creation_naming_a_model_is_still_rejected():
    assert W.janitorial("new article, drafted with ChatGPT", created=True)


def test_an_expansion_summary_is_kept():
    for summary in ["expand early life", "add 1924 appointment and sources", "", "\u2192Career: added detail"]:
        assert not W.janitorial(summary), summary


DIFF = """<table class="diff">
<tr><td colspan="2" class="diff-empty"></td>
<td class="diff-marker" data-marker="+"></td>
<td class="diff-addedline"><div>A graduate of Cambridge, Appleton was commissioned in 1915.</div></td></tr>
<tr><td class="diff-marker" data-marker="-"></td>
<td class="diff-deletedline"><div>He went to <del class="diffchange">Cambridge</del>.</div></td>
<td class="diff-marker" data-marker="+"></td>
<td class="diff-addedline"><div>He went to <ins class="diffchange">Oxford</ins> in 1912 and stayed.</div></td></tr>
<tr><td class="diff-marker" data-marker="-"></td>
<td class="diff-deletedline"><div>The depot held the reserve stock.</div></td>
<td colspan="2" class="diff-empty"></td></tr>
<tr><td colspan="2" class="diff-empty"></td>
<td class="diff-marker" data-marker="+"></td>
<td class="diff-addedline"><div>The depot held the reserve stock.</div></td></tr>
<tr><td colspan="2" class="diff-empty"></td>
<td class="diff-marker" data-marker="+"></td>
<td class="diff-addedline"><div>* [[File:x.jpg|thumb]]</div></td></tr>
<tr><td colspan="2" class="diff-empty"></td>
<td class="diff-marker" data-marker="+"></td>
<td class="diff-addedline"><div><ins class="diffchange">A wholly new line wrapped in ins.</ins></div></td></tr>
<tr><td class="diff-marker" data-marker="-"></td>
<td class="diff-deletedline"><div>The old sentence stood alone.</div></td>
<td class="diff-marker" data-marker="+"></td>
<td class="diff-addedline"><div>A replacement sentence with no ins markers.</div></td></tr>
</table>"""


def test_only_a_wholly_new_line_is_taken():
    lines = W.added_lines(DIFF)
    assert "A graduate of Cambridge, Appleton was commissioned in 1915." in lines, lines
    assert not any("He went to" in line for line in lines), lines
    assert not any("He went to Cambridge" in line for line in lines), lines


def test_a_partly_edited_line_is_not_the_editors_prose():
    # the cell holds the WHOLE new line with only the changed words in <ins>, so keeping it
    # harvests paragraphs the editor never wrote - and the row would carry their name and date
    assert not any("stayed" in line for line in W.added_lines(DIFF)), W.added_lines(DIFF)


def test_a_new_line_wrapped_in_ins_is_not_taken():
    # isolates the ins guard: this row has an empty cell opposite, so only that check stops it,
    # and MediaWiki does wrap a whole new line in ins when it sits next to a change
    assert not any("wrapped in ins" in line for line in W.added_lines(DIFF)), W.added_lines(DIFF)


def test_a_wholly_replaced_line_is_not_taken():
    # isolates the empty-cell guard: no ins markers here, so only that check stops it. The new
    # text probably IS the editor's, but taking it means trusting a diff shape to say so, and
    # erring the other way costs yield rather than the provenance claim.
    assert not any("replacement sentence" in line for line in W.added_lines(DIFF)), W.added_lines(DIFF)


def test_a_moved_paragraph_is_not_taken():
    # a move shows up as a whole deletion in one place and a whole addition in another
    assert not any("reserve stock" in line for line in W.added_lines(DIFF)), W.added_lines(DIFF)


def test_added_lines_still_reach_the_prose_filter():
    assert any(line.startswith("* [[File") for line in W.added_lines(DIFF)), W.added_lines(DIFF)


def test_a_raw_line_is_screened_before_paying_for_a_render():
    # the API budget for an anonymous client is a few hundred calls an hour, and rendering is a
    # call per candidate. Anything decidable from the wikitext is decided before spending one.
    long_raw = " ".join(["word"] * 120)
    assert W.raw_ok(long_raw)
    # a non-citation template will not survive the reject chain, so do not render it
    assert not W.raw_ok(long_raw + " {{convert|5|km}}")
    # citation templates render to markers that get stripped, so they are fine
    assert W.raw_ok(long_raw + " {{sfn|Kress|2002|p=27}}")
    assert W.raw_ok(long_raw + " {{cite book |title=A}}")
    # script and quote dumps are visible in the raw text too
    assert not W.raw_ok(long_raw + " \u041c\u043e\u0441\u043a\u0432\u0430")
    assert not W.raw_ok('"' + " ".join(["praise"] * 80) + '" ' + " ".join(["word"] * 40))
    # too short to ever reach MIN_WORDS once rendered
    assert not W.raw_ok(" ".join(["word"] * 60))


SHORT_DIFF = """<table class="diff">
<tr><td colspan="2" class="diff-empty"></td>
<td class="diff-marker" data-marker="+"></td>
<td class="diff-addedline"><div>A short sentence that never reaches the word floor.</div></td></tr>
</table>"""

LONG_DIFF = SHORT_DIFF.replace("A short sentence that never reaches the word floor.",
                               " ".join(["word"] * 120))


def stub(body, calls):
    def fake(params, post=False):
        calls.append(params["action"])
        return {"compare": {"compare": {"body": body}},
                "parse": {"parse": {"text": "<p>" + " ".join(["word"] * 120) + "</p>"}}}.get(params["action"], {})
    return fake


def render_calls(body):
    # the raw screen exists to save API calls, so the only way to test it is to count them
    calls, real = [], W.call
    W.call = stub(body, calls)
    try:
        W.paragraph({"revid": 1, "title": "Title"}, {})
    finally:
        W.call = real
    return calls


def test_a_screened_out_line_is_never_rendered():
    assert render_calls(SHORT_DIFF) == ["compare"], render_calls(SHORT_DIFF)


def test_a_line_that_passes_the_screen_is_rendered():
    assert render_calls(LONG_DIFF) == ["compare", "parse"], render_calls(LONG_DIFF)


def test_a_list_or_template_line_is_not_prose():
    for line in ["* a bullet", "| cell", "! header", "= Heading =", "{{Infobox person", ":indented",
                 "[[File:x.jpg|thumb]]", "#REDIRECT [[Foo]]", "", "   "]:
        assert not W.prose_line(line), line
    assert W.prose_line("A graduate of the University of Cambridge, Appleton was commissioned in 1915.")


PARSE = """<div class="mw-parser-output"><p>Logistical planning requires forecasting of future
consumption.<sup id="cite_ref-FOOTNOTEKress200227_1-0" class="reference"><a href="#cite_note-1">
<span class="cite-bracket">&#91;</span>1<span class="cite-bracket">&#93;</span></a></sup> The depot
held 3&#160;000 rounds.</p></div>"""


def test_reference_superscripts_leave_no_brackets():
    text = W.to_text(PARSE)
    assert "[" not in text and "]" not in text, text
    assert "1 The depot" not in text, text
    assert text.startswith("Logistical planning requires forecasting of future consumption."), text


def test_entities_and_odd_spaces_become_plain_text():
    text = W.to_text(PARSE)
    assert "&#" not in text and "&nbsp;" not in text, text
    assert "3 000 rounds" in text, text
    assert "\u00a0" not in text and "\u2009" not in text and "\u202f" not in text, text


def test_zero_width_characters_are_removed():
    # an invisible character is a one-sided giveaway, and \\s does not match these
    text = W.to_text("<p>Ger\u200bmany\u00ad Poland\ufeff relations held.</p>")
    assert text == "Germany Poland relations held.", repr(text)


def test_a_stripped_tag_leaves_no_gap_before_punctuation():
    # "[[Foo]]." renders as <a>Foo</a>. and a tag replaced by a space gives "Foo ." - a pattern
    # carried by 1.75% of human prose rows in the set and 0.00% of AI rows. One-sided format.
    assert W.to_text('<p>He fought in the <a href="/wiki/G">Guadalcanal campaign</a>.</p>') \
        == "He fought in the Guadalcanal campaign.", W.to_text('<p><a href="/x">G</a>.</p>')
    assert W.to_text('<p>The area is 30&#160;km<sup>2</sup>.</p>') == "The area is 30 km."
    assert W.to_text('<p>It went to trial<sup id="x" class="reference">[1]</sup>, and failed.</p>') \
        == "It went to trial, and failed."


def test_a_possessive_after_a_tag_is_not_split_off():
    assert W.to_text('<p>At <a href="/wiki/WC">Winston Churchill</a>&#39;s request he left.</p>') \
        == "At Winston Churchill's request he left.", W.to_text('<p><a href="/x">C</a>&#39;s r</p>')


def test_an_inline_tag_inside_a_word_does_not_split_it():
    # isolates the structural fix: no gap-closing regex can put "Guadalcanal" back together,
    # so this is the test that fails if inline tags go back to being replaced by a space
    assert W.to_text("<p>Guadal<i>canal</i> campaign ended.</p>") == "Guadalcanal campaign ended."
    assert W.to_text('<p>the <a href="/x">USS</a><i>Ranger</i> sailed.</p>') == "the USSRanger sailed."


def test_a_gap_already_in_the_source_is_closed():
    # isolates the safety net: the gap is in the text, not left by a tag, so the structural
    # fix cannot reach it. Editors do leave these, and so do some templates.
    assert W.to_text("<p>He left , and returned .</p>") == "He left, and returned."


def test_a_clitic_already_split_in_the_source_is_rejoined():
    assert W.to_text("<p>Churchill 's speech ended the debate.</p>") == "Churchill's speech ended the debate."


def test_paragraphs_do_not_weld_together():
    # closing the gap must not go so far that sentences run into each other
    assert W.to_text("<p>One.</p><p>Two.</p>") == "One. Two."
    assert W.to_text("<p>One.</p><table><tr><td>x</td></tr></table><p>Two.</p>") == "One. Two."


def test_a_surviving_space_before_punctuation_is_rejected():
    # last line of defence: if some tag shape gets past the cleaning, the row does not ship
    assert W.reject("The battle ended in defeat , and the army withdrew. " + LONG) == "spacing"


def test_tables_headings_and_blockquotes_are_dropped_whole():
    html = ('<p>Real prose here.</p><h2>Career</h2><table><tr><td>1998</td></tr></table>'
            '<ul><li>a list item</li></ul><blockquote>a quoted block</blockquote>'
            '<span class="mw-editsection">[edit]</span>')
    text = W.to_text(html)
    assert text == "Real prose here.", text


def test_the_row_is_one_line_with_no_double_spaces():
    # blank-line paragraphs broke an earlier fit, so a row must not carry newlines
    text = W.to_text("<p>One.</p>\n\n<p>Two.   Three.</p>")
    assert "\n" not in text and "  " not in text, repr(text)


def test_surviving_markup_is_rejected():
    assert W.reject(LONG + " <span class='x'>") == "markup"
    assert W.reject(LONG + " &amp;lt;") == "markup"


def test_truncated_wikitext_is_rejected():
    # a diff cell cut mid-template leaves the braces behind
    assert W.reject(LONG + " {{sfn|Kress") == "wikitext"
    assert W.reject(LONG + " [[Fenny Stratford") == "wikitext"
    assert W.reject(LONG + " '''bold'''") == "wikitext"


def test_non_latin_script_is_rejected_not_stripped():
    # the AI side is English only, so a native-name gloss would teach script instead of voice
    assert W.reject(LONG + " (Yiddish: \u05d3\u05d0\u05b8\u05e1)") == "script"
    assert W.reject(LONG + " \u041c\u043e\u0441\u043a\u0432\u0430") == "script"


def test_latin_diacritics_are_kept():
    # Claude writes these too, so they are two-sided and must not be a reject
    assert W.reject("M\u00fcllerian \u014cita na\u00efve " + LONG) is None


def test_an_en_dash_becomes_a_hyphen():
    # 9.4% of these rows carry one against 1.2% of the AI rows, because the style guide asks for
    # it in ranges and name pairs. That is a house format, so map it and leave the words alone.
    assert W.to_text("<p>The score was 2\u20131 in the Germany\u2013Poland match.</p>") \
        == "The score was 2-1 in the Germany-Poland match."
    # the em dash is a voice feature, not a style rule, and the AI side uses more of them
    assert W.to_text("<p>He left \u2014 and never returned.</p>") == "He left \u2014 and never returned."


def test_a_quote_heavy_row_is_rejected():
    quoted = '"' + " ".join(["praise"] * 70) + '" ' + " ".join(["word"] * 60)
    assert W.reject(quoted) == "quoted"


def test_prose_between_two_quotations_is_not_counted_as_quoted():
    # pairing any quote mark with any other made this a screen against quoting TWICE, which cut
    # reported speech and attribution out of the human class only - 31% of the AI prose rows in
    # the set carry two or more quote marks and nothing filters those
    attributed = ('The tribunal called the plan "wholly inadequate" in its final report, and the '
                  'minister replied that the finding was "a matter for the inquiry to weigh". '
                  + " ".join(["word"] * 90))
    assert W.quoted_share(attributed) < 0.2, W.quoted_share(attributed)
    assert W.reject(attributed) is None


def test_quoted_share_counts_the_words_inside_the_marks():
    assert W.quoted_share('He said "one two three four" and left.') == 4 / 8
    assert W.quoted_share("No quotes at all here.") == 0.0


def test_a_life_dates_lead_is_rejected():
    # Life dates right after the subject's name only ever open an encyclopedia article. This is
    # the one lead marker that is unambiguous, so it is the only one left.
    for lead, title in [
            ("Milton W. Brown (1911 - February 6, 1998), American artist and art historian.", "Milton W. Brown"),
            ("Jane Doe (born 1974) is a chemist of some note.", "Jane Doe"),
            # the title is the common name, the lead uses the full legal name plus an honorific
            ("Sir Winston Leonard Spencer Churchill (1874-1965) was a British statesman.", "Winston Churchill")]:
        assert W.reject(lead + " " + LONG, title) == "lead", lead


def test_a_date_in_ordinary_prose_is_not_a_lead():
    for start, title in [
            ("He joined the Royal Engineers (1915) and served on the Western Front.", "Edward Victor Appleton"),
            ("The treaty (1919) settled the border for a generation.", "Treaty of Versailles"),
            # a real date range, but the words before it do not name the article's subject
            ("The conflict (1914-1918) ended with an armistice in November.", "Western Front")]:
        assert W.reject(start + " " + LONG, title) is None, start


def test_life_dates_later_in_the_row_are_not_a_lead():
    # the formula is the opening of the first sentence. A date range deeper into the paragraph is
    # prose about someone, and searching the whole row for it would throw those rows away.
    body = ("The committee met twice that winter and agreed the terms without a vote, which left "
            "the question of funding open until the spring. Churchill (1874-1965) chaired it. ")
    assert W.reject(body + LONG, "Winston Churchill") is None, W.reject(body + LONG, "Winston Churchill")


def test_a_subject_initial_definition_is_kept():
    # This is the construction the earlier filters kept reaching for, and it is the wrong target:
    # 7.7% of the human prose rows in the set already open this way and 5.5% of the AI rows do,
    # so it does not separate the classes. Cutting it from one source would make it an AI cue.
    for start, title in [
            ("Lost Eidolons is a 2022 tactical role-playing game developed by Ocean Drive.", "Lost Eidolons"),
            ("Appleton was a keen golfer and a member of two clubs.", "Edward Victor Appleton"),
            ("Inga alley cropping is the planting of crops between rows of trees.", "Inga alley cropping"),
            ("Mercury is the smallest planet in the Solar System.", "Mercury (planet)")]:
        assert W.reject(start + " " + LONG, title) is None, start


def test_an_ordinary_copular_sentence_is_kept():
    for start, title in [
            ("The battle was a decisive victory for the Habsburgs, and the siege lifted.", "Siege of Vienna"),
            ("In 1924 he was the first to measure the height of the ionosphere.", "Edward Victor Appleton"),
            ("By then the company was a subsidiary of Diageo and no longer traded.", "Chalone Wine Group"),
            ("War was declared in April and the blockade was a failure.", "War of the Pacific"),
            ("This is the only surviving copy of the charter.", "Magna Carta")]:
        assert W.reject(start + " " + LONG, title) is None, start


def test_an_ordinary_mid_article_sentence_is_kept():
    for start in ["After the ferry sank off the coast, the inquest opened.",
                  "In August of that year, the panel ruled 2-1 to uphold the conviction.",
                  "A graduate of the University of Cambridge, Appleton was commissioned in 1915."]:
        assert W.reject(start + " " + LONG, "Edward Victor Appleton") is None, start


def test_a_statistics_dump_is_rejected_on_digit_density():
    assert W.reject(" ".join(f"1998 {i} 4567 89" for i in range(40))) == "digits"


def test_ordinary_date_density_is_kept():
    # encyclopedic prose is genuinely date-dense; the cap must clear real years
    dated = "He became professor in 1924 and a fellow in 1927, returning in 1936 and dying in 1965. " + LONG
    assert W.reject(dated) is None, dated


def test_length_floor_matches_the_verdict_floor():
    assert W.reject(" ".join(["word"] * 80)) == "length", "detect.py gives no verdict at 80 words"
    assert W.reject(" ".join(["word"] * 400)) == "length"
    assert W.reject(" ".join(["word"] * 100)) is None


def test_a_disclosed_model_is_rejected():
    assert W.reject(LONG + " This section was generated with ChatGPT.") == "disclosed"


def test_rows_carry_what_the_builder_and_the_split_need():
    made = W.row(user(), "Edward Victor Appleton", 1352724559, "2026-05-05T11:00:00Z", LONG)
    assert made["label"] == 0 and made["model"] == "human", made
    assert made["source"] == "wikipedia" and made["domain"] == "encyclopedia", made
    assert made["group"] == "wp:hawkeye7", made
    assert made["date"] == "2026-05-05", made
    assert made["author"] == "Hawkeye7" and made["title"] == "Edward Victor Appleton", made
    assert made["revid"] == 1352724559, made
    assert made["editor_since"] == OLD and made["editor_edits"] == 133956, made


def test_one_group_per_editor():
    # an editor must not straddle the train/test split, the way one repo does for docs
    a = W.row(user(name="Hawkeye7"), "A", 1, "2026-01-01T00:00:00Z", LONG)
    b = W.row(user(name="hawkeye7"), "B", 2, "2025-01-01T00:00:00Z", LONG)
    assert a["group"] == b["group"], (a["group"], b["group"])


def test_calls_are_paced_apart():
    # back-to-back calls are what earned the 429 that stalled a whole run, so the interval is
    # the politeness contract and its value is part of the behaviour, not a tuning knob
    assert W.MIN_INTERVAL >= 0.5, W.MIN_INTERVAL
    old, W.MIN_INTERVAL = W.MIN_INTERVAL, 0.05
    try:
        W.pace()
        start = time.monotonic()
        W.pace()
        assert time.monotonic() - start >= 0.05, "second call was not paced"
    finally:
        W.MIN_INTERVAL = old


def test_windows_spread_across_the_whole_range():
    # one walk back from today lands the whole sample in one month
    spread = W.windows("2026-01-01T00:00:00Z", "2022-01-01T00:00:00Z", 4)
    assert len(spread) == 4, spread
    assert spread[0][0] == "2026-01-01T00:00:00Z", spread
    assert spread[-1][1] == "2022-01-01T00:00:00Z", spread
    assert all(end < start for start, end in spread), spread
    starts = [s for s, _ in spread]
    assert starts == sorted(starts, reverse=True), starts


def test_each_editor_starts_at_a_different_window():
    # otherwise every editor is sampled from the same month and the dates bunch up
    assert W.offset(0, 4) != W.offset(1, 4)
    assert all(0 <= W.offset(i, 4) < 4 for i in range(20))


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

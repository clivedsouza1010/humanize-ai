# Tests for provenance.py. Plain asserts, no test dependency.
# The fixtures are the templates these projects really use, copied from pull requests in Cantera,
# trickster, wagtail, Cataclysm-BN, open-logic, hister, eslint, verus, maplibre, cargo-msrv, agones,
# tree-sitter, OWASP threat-dragon, OWASP CheatSheetSeries and earthaccess.
# Usage: python3 provenance_test.py
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import provenance as P

CLAUDE = "docs: fix the install page\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
PERSON = "docs: fix the install page\n\nCo-authored-by: Dana Reed <dana@example.com>"
TRICKSTER_NO = ("## Description\r\n\r\nUpdate a link.\r\n\r\n## AI Disclosure\r\n\r\n"
                "- - [x] This contribution DOES NOT include AI-generated changes\r\n"
                "- - [ ] This contribution DOES include AI-generated changes, and I have reviewed the relevant contributing guidelines.\r\n"
                "\r\nCloses #1130 ")
TRICKSTER_YES = ("## AI Disclosure\r\n\r\n"
                 "- - [ ] This contribution DOES NOT include AI-generated changes\r\n"
                 "- - [x] This contribution DOES include AI-generated changes, and I have reviewed the relevant contributing guidelines.\r\n")
CANTERA_NO = ("**AI Statement (required)**\r\n\r\n"
              "- **No generative AI was used.** This contribution was written entirely without AI assistance.\r\n\r\n"
              "**Checklist**\r\n\r\n- [x] AI Statement is included\r\n")
CANTERA_YES = ("**AI Statement (required)**\r\n\r\n"
               "- **Extensive use of generative AI.** Significant portions of code or documentation were generated\r\n"
               "with AI, including logic and implementation decisions.\r\n\r\n- [x] AI Statement is included\r\n")
CANTERA_BLANK = ("**AI Statement (required)**\r\n\r\n"
                 "- **No generative AI was used.** This contribution was written entirely without AI assistance.\r\n"
                 "- **Limited use of generative AI.** Standard or boilerplate code snippets were generated with AI.\r\n"
                 "- **Extensive use of generative AI.** Significant portions of code or documentation were generated with AI.\r\n\r\n"
                 "- [ ] AI Statement is included\r\n")
WAGTAIL = "### Description\r\n\r\nFixes the breadcrumbs.\r\n\r\n### AI usage\r\n\r\n\r\n{}"
WAGTAIL_BLANK = ("### AI usage\r\n\r\n<!-- Please give details of any AI assistance that has been used for this PR - "
                 'including for writing this description - or "None" if no AI has been used. -->\r\n')


def verdict(body="", commits=(), author=None):
    return P.read(body, commits, author)[0]


def test_a_trailer_naming_a_tool_is_ai():
    assert verdict(commits=[CLAUDE]) == "ai"


def test_a_trailer_naming_a_person_is_not_ai():
    assert verdict(commits=[PERSON]) == "unknown"


def test_the_assisted_by_trailer_two_projects_require_is_ai():
    assert verdict(commits=["fix a typo\n\nAssisted-by: Claude:claude-opus-5-5"]) == "ai"


def test_the_genai_trailer_open_logic_uses_is_ai():
    assert verdict(commits=["DOC: add a page\n\nGenAI: Claude Code claude-opus-5-5-20261107"]) == "ai"


def test_a_trailer_is_ai_on_its_address_when_it_names_no_product():
    assert verdict(commits=["tweak\n\nCo-Authored-By: Vibe <vibe@mistral.ai>"]) == "ai"


def test_the_badge_a_tool_writes_without_a_trailer_is_ai():
    assert verdict(commits=["add a guide\n\n\U0001f916 Generated with [Claude Code](https://claude.com/claude-code)"]) == "ai"


def test_a_tools_own_account_opening_the_pull_request_is_ai():
    assert verdict(author="devin-ai-integration[bot]") == "ai"


def test_a_bot_that_writes_no_prose_is_not_ai():
    assert verdict(author="dependabot[bot]") == "unknown"
    assert verdict(author="renovate[bot]") == "unknown"


def test_a_checked_box_that_denies_ai_is_human():
    assert verdict(TRICKSTER_NO) == "human"


def test_a_checked_box_that_admits_ai_is_ai():
    assert verdict(TRICKSTER_YES) == "ai"


def test_an_unchecked_box_declares_nothing():
    assert verdict("## AI Disclosure\r\n\r\n- [ ] This contribution DOES include AI-generated changes\r\n") == "unknown"


def test_the_statement_a_contributor_kept_is_the_one_that_counts():
    assert verdict(CANTERA_NO) == "human"
    assert verdict(CANTERA_YES) == "ai"


def test_a_template_with_every_option_still_in_it_declares_nothing():
    assert verdict(CANTERA_BLANK) == "unknown"


def test_a_box_saying_a_statement_exists_is_not_the_statement():
    assert verdict("- [x] AI Statement is included\r\n") == "unknown"


def test_a_section_answered_none_is_human():
    assert verdict(WAGTAIL.format("None")) == "human"


def test_a_none_answer_survives_a_footnote_landing_under_it():
    assert verdict(WAGTAIL.format("None\r\n\r\n[^1]: https://github.blog/some-post")) == "human"


def test_a_section_left_unanswered_declares_nothing():
    assert verdict(WAGTAIL_BLANK) == "unknown"


def test_an_answer_the_phrases_cannot_read_still_counts_as_a_declaration():
    # "for advice on" matches nothing, but naming a tool in that section is the declaration
    assert verdict(WAGTAIL.format("Claude Code for advice on how to make nested backticks work properly")) == "ai"


def test_an_answer_counts_on_a_generic_word_when_the_tool_is_unknown_here():
    assert verdict(WAGTAIL.format("Draft original, revised by AI for clarity, and final edits by human.")) == "ai"


def test_text_the_last_section_swallowed_is_not_an_answer():
    # the AI section is last in most templates, so "Closes #1130" lands inside it
    assert P.votes(TRICKSTER_NO) == (0, 1)
    assert verdict("### AI usage\r\n\r\nCloses #1130\r\n") == "unknown"


def test_a_checkbox_section_is_left_to_the_boxes():
    # reading it as prose as well turns "AI tools used: none" into an answer and loses the no
    assert verdict("## AI Disclosure\r\n\r\n- [x] AI tools used: none\r\n") == "human"


def test_a_trailer_beats_a_description_that_denies_ai():
    assert verdict(CANTERA_NO, commits=[CLAUDE]) == "ai"


def test_a_description_that_declares_both_ways_declares_nothing():
    assert verdict(TRICKSTER_YES + CANTERA_NO) == "unknown"


def test_the_instructions_in_an_html_comment_never_vote():
    assert P.votes(P.COMMENT.sub("", WAGTAIL_BLANK)) == (0, 0)


def test_free_text_outside_any_section_is_read():
    assert verdict("**Disclosure on GenAI Usage:** This PR was prepared with assistance from Claude Code (Anthropic).") == "ai"
    assert verdict("Draft for review. Implementation was assisted in Cursor.") == "ai"
    assert verdict("I used OpenCode and DeepSeek v4.1 flash for the implementation.") == "ai"


def test_a_pull_request_that_says_nothing_declares_nothing():
    assert verdict("Fixes a typo in the README.", ["docs: fix a typo"]) == "unknown"


def test_a_commit_that_only_mentions_the_policy_is_not_a_declaration():
    assert verdict("", ["DOC: Add GenAI Policy", "CLEANUP: Improve AI instructions file"]) == "unknown"


def test_a_negation_inside_markdown_emphasis_still_denies():
    # eslint's template writes it this way, and "_" counts as a word character
    assert verdict("#### AI acknowledgment\r\n\r\n- [x] I did _not_ use AI to generate this PR\r\n") == "human"


def test_a_negation_in_a_pasted_prompt_does_not_flip_the_claim():
    box = ("- [x] I have used AI tools to generate the contents of this PR. The LLM used is `Claude Opus 5.5` "
           "and the prompt used is `find the links whose fragment doesn't match a heading`.\r\n")
    assert verdict(box) == "ai"


def test_a_box_that_offers_both_answers_at_once_declares_nothing():
    assert verdict("- [x] I have disclosed AI tool usage below, or confirmed that no AI tools were used\r\n") == "unknown"


def test_a_version_number_does_not_break_the_sentence():
    assert verdict("I have used Claude Opus 5.5 to help uncover reasons for the issues listed above.") == "ai"
    # the model's version number is the only full stop between "used" and the verb
    assert verdict("Sections 2 and 3 used Claude Opus 5.5 to draft the examples.") == "ai"


def test_the_channel_says_how_far_the_verdict_can_be_trusted():
    assert P.read("", [CLAUDE])[2] == "trailer"
    assert P.read(WAGTAIL.format("None"), [])[2] == "description"
    assert P.read("nothing here", ["a plain commit"])[2] is None


def test_a_trailer_in_the_description_counts_like_one_in_a_commit():
    # verus asks for it in the pull request, not the commit
    assert P.read("Assisted-by: claude:opus-5.5", []) == ("ai", "Assisted-by: claude:opus-5.5", "trailer")
    assert P.read("Assisted-by: GPT-5.6 Sol for testcases", [])[0] == "ai"


def test_a_trailer_in_backticks_is_still_a_trailer():
    assert P.read("Fixes #3211\r\n\r\n`Assisted-by: kiro:Fable5.1`\r\n", []) == ("ai", "Assisted-by: kiro:Fable5.1", "trailer")


def test_a_box_conditional_on_ai_having_been_used_answers_nothing():
    assert verdict("- [x] If AI tools were used: I have disclosed the tool and extent of usage below.") == "unknown"


def test_agreeing_to_the_policy_is_not_a_declaration():
    assert verdict("- [x] Confirm you have read our AI policy [here](https://example.com/AI_POLICY.md).") == "unknown"
    assert verdict("- [x] I have read and agree to be bound by the [AI / LLM policy](https://example.com/p).") == "unknown"
    assert verdict("- [x] any [use of AI](../contributing.md#use-of-ai) has been declared in this pull request") == "unknown"


def test_the_same_project_s_real_either_or_box_still_counts():
    assert verdict("- [x] *either* no AI-generated content has been used in this pull request") == "human"


def test_a_one_letter_answer_to_an_ai_question_is_an_answer():
    assert verdict("**Did you use AI tools in preparing this PR?**:\r\n\r\nY") == "ai"
    assert verdict("**Did you use AI tools in preparing this PR?**:\r\n\r\nN") == "human"


def test_a_tool_named_as_the_one_who_did_the_work_counts():
    assert verdict("Claude found this issue and made the fix while working on a different issue.") == "ai"
    assert verdict("I wrote this PR with a lot of the grunt work done by GPT-6.1 Sol") == "ai"
    assert verdict("Per the policy, I authored this using OpenAI Codex and reviewed it myself.") == "ai"


def test_a_tool_merely_named_is_not_a_declaration():
    assert verdict("This adds support for the Claude API to the client.") == "unknown"
    assert verdict("Uses the Gemini SDK to generate embeddings for each page.") == "unknown"


def test_the_reason_says_which_evidence_decided_it():
    assert "anthropic" in P.read("", [CLAUDE])[1].lower()
    assert P.read(WAGTAIL.format("None"), [])[1] == "the description says no AI was used"


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

# Grade humanizer eval runs: score each final.txt with every detector and write grading.json next to it.
# Needs the scorer running (detect.py --serve). Usage: python grade_evals.py WORKSPACE/iteration-N
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(REPO, "plugin", "skills", "humanize-ai", "scripts"))
import detect  # noqa: E402

HIDDEN = re.compile("[​-‏⁠﻿­]")
NON_LATIN_LETTER = re.compile("[Ͱ-ϿЀ-ӿ]")
# padding is the easy way past the docs detector, and blind judges marked padded docs down hard
DOCS_LENGTH = (0.85, 1.15)
PROSE_LENGTH = (0.7, 1.3)
# SKILL.md step 6's guardrail on the runaway tail. Nothing here read it until 2026-11-14
MAX_VOICE_DRIFT = 0.22


def case_genre(case, draft):
    # the genre the loop runs with: the case's own tag when it has one, else what detect.py reads off the draft
    prompt = os.path.join(REPO, "evals", case, "prompt.md")
    tags = []
    if os.path.exists(prompt):
        match = re.search(r"(?m)^tags:\s*\[([^\]]*)\]", open(prompt).read())
        tags = [t.strip() for t in match.group(1).split(",")] if match else []
    return "docs" if "docs" in tags else detect.pick_genre(draft, "auto")


def length_bounds(genre):
    # `both` is scored by the docs blend as well, so padding buys it the same unearned pass
    return DOCS_LENGTH if genre in ("docs", "both") else PROSE_LENGTH


def score(text, genre):
    # the loop scores every round with one genre (SKILL.md step 1); grading used to let detect guess it
    # again, so the verdict and the length bound could be judged as different genres in the same run
    result = detect.ask_server(text, True, genre)
    if result is None:
        sys.exit("start the scorer first: detect.py --serve")
    return result


def odd_words(draft, final):
    known = {w.lower() for w in detect.WORD.findall(draft)}
    odd = []
    for word in detect.WORD.findall(final.translate(detect.QUOTES)):
        if word[0].isupper() or word.lower() in known or detect.common_word(word):
            continue
        odd.append(word)
    return odd


def main():
    iteration = sys.argv[1]
    rows = []
    # runs live at CASE/CONFIG/outputs or, when repeated, CASE/CONFIG/run-N/outputs
    for final_path in sorted(glob.glob(os.path.join(iteration, "**", "outputs", "final.txt"), recursive=True)):
        run_dir = os.path.dirname(os.path.dirname(final_path))
        case, *config = os.path.relpath(run_dir, iteration).split(os.sep)
        draft = open(os.path.join(REPO, "evals", case, "files", "draft.txt")).read()
        final = open(final_path).read()
        genre = case_genre(case, draft)
        before, after = score(draft, genre), score(final, genre)
        facts = detect.compare(draft, final)
        odd = odd_words(draft, final)
        tricks = HIDDEN.findall(final) + NON_LATIN_LETTER.findall(final)
        low, high = length_bounds(genre)
        # The second opinion reads prose. references/metrics.md puts it below chance on docs (AUROC 0.345: 16% of
        # known-human docs flagged against 9% of AI docs caught), and a document takes the highest of its
        # sections, so on docs this check fails the long human rewrites and passes the AI ones. `both` keeps
        # it: the inversion was measured on the docs corpus, and a `both` case is prose with headings.
        second = [] if genre == "docs" else [
            ("final.txt scores under 0.5 on the held-out fakespot RoBERTa detector", after.get("heldout_roberta", 1.0) < 0.5,
             f"RoBERTa {after.get('heldout_roberta', 'not reported')} (draft {before.get('heldout_roberta', 'not reported')})")]
        # SKILL.md's first pass condition is one requirement in three parts: the document verdict, every
        # deciding section human when the text split into sections, and -- outside docs -- no section
        # reading `ai` at all, because a short AI-looking section is real signal in prose. Only the first
        # part was checked here. A text short enough to score in one piece has neither field, and then the
        # verdict is the whole of it.
        stray = [s for s in after.get("sections", []) if s.get("verdict") == "ai"]
        # A docs text with under 120 words of prose once code and markup are removed comes back with a warning
        # and no verdict. Base reached that for a short docs final with code and raised on it; forcing the case's
        # genre adds one more way in, a docs case whose final dropped every code block. Either way it fails here
        # with the warning rather than raising.
        reads_human = (after.get("verdict") == "human" and after.get("all_sections_human", True)
                       and (genre == "docs" or not stray))
        if "verdict" not in after:
            sections_note = f", no verdict: {after.get('warning', 'the scorer returned none')}"
        elif "all_sections_human" in after:
            sections_note = f", all_sections_human {after['all_sections_human']}"
        else:
            sections_note = ", scored in one piece"
        if stray:
            sections_note += f", sections reading ai: {[s['section'] for s in stray]}"
        # two rules, so two wordings, the way the two grader 01 variants have them
        verdict_text = ("final.txt gets verdict \"human\" from the blend, and every section it is read from reads human"
                        if genre == "docs" else
                        "final.txt gets verdict \"human\" from the blend, every section it is read from reads human, "
                        "and no section reads ai")
        checks = [
            (verdict_text,
             reads_human,
             f"{after['genre']} blend {after.get('ai_probability', 'none')} (draft {before.get('ai_probability', 'none')}), bar "
             + ", ".join(f"{g} {b['threshold_human']:.3f}" for g, b in detect.load_blends(after["genre"]).items())
             + sections_note),
            *second,
            # Stricter than the loop on purpose. SKILL.md step 6 reads these lists with judgement, because compare()
            # lists ordinary words ("DM" for "message me", a reworded heading); grading fails on any entry, so it
            # stays repeatable. bench/REPORT.md, "One difference is deliberate".
            ("no facts from draft.txt missing in final.txt", not facts["missing"], f"missing: {facts['missing']}"),
            ("no new numbers, names or quotes in final.txt", not facts["added"], f"added: {facts['added']}"),
            (f"final.txt's prose is {low}x-{high}x the prose word count of draft.txt", low <= facts["length_ratio"] <= high,
             f"length ratio {facts['length_ratio']}"),
            ("no hidden characters, look-alike letters or deliberate misspellings", not tricks and len(odd) <= max(1, len(final.split()) // 100),
             f"hidden/look-alike: {len(tricks)}, words not in the dictionary: {odd[:8]}"),
            # a missing measurement is not a pass: compare drops voice_drift if blend.json carries no docs
            # ngram table, and a rollback can do that
            (f"final.txt stays inside {MAX_VOICE_DRIFT} voice_drift of draft.txt", facts.get("voice_drift", 1.0) < MAX_VOICE_DRIFT,
             f"voice_drift {facts.get('voice_drift', 'not reported: blend.json has no docs ngram table')}"),
        ]
        # Code blocks are checked in every genre. facts() leaves anything inside a block to this check, so it is
        # the only fact check a block gets: a number invented inside an added fence never reaches `added`, and
        # prepare() strips it before length_ratio. A prose draft cannot hold a fence (has_code() routes it to
        # docs), so in prose this fires on a block the rewrite added, or on a reworded indented passage that
        # nothing else was watching.
        checks.append(("every code block in draft.txt is unchanged and none were added",
                       facts.get("code_blocks_changed", 0) == 0 and facts.get("code_blocks_added", 0) == 0,
                       f"changed {facts.get('code_blocks_changed', 0)}, added {facts.get('code_blocks_added', 0)}"))
        # links are the docs bullet in SKILL.md step 6, and a `both` document carries the docs blend's link credit
        if genre in ("docs", "both"):
            checks.append(("no links added to final.txt", not facts.get("links_added"),
                           f"links added: {facts.get('links_added', 0)}"))
        expectations = [{"text": t, "passed": bool(p), "evidence": e} for t, p, e in checks]
        passed = sum(1 for x in expectations if x["passed"])
        grading = {
            "expectations": expectations,
            "summary": {"passed": passed, "failed": len(checks) - passed, "total": len(checks), "pass_rate": round(passed / len(checks), 2)},
        }
        with open(os.path.join(run_dir, "grading.json"), "w") as f:
            json.dump(grading, f, indent=2)
        # the table prints what the scorer returned; a result with no verdict or no second opinion shows "-"
        rows.append((case, "/".join(config), before.get("ai_probability", "-"), before.get("heldout_roberta", "-"),
                     after.get("ai_probability", "-"), after.get("heldout_roberta", "-"), after.get("verdict", "-"),
                     passed, len(checks)))
    print("| case | config | blend before | RoBERTa before | blend after | RoBERTa after | verdict | checks |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        print("| " + " | ".join(str(x) for x in r[:7]) + f" | {r[7]}/{r[8]} |")


if __name__ == "__main__":
    main()

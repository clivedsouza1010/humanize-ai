---
name: humanize-ai
description: Detect AI-written text and rewrite it so it reads like a person wrote it, checked in rounds against local AI detectors (Binoculars-style language-model scoring, writing-style tells, and a separate RoBERTa detector). Use this whenever someone asks whether text "sounds like AI" or "reads like ChatGPT", asks to humanize, de-AI, or make a draft sound more natural or less robotic, or is about to post or send something an AI helped write (talk abstract, LinkedIn or X post, Reddit reply, cover letter, email, blog post, README intro), even if they don't say "detector".
---

# Humanize

Scores text for AI signals, then rewrites flagged text in rounds until the detectors read it as human and the facts still match the original.

Set these once per shell:

```bash
PY=~/.cache/humanize/venv/bin/python
D=${CLAUDE_SKILL_DIR}/scripts/detect.py
```

If `$PY` doesn't exist, run `bash ${CLAUDE_SKILL_DIR}/scripts/setup.sh` first. It needs Python 3.11 or newer (if `python3` is older, run it as `PYTHON=python3.11 bash ...`) and downloads about 6.7 GB of models plus the Python packages, so tell the user before you start it.

Start the scorer once. It keeps the models loaded, so every check after this takes under a second instead of 15. It shuts itself down after 15 idle minutes.

```bash
bash ${CLAUDE_SKILL_DIR}/scripts/start-scorer.sh
```

If a check exits with "runs older detect.py code", the scorer predates an edit to `detect.py`. Stop it with `pkill -f 'detect.py --serve'` and run the start script again. If the start script says something else is answering on the port, another app holds 8765 (AnkiConnect uses it by default): set `HUMANIZE_PORT` to a free port for the start script and every check.

## Detect

```bash
$PY $D draft.txt --heldout > score.json
```

Read these fields:

- `ai_probability` and `verdict`: the fitted blend of every signal. `verdict` is `ai` (at the cut or above), `human` (under the bar the rewrite loop aims for) or `unclear` (in between). The cut is 0.5 unless you pass `--register`.
- `verdict: known text`: the models predict almost every word, so it's a widely published text (a licence, the Contributor Covenant, a famous quote) or text that repeats itself. That says nothing about who wrote it. Tell the user that, not "AI".
- `more_ai_like_than_human_samples`: where the text sits among the human texts the blend was checked on. "95%" means it reads more AI-like than 95% of them.
- `heldout_roberta`: a separately trained detector (fakespot RoBERTa), 0 to 1. A second opinion on prose, and nothing on docs. `bench/metrics.md` scores it on every fit, and the two genres are not close: on prose AUROC 0.790, catching 64% of AI text at 16% of human text flagged; on docs AUROC **0.345**, which is below chance, flagging 16% of known-human docs while catching 9% of the AI ones. So a high reading on a doc is weak evidence it was written by a person, and one register is worse still: on 20 OWASP security cheat sheets written before any AI policy existed it flagged 15, median 0.956. A document's number is the highest of the sections that decide its verdict, so it also climbs with length: of known-human docs, 4% of single-section ones reach 0.5 against 64% of those with five sections or more.
- `sentences[].flags`: why each sentence looks AI. This is what you rewrite against.
- `sentences[].habits`: patterns like colons, em dashes or "However," openers that, in this genre's training data, people use as much as models do. Shown for interest; don't rewrite for them.
- `sentences[].recalled`: the sentence is quoted or standard wording (no AI training sentence scores that predictable), so it carries no flags.
- `warning`: under 80 words there's no verdict at all, only the sentence flags. No AI training text was that short, so any score would be a guess.
- `human_bar`: the score a text has to stay under for `verdict: human`.
- `ai_bar`: the score at which the verdict turns `ai`, and `register`: the register it was judged against, if you named one.
- `voice_pushes_ai`: for docs, the function-word patterns pushing this section toward AI, strongest first, as pattern, count and push. `...` is any other word, `(sentence start)` is the start of a sentence and `(name)` is a name or code. `(sentence start) ...` counts imperatives and fragments like "Needs Node 18", so it can stay on top of a doc that's fine.
- `not_read`: words the scorer skipped, such as table cells or HTML comments. Mention it when it's a large part of the file.
- `voice_drift`: from `--compare` only. How far the rewrite's function words have moved from the draft's, in nats, as reverse KL. 0 means the text is unchanged. Read it next to the score, never alone: across 108 graded runs the score bought per unit of drift is flat to about 0.15 and halves after it, so drift past that is paying more for less. Two things it is **not**. It does not detect AI: on 4,307 matched items, a ChatGPT answer was further from a human answer than a second human answer only 46% of the time. And it cannot tell one author from another at normal lengths: two halves of a single human document differ by 0.26-0.42, which is wider than any rewrite in the graded set. It only means something comparatively, between rewrites of the same draft.

Markdown is handled for you. Once text is treated as markdown, a CommonMark parser keeps only paragraph text, so code, tables, images, HTML, headings, link-only rows like "Docs · npm · Demo", bold labels and the License section never reach the scorer. Long prose is scored in sections of about 300 words, like Grammarly's "how much of this looks AI". `genre` in the output says which detector was used:

- `docs`: the text has a fenced code block or a table, or an indented code block plus headings, or the file is a README, CHANGELOG, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY or anything under `.github/`. The docs detector masks every content word and reads the function words and punctuation left over, so a doc's subject, names and code can't sway it. A doc that links out a lot gets a credit, because people link out and agents mostly don't. The language-model signals are shown but only used to spot known text: on docs they drift with the calendar.
- `both`: markdown with headings but no code, like a blog post. Both detectors score it. The verdict is `ai` if either says so, and `human` only if both agree; `by_genre` shows both scores. First-person writing and anything under 120 words get the prose detector only, because the docs detector never saw either.
- `prose`: plain text. A link or an email `--` signature doesn't make text markdown.

Pass `--genre prose`, `docs` or `both` when you know better than the guess. A doc with under 120 words of prose left after removing code gets a warning and no verdict.

### Registers

One cut can't mean one thing for every kind of writing. At 0.5 the detector flags 37% of the genuine news writing in its training set and almost none of the literary writing: the same number sits at the 63rd percentile of one group's scores and above nearly all of the other's. `--register NAME` compares a prose text against one kind of writer instead of all of them.

```bash
$PY $D draft.txt --heldout --register news > score.json
```

| `--register` | the human writing it is compared against | cut | bar |
|---|---|---|---|
| `news` | RAID news: BBC wire copy from 2004-05 | 0.792 | 0.656 |
| `forum` | Reddit answers and Hacker News comments, 2022-26 | 0.620 | 0.319 |
| `email` | Enron work email, around 2001 | 0.491 | 0.250 |
| `academic` | RAID paper abstracts | 0.263 | 0.134 |
| `encyclopedia` | Wikipedia article prose, 2023-26 | 0.242 | 0.148 |
| `literary` | RAID book plot summaries, from Wikipedia | 0.219 | 0.134 |

Each cut is the score a tenth of that register's own writers land above, each bar the score four fifths of them land under, both out of fold. Everything below 0.5 is a register judged more strictly than the pooled cut judges it, email included. `ai_bar` in the output says which cut was used.

Pass it when you know what the text is. Leave it off when you don't: the pooled 0.5 and bar apply and nothing changes. Three things to know first:

- **It cuts both ways.** For news and forum writing the cut goes up, so less is called AI: news false alarms fall from 37% to 10% and AI news caught from 93% to 85%, and forum false alarms fall from 13% to 10%. For academic, literary and encyclopedic writing the cut goes *down*: false alarms rise from 5% or less to about 10%, and a few more AI texts are caught. Email sits at about 10% either way. Naming a register asks to be judged against those writers, in both directions.
- **The wrong name gives the wrong answer.** A real 2004 news story scoring 0.56 reads as ordinary news writing under `--register news` and as AI under `--register literary`. Don't guess.
- **`news` is the loosest pair here**, because its reference is wire copy this detector reads as unusually AI-like. It is not a way to wave text through.

There is no register for reviews, blog posts, cover letters, talk abstracts, LinkedIn or X posts. The set holds no human writing of those kinds, so there is nothing to set a cut from, and they keep the pooled pair. Docs have no registers at all: their bar is the score only 2% of AI sections fall under, not a quantile of human scores.

If you pass `--register`, pass it to every score in the loop below, or the bar moves between rounds.

For a document split into sections:

- `verdict` is `ai` when at least a quarter of the words sit in sections the cut calls `ai` (0.5 or more, or the register's cut). It's `human` when under half the words sit in sections that aren't `human` and no section scores 0.9 or more. One stray section is normal in a long human doc. Sections under 120 words, and sections of known text, are shown but don't decide.
- `all_sections_human` is the stricter check the rewrite loop uses. Like `ai_share` and `ai_probability`, it only covers the sections that decide (120+ words, not known text).
- `ai_share` is that share of words; `ai_probability` is the worst deciding section's score. A shorter section can score higher and still only show up in `sections[]`.
- `sections[]` holds each section's own result, with `starts` (its first words) so you can find it.

To check a whole repo or folder, score every tracked `.md`, `.mdx` and `.txt` file in one go:

```bash
$PY $D --scan ~/dev/my-repo --out scan.json
```

It prints one line per file and writes every full result to `scan.json`.

When reporting to the user, give the probability, the verdict, the percentile and the flagged sentences with their reasons. For a document, give `ai_share` and a line per section that isn't `human`. Say plainly that it's a statistical guess, not proof of authorship. The current detector's measured accuracy is in `bench/metrics.md` (rewritten on every retrain), and what those numbers mean and where they fall short is in `bench/REPORT.md`. Quote from those, not from memory.

## Humanize

Two things have to be true at the end: a person reading it believes a person wrote it, and the detectors agree. The first matters more. In blind tests, rewrites that chased the score read worse to people than a plain rewrite did, so the reader comes first in every round.

Humanizing doesn't change anyone's duty to disclose AI help. If the user says the text is going somewhere with a rule against AI help, such as a class that bans it, say plainly that a rewrite doesn't change that rule, and don't run the rewrite loop to get it past a detector there. Scoring the draft and explaining its flags is still fine. If the rule only asks for AI help to be disclosed, rewrite as usual and remind them to disclose it.

Work in a scratch folder. Keep the original as `r0.txt` and never edit it.

1. Score the original by its real path, not the `r0.txt` copy, because a README, CHANGELOG or anything under `.github/` is routed to `docs` by its file name. Note the `genre` it gets. Then score `r0.txt` with `--heldout --genre <that genre>`. If the verdict is `known text`, it's a published standard text; say so and only reword it if the user still wants that. If the verdict is `human`, no sentence is flagged, and the user didn't say it reads like AI, say so and stop. Otherwise go on, even if the score is under the bar: a reader still notices "Spoiler:" or a tidy list of three. Don't let RoBERTa alone trigger a rewrite; it disagrees with real human writing too often.
2. Read `references/rewrite-guide.md` once, before the first rewrite.
3. Round 1 is a fresh write for the reader, not an edit:
   - First write `facts.md`: every number, name, date and claim in the draft, and how strongly each is made ("suggests", "usually", "we recommend" stay that strength).
   - Then write `r1.txt` from that list, the way the author would say it on a good day, in their register, without looking at `signals` and without working through the draft sentence by sentence. Editing in place keeps the draft's skeleton, and in blind tests that was the most common reason people still read the result as AI, even when the detector passed it.
   - Drop structure that's a model habit, not just the words (see "Layout" and "Skeletons" in the guide).
4. Later rounds fix what's still flagged, plus anything `--compare` complains about. Rewrite the whole sentence in plain words rather than swapping a word for a rarer one. Read each changed sentence as if aloud: if the author wouldn't say it, it's wrong even if the score drops. If nothing is flagged and the score is still high, follow "When nothing is flagged" in the guide. Never edit the text to push one number in `signals`.
5. Check the round with the genre from step 1 (here the original was a README, so `docs`):
   ```bash
   $PY $D rN.txt --heldout --genre docs > rN.json
   $PY $D rN.txt --compare r0.txt
   ```
6. A round passes when all of these hold:
   - `verdict` is `human`, and for a document split into sections, `all_sections_human` is true. Outside docs (prose and `both`), also no entry in `sections[]` has verdict `ai`: a short AI-looking section is real signal there. In docs it's mostly a false alarm, so skip that part.
   - outside docs, `heldout_roberta` is under 0.5. That includes `both`: the inversion below was measured on the docs corpus and a `both` document is prose with headings. Not for docs: it is below chance there, so the check fails long human docs and waves AI ones through. The number is still worth reading and reporting, just not worth passing or failing a round on.
   - nothing real is listed under `missing`, and nothing you made up is under `added`. Read both lists rather than treating any entry as a failure: the check sometimes lists an ordinary word that starts a sentence.
   - `length_ratio` is between 0.7 and 1.3
   - no hidden characters, look-alike letters or deliberate misspellings. Words already in the draft and capitalised words don't count; of the rest, `bench/grade_evals.py` allows one per 100 words of the rewrite, and always at least one, because a rewrite in someone's own vocabulary trips a spellcheck honestly.
   - `code_blocks_changed` and `code_blocks_added` are both 0, in every genre. `--compare` leaves whatever sits inside a code block out of `missing` and `added`, so this is the only check on what a block says. A prose draft can't hold a fenced block, so in prose it fires when the rewrite adds one, or touches an indented passage at all, such as a quoted address: keep those exactly as they are.
   - for docs and `both`, `links_added` isn't there, and `length_ratio` is between 0.85 and 1.15. Both rules cover `both` because half of a `both` verdict is the docs blend: padding is what moves it, and the link credit is part of it.
   - `voice_drift` is under 0.22, and a round with no `voice_drift` reported has not passed it: `--compare` leaves the field out when `scripts/blend.json` carries no docs ngram table, and a rollback can do that. That is a guardrail on the runaway tail, not a target: no round that ever passed went above 0.214, and the price of score halves past 0.15. A low number is not a good sign on its own — see below.
7. Stop at the first passing round, or after 5 rounds.
8. Before handing it over, read the chosen round start to finish as an editor would. Check it against `facts.md` (every fact there, no new facts, each claim as strong as before), not against the draft's wording, and don't pull sentences back toward the draft. New phrasing is fine; new information isn't. Fix anything stiff, odd or unlike the author, then score it again. If the fixed version still passes, give that one. If the fix costs the pass, give the user the natural version and say plainly that it scores `unclear` or `ai`, and what it scored. Don't hand over awkward text just because it passed. If no round passed at all, give the EARLIEST round that keeps the facts, not the best-scoring one, and say which check it fails. When nothing passes you are choosing between failures, and the later round is the worse piece of writing: across 40 blind pairs of two rounds from the same run, judges picked the later round 43% of the time, and 33% when they were confident about the difference.

Single line breaks don't change the score. Layout still can: list markers ("- ", "1.") in plain text are read as text, and in anything over about 300 words, paragraph breaks decide where the sections split, which changes `all_sections_human`. So settle the layout for the reader first (see "Layout" in the guide), keep it fixed between rounds, and if you change it late, score again before calling the round passed.

Give the user the final text, then a short table:

| round | AI probability | verdict | RoBERTa | flagged sentences | facts kept |
|---|---|---|---|---|---|

Be straight about what a pass means. It passed these detectors. Turnitin, GPTZero and Grammarly are trained differently and can disagree, and `bench/REPORT.md` shows this blend catches much less AI text from model families it wasn't fitted on. A pass here says nothing about other detectors, so don't suggest it does.

A docs verdict needs the same care. The docs detector reads the voice coding agents have had since about the start of 2026. It misses most AI docs from 2025 and could miss the next model's. On 2024-26 docs from projects that ban AI it calls about 1 doc in 8 AI, so a terse or heavily copy-edited human doc can get flagged. Say so when you report one.

Then record the run. Every humanize leaves a row behind, and that row is how the skill compounds without ever grading its own homework:

```bash
R=${CLAUDE_SKILL_DIR}/scripts/record.py
$PY $R add --draft draft.md --rewrite final.md --genre docs \
  --before 0.81 --after 0.04 --rounds 3 --heldout 0.12 \
  --moves "fresh write, split the list, cut the hedges"
```

A run is evidence, not a label. The draft has an author only the user can state, and the rewrite was written by this skill, so neither reaches the detector except through `label.py`. `record.py` cannot write to the label store at all, and `record_test.py` holds that open.

## Technical docs (READMEs, guides, API pages)

Docs always run the full loop, to the bar, whatever the first score says. Here passing comes before how the doc reads, unlike prose. The docs `human_bar` is much lower than the prose one, so `verdict: human` takes more work.

The docs detector reads function words, so most rounds have no flagged sentences and the advice to touch only flagged sentences doesn't apply. Steer by `voice_pushes_ai` in each section, and use the moves under "Technical docs" in the guide. Change a few things a round: moves that fix one pattern often add the next, and a round of many edits won't show which one worked.

It's the same loop, with these changes:

- Keep the fresh write in step 3, but leave short fragments and lead-ins like "Install it:" as they are. Blind readers ranked it above a round 1 of small edits to the draft, which came out choppy.
- At step 8 a pass comes first. If an editor's fix costs the pass, find another wording that keeps it, and hand over a passing version. Facts, code, length, drift and the no-added-links check still can't be traded for a pass. Rescoring those fixes doesn't count toward the 5 rounds.
- Read step 8 closely on claim strength. `--compare` can't see "is one of" softened to "can be", or a sequence the draft never claimed, and small edits made both happen.
- When you hand it over, say a pass can read worse than the draft: in every blind test here, readers picked the draft.
- Rewrite only the prose. Code blocks, commands, file paths, API, function and option names, version numbers, URLs and tables stay exactly as they are. `--compare` reports `code_blocks_changed` and `code_blocks_added`, and a round only passes when both are 0.
- Keep the precise technical word. In docs, "peer dependency" or "idempotent" is the plain word; swapping it for something vaguer makes the doc worse and doesn't read as more human.
- Don't invent limitations, version history, benchmarks or "we tried X" stories to make it sound lived-in. Those are facts.
- Keep a terse doc terse. The easy way to pass is padding, and blind judges marked padded docs down hard. Fix flagged sentences by rewording or joining them, not by adding explanations. For docs a round passes only if `length_ratio` is between 0.85 and 1.15, not 0.7 to 1.3.
- If 5 rounds don't reach the bar inside those limits, hand over the EARLIEST round that keeps the facts and the code, not the one that scored closest, and say what it scored. Rounds are not free: the extra rounds buy score at the cost of the writing, and how much score they buy does not predict how much writing they cost (Spearman -0.04 over 40 pairs). So a round that got closer is not a better thing to hand over.
- For a long document, rewrite only the sections whose verdict isn't `human`, then score the whole file again at the end.
- Read "Technical docs" in the guide for the tells that are specific to docs.

## Rules for the rewrite

The full list is in `references/rewrite-guide.md`. The ones that matter most:

- Keep every fact, number, name and claim. Add none. No invented anecdotes or experiences.
- A turn of phrase isn't a fact. "If the printer cooperates" or "so nobody gets blindsided" adds voice, not information, and that's what makes text sound like someone wrote it. A new number, name, event, reason or claim is a fact, and isn't allowed.
- Keep the genre and register. An abstract stays formal. A Reddit reply can be loose.
- No typos, hidden characters, look-alike letters, or slang the writer and genre wouldn't use. They make the text worse, and detectors catch them. Casual markers the genre normally uses ("imo" on Reddit) are fine.
- Keep lists that organise information the reader will scan or act on (a plan, steps, dates). Only drop decorative ones.
- If the user gives a sample of their own writing, match its sentence length, punctuation habits and word choice.

## Learning from labels

The detector gets better only from texts whose author is actually known. Its own verdicts and your rewrites are never evidence: training on them would teach it to agree with itself.

When the user tells you who wrote something, save it:

```bash
L=${CLAUDE_SKILL_DIR}/scripts/label.py
$PY $L add README.md --human --note "wrote this myself, no AI"
$PY $L add docs/guide.md --ai --note "Claude draft, lightly edited"
$PY $L list
```

- `--human` means a person wrote it with no AI help. `--ai` means an AI wrote it, edited or not.
- Only label what the user states. Don't guess from the score, and never label a humanized rewrite as human.
- A wrong label can be taken back with `$PY $L remove ID`.

Then retrain:

```bash
$PY ${CLAUDE_SKILL_DIR}/scripts/retrain.py
```

Retraining needs the training corpus in `~/.cache/humanize/data`, which isn't shipped with the skill. Without it `retrain.py` stops and names the missing files, and the labels stay saved for when the corpus is there.

The detector records which labels it has learned from as salted hashes, so `blend.json` can't be matched to the labelled texts. The salt is `~/.cache/humanize/label-salt` and never leaves the machine. Keep it with `~/.cache/humanize/data` if you move machines. Without it every label counts as new, so a genre with nothing new gets refit and judged again until a promotion records the new salt.

It rebuilds the data and fits a candidate. Then, for each genre that has new labels or a new dataset, it fits the old and new setups on the same 20 random splits and scores them on the same held-out texts. A genre with nothing new stays exactly as it is. A genre's detector is replaced only if, on average, AUROC doesn't drop more than 0.005, false alarms on human text don't rise more than 1 point, AI caught doesn't drop more than 2 points, it doesn't do worse on the new data, no new source's own human rows flag more than 3 points above the rate on everything else, and — for `docs` — it doesn't call more than 1 point more of the held-out human docs AI.

The fifth is the only one that's a property of the batch rather than a comparison, so it reads the same way every run until someone acts on it. The first four can clear with more data. A source with fewer than 250 human rows long enough to score is printed as too thin to judge, and is not judged.

The sixth is the only one read on text outside the split: the ban-policy docs and the pre-policy project snapshots that `bench/holdouts.py` reports, scored on the blend that would actually ship. It exists because the second check cannot see what it is for — that figure is pooled over thousands of pre-2023 docs, so a few hundred recent ones cannot move it however badly they go. Measured across the saved versions with `bench/score_blend_versions.py`, five promotions in a row left the held-out rate at 0.091 and then two on 2026-11-11 took it to 0.105 and 0.127, while the pooled figure went 0.006 to 0.007. Both would now be refused, which is the point: the trade is real and it should be yours to make with `--force` rather than one the gate makes quietly. Under 100 held-out docs it says so and does not judge.

If the gate keeps the current detector, the labels stay saved. Show the user the table it prints and let them choose: catching more text like theirs at the cost of more false alarms is their call. To accept it:

```bash
$PY ${CLAUDE_SKILL_DIR}/scripts/retrain.py --force docs --note "accepted the false alarms to catch more of my own docs"
```

Every version your own retrains replace is kept on this machine, with its metrics. `--history` also lists the maintainer's earlier versions, which don't ship, so only the ones saved here can be rolled back to:

```bash
$PY ${CLAUDE_SKILL_DIR}/scripts/retrain.py --history
$PY ${CLAUDE_SKILL_DIR}/scripts/retrain.py --rollback VERSION   # one saved on this machine
```

A handful of labels moves the numbers very little next to the 4,000 sections it trains on (about 3 labels in 10 are held back for testing instead). That's on purpose: one mislabelled file shouldn't swing the detector. Tell the user that labels pay off in bulk, that the clearest wins come from texts the detector currently gets wrong, and that for docs the most useful label of all is recent human writing, because the human docs here stop in mid-2024.

The next few paragraphs, up to the run store, are for whoever holds the training corpus and the held-out docs, which don't ship. Keeping the human side as recent as the AI side matters as much as new AI data. `bench/fetch_hn.py` tops up recent forum prose and `bench/fetch_wikipedia.py` tops up recent encyclopedic prose; neither needs a token or a label, and both should be run every few months.

For **docs**, recency is the hard one, because a date window is not provenance: writing since 2023 is exactly where AI help is most common. The only route that holds up is projects that publicly **ban** AI contributions, taking the docs they gained after the ban took effect. A **disclosure** rule is not provenance and must not be used this way: it permits AI, so the window is mostly AI prose. Measured on 2026-11-11, docs from ban projects flag as AI 1.8% and 10.9% of the time in two independent batches, while docs from disclosure projects flag 44.6% and 77.3% of the time against 77.5% for a corpus of self-declared AI PRs. Run `bench/holdouts.py` rather than trusting the numbers written here: they moved to 3.6% and 12.8% that day under two promotions and back again when those were rolled back, and the gate's own false-alarm check saw almost none of it. That is what the sixth check is for. Read the holdout's ban line as the false-alarm number; its disclosure line is a mixture, not a human rate. `~/.cache/humanize/data/github/policies.json` holds the 25 projects behind the holdout and `policies-train.json` the 17 added later, each with the verbatim policy quote, its URL, and the date the clause was demonstrably present by. Neither trains: `bench/holdouts.py` reads both. Both files also keep every rejection, which is the more useful half: 421 of 439 candidates failed. Before adding a project, check the four things that did the rejecting — docs that are prose markdown rather than `.rst`, `.adoc` or generated reference; a real ban rather than "review what you submit" (a must-disclose rule can be recorded, but never used as human provenance); no `AGENTS.md`, `CLAUDE.md`, `.cursor/rules` or Copilot instructions in the repo, because a project that runs on agents cannot vouch for its own docs; and few AI trailers on docs commits since the policy. Watch for the trap in the last one: a policy that forbids AI trailers makes its own docs unverifiable, so a zero count there proves nothing and the PR bodies have to be read instead. `bench/provenance.py` does that reading — a merged pull request's trailers, checkboxes and AI-usage section, giving `ai`, `human` or `unknown`, with `fetch_github_docs.py pr` collecting the docs those pull requests wrote. It is accurate (against an independent reader on 363 pull requests from 21 projects it agrees on 359, and every verdict it issues matches) and it is still not a way to get human docs: 4,779 merged pull requests gave 1,455 AI declarations and 491 human ones, and once a label is only allowed to cover a file the pull request wrote nearly all of, 41 AI docs and 1 human doc survive. Those are held back as well, and `holdouts.py` pairs each project against its own docs from the day its policy took effect, because a project's pre-policy flag rate runs from 0.000 to 0.417 and one pooled number hides that completely. Err late on the date — too early pulls pre-policy docs onto the human side, too late only costs rows.

Watch the register whenever a human source lands. The first HN run added 520 short forum comments and the gate refused them, and the damage turned out to sit in **one** register: declarative third-person reportage went from 35% to 42% flagged while every other human register stayed put or improved. REPORT.md has that round in full, including the per-register table the pooled false-alarm number hides.

Three things that round taught, worth checking before any new human source lands:

- **A filter that removes something both labels do is worse than no filter.** It turns that thing into an AI cue. Two filters in the Wikipedia fetcher failed this way before anyone noticed: one dropped every sentence with a copula plus an article, the other dropped any paragraph that quoted twice. Both read as format filters and both were style filters. Look at the drop counts, not at a green test suite.
- **Check who actually wrote the text, not who saved it.** A diff cell for a partly edited line holds the whole line, so "added by" is not "written by" unless the line is wholly new.
- **A contaminated batch is checked for now, but the check is narrow.** The gate refuses a new source whose own human rows flag more than 3 points above the rate on everything else, measured per source and only once the source has 250 scorable human rows. It catches roughly 7% mislabelled AI text in a 300-row prose batch and about 1% in a docs batch, because the docs detector keeps flagging the mislabelled rows even after training on them while the prose one absorbs them. Four things it can't do: it can't tell a mislabelled batch from a register the detector reads badly, so it refuses both and leaves the call to you; it's blind to contamination made of default-voice Claude prose, which the prose detector caught only 59% of the time in the 2026-11-10 contamination runs (REPORT.md, "The contamination check"); it reads one rate per source, so a bad register inside a mixed source still averages away; and hand-labelled rows all share the source name `feedback`, so that channel can't reach the row floor and is never judged. The old advice still holds for everything the check can't see: read `new_human_flagged` and the per-source rates in the output yourself.

`bench/REPORT.md` says how the data was built and what the numbers mean, and `bench/metrics.md` holds the numbers from the last fit.

### What the run store is for

Runs accumulate on their own. Two things to do with them:

```bash
$PY ${CLAUDE_SKILL_DIR}/scripts/record.py queue   # drafts whose author only the user can state
$PY ${CLAUDE_SKILL_DIR}/scripts/record.py stats   # score drift, which is how staleness shows up
```

`queue` is the bridge between a run and a label. It shows the draft, never the rewrite, because the rewrite's author is this skill and labelling it human is the one move that would teach the detector to agree with itself. When the user says who wrote one of those drafts, label it and the normal gate applies.

`stats` splits each genre's runs into older and newer halves and compares the median score of the drafts coming in. A drop means incoming drafts now score far lower than they used to, which is what a stale detector looks like: the voice it was fit on has moved on, and the fix is new AI data and a retrain, not a lower bar. A rise means either the drafts really are more machine-like or the detector has grown trigger-happy, so check false alarms on known human text with `bench/holdouts.py` (it needs the held-out docs) before trusting it. Below six runs in a genre it says so and reports nothing, because a handful of runs is not a trend.

The store never feeds training. That is the whole point of keeping it separate.

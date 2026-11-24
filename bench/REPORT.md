# How well humanize works

Short version: on prose the detector is right about 86 times in 100, and flags about 1 human text in 8. On technical docs it's right about 96 times in 100 on its test split, but that split sets people from 2024 or earlier against AI from 2025-26. On recent docs from projects that ban AI it calls about 1 doc in 8 AI. The 1 in 8 is an average: at a single cut it is about 1 in 3 for news writing and 1 in 25 for literary writing, and naming the register brings every kind of writing to about 1 in 10 of its own. Not 98 either way. Claude writing in its default style is the hardest case for prose: it is caught about seven times in ten, against 82-94% under a house style guide. The rewrite loop gets most Claude drafts under the bar without inventing anything.

`metrics.md` has the full tables for the detector in use and is rewritten on every promotion, so if the two ever disagree, trust `metrics.md`. This file explains them.

## Detectors

There are two, picked by genre (see SKILL.md):

- **Prose** is a logistic regression over 26 signals. 10 come from two small language models (Qwen2.5-1.5B base and instruct): Binoculars, Fast-DetectGPT, perplexity and how evenly predictable the sentences are. 16 come from writing style: tell words, "it's not X, it's Y" frames, lists of three, sentence length spread, word variety and so on.
- **Docs** reads function words. It masks every content word, keeps about 250 function words and the punctuation, and scores the one- and two-word patterns left over with a table of 1,360 weights. A doc that links out a lot gets a credit, because people link out and agents mostly don't. The language models only spot known text here: on docs their scores drift with the calendar. "The docs rebuild" below has the evidence.

In prose, the AI-tell signals can only push toward "AI", so a rewrite can't pass by adding tells. The docs table has no such rule: 44% of its weights lean human, which is what makes it good and what makes it easier to game.

Measured on held-out text (mean over 20 random grouped re-splits, 5th-95th percentile in brackets):

| | prose | docs |
|---|---|---|
| accuracy | 0.864 (0.851-0.878) | 0.960 (0.948-0.970) |
| AI text caught | 0.852 (0.831-0.875) | 0.864 (0.821-0.898) |
| human text wrongly flagged | 0.122 (0.096-0.150) | 0.005 (0.001-0.008) |
| AUROC | 0.946 (0.937-0.954) | 0.982 (0.974-0.991) |
| Claude text caught | 0.771 (0.727-0.806) | 0.979 (0.968-0.989) |

The prose numbers count only texts of 80 words or more, the ones that get a verdict.

**Real-world checks for docs.** Don't read the docs column as what you'll see in use. Docs the detector never trained on, from `bench/holdouts.py`:

| docs | docs scored | called AI | sections flagged |
|---|---|---|---|
| new docs, Jun 2024 to Jun 2025, same TS and React repos | 482 | 4.4% | 2.7% |
| 17 projects that ban AI, 2024-26 | 126 | 11.9% | 10.9% |
| 8 projects that require AI disclosure, 2025-26 | 124 | 34.7% | 44.6% |
| Homebrew PRs that disclosed AI, 2026 | 61 | 77.0% | 77.5% |
| labelled docs, trained without them | 11 | 11 of 11 | 38 of 38 |

The ban row is the nearest thing here to a false-alarm rate for people writing today, and it's about 20 times the test split. It's lumpy: Servo's book 4%, Cataclysm 5%, p5.js and Immich 0, against MonoGame 28% and homepage 19%. The spread is not evidence that anyone broke a rule. Three of the 21 docs flagged before the cut was raised were set aside, two bot-generated and one crediting AI, and from here I can't tell a false alarm from AI use in the rest. The 0.7 cut was chosen using the 2024, ban and Homebrew rows, so those aren't fully untouched. A cut of 0.6 calls 15% of ban docs and 90% of Homebrew's AI, 0.75 calls 9% and 69%.

Claude prose by style, on the held-out split:

| | Haiku | Sonnet | Opus |
|---|---|---|---|
| written under a house style guide | 0.82 | 0.94 | 0.89 |
| default style (no style guide), both batches | 0.73 | 0.73 | 0.73 |

Whole held-out documents, scored the way the skill does it: Claude's docs get an "ai" verdict 98% of the time when written under a house style guide, and 34 of 34 times in its default styles (plain, formal, long, marketing and first-person). Human READMEs get "ai" 0-4% of the time and read "human" 40-92% of the time, depending on the source. Docs from real repos credited to an AI tool (Claude, Copilot, Cursor, Codex, Devin or Gemini) are caught about half the time, 37 of 66. An earlier set also held back AI guides, FAQs, migration notes and release notes that never trained, and caught 83-100% of them, with API pages at about 60%; the current set holds none back.

For comparison, on the prose test split Binoculars alone gets 0.71 accuracy, and the off-the-shelf fakespot RoBERTa detector 0.74 while flagging 16% of human text. Both move with every refit; `metrics.md` carries the current pair.

### What it was checked on

| source | label | rows | what it is |
|---|---|---|---|
| RAID (abstracts, books, news) | human / AI | 360 / 350 | the benchmark Grammarly cites; AI side is ChatGPT, Llama, Mistral and MPT chat models from 2023 |
| HC3 reddit_eli5 | human / AI | 150 / 133 | real Reddit answers next to ChatGPT answers to the same questions |
| AESLC | human | 300 | Enron work emails, around 2001 |
| Wikipedia | human | 92 | paragraphs from articles created 2023-26 by editors who registered before ChatGPT |
| Hacker News | human | 260 | 180 comments and 80 Ask HN posts of 100+ words, 2024-05 to 2026-11, one per author, accounts opened before ChatGPT |
| npm READMEs | human | 863 sections | small packages (616) and popular ones (247) whose last release was before June 2022 |
| Claude, house style guide | AI | 202 prose, 362 doc sections | written by agents that had a house style guide, in the genres people humanize |
| Claude, default style | AI | 271 prose in two batches (156 and 115), 90 doc sections | written by agents without it: plain, marketing, long, formal and first-person registers |
| GitHub docs before ChatGPT | human | 2,311 sections | 1,395 docs from 279 TypeScript, React and Next.js repos, each pinned to its last commit before Nov 2022 |
| GitHub docs from 2023 | human | 1,098 sections | 630 docs those repos gained between Nov 2022 and Jun 2024; a few may be AI-assisted |
| AI-credited docs | AI | 457 sections | 294 docs from 173 JS and TS repos, 2025-26, added or nearly rewritten in a commit crediting Claude, Copilot, Cursor, Codex, Devin or Gemini; a person may have edited some |
| paired docs | AI | 352 sections | Claude (Haiku, Sonnet, Opus) writing 126 of the same docs for the same projects as the human ones, no style guide |
| labelled docs | AI | 38 sections | 11 docs whose author confirmed AI helped with all of them |

Until 2026-11-15 the prose set also held 300 Yelp reviews. Yelp's dataset terms don't allow publishing results from them, so the prose detector was refit without them that day, and their rows and figures were taken out of this report. The prose figures at the top and in the list below are from the refit. The dated sections further down were measured with the reviews in the set. Every saved version before the refit was fitted on them too, so those were removed from `bench/blend-history/`, and the rollbacks those sections name no longer exist.

### Limits, plainly

- **Default-style Claude prose.** Prose written without a style guide is caught 58-80% of the time depending on the model and the split, so read it as "about seven in ten". Opus's is the weakest at 58-74%. Modern Claude's plain default prose is simply hard for this detector.
- **New model families.** Trained without Claude, the prose blend catches 2% of Claude text. Each 2023 family left out is still caught 92-100% of the time, because they write alike and Claude doesn't. A very different new model will mostly slip through. For docs, see "Unseen tools" below.
- **Genres with no human samples.** There are no human reviews, cover letters, LinkedIn posts, talk abstracts or student essays. False alarms on those are unmeasured. Forum and discussion prose now has 260 real 2024-26 examples. Docs now have human guides, contributing guides, changelogs and blog posts from 279 repos, but security pages are still thin at 13 held-out human sections.
- **It reads one voice.** AI-credited docs caught by half-year: 2025H1 0 of 11, 2025H2 3 of 15, 2026H1 25 of 38, 2026H2 31 of 37. Trained on 2026 text it mostly misses 2025 text, and on 2023 chat-model prose it's at chance (AUROC 0.48). A model that goes back to "will be" and "of the" would slip through, and the next voice might too. Retrain every few months with fresh `fetch_github_docs.py ai` data.
- **Unseen tools.** Trained without that tool's AI docs, it catches Cursor 80%, Codex 98%, Copilot 45%, Devin 47%, Gemini 41%, and Claude 58%. Those rows are all the same era, so they don't show what a new model will do. Devin and Gemini rest on 66 and 27 sections.
- **Terse writers.** People who write present tense, active voice, no padding sit nearer the AI voice. In the rebuild's checks, a rule-based copy edit with no AI in it (serial commas, present tense, second person) tripled false alarms.
- **Link credit.** A section pasted without its doc, or text with the links stripped, gets no credit. Adding links by hand beats it, so `--compare` rejects a rewrite that adds any.
- **Who it's unfair to.** Non-native English writers and very formal human writing score more AI-like. Never use a score as proof someone used AI.
- **Short text.** Under 80 words of prose (120 for docs), scores swing a lot or aren't given.
- **The human side is still older than the AI side.** Enron email is 2001, HC3 Reddit 2022, RAID pre-2023. Only the 260 Hacker News rows and the 92 Wikipedia paragraphs are as recent as the AI side, and they are two registers: argumentative forum prose and encyclopedic writing from new articles. Most recent *formal* human prose is still the gap, and it is hard to fill honestly, because formal writing since 2023 is exactly where AI help is most common.
- **One register carries almost all the false alarms at the pooled cut.** Per register, human prose flagged as AI at 0.5: news 0.364, Ask HN 0.291, Reddit 0.139, email 0.076, forum 0.073, encyclopedia 0.055, books 0.040, abstracts 0.028. The pooled 12% figure is the average of one bad register and seven good ones, and the gate only ever sees the pooled number. "Per-register cuts" below gives each register a cut set by its own writers, which fixes the number but not the gate: a caller has to name the register, and the gate still measures everything at 0.5.
- **The gate cannot see a contaminated batch.** Hold a fixed half of the Claude-formal AI rows out of training, then add 30 of them back labelled human — what a 300-row human batch with 10% AI in it does to the boundary. Claude's formal prose caught falls 3.2 points, AUROC moves 0.001, and the pooled false-alarm number gets 1 point *better*. All four checks pass. The fourth, "does worse on the new data", cannot fire on a human-labelled batch at all: with no AI rows in it the check reduces to `1 - new_human_flagged`, and the candidate trained on exactly those rows, so the candidate always wins the comparison. `new_human_flagged` was a usable signal that nothing checked — it rose 0.119 to 0.211 as contamination went 0 to 60 rows, and the real Hacker News batch logged 0.1495. "The contamination check" below is what now reads it, and what it still cannot see.
- **The gate ratchets.** It refits its own baseline from the current row pool every run, so last run's accepted cost becomes this run's starting point and a fresh 1 point of tolerance is granted against it. On 2026-11-10 prose false alarms went 0.1156 to 0.1241 (promoted 06:46) and then 0.1255 to 0.1333 (promoted 08:31): two legal steps, and re-running the second candidate against the baseline from two runs back makes the gate refuse it. Nothing in the repo records what false alarms were when the detector was last trusted, so no run can say whether the current rate is 12% or 20%.
- **The Wikipedia rows are new articles, not Wikipedia in general.** They come from articles a long-standing editor created from scratch, which is what makes the authorship airtight and what keeps the fetch affordable. It also means the slice skews to the long tail — newly notable people, places and works — and carries none of the prose from mature, heavily edited articles. If the register transfers, it should transfer from either; that assumption is untested.
- **What a pre-ChatGPT account proves.** The Hacker News rows come from accounts opened before 2022-11-30, one row each, with anything disclosing a model dropped. That is provenance, not proof: a long-standing account can still paste a model's text. The detector is never used to screen them, because filtering human-labelled rows by its own verdict is the agree-with-itself failure that `record.py` exists to avoid.

### What earlier versions got wrong

The first fit reported 98% accuracy. An audit found almost all of that came from layout. No human sample had a blank-line paragraph and most AI samples did, so "has paragraphs" meant "AI". Now every prose score is taken on the text flattened to one line, `fit.py` refuses to run if layout can move a score, and the paragraph and markdown features are gone. The same audit removed contraction and slang counts, which tracked register rather than authorship and which the rewrite loop learned to game.

The first docs fit reported 96.5%, and a second audit took it apart:

- **Glued sentences.** Markdown lines without full stops were glued into giant "sentences", so the biggest weight was really measuring old READMEs' unpunctuated headings and bullets. A CommonMark parser now ends every paragraph and list item as its own sentence, and five residue checks stop the build if markup survives on either side.
- **Tells counted as human.** Because 2012-2022 READMEs use "simply" and "easily" more than Claude does, two inserted tells turned a Claude README "human". Tell weights now can't go negative.
- **Familiarity, not authorship.** The language-model signals tracked how familiar a package was, so docs are now style-only.
- **The real cause underneath.** Every Claude sample up to then had been written by agents that received a house style guide (short sentences, no filler words). The AI side was Claude-under-a-style-guide, not Claude. Default-style samples from agents without it were added for both prose and docs, and they're what exposed the prose weakness above.

Honest numbers after all of that: docs went from 0.965 to 0.904, prose from 0.905 to 0.867.

### The spacing artifact

A space before the full stop or comma, as in "the soup was good ." (an invented example), sat on 24 of 1,370 human prose rows (1.75%) and 0 of 956 AI rows (0.00%). Same shape as the blank-line problem above: a format habit that only one label has, so the detector can read spacing where it should be reading voice. Small, but free — any gap is a human vote, and a rewrite can buy one by pressing the space bar.

Reading the 24 rows, most of them are not extraction residue. Nineteen are in the source as typed: writers who space before the stop, an arXiv abstract ending "available at <url> .", a sentence closing on `Thee" .`, a LaTeX `\dots . \]`. Five are upstream preprocessing — AESLC's quoted-printable soft wraps ("leave the house= ,"), its one-sentence-per-line split putting a typed "..." on lines of bare dots, and two RAID rows where a stripped name left "staffed by , scantily clad" and "in the final." on its own line ahead of ", who broke onto".

It was closed anyway, on both labels, because what it teaches is typing and not authorship. `build_set.py` now runs one `close_gaps()` over every assembled row — the rule `detect.py` uses on the docs path, plus `detokenize()`'s clitic case — instead of each fetcher carrying its own copy. `ARTIFACTS` gained the pattern, so the build stops if it ever comes back.

The alarm needed widening too. The check was `min(counts) == 0 and max(counts) >= 5` over every row, prose and docs pooled, and on a near-miss pattern it would have stayed quiet: before the fix the wider `[.,;:!?]` shape read human 53, ai 2, the two AI rows being docs sections that open a paragraph on `: ` — a different artifact. Two rows were enough to make `min` non-zero and wave through a 48-to-0 split in prose. It is now `max(counts) >= 5 and min(counts) < max(counts) / 10`: ten to one either way, with five rows as the floor so a couple of stray hits stay noise. Run over the pre-fix rows it fires on that 53-to-2 split; over the rows as built on 2026-11-13 it leaves all five entries quiet — 0/0, 32/12, 0/0, 0/2, 0/0.

Arming it exposed one of the entries. `spaced markup` was `\* \*`, and the rows it actually reads are cron expressions, C and JSX comments and the `* * *` dividers Enron senders typed — eight human and two AI, on both labels. Under `min == 0` those two AI rows kept it quiet for good; under the ratio it sat thirteen human rows from halting the build with a message asking someone to clean out text that has nothing wrong with it. From there the only two moves are deleting cron lines off the human side — a filter that removes something both labels do is worse than no filter, the trap further down this page — or editing the gate to get past the gate. It now wants a word beside the stars, `\*\s\*(?=\w)|(?<=\w)\*\s\*`, which still reads space-tokenized bold and reads none of those rows: 0 and 0. HC3's human answers were the only source that ever carried the residue, and `HC3_RESIDUE` drops them before they reach the set, so there is nothing left for the entry to catch there either.

| | human | AI |
|---|---|---|
| before | 24 / 1,370 = 0.0175 | 0 / 956 = 0.0000 |
| after | 0 / 1,370 = 0.0000 | 0 / 956 = 0.0000 |

72 rows changed across eight sources, 71 human and 1 AI. The rule runs on both sides and finds almost nothing on the AI side, which is the asymmetry it exists to remove.

What this left:

- **Prose was refit, docs was not.** Cleaning rows adds no unseen source, and `retrain.py` only refits a genre that has one — asked on its own it refused both with "no new data", and nothing was forced. The Wikipedia source landed later the same day and carried prose through a refit, so the shipped prose blend is fitted on the cleaned rows (AUROC 0.9405 → 0.9409, promoted with no `--force`). Docs is not: three of the touched rows are docs rows — one `gh-human`, one `npm-popular`, one Claude sample — and they wait for the next docs source.
- **The scorer still sees the gap.** For plain prose `prepare()` only strips link syntax and `canon()` only collapses whitespace, so pasted human text keeps its spaces while nothing in training carries any. Closing it in `detect.py` moves every prose score, so that is its own change.

Left in on purpose: a line opening on `:`, one on `!`, with text behind it or a blank line in front — 11 human rows and 2 AI on 2026-11-13. That is `doc_prose` dropping a bold label and AESLC breaking after "P.S.", pulling it back welds two sentences, and unlike the spacing habit it sits on both labels.

## Per-register cuts

A probability is not a verdict until something draws a line, and until 2026-11-10 prose had one line for every kind of writing: 0.5. That number means a different thing in each one. It sits at the 59th percentile of the news writers' scores in the training set and the 97th of the literary writers'. So the same detector flagged 42% of genuine news writing and 4% of genuine book prose, and called both "1 human text in 10".

It is not that news is hard. Scored against each other, news rows separate at AUROC 0.938, about the same as email (0.939). The AI news prose really does sit above the human news prose. The boundary was just in the wrong place for it.

`detect.py --register NAME` now compares a text against one kind of writer. Each register's cut is the score a tenth of its own writers land above, its bar the score four fifths land under, and its percentile line is read off its own writers too — the same three numbers the pooled blend always had, counted per register instead. Both come from out-of-fold training scores, so no text sets the cut it is judged by. SKILL.md has the table in use.

Measured the way the gate measures — 20 paired re-splits, the cuts refitted inside each split from that split's training humans, then applied to held-out rows:

| register | cut | human flagged at 0.5 | at its cut | AI caught at 0.5 | at its cut |
|---|---|---|---|---|---|
| news | 0.803 | 0.415 | **0.090** | 0.947 | 0.847 |
| forum | 0.504 | 0.125 | 0.125 | 0.869 | 0.869 |
| email | 0.438 | 0.075 | 0.091 | 0.701 | 0.756 |
| academic | 0.345 | 0.046 | 0.107 | 0.849 | 0.908 |
| encyclopedia | 0.253 | 0.050 | 0.074 | - | - |
| literary | 0.248 | 0.041 | 0.107 | 0.982 | 0.990 |
| every row | | 0.124 | **0.101** | 0.840 | 0.834 |

AUROC is 0.942 either way. The model is untouched: the refit reproduced all 14 of the prose blend's existing keys byte for byte and added one. Only the line moved.

**It costs catches, and I had the direction wrong.** I reported earlier that per-register cuts came free, with AI caught going slightly up. Measured on the finished code it goes slightly **down**, 0.840 to 0.834, for 2.3 points fewer false alarms. The earlier number pooled the AI rows differently and read better than the truth.

**It cuts both ways, by design.** Four registers get a cut *lower* than 0.5, so naming them raises false alarms from 4-5% to about 10% and catches a little more AI. Asking to be judged against literary writers means being held to what literary writers score, in both directions. Any other reading of `--register` would make it mean one thing for news and another for books, which is the problem it exists to fix.

What it does not fix:

- **Six registers it cannot cover.** Reviews, essays, blog posts, cover letters, talk abstracts and social posts are AI-only in this set (reviews since the Yelp rows came out), so there is no human writing to set a cut from. They keep the pooled 0.5, and they are the kinds of text people bring to this skill most often.
- **`news` inherits its corpus.** Its reference is 2004-05 BBC wire copy, and the round above showed that corpus's problem is not its register. A cut of 0.80 and a bar of 0.72 are the loosest pair here, fitted to the hardest corpus; whether they suit a news-style piece written today is untested, and there is no modern human news prose here to test it with.
- **A wrong name is worse than no name.** A real 2004 news story scoring 0.564 reads human under `--register news` (67th percentile of those writers) and AI under `--register literary` (100th).
- **The gate is unchanged.** It measures human flagged and AI caught at 0.5, so it can neither see a per-register cut nor be misled by one — and it still cannot see a single register going bad. That remains open, along with the three gate defects the round above recorded.

Twenty-seven mutations of the cut code, 26 caught by `detect_test.py` and `fit_test.py`. The twenty-seventh deletes the line that writes the cuts into `blend.json`; only the live file shows that, so it is caught at the next refit — when the live-blend test fails — rather than by the suite.

## The docs rebuild

The style-only docs detector looked good because it was tested on data like its training data. It scored AUROC 0.973 and caught 93%. In November 2026 it met real data for the first time and fell apart: on AI-credited GitHub docs it caught 24%, on docs Claude wrote for real projects 48%, and across the new GitHub data its AUROC was 0.736. That's why the scan of the labelled docs disappointed.

Refitting on the new data didn't fix it. Style alone reached 0.805 and flagged 21% of people. Adding the language models reached 0.833 and caught 94% of the labelled sections, and that one was a trap. Those scores drift with the calendar: on guides the top-1 signal's AUROC runs 0.66, 0.54, 0.28, 0.10 from early 2025 to late 2026, crossing chance and moving in all six tools. The gain goes away once the last few months of AI docs are removed, and swapping 6% of a human section's words for unexpected ones triples its false alarms.

What worked was simple: mask every content word and fit a linear model on what's left. Same-repo AUROC against the human original went from 0.82 to 0.99, and a Claude doc outscored its own human twin in 125 of 125 pairs. Style, language models, doc-type cuts and source weights added nothing on top, so they went. The link credit stayed because it can only clear people.

Two agents then tried to break it. They found no leak through characters, markdown handling, project names, dated terms or repo clustering, and no bench bug: seeds nobody had used gave the same numbers, and swapping in sklearn's stopword list for the hand-written one changed nothing. They did find three real problems, now fixed or stated here: a calendar check was contaminated, so a claim that forward splits held was withdrawn; re-splits gave a repo with two sources two chances at the test side, which is now one; and the whole-document table merged a repo's human and AI docs, which now key on the doc.

The worry left over was whether this just reads "written after 2024". Nothing in the training set can answer that, since its human side stops in 2024. So the rebuild went and got docs that can: new docs from mid-2024 on, projects with written no-AI rules, and Homebrew, which asks every PR about AI. Homebrew paragraphs people wrote in 2023-25 stayed at human level (0 of 35 sections flagged), then its maintainers' 2026 docs jumped to about 85% flagged, and when checked, those same authors had disclosed AI use on 104 of their 110 docs PRs, though a disclosure often covers the whole PR rather than the docs. Training on the no-AI projects' docs didn't help unseen ones, so they stay held out.

## Learning from labels

The docs numbers in this section come from the style-only detector, before the rebuild.

The detector can't learn from its own verdicts, or from the skill's rewrites: that would only teach it to agree with itself. It learns from texts the user confirms the author of (`label.py`), through `bench/retrain.py`.

**The first round.** An author confirmed AI helped write all of a set of their docs. Eleven were labelled, giving 38 usable sections. Before those labels, those docs were the first real test of the docs detector on text it hadn't been built around. It caught about half of the held-out sections, against 93% on its training sources. The gap is exactly what labels are for. Averaged over 20 paired splits, on the rows both versions know:

| docs detector | AUROC | human flagged | AI caught | held-out labelled sections right |
|---|---|---|---|---|
| without the labels | 0.972 | 0.096 | 0.927 | 0.50 |
| with the labels | 0.968 | 0.117 | 0.918 | 0.65 |

So labels work, at a price: 15 points more of the labelled kind of docs, for about 2 points more false alarms on old human READMEs. Holding false alarms level doesn't remove the cost: the gain stays about 12 points and AI caught on the older rows drops 2.5. One small AI sample pulls the boundary with nothing on the human side to balance it. The gate kept the existing detector, and the labels stay saved. What would really fix this is human docs written since 2023 by known authors.

**Why the gate uses paired splits.** The first gate compared one fixed test split, and it failed in both directions. It blocked a prose change that won AUROC on 20 of 20 re-splits, and it would have passed this docs change, which loses AUROC on 19 of 20. It now fits both setups on the same 20 splits and decides per genre, so a result in one genre can't block the other. A genre with no new labels stays as it is, because refitting it only moves it around by chance.

**What scanning the labelled docs fixed, without labels.** These needed no ground truth, only a check against the training data:

- A colon ending a paragraph fused it with the next one, affecting 13% of doc sentences.
- Sentences starting with a scoped package name, `.env` or `--flag` didn't split, and nav rows and bold labels counted as sentences.
- Published text the models know by heart scored "ai" at 1.0. The Contributor Covenant did this, and it now reads `known text`.
- A 9-word PR template got a verdict. Under 80 words there's no verdict now.
- Colons, stock openers and "too predictable" were being flagged in docs, where people use them more than models do. Which habits count as flags is now learned per genre and has to hold on held-out text.
- One stray section made long human docs `unclear`.
- A link or a `--` signature made plain text count as markdown.

Refit on the corrected text, docs AUROC went from 0.969 to 0.973 and AI caught from 0.907 to 0.929, with human flagged unchanged at 0.097. Prose moved from 0.948 to 0.950.

**Recent human prose.** Every human source here predated 2023 while the AI side is 2026, and that gap is what set the false-alarm floor. `fetch_hn.py` adds Hacker News comments and Ask HN posts from 2024 on, one per author, from accounts opened before ChatGPT.

The first try took everything from 60 words up, 520 rows, and the gate refused it. Each pair below is its own comparison, so the two "current" lines differ: they are measured against different sets of new rows.

| round | AUROC | human flagged, older sources | AI caught | flagged of the new rows |
|---|---|---|---|---|
| 520 rows, 60 words up — current | 0.943 | 0.124 | 0.841 | 0.140 |
| 520 rows, 60 words up — candidate | 0.936 | **0.149** | 0.839 | 0.097 |
| 260 rows, 100 words up — current | 0.942 | 0.125 | 0.841 | 0.150 |
| 260 rows, 100 words up — candidate | 0.940 | 0.133 | 0.837 | 0.120 |

The cost landed on **one register**, and the first version of this paragraph got that wrong by pooling RAID's three domains together. Fitting with and without the 260 rows and scoring both on identical test rows, over 20 paired re-splits:

| human register | without the new rows | with them | change |
|---|---|---|---|
| raid / **news** | 0.350 | **0.423** | **+0.073** |
| raid / abstracts | 0.051 | 0.048 | -0.003 |
| aeslc / email | 0.083 | 0.075 | -0.008 |
| raid / books | 0.051 | 0.041 | -0.010 |

Nothing but news moved outside row-sampling noise. So the lesson is narrower than "formal prose got worse": **adding easy recent casual prose moved the boundary away from declarative third-person reportage**, and nothing else noticed. Pooling the three RAID domains reported this as 0.226 to 0.235, which understates the hit on news by about three times and spreads it across two registers that did not move.

Sweeping the word floor from 60 to 130 showed why. The cost on older human text fell from +2.5 points to +0.3 while the gain on recent prose stayed at 3-4 points, and the curve is flat from 90 up, so it isn't a cliff. The floor is 100 because `detect.py` gives no verdict under 80 words — a shorter comment teaches this about text it will never judge — and 20 words is margin for the rewrite loop.

What got better: recent forum prose flagged as AI fell 15.0% to 12.0% on held-out rows. What it cost: 0.8 points of false alarms on the older sources, 0.4 of AI caught, and Claude caught went 0.744 to 0.738. Rollback is `retrain.py --rollback 20261110-083125`.

**The JavaScript workhorses.** The curated repo list was React- and TypeScript-shaped, and `find_repos` only ever searched `language:TypeScript`, so lodash, express, jest, webpack and babel could not be found by either route. 94 verified repos were added to the list: the libraries themselves, the separate repos that hold their docs (`expressjs/expressjs.com`, `webpack/webpack.js.org`, `babel/website`, `moment/momentjs.com`, `axios/axios-docs`), the build and test tier, Node web and database work, the utility belt, and the pre-React frontend era back to jQuery and Bootstrap. Each one was checked before being listed: resolve the commit that was head on 2022-11-01, then count the markdown files the fetcher's own filters would accept. That ranged from `ember-learn/guides-source` at 7,324 files to `knockout/knockout` at 1, and it caught two things a bare list would have missed — `lodash/lodash` yields almost nothing because its docs are generated from jsdoc, and `browserify/browserify` yields only a security page because its readme is `README.markdown`, which `doc_type` does not accept.

The fetch took 1,867 docs from 480 repos, none of them already held, every snapshot at or before 2022-10-31. 1,102 are guides. It went to its own file so it would arrive as its own source, `gh-workhorse`, because `is_new` keys on source name and rows appended to `human.jsonl` would have been invisible to the gate; that needed one new flag, `--besides`, to stop a fresh output file re-fetching the 1,395 docs already there.

| docs detector | rows | AUROC | AI caught | human flagged |
|---|---|---|---|---|
| before, on its own test split | 5,358 | 0.976 | 0.844 | 2/965 = 0.002 |
| after, on its own test split | 8,529 | 0.976 | 0.847 | 17/2107 = 0.008 |
| the two on the same rows, 20 paired re-splits | | 0.980 -> 0.981 | 0.863 -> 0.867 | 0.006 -> 0.006 |

Read the paired row, not the first two: the test split nearly doubled and took the harder rows into it, so the two held-out lines are measured on different text. The same shift inflates every baseline in the table — Binoculars alone goes from 0.712 accuracy to 0.843 without changing at all, because the split is now 2,107 human rows against 391 AI ones.

**What it actually bought.** Not the headline number, which held. Every human docs source already in the set reads at or near zero at the 0.5 cut — `gh-human` guides are 0/287. The new source reads 0.012 on 646 guides and 0.019 on 206 readmes. So the old false-alarm figure was partly measuring familiarity rather than difficulty, and there is now human docs prose in the corpus that the detector does not handle trivially. It does nothing for the recency gap: these snapshots are older than the data already there, not newer, and recent human docs by known authors is still the thing that would help most.

**The gate refused it, on 0.0006.** AUROC up, AI caught up, false alarms flat on common rows, and the batch clean by the new check at +0.001 against a 0.03 line — the fifth check's first run on data nobody had seen. The only refusal was the fourth check, `does worse on the new data 0.994 -> 0.993`, which is the one check of the five with no tolerance at all. That difference is reproducible rather than noise: across six disjoint 20-seed blocks it reads -0.0000, -0.0007, -0.0006, -0.0006, -0.0006, -0.0008, sd 0.0003. It is also measured against a detector that never trained on those 3,666 sections, which is the same weak comparison that was rejected outright for the fifth check. Promoted with `--force docs` and the reason in the log; rollback is `retrain.py --rollback 20261111-065040`. Giving the fourth check a tolerance would unblock every future retrain the same way, and would also let real differences under it through, so it was left alone.

**Recent human docs, and why a disclosure rule is not provenance.** The human docs side mostly predates 2023, and docs written since are the gap. A date window cannot fill it, because formal writing since 2023 is where AI help is most common. The route already in the repo is projects with a published AI policy: `policies.json` holds 25, verified from 75 candidates, and they are kept out of training by `KEPT_BACK` because `bench/holdouts.py` is the only honest read on false alarms for recent human docs.

Expanding that list went badly in an instructive way. 24 code-search phrasings taken from the accepted projects' own policy quotes gave 1,961 candidate repos; filtering to alive, non-fork, pushed since 2025, with a ban or must-disclose clause within 400 characters of an AI mention left 703; two verification passes over 439 of those accepted **17**, which fetched 162 docs from 15 repos. `policies-train.json` holds all of it, including the 421 rejections, which are the reusable half. What did the rejecting, in order: docs that are not prose markdown (`.rst`, `.adoc`, Doxygen, LaTeX, or generated reference stubs) — this killed four in ten of the first pass, because a 200-star floor selects for exactly those projects; the project itself shipping an `AGENTS.md`, `CLAUDE.md`, `.cursor/rules` or Copilot instructions, which was nine of sixteen in one second-pass slice and included three projects carrying a genuine hard ban; hedged "review what you submit" policies; search phrases matched in vendored or generated files that were never that project's policy; and no docs activity after the policy landed.

Then the gate refused the batch, and the fifth check named it: `flags gh-policy's own human rows 0.637 against 0.005 on the rest (359 rows)`, alongside AI caught falling 0.865 to 0.832. The detector still flagged 64% of them after training on them, which on docs is the contamination signature rather than the hard-register one. `holdouts.py` says why, and the split is entirely by policy kind:

| docs | docs scored | called AI | sections flagged |
|---|---|---|---|
| new docs Jun 2024 to Jun 2025, date window only | 482 | 0.048 | 0.029 |
| projects that ban AI, 2024-26 | 126 | 0.127 | 0.112 |
| **more projects that ban AI, 2025-26** | 29 | 0.034 | **0.018** |

(Those are the rates the detector gave on the day. Training on 41 AI docs later the same day moved the two
ban lines to 0.069/0.036 and 0.159/0.128 — see the before-and-after table two sections down.)
| projects that require AI disclosure, 2025-26 | 124 | 0.347 | 0.449 |
| **more that require AI disclosure, 2025-26** | 128 | 0.758 | **0.776** |
| Homebrew PRs that disclosed AI, 2026 | 61 | 0.803 | 0.800 |

A ban means the docs are human. A disclosure rule means AI is **permitted** and declared, so the window after it is mostly AI prose: 0.776 against 0.800 for a corpus of self-declared AI pull requests. The batch was 13 disclosure projects to 4, so 133 of its 162 docs were AI and the check caught a corpus this round built itself. Two things follow. The 29 ban-sourced docs are the cleanest recent human docs in the repo at 1.8% flagged, below even the date-window batch, and they corroborate the 11.2% ban figure from the other direction rather than contradicting it. And the existing holdout's disclosure line, 0.449, has never been a human false-alarm rate either — it is a mixture, and the number to quote for recent human docs is the ban line.

Nothing was promoted and `blend.json` is untouched. `policy-train.jsonl` joined the held-back side next to `policy.jsonl`, with `holdouts.py` reporting both halves, which is where its value actually is. The ban subset is far too small to train on — 29 docs is also below the gate's own 250-row floor, so the gate could not have judged it either way.

**What this route cannot give.** Strong-provenance recent human docs are genuinely scarce, and the limit is structural rather than a matter of searching harder: projects big enough to have real prose docs mostly do not write them in markdown, and projects that ban AI in contributions frequently run on agents themselves. At a 4% acceptance rate another thousand candidates buys single-digit repos. The one unexplored lead was per-PR provenance: a disclosure project labels AI use per pull request, so reading each docs PR's disclosure would separate the two sides. The next section does it. The guess here, from hand-checking `agones-dev/agones`, was that roughly a quarter of a disclosure project's docs would turn out human; across 21 projects it is 1 doc in 42, because the rule that makes a pull request's label mean anything for a file — that the pull request wrote nearly all of it — throws away two thirds of the candidates on both sides.

## Reading the pull request instead of the window

The lead from the previous section, done. `bench/provenance.py` reads a merged pull request's own evidence
and returns `ai`, `human` or `unknown`, and `fetch_github_docs.py pr` walks the merged pull requests of a
project with a published disclosure policy and keeps the docs they wrote. A label only counts for a file
the pull request wrote nearly all of, the same rule the `ai` side has always used, because a declaration
covers the whole branch and an edit to an existing page carries someone else's words.

**What a declaration looks like.** Three kinds, and only the first is structured. A trailer or a tool's own
account: `Co-Authored-By: Claude Opus 5.5`, `Assisted-by: kiro:Fable5.1`, `GenAI: Claude Code
claude-opus-5-5-20261107`, `Co-authored-by: Copilot <copilot@github.com>`, or a pull request opened by
`devin-ai-integration[bot]`. A checkbox: trickster's `[x] This contribution DOES include AI-generated
changes`, eslint's `[x] I did _not_ use AI to generate this PR`, Cantera's three-way statement, agones
answering its own question `Did you use AI tools in preparing this PR?` with one letter. Or free text in an
`### AI usage` section, from `None` to `Claude Opus 5.5 was used to generate the initial draft, but it was
too verbose`. Silence is `unknown`, never `human`: under a rule that requires declaring, a quiet pull
request is as likely to be someone ignoring the rule.

**The blind check, which changed the result.** The patterns were written against six projects and then run
against 21. Eight agents read 363 pull requests from the other 15, cold, applying the same written rule to
the same evidence with no sight of the classifier's answers. It agreed on **292 of 363**. Split by the
channel that decided each verdict, the diagnosis was not subtle:

| channel | agreement, before the fixes |
|---|---|
| a trailer or a tool's account | 34/34 |
| the description | 52/90 |

Six defects, each a class rather than a quirk. `[x] I did _not_ use AI` read as **AI**, because `_` is a word
character and markdown emphasis hid the negation from `\bnot\b` — 16 eslint pull requests, in the worst
direction. A checked box admitting AI read as **human**, because the author had pasted their prompt into it
and the prompt contained "doesn't", and the negation test scanned the whole paragraph instead of the claim.
`Confirm you have read our AI policy` counted as a declaration, which is why maplibre appeared to declare
161 AI pull requests: agreeing to a rule says nothing about what went into the work. `If AI tools were
used: I have disclosed the tool below` — a box conditional on the very thing being asked. verus asks for
`Assisted-by:` in the description rather than the commit, wrapped in backticks, and only commits were being
read. And a model's version number broke a sentence matcher, because `used Claude Opus 5.5 to help` has a
full stop in it.

After the fixes, **359 of 363**. Every verdict it issues now matches: 42 of 42 from a trailer, 97 of 97
from a description. All four remaining disagreements are pull requests it calls undeclared and the reader
calls AI, so it under-claims rather than mislabels, and the `ai`/`human` confusion cells are empty. Read
that number for what it is — the patterns were fixed against these same projects, so an unseen template
will do worse. Every defect has a test and all 13 mutants are caught.

**What it collected.** 4,779 merged pull requests across the 21 projects: **1,455 declared AI, 491 declared
no AI, 2,833 declared nothing**. 599 of the declarations came from a trailer and 1,362 from a description.
From those, 1,907 candidate docs, and **42 kept**: 41 AI, 1 human, 9 projects, 63,460 words. The drop
reasons are the finding:

| why a candidate doc was dropped | docs |
|---|---|
| the pull request only edited it, it did not write it | 1,250 |
| not prose a person reads | 347 |
| a held-back source already has the text | 268 |
| **kept** | **42** |

Two thirds of the candidates fail the whole-file rule. Declaring is now common — two in five of these pull
requests declare something — but writing a whole documentation page in one pull request is not, and the
rule that makes a branch-level label mean anything for a file is the same rule that empties the set. The
41 that survive are concentrated: 24 come from two repositories, and 20 of those from two people.

**Each project against its own earlier docs.** A flag rate on one project's docs means nothing on its own:
across these nine, the rate on docs written before the policy existed runs from 0.000 to 0.417. So every
project is paired with a snapshot of its own docs from the day its policy took effect, 168 docs in
`pr-control.jsonl`, fetched by the same path rules.

| docs | docs scored | called AI | sections flagged |
|---|---|---|---|
| trickster: its own docs that day | 14 | 0.000 | 0.000 |
| trickster: pull requests that declared AI | 15 | **0.933** | 0.984 |
| open-logic: its own docs that day | 14 | 0.000 | 0.000 |
| open-logic: pull requests that declared AI | 9 | **0.444** | 0.381 |
| threat-dragon: its own docs that day | 4 | 0.000 | 0.000 |
| threat-dragon: pull requests that declared AI | 6 | **0.333** | 0.143 |
| CheatSheetSeries: its own docs that day | 20 | 0.100 | 0.059 |
| CheatSheetSeries: pull requests that declared AI | 4 | **1.000** | 1.000 |
| wagtail: its own docs that day | 14 | 0.071 | 0.067 |
| wagtail: pull requests that declared AI | 4 | **0.250** | 0.286 |

Five projects with four or more labelled docs, five in the same direction. It is not length: matched to
500-2500 words on both sides the gap holds, trickster 0.000 on 28 sections against 1.000 on 25. It is not
the house style, which is what the control is for. One file shows it on its own — trickster's
`docs/per-query-instructions.md` scores 0.016 in a 2022 snapshot and 0.998 after a declared-AI
pull request rewrote it.

Pooled, the detector calls 0.634 of these recent declared-AI docs AI. That is well under the 0.800 it gets
on Homebrew's self-declared AI pull requests, and the per-project spread, 0.25 to 1.00 against baselines
near zero, says it reads one kind of AI documentation much better than another. Those are the first
controlled numbers in this repo for recent AI docs; the Homebrew line is pull request descriptions.

**A label of mine was wrong, and the detector was right.** The first run of this fetch produced three docs
from `OWASP/CheatSheetSeries` whose pull requests it read as "no AI", and all three flagged at 1.000
against that project's own 0.100. That looked like a false declaration and it was written up as one. It was
not. The fixed classifier reads both pull requests as declaring AI, and the description of one of them says
so at length: "GPT-6 Astra for necessity/scope, GPT-6.1 Sol for correctness/regressions, then
`gpt-daybreak-blue-latest` for security through Codex CLI 0.160.0". The docs flag because they are AI. The
claim that an explicit per-pull-request denial cannot be trusted rested on a bug here and is withdrawn.

**The second detector cannot referee this.** RoBERTa reads those docs at 0.131, 0.287 and 0.376, under its
own cut, which looked exculpatory until it was given a baseline: on the 20 known-human OWASP cheat sheets
it flags **15**, median 0.956. On that register it carries no information at all. The "about 1 in 6 human texts" SKILL.md
carried at the time was a pooled figure, and this is what one register can do to it. The genre turned out to
be worse than the register: see "The second opinion is not a gate on docs" below.

**Then trained on, which spends the measurement.** Everything above is the reading *before* any of these
docs trained, and it is recorded here because it cannot be taken again: the 41 AI docs went into the set on
2026-11-11 by my choice, against this paragraph's first draft, which recommended keeping them
as the only controlled read on recent AI docs rather than a 14% top-up to an AI side that already
has 294. What survives as a holdout is the other half — the 168 control docs in `pr-control.jsonl` never
train, and `holdouts.py` reports them per project, which is the only form in which that number is readable.
The human side is one doc, agones answering its own AI question with `N`, and it stays out of the set: it
flags at 1.000 against that project's 0.071, and one document is not a label either way.

**What training on them bought.** The 41 docs entered the set as 124 AI sections, 1% of 12,499 rows, and the
gate promoted the candidate: AUROC 0.982 to 0.981, false alarms on human text 0.006 to 0.007, AI caught
0.862 to 0.864, and recall on the new rows themselves 0.695 to 0.703. Eight tenths of a point on data it
trained on is the number to look at — the blend is an n-gram voice score and a link credit, and 124 rows
cannot move it far. The split explains the rest: a repo stays on one side, so trickster's 62 rows went to
train, and trickster is the project the detector already read at 0.933. The held-out side of this source is
12 rows.

`holdouts.py` before and after, in documents rather than rates, because the samples are small:

| held-out docs | n | called AI before | after |
|---|---|---|---|
| new docs, Jun 2024 to Jun 2025 | 482 | 23 | 22 |
| projects that ban AI, 2024-26 | 126 | 16 | **20** |
| more projects that ban AI, 2025-26 | 29 | 1 | **2** |
| disclosure projects' own docs, policy day | 120 | 12 | **13** |
| projects that require AI disclosure, 2025-26 | 124 | 43 | 48 |
| more that require AI disclosure, 2025-26 | 128 | 97 | 104 |
| Homebrew PRs that disclosed AI, 2026 | 61 | 49 | 49 |

Five more false alarms across 757 held-out human docs, and the direction is the same on all three
human-provenance lines. Against that, twelve more docs caught in the two disclosure mixtures, which are
roughly four-fifths AI, and **nothing** on Homebrew's self-declared AI pull requests: 49 of 61, unchanged.
So the trade is close to a wash — a handful of documents each way, which is what a 1% addition to the set
should do.

The part worth keeping is the shape of the miss. The gate's own false-alarm figure moved 0.1 of a point
while the ban lines moved three points, because that figure is pooled over thousands of pre-2023 docs and
126 recent ones cannot shift it. That is the blind spot recorded in "Limits, plainly", and this is the
first time a promotion has been measured against it from both sides. Rollback is
`retrain.py --rollback 20261111-112023`.

**Still open.** The classifier's recall is the weak end: 2,833 of 4,779 pull requests declare nothing, and
in a project whose rule requires declaring, some of that is non-compliance rather than hand-written work,
which no amount of reading the pull request will separate. The whole-file rule cannot be loosened without
losing the label, so this route cannot be scaled by finding more projects; it is bounded by how often
anyone writes a whole page at once. And `hister` and `earthaccess` flag their own pre-policy docs at 0.417
and 0.214, far above the other seven, which is a false-alarm pocket this report does not explain.

## The contamination check

The gate's fifth check. A new source whose own human rows flag more than 3 points above the rate on everything else is refused, per source, once that source has 250 human rows long enough to score.

**The hole it closes.** Across 99 points of a contamination sweep, the fourth check — "does worse on the new data" — fired exactly zero times. It cannot fire on a human-labelled batch: with no AI rows in it the check reduces to `1 - new_human_flagged`, and the candidate trained on those very rows, so the candidate always wins. Meanwhile the pooled false-alarm number gets *better* as contamination rises, 0.1073 clean to 0.0901 at 30%, because the mislabelled rows drag the boundary towards them. Recall on never-trained Claude formal prose falls 0.640 to 0.599 at 10% and 0.546 at 30%. Every headline number improves while the detector gets worse at the only thing it is for.

**What a clean batch looks like.** Replaying each human source as if it were the new batch, candidate setup, excess over the pooled rate:

| genre | source | scorable humans | own rate | pooled | excess |
|---|---|---|---|---|---|
| prose | wikipedia | 92 | 0.050 | 0.130 | -0.080 |
| prose | aeslc | 227 | 0.075 | 0.134 | -0.059 |
| prose | hn | 260 | 0.122 | 0.124 | -0.002 |
| prose | hc3 | 103 | 0.134 | 0.123 | +0.011 |
| prose | **raid** | 360 | **0.171** | 0.105 | **+0.066** |
| docs | gh-human | 2311 | 0.004 | 0.007 | -0.004 |
| docs | gh-2023 | 1098 | 0.006 | 0.005 | +0.001 |
| docs | npm | 471 | 0.011 | 0.004 | +0.007 |
| docs | npm-popular | 179 | 0.003 | 0.005 | -0.003 |

Every clean batch sits within +0.011. raid sticks out at +0.066 because its news third is flagged 42% of the time at the 0.5 cut — the defect that took eight days to find, and which a check like this would have put in front of someone on day one.

**Where the line goes.** Injecting held-out Claude formal rows into a clean host batch, relabelled human, mean of three draws:

| contamination | hn host (260) | aeslc host (300) |
|---|---|---|
| 0% | -0.009 | -0.029 |
| 3% | +0.003 | -0.011 |
| 5% | +0.019 | -0.001 |
| 7% | +0.031 | +0.021 |
| 10% | +0.052 | +0.049 |
| 20% | +0.094 | +0.111 |

So 0.03 catches 7-10% mislabelled text in a 300-row prose batch. On docs it catches about 1%: clean docs batches sit within ±0.007 and 10% contamination lands at +0.097, a tenfold margin, because the docs detector keeps flagging the mislabelled rows (0.84-0.93) even after training on them while the prose detector absorbs them (0.45-0.67). No threshold in 0.00 to 0.08 blocks anything in the recorded history. 0.00 and 0.01 false-alarm on hc3; raid passes at 0.08; 0.02 has no noise margin. 0.03 is the only value that clears history, catches raid, and keeps a margin.

**Three forms that do not work.** Measuring against the current detector on the same rows is structurally dead: the candidate's rate came in *below* the current's on 6 of 6 clean replays and 15 of 15 contaminated runs, because the candidate trains on those rows, and the current detector's rate measures how new the register is rather than how clean it is. That form would also have refused the real Hacker News promotion. A fixed ceiling of 0.25 never fires anywhere. Twice the pooled rate refuses the clean npm batch on docs (0.011 against 2 x 0.0045) and misses 19% contamination on prose, where twice pooled is 0.248.

**Why per source, not pooled.** On 2026-11-03 the docs genre was promoted with four new sources at once. Contaminating gh-2023 at 5%, the pooled number reads +0.010 and passes while gh-2023's own rate reads +0.036 and fires. Pooling diluted a real signal by more than three times, because the clean source was twice the size. That is the same averaging fault the check exists to fix, one level up.

**Why 250 rows, counted that way.** Seed choice barely matters: across five disjoint 20-seed blocks a clean source's excess moves by 0.009-0.031 (sd 0.004-0.011). Which *rows* are in the batch matters a great deal: resampling them gives an sd of 0.025-0.033, three to six times larger. Pooling 625 clean prose measurements by size, the false-trip rate at +0.03 is 1% at 250 rows and up, 6% at 200-249, 21% at 150-199, and 23-42% below that. Small clean batches drift upward for a mechanical reason — the candidate trains on the batch, and a big batch buys itself a large discount on its own flag rate while a 20-row batch buys almost none. The floor counts rows long enough to score, not rows in the pool, because that is the denominator the noise comes from: aeslc is 227 scorable of 300, hc3 103 of 150. Counting pool rows would judge an aeslc-shaped batch on 195 rows while reading 250.

**Four things it does not catch.**

- **It cannot tell a mislabelled batch from a register the detector reads badly.** raid, which is clean, is the most contaminated-looking batch in the whole set on every statistic tried: excess +0.066 (above 10% contamination), Claude-formal recall -0.117 (above 19%), high-confidence tail excess +0.041 (above 15%). So the check refuses both and leaves the call to a person. For a single bad register the right answer is a register cut, not `--force` — and there is a trap in that: news has its own 0.815 cut only because raid's 120 news rows are in the training pool, so refusing a raid-like batch also refuses the rows that would produce the cut that fixes it.
- **It is blind to default-voice contamination.** Mislabelled rows made of Claude's plain default prose, which the prose detector catches only 59% of the time, land at about +0.009 and fire nothing.
- **It reads one rate per source.** raid's own registers are news 0.465, literary 0.100, academic 0.031, and raid as one source reads 0.217 — a 2.1x dilution inside a single source. Keying on source and register would fix it and is not done here.
- **Hand-labelled rows are never judged.** `is_new` keys feedback on the label group but the rate keys on the source name, which is the literal string `feedback` for all of them. At 11 rows in a week that bucket will never reach 250, so the channel where a mislabel is most likely is exempt.

**And one thing it makes slightly worse.** A contaminated batch that does get through becomes "old" next run and lifts the pooled rate for every later check. For a gh-2023-shaped batch that is about 1102/4073 x 0.048 = +0.013, which is 43% of the whole 0.03 margin. One miss makes the next one easier.

**Testing.** The four older checks moved out of `main()` into `reasons_to_keep(cur, cand)`, and the per-genre decision into `decide(report_g)`, which is what makes any of this testable; `bench/retrain_test.py` holds 27 tests. Two bugs in the first version were found by mutation testing and by an independent read, and both were real: a source with no scorable human row vanished from the report entirely rather than being named as thin, which is a silent pass on a 100%-flagged batch, and the row floor counted pool rows against a rate measured on scorable ones. Of 19 mutations of the fixed code, 18 are caught; the one survivor drops `sorted()` from the per-source dict, which changes the order reasons print in and nothing the gate decides.

**Still open.** The pre-existing fourth check has no tolerance, so it emits reasons like `does worse on the new data 0.908 -> 0.908` on a drop of 0.0004. The gate still measures everything at 0.5 and still cannot see a single register going bad. And a refusal is genre-wide: there is no way to drop one source, so firing on gh-2023 would also hold back gh-human in the same run.

## The holdout check

The gate's sixth check, and the only one read on text that is not in the dataset at all. For `docs`, a
candidate is refused if it calls more than a point more of the held-out human docs AI.

**The hole it closes.** The second check — false alarms on human text — is pooled over the whole test
split, which is thousands of pre-2023 docs. A few hundred recent ones cannot move it however badly they
go. Scoring the saved blends against the same 275 held-out docs shows what that cost:

| blend | what it was | called AI | change |
|---|---|---|---|
| 20261110-064622 | five versions, through the Wikipedia and HN work | 0.091 | |
| 20261110-083125 | | 0.091 | +0.000 |
| 20261110-171814 | | 0.091 | +0.000 |
| 20261110-185147 | | 0.091 | +0.000 |
| 20261111-065040 | before the workhorse batch | 0.091 | +0.000 |
| 20261111-112023 | after the workhorse batch | **0.105** | **+0.015** |
| current | after the 41 declared-AI docs | **0.127** | **+0.022** |

Five promotions in a row left it untouched to three decimal places, then two moved it. 25 docs of 275
became 35, a 40% rise, across two promotions the gate reported as leaving false alarms flat at 0.006 and
0.007. `bench/score_blend_versions.py` prints that table from the saved versions, so a regression can be
traced to the promotion that caused it. The second one passed all five checks. The first was forced past check 4 and nothing mentioned this
at all. Note which batch did the first half of the damage: 3,666 sections of pre-ChatGPT human JavaScript
docs. More human data raised false alarms on held-out human docs, because the registers differ — the ban
projects are Rust, Python and C#, and the workhorse batch is not.

**What it reads.** `bench/holdouts.py` now exposes `human_holdout()` and `rates()`, and `retrain.py`
imports them, so the check and the table are one measurement rather than two that drift. The set is the
strongest human provenance in the repo that never trains: docs a project gained after it banned AI
contributions, and the docs a disclosure project already had on the day its policy took effect. The
date-window batch is deliberately left out — a window is not provenance, so a rise there could as easily
be AI being caught, and this set has to mean false alarms and nothing else.

It scores the blend that would actually ship rather than the 20 re-splits, so there is no seed noise and a
refusal can be reproduced by hand with `holdouts.py`. That is also why the tolerance is not a noise floor:
fitting is deterministic, 0.01 is about three documents of 275, and five consecutive promotions moved it 0.000.
Under 100 held-out docs the rate turns on single documents, so it says so and does not judge.

**Rolled back on the strength of it.** With the check in place the number it reads was the argument for
undoing both promotions, and `retrain.py --rollback 20261111-065040` did that. What the rollback traded,
in documents:

| held-out docs | n | after both promotions | rolled back |
|---|---|---|---|
| projects that ban AI, 2024-26 | 126 | 20 | **15** |
| more projects that ban AI, 2025-26 | 29 | 2 | **1** |
| disclosure projects' own docs, policy day | 120 | 13 | **9** |
| new docs, Jun 2024 to Jun 2025 | 482 | 22 | 21 |
| Homebrew PRs that disclosed AI, 2026 | 61 | 49 | **47** |

Ten fewer false alarms across the 275 strong-provenance human docs, for two fewer catches on the 61
self-declared AI pull requests. The two disclosure mixtures also fall, 152 docs to 140, and that number
cannot be read either way because they are roughly four-fifths AI.

The state this leaves is stable rather than merely reverted: `workhorse.jsonl` and `pr-docs.jsonl` are
still in the dataset, so the next run sees both as new, refits a candidate with them, and the sixth check
refuses it at 0.091 against 0.127. Promoting them again takes a `--force` and a note, which is where that
decision belongs. `words.txt` is deliberately not rolled back — `build_set.py` writes it from the dataset
rather than the fit, and nothing in the docs voice path reads it.

**Checked against the three transitions it was built from.** A neutral refit promotes, the workhorse batch
is refused at 0.091 to 0.105, and the 41 declared-AI docs are refused at 0.105 to 0.127. Both refusals
carry the numbers, and `--force` with a note still takes them, which is the intent: the trade between
catching more AI and flagging more recent human docs is a judgement, and the gate's job is to put it in
front of someone rather than make it quietly. Docs only, for two reasons — prose has no set that never
trains, and the prose blend carries no ngram table, so the scorer would raise on it.

**Still open.** The check compares two numbers on one set, so it cannot say *which* register went worse;
the per-project table in `holdouts.py` has to be read for that, and it is where `hister` at 0.417 and
`earthaccess` at 0.214 came from. And it only guards `docs`.

## Rewrite loop

Eight Claude drafts (the `evals/` folder): a talk abstract, two social posts, a Reddit answer, an email, a cover letter, an op-ed and a paper abstract. Each was rewritten by an agent using the skill and by an agent with no tools ("baseline"). These runs used the eval prompts as they stood then; on 2026-11-15 the prompts that asked to get past a detector or an institution's AI check were reworded to ask for writing that sounds like a person. One run per case per iteration, so single cases swing a lot; read the totals.

These rounds ran against the prose blend as it was on 2-3 November. The refit since then (default-style data, the first-person fix, bounded tell weights) moved the prose "human" bar from 0.164 to 0.300, so the pass counts below aren't exact for the current blend. The judge comparisons don't depend on the blend.

Blend verdict "human" on the final text:

| iteration | what changed | with skill | baseline |
|---|---|---|---|
| 1 | first version (old blend) | 7/8 | 2/8 |
| 2 | contraction and slang counts dropped from the blend | 6/8 | 2/8 |
| 3 | guide: the model's own "human" fingerprint | 5/8 | 2/8 |
| 4 | reader-first rounds, editor pass, layout as a reader decision | 5/8 | 2/8 |
| 5 | facts list first, then a fresh write instead of an edit (two runs per case) | 10/16 | 3/16 |
| 6 | keep lists the reader uses; genre-normal casual markers allowed (two runs per case) | 8/16 | 4/16 |
| 7 | voice isn't a fact; eval phrases removed from the guide (two runs per case) | 8/16 | 4/16 |

Iterations 2-7 use the current blend: 42/72 (58%) with the skill against 17/72 (24%) for the baseline. The mean blend score after rewriting was 0.22 with the skill in round 5 and about 0.32 in rounds 6 and 7, against about 0.5-0.6 for the baseline.

The held-out RoBERTa detector, kept out of the loop, read nearly every final as human in both configurations. It's too easy to fool on rewritten Claude text to tell the two apart, so it isn't evidence either way.

### Do people think it reads better?

The loop optimises against detectors, and that can make writing worse. So in iterations 3 and 4, three blind judges per case read the draft and the two finals, unlabelled and in alternating order, and picked a winner. The judges were Claude models. They can't reliably spot AI text either, so treat their believability scores as an editor's opinion, not ground truth.

| | iteration 3 | iteration 4 | iteration 5 | iteration 6 | iteration 7 |
|---|---|---|---|---|---|
| judge votes, skill vs baseline | 3 vs 21 | 9 vs 15 | 12 vs 36 | 19 vs 29 | 22 vs 26 |
| pairs won by majority (rounds with 2 runs) | - | - | 3/16 | 7/16 | 7/16 |
| believability (1-10), skill vs baseline | 6.4 vs 7.9 | 6.8 vs 7.7 | 7.1 vs 7.9 | 7.2 vs 7.9 | 7.2 vs 7.8 |
| writing | 6.9 vs 8.2 | 7.3 vs 7.9 | 7.1 vs 8.1 | 7.4 vs 8.2 | 7.2 vs 8.1 |
| genre fit | - | 7.6 vs 8.3 | 7.5 vs 8.4 | 7.8 vs 8.3 | 7.7 vs 8.4 |
| faithfulness | 8.8 vs 7.4 | 8.8 vs 7.0 | 8.8 vs 7.1 | 8.9 vs 7.2 | 8.8 vs 6.9 |

Iteration 3's judges named the problem: score-chasing rewrites read "like a synonym-swap pass", and kept bold headers and three-bullet lists that detectors ignore but people notice. Iteration 4 made round 1 reader-first and added an editor pass, and the vote gap closed by half. Iteration 5 had round 1 write fresh from a facts list. That fixed the op-ed (judges now prefer the skill's version 4 times in 6, and its score dropped from 0.89 to about 0.5) and lowered the average score further. The overall vote share didn't move beyond noise.

Iteration 6 fixed the two misapplications found in iteration 5. Lists the reader scans or acts on stay lists, and casual markers a genre normally uses ("imo" on Reddit) are allowed. Judge votes rose to 19 in 48 and every quality score moved closer to the baseline. Detection slipped from 10/16 passes to 8/16, mostly on the email, so this is a trade between readability and score.

Iteration 7 said plainly that a turn of phrase isn't a fact, and stopped kept lists being rebuilt into matching lines. It also fixed a flaw in the benchmark itself. Rounds 5 and 6 had example phrases in the guide that were lifted from the eval drafts ("a fair price for peace of mind", "What draws me to", "The first half covers"). They were there as things to avoid, but the agent could see the exact strings it was graded on. In round 7 all of them were swapped for equivalents from outside the test set, and no 4-word phrase in the skill text now appears in any draft. Judge votes still rose, to 22 in 48, so rounds 5 and 6 weren't mainly flattered by it. Pairs won by majority held at 7 of 16, the same as round 6, which says guide wording has reached the noise floor of this benchmark.

The installed skill is the iteration 7 version. Earlier texts are kept in `~/.cache/humanize/workspace/skill-snapshot-4`, `-5` and `-6`. Iteration 5 had the best detector numbers (10/16, mean 0.22) and the lowest judge share (12/48).

So, plainly: people (or at least Claude judges) still prefer an unconstrained rewrite slightly more often than not, about 26 votes in 48 against 22 after iteration 7. Three things sit behind that.

- **The skill won't invent.** Baseline rewrites add small vivid details ("about ten seconds", "a phone that buzzes every few minutes"). They read as human, and they're made up. The skill never does this, which is why it wins on faithfulness every round.
- **Fluency and detectability pull against each other.** Smooth, predictable prose is what judges find natural and what the detector reads as AI. The baselines the judges preferred score 0.61 on average, so most would likely be flagged by a real detector too.
- **Readability and the score still trade against each other.** In iteration 7 the LinkedIn post won all 6 judge votes and was flagged by both detectors (blend 0.88-0.90, RoBERTa 0.60-0.89). Rounds that made the writing warmer cost detector passes, and the round with the most passes had the least-liked writing.

More rounds of guide tweaks are unlikely to show up in an eight-case benchmark. The next real step is outside it: a few people who don't know which version is which, or other detectors, such as GPTZero, run on texts whose author is known, to see where they disagree with this one.

Judges are Claude models, so treat all of this as an editor's opinion. The only real test of "does it read as human" is a person who doesn't know which is which.

## Rewrite loop on technical docs

Four Claude-written docs the detector never trained on (two READMEs, a getting-started guide and an API reference page), each rewritten twice with the skill and twice without it, in two rounds. A seventh check requires every code block to come back unchanged, and docs have to land within 0.85-1.15x the draft's length rather than the 0.7-1.3x prose gets.

| | round 1, skill | round 2, skill | plain rewrite (both rounds) |
|---|---|---|---|
| docs detector verdict "human" | 7/8 | 7/8 | 0/16 |
| code blocks unchanged | 8/8 | 8/8 | 15/16 |
| all checks passed | 48/56 | 55/56 | 78/112 |
| prose length vs draft (mean) | 1.20x | 1.06x | 1.14x |
| inside the 0.85-1.15x length bound | 1/8 | 8/8 | 10/16 |
| blind judge votes for the skill | 7 of 24 | 8 of 24 | - |
| faithfulness (1-10), skill vs plain | 8.8 vs 8.6 | 9.3 vs 8.3 | |
| genre fit | 8.0 vs 8.5 | 8.4 vs 8.4 | |
| writing | 7.4 vs 8.3 | 7.5 vs 8.2 | |

Those pass counts are re-graded. Until 2026-11-13 `bench/grade_evals.py` held every case to the prose length bound, so seven of the eight round 1 runs were scored as passing a length check they had failed, and three plain rewrites with them. The grader now reads the case's genre and applies 0.85-1.15x to docs, which takes round 1 from 55/56 to 48/56 and the plain rewrites from 81/112 to 78/112. Round 2's skill runs don't move, so what fixed the padding was the rule in the skill, not the grader.

In round 1 the skill passed the docs detector by getting wordier: longer sentences, explanatory asides, and colons before code blocks turned into full sentences. Judges preferred light two-line edits. Round 2 told the loop to keep terse docs terse, required docs to stay within 0.85-1.15x the original length, and said to hand over an honest "unclear" rather than pad. The padding went away (1.20x down to 1.06x), detection held (mean score 0.17), faithfulness went up, and genre fit drew level. The pytest README went from 1 judge vote in 6 to 5 in 6.

What's left comes from the detector rather than the guide. In the two docs that still lose every vote, judges point at repeated nouns ("the middleware", "the request ID" over and over) and chains of "so" and "because". Those are exactly the moves that lower the docs blend's vocabulary-variety and short-sentence signals, its learned picture of a 2012-2022 README. The plain rewrites win on second-person warmth ("Give yourself about ten minutes"), and sometimes by adding small claims the draft never made, which the skill won't do.

So for docs, a pass means the detector reads it as human, and the text stays faithful and about as long as before. It doesn't mean a reader will prefer it over a light edit. Closing that gap needs human docs written recently (2023 onward, with known authors) to train on. Better wording in the guide won't do it. These results are from the style-only detector.

### Rewriting against the function-word detector

The same four docs, run to the bar against the new detector. Every version below passed all 7 checks on all 4 docs, bar test 2's small edits, which stayed at 6/7 because all 4 still scored `ai`. Three blind readers (a user, a maintainer and an editor) ranked three versions of each doc, so each test has 12 votes:

| test | versions | picked best | picked worst |
|---|---|---|---|
| 1 | draft / round 1 / passing final | 12 / 0 / 0 | 0 / 9 / 3 |
| 2 | draft / test 1's final / small edits to the draft | 12 / 0 / 0 | 0 / 2 / 10 |
| 3 | draft / test 1's final / the loop as it stands now | 12 / 0 / 0 | 0 / 6 / 6 |

The draft won every vote in every test. The detector's human side is future tense and passives, and its AI side is the plain present tense a good doc uses, so a doc can't move toward one without moving away from the other. A light edit that stopped at what a reader would notice left 3 of the 4 docs unchanged and all 4 still scoring `ai`.

I chose to reach the bar anyway, so docs always run the full loop. Test 2 tried doing that with small edits, on the theory that splitting comma joins would hurt less than "will" and passives. It hurt more: readers called the result choppy and machine-written. So round 1 stays a fresh write, and the guide warns against chopping. Test 3 ties test 1's approach, and in 8 of its 12 votes the reader would ship two of the three versions. Passing still costs some readability. Tell the user that when you hand a doc over.

These were Claude readers on Claude-written drafts, on 4 docs. Treat it as a direction, not a measurement.

## Rerun everything

From `~/.cache/humanize` with `PY=~/.cache/humanize/venv/bin/python` and `B=~/humanize-ai/bench`, where `~/humanize-ai` is a clone of this repo:

```bash
$PY $B/fetch_raid.py data/raid.jsonl 120
$PY $B/fetch_hn.py data/hn.jsonl --comments 180 --posts 80
$PY $B/fetch_wikipedia.py data/wikipedia.jsonl --rows 300
$PY $B/fetch_npm_docs.py data/npm-docs.jsonl 400 lower
$PY $B/fetch_npm_docs.py data/npm-docs-popular.jsonl 160 upper
$PY $B/fetch_github_docs.py human $PWD/data/github/human.jsonl
$PY $B/fetch_github_docs.py human $PWD/data/github/workhorse.jsonl --besides $PWD/data/github/human.jsonl
$PY $B/fetch_github_docs.py ai $PWD/data/github/ai.jsonl
$PY $B/fetch_github_docs.py recent $PWD/data/github/recent.jsonl data/github/recent-windows.txt
$PY $B/fetch_github_docs.py recent $PWD/data/github/policy.jsonl data/github/policy-windows.txt
$PY $B/fetch_github_docs.py recent $PWD/data/github/policy-train.jsonl data/github/policy-train-windows.txt
$PY $B/fetch_github_docs.py pr $PWD/data/github/pr-docs.jsonl data/github/pr-projects.txt
$PY $B/fetch_control_docs.py
$PY $B/paired_docs.py briefs data 9 14
$PY $B/paired_docs.py import data WORKFLOW_OUTPUT.json
$PY $B/retrain.py
```

`retrain.py` is the last line because it is the only path that gates a fit: it runs `build_set.py`, the
`--batch` scoring and `fit.py` itself, then puts the result through the six checks and archives whatever it
replaces. `fit.py` run by hand needs both output paths and will say so; it will not write the live `blend.json`.

Four of those fetches were missing from this list until 2026-11-14, and what they feed is not marginal.
`workhorse.jsonl` alone is 3,666 of the 10,081 docs rows, so a rebuild without it loses a third of the docs
pool. `policy-train.jsonl`, `pr-docs.jsonl` and `pr-control.jsonl` are 149 of the 275 held-out docs the
gate's sixth check reads, and with only `policy.jsonl` present that check scores the *same* blend at 0.119
instead of 0.091 while still clearing `MIN_HOLDOUT_DOCS`, so it keeps running and says nothing. Seven inputs
have no fetcher and don't ship, all assembled by hand in `data/github/`: the window lists `recent-windows.txt`,
`policy-windows.txt` and `policy-train-windows.txt`, `pr-projects.txt`, the policy lists `policies.json` and
`policies-train.json`, and `homebrew-disclosed.jsonl`. So away from the maintainer's machine the recipe stops at
the first `recent` fetch. The Claude-written `claude-*.jsonl` and `default-*.jsonl` samples were generated once and aren't in it either.
`holdouts.py` stops with a message when its core files are missing, and leaves the Homebrew row out when only
that one is absent.

`fit.py` writes the per-register cuts as part of the prose blend, so a plain refit picks them up. A rollback to a blend from before 2026-11-10 drops them, and `tests/detect_test.py` fails until a refit puts them back — `--register` would otherwise be accepted and quietly do nothing.

The GitHub fetches use your `gh` token, one request at a time, and the AI side takes about an hour because commit search allows few requests. Other jobs on the same token can use up the hourly limit, and the fetcher then waits it out. `paired_docs.py briefs` writes briefs for writing agents, which should be `Explore` agents so they don't inherit a CLAUDE.md. `holdouts.py` reprints the real-world table; run it after every retrain.

**Recent formal human prose, and why the idea was wrong.** The round above left declarative third-person prose as the one bad register, so the next step was obvious: get recent prose in that register and refit. `fetch_wikipedia.py` collects it — 92 paragraphs from 92 new articles by 32 editors who registered before ChatGPT, 2023-01 to 2026-10, zero one-sided artifacts.

The gate promoted them with no `--force`, on 20 paired re-splits:

| version | AUROC | human flagged | AI caught | new rows flagged |
|---|---|---|---|---|
| current | 0.940 | 0.127 | 0.837 | **0.051** |
| candidate | 0.941 | 0.130 | 0.840 | 0.050 |

Rollback is `retrain.py --rollback 20261110-171814`. AUROC and AI caught both rose, false alarms cost 0.3 points, and Claude's formal prose caught went 0.741 to 0.745 — no sign of contaminated rows.

**The 0.051 is the result, and it kills the premise.** That column is the never-trained number: the detector fitted without these rows flags 5.1% of them. Recent encyclopedic declarative prose is not hard for it. It sits with abstracts at 4.6%, not with news at 41.5%.

A second measurement says the same thing independently. Re-running last round's comparison on the current set, fitting with and without the Hacker News rows:

| human register | without hn | with hn | change |
|---|---|---|---|
| raid / news | 0.351 | 0.415 | **+0.064** |
| wikipedia / encyclopedia | 0.048 | 0.050 | **+0.002** |
| raid / abstracts | 0.055 | 0.046 | -0.010 |
| aeslc / email | 0.080 | 0.075 | -0.005 |

If casual prose damaged the *declarative formal register*, it would have damaged both formal registers. It damaged one. So RAID's news problem belongs to that corpus — 2004-05 BBC wire copy — and not to the register it is written in. Era, or something else particular to those 360 rows, is the remaining explanation; more modern prose in the same register cannot reach it, because the modern prose was never failing.

What the rows are still worth: a recent human register with structural provenance, which the set had none of, and a small genuine gain. What they are not: a fix for news.

**One more reason not to trust a pooled number.** Adding an easy formal register moved "formal prose false alarms" from 0.242 to 0.185 without changing anything about news. Per register after this round: news 0.415, Ask HN 0.267, Reddit 0.134, email 0.075, forum 0.052, encyclopedia 0.050, abstracts 0.046, books 0.041. A bucket average improves when you add easy rows to the bucket, which is the opposite of progress.

`fetch_wikipedia.py` needs no token either, and takes a couple of hours — not because the work is hard but because an unauthenticated client gets a few hundred Action API calls an hour, so it paces itself at one call every six seconds. Run it on its own: two clients on one IP earn a 429 that outlasts the run, and a throttled fetcher looks exactly like a source with nothing in it.

What it keeps is narrow on purpose. It samples editors from recent changes, keeps those who registered before 2022-11-30 with 20,000+ edits, unblocked and not a bot, then looks at the **articles they created** from 2023 on. Creations rather than all edits for two reasons: every line of a new article is the creator's prose, so the provenance needs no argument, and asking for every edit cost 11 API calls per kept row — most of them spent discovering that a large edit had added a table. So this source is recent *new* Wikipedia articles by long-standing editors, not recent Wikipedia prose in general. **It only takes paragraphs that are wholly new in the diff** — a cell for a partly edited line holds the entire new line with just the changed words marked, so taking those would harvest other people's prose under this editor's name and today's date, and the tenure screen would mean nothing. Anything deleted elsewhere in the same diff is dropped too, which catches moved paragraphs. Then it rejects non-Latin script (one-sided: the AI side is English), quote dumps, surviving templates or markup, zero-width characters, statistics dumps, life-dates lead sentences, and anything under 100 words.

One artifact is normalised rather than rejected. Wikipedia's style guide asks for an en dash in ranges and between paired names, so these rows carry one at 9.4% against 1.2% of the AI rows — an eight-fold enrichment of a house format, not a voice. The fetcher maps it to a hyphen, which leaves the words alone. The proper fix is to normalise it on both sides of the whole set at once, the way `detokenize()` already handles HC3's tokeniser residue; doing it in one fetcher only is the expedient version, and it leaves these rows at 0% against the AI side's 1.2%.

Two filters here were wrong in ways worth remembering, both found by looking at the drop counts rather than at a green test suite. The lead-sentence reject first matched any copula plus an article in the first 60 characters, which threw out 136 of 190 candidates: that is not a format filter but a style one, and it was quietly teaching the human class to avoid "was a". The quote cap paired any quote mark with any later one, so it counted the prose *between* two quotations as quoted and became a screen against quoting twice — which cut reported speech out of the human side only, in the news register this source exists to fix. **A filter that removes something both labels do is worse than no filter**, because it makes that thing an AI cue.

`fetch_hn.py` needs no token and takes about six minutes. It drops anything under 100 words or with a link, a code block, a `>` quote line, surviving markup or a sentence saying a model wrote it, keeps one row per author, and only trusts accounts opened before 2022-11-30. It samples eight points spread across 2024 to now rather than walking back from today, or the whole set comes from one news cycle. Re-run it every few months: its whole job is to be as recent as the AI side.

`fetch_raid.py` reads random row groups straight from RAID's parquet on Hugging Face and can sit in rate-limit backoff for several minutes. `--batch` takes about 0.5 seconds a row on an M-series Mac. `--reuse` copies the model scores for rows whose scored text hasn't changed, so after a small data change only the new rows cost time; drop it to recompute everything. Stop any running scorer first so two copies of the models aren't loaded at once.

The other sources were downloaded once into `data/`: `reddit_eli5.jsonl` from Hello-SimpleAI/HC3 and `aeslc-test.parquet` from Yale-LILY/aeslc. `claude-*.jsonl` were written by Claude agents that had a house style guide. `default-docs.jsonl` and `default-prose.jsonl` came from agents without it (the built-in Explore type), imported from the workflows' output with `import_default_samples.py`.

`retrain.py` runs the last three of those steps for you and compares the result with the current detector. Use it after adding labels. `--rollback VERSION` puts back any earlier detector and its metrics.

To regrade a benchmark run with the scorer running:

```bash
$PY $B/grade_evals.py ~/.cache/humanize/workspace/iteration-2
```


## Anchoring the rewrite to the draft's voice

The rewrite loop maximises a detector score over five rounds. Nothing in it anchors the result to how the draft was written: the automated checks cover facts, length, code blocks and links, and none of those touch voice. Standard RL post-training would call that a reward optimised with no KL penalty against a reference, which is the setup where a policy exploits an imperfect reward. `voice_drift` in `detect.py` was added to measure it — the reverse KL between the rewrite's function-word distribution and the draft's, over the same masked skeleton the docs detector reads, so it is topic-independent by construction. `--compare` reports it.

Three measurements, all read-only over what was already on disk. The short version is that the metric is sound and the hypothesis it was built to test is wrong.

**The loop does not drift as it optimises.** Across 108 graded runs with round chains, the median final drift is 0.150 (IQR 0.129-0.179, max 0.273). But the median run has 97% of its final drift already at r1, the loop adds a median of +0.0000 after it clears the bar (only 6 of 69 passing runs moved at all afterwards), and only 22 of 93 chains rise monotonically. One-pass rewrites with no loop drift further than the loop's finals, 0.178 against 0.150. Whatever voice costs, it is paid by rewriting at all, not by the rounds.

**Drift does not predict which rewrite a judge prefers.** Over the 64 prose A/B pairs with per-pair votes, the lower-drift side won 28, or 43.8% (binomial p=0.38). Conditioning shows why that is a true null and not a weak effect: drift picked the skill rewrite in 44 pairs and that side won 32% of them against a 31% base rate, and picked the baseline in 20 pairs where that side won 70% against 69%. It carries no information beyond which arm it named.

**The detector score predicts the judges backwards.** On those same 64 pairs the lower `ai_probability` side won 16, or 25% (p=0.0001), and the margin runs the wrong way too: the more AI-like the skill rewrite scored relative to the baseline, the more votes it took, Spearman +0.438 (p=0.0003). Drift beats the score head to head (McNemar p=0.023 over 24 discordant pairs), but that is the score being reliably wrong rather than drift being right. This is the measurement to act on. It says the problem is not a missing constraint on the rewriter, it is that optimising this reward moves away from the thing the reward stands for.

**The metric cannot see authorship, and should never be sold as if it can.** Two halves of one unmodified human document differ by a median of 0.371 pooled, 0.26-0.42 on the prose cases; two docs from different projects differ by 0.390. At 100-400 words the estimate is too noisy to separate same-author from different-author, and every loop final sits below the floor's 10th percentile. It is also not a detector: on 4,307 HC3 items holding two human answers and a ChatGPT answer, the ChatGPT answer was further from a human answer than the second human answer only 46.2% of the time.

What it is good for is the price curve, which is real. Pooled over 724 scored rounds with case fixed effects, drift and score drop correlate at +0.619 (slope +5.74). Per drift-adding step the score bought is flat at about 8.3 points per nat up to a starting drift of 0.15, then halves to 4.5, and the best detector score anyone has reached (0.004) is already available in the 0.12-0.14 band. So 0.22 ships as a reject threshold: the highest drift any passing run ever reached is 0.2144, which makes 0.22 a guardrail that rejects nothing that has worked while catching 20% of failures and the whole runaway tail. 0.15 is a steering target, not a filter — enforcing it would fail 41% of currently passing runs, and only 6% of all scored rounds have ever landed below 0.10, so the low-drift region is unexplored rather than known-infeasible.

Caveats that limit all of the above. Every judge is a Claude model, so "preference" means a model's opinion and not a reader's; there is still no human preference data anywhere. The 64 pairs come from only 8 distinct drafts, so they are clustered and the effective n is well under 64. The stored detector scores were computed against the prose blend of 2-3 November, before the refit that moved the human bar from 0.164 to 0.300, so the head-to-head compares a current drift against a stale score. And the cap table filters rounds that were never searching at low drift, so it cannot say what a drift-aware loop would reach.

## A preference reward, and what the preference data will and won't support

The detector score predicts blind judges backwards (see above), so the obvious repair is to fit a reward on preferences instead and optimise that. Two attempts, one per dataset.

**On the existing 64 prose pairs it cannot be done.** Fitting Bradley-Terry over three text features (`ai_probability`, `voice_drift`, length ratio) with a binomial likelihood over all 192 votes, scored leave-one-CASE-out because the 8 drafts are the clustering unit, gives 0.766. That looks good until it is put beside the right baseline. The constant rule "always pick the unconstrained rewrite" gets 0.688, and the fitted model does not beat it (exact McNemar p=0.18, 7 discordant against 2). It is also barely a model: `ai_probability` alone scores 0.750, drift alone 0.562. And its weight on `ai_probability` is +2.166, meaning it prefers the more AI-looking text, which as a reward would tell the loop to stop rewriting. Adding an explicit arm intercept makes it worse (0.703), which says the features already encode the arm. Every pair in that set is with_skill against without_skill, so the reward learns which arm wrote the text, not which text is better.

**A contrast with the arm held constant does support something.** 40 blind pairs were built where A and B are two rounds of the SAME run — same draft, same arm, same skill, differing only in how hard the score was pushed (mean score drop 0.440 between sides, mean drift added +0.0039). 12 judges, 3 per pair, 120 judgments, answer key withheld. The more-optimised round lost on every cut: 50/120 (0.417, p=0.082) on "reads like a person wrote it", 52/120 (0.433, p=0.171) on "better writing", 17/40 and 18/40 at pair level, and 19/57 (0.333, p=0.016) among judgments the judge marked confidence 3 or higher. Judges were unanimous on 32 of 40 pairs and the two questions agreed on 112 of 120 judgments, so the measurement is stable even where it is not significant.

The useful null sits beside it: how much score a later round bought does not predict how much writing it cost (Spearman -0.041, p=0.80 against the pair's own score drop; +0.076, p=0.64 against drift added). The cost is not proportional to the optimisation, so it cannot be tuned away by pushing less hard. The actionable form is a stopping rule rather than a reward term, and it is now in SKILL.md: when no round passes, hand over the earliest round that keeps the facts, not the one that scored closest.

Caveats. The confidence-3 slice was chosen after seeing the main result and is a robustness check, not an independent test; on its own, only that slice clears p=0.05, and the headline numbers do not. The judges are Claude models, as everywhere else in this report. The 40 pairs come from 12 cases, so they are clustered and the effective n is below 40. And the pairs are r1 against the final round, so this measures "later is worse", not "round N is worse than round N-1" for any particular N.

## The HC3 pairs, and why 150 is the right number

`hc3_rows()` in `build_set.py` writes the same `group` on both the human and the ChatGPT answer to each HC3 question, so 16,657 genuine same-question pairs sit on disk and the fit takes 150. Its call in `main()` caps it deliberately, to stop reddit skewing the pooled mix. The argument for lifting the cap was that a *pairwise* fit differences within a pair, so reddit's register would cancel and the pairs could finally be used. That argument is wrong, and it is wrong in a way worth writing down.

3,000 pairs were built with the same detokenizer, residue filter and 60-350 word rule as the shipped rows, and featurized with `detect.py --batch` (2,904 of 2,952 groups keep both sides). 300 pairs were held out of every arm. Three fits were compared on a fixed evaluation set over 20 seeds, with the same non-HC3 split given to each arm so only the training setup varies: **A** pooled on the current data, **B** pooled on the expanded data, **C** pairwise Bradley-Terry on difference vectors, intercept recovered afterwards on the pooled rows with the weights held fixed.

| arm | non-HC3 AUROC | non-HC3 human flagged | non-HC3 AI caught | HC3 AUROC |
|---|---|---|---|---|
| A pooled, current data | **0.9354** | 0.1247 | **0.8174** | 0.9798 |
| B pooled, expanded | 0.9150 | 0.0542 | 0.5996 | 0.9930 |
| C pairwise, expanded | 0.7315 | 0.1030 | 0.4151 | **0.9977** |

C is the best arm on HC3 and the worst by a distance everywhere else, losing 0.15 to 0.20 AUROC at every regularisation strength tried (C = 0.5, 2.0, 5.0) and winning **0 of 20 seeds** in all three sweeps. That split result is also the control that rules out a bug: a broken fit does not top the in-domain table. The gradient was checked against finite differences (max error 1.1e-08), the fit recovers a planted within-pair signal, and the non-negativity clamp on the tell features holds under data that pushes against it.

The reason is that differencing cancels the absolute feature levels along with the nuisance. What survives is the direction separating a 2022 ChatGPT answer from a human answer *to the same reddit question*, which is precise, reddit-shaped and worthless on abstracts or email. Adding the pairwise term on top of the pooled loss rather than in place of it does not rescue it: sweeping lambda over 0, 0.1, 0.5, 1.0 and 3.0 moves non-HC3 AUROC monotonically down (0.9150 to 0.9096) and HC3 AUROC monotonically up (0.9930 to 0.9944), and every setting loses to A on 0 of 20 seeds. It is a dial that trades out-of-domain accuracy for in-domain accuracy, nothing more.

B is the arm that looks tempting and is not. Its false-alarm rate on non-HC3 prose is 0.0542 against A's 0.1247, which would be a real answer to prose's documented 12-14% false alarms. But its AUROC is lower, so it is an operating point and not a better detector. Matching A's threshold to B's own false-alarm rate on each seed, A catches 0.6656 against B's 0.5996 and wins 20 of 20 seeds.

Two things to keep from this. The cap at 150 is correct, and for a stronger reason than source balance: the HC3 pairs cannot improve this detector by any of the three routes tried. And the threshold-matching run says something useful in passing — the current prose blend can be run at 5.4% false alarms for 66.6% of AI caught, against the shipped 12.5% and 81.7%. That is a cut choice already available, with no refit and no new data.

Caveats. HC3's AI side is 2022-23 ChatGPT, so none of this measures the 2026 agent voice; a win here would not have transferred either. Only 3,000 of the 16,657 pairs were used, though the effect is large, monotone in lambda and unanimous across seeds, so more pairs would not plausibly reverse it. Every arm used a fixed C rather than the grouped-CV search the shipped fit runs, which is the fairer comparison between objectives but is not what ships.


## The second opinion is not a gate on docs

`heldout_roberta` is fakespot's RoBERTa detector, held out of the fit on purpose and reported beside the
blend as a second opinion. Until 2026-11-14 SKILL.md made it a hard pass condition on every rewrite round
with no genre carve-out, `grade_evals.py` scored the same bare 0.5 as one of each eval case's checks, and
an LLM grader file repeated it in all twelve cases.

`metrics.md` has been contradicting that on every fit. `fit.py` writes a "fakespot RoBERTa alone" row
per genre, and the two rows are not the same detector in any useful sense:

| genre | accuracy | AI caught | human flagged | AUROC |
|---|---|---|---|---|
| prose | 0.752 | 211/331 = 0.637 | 57/382 = 0.149 | 0.799 |
| docs | 0.622 | 36/391 = 0.092 | 158/965 = 0.164 | **0.345** |

AUROC 0.345 is below chance, and the shape of it is that on docs the detector flags more known-human
documents than it catches AI ones. So the cut pointed the wrong way: a doc over 0.5 was likelier to be
human than AI, and the round failed anyway. Over every non-extra row rather than the test split it reads
the same, 0.337 per section and 0.290 per document. Half of this was already written down at the OWASP
cheat sheets, where it flagged 15 of 20 known-human pages at median 0.956 and "carries no information at
all". That was read as one bad register. It is the genre.

**Length made it worse, through the aggregate.** A document's reading was the max over every section,
including sections too short to carry a verdict and sections of known text, while `ai_probability` and
`all_sections_human` are read off `counted`, the sections that decide. A max over more sections can only
go up, so for known-human docs the chance of reaching 0.5 ran 0.038 at one section, 0.246 at two to four,
and 0.644 at five or more. A long human README failed on arithmetic.

The aggregate now reads `counted`, the same sections as the verdict. On its own that moves known-human docs
from 0.298 to 0.287, which is small; the point is that one number was being read off text the verdict
refused to judge. The pass condition is prose only now, in SKILL.md and in `grade_evals.py`, and the grader
file is gone from the four docs cases. `both` keeps the check: the inversion was measured on the docs
corpus and a `both` case is prose with headings. The number is still computed, still in the round table and
still recorded by `record.py`. It just does not pass or fail a docs round.

**This moves a denominator.** Docs eval cases carried seven checks and went to six, five base plus the
code-block one, the same six prose carried. The next section moves both genres again, to eight. The 7-based docs totals in the table above (48/56, 55/56,
78/112) measure runs that were graded with the RoBERTa check in them. They stand as history and are not
comparable with anything graded after 2026-11-14.

Worth knowing before quoting any figure above: when these were measured the model was unpinned.
`setup.sh` called `snapshot_download` on the RoBERTa repo with no `revision=`, so every number in
this section is against whatever snapshot that repo's `main` pointed at the day setup last ran. Since
2026-11-15 setup and `detect.py` pin all three models to one commit each (DATA.md lists them), and the
pinned snapshot scores the same. `detect.py` still reads the AI class index out of the config, with a
fallback to index 1.


## Three statements of one rule

"A round passes" was written down in three places and they had drifted apart: `SKILL.md` step 6, the
`checks` list in `bench/grade_evals.py`, and one LLM grader file per requirement under `evals/*/graders/`.
A rewrite could satisfy any one of them and fail another, and nothing compared them.

What each path was missing on 2026-11-14:

| requirement | SKILL.md | grade_evals.py | grader file |
|---|---|---|---|
| `voice_drift` under 0.22 | yes | **no** | **no** |
| document: `all_sections_human` | yes | **no** | docs only, and worded as the prose rule |
| prose: no section reading `ai` | yes | **no** | **no** |
| docs: no links added | yes | only when links *were* added | **no** |
| code blocks unchanged | docs | whenever `compare` returned the keys | docs |
| no hidden characters | not in step 6 | yes, with a one-in-100 budget | yes, as an absolute |
| verdict `human` | verdict + sections | verdict only | two wordings, neither the rule |

The sharp one is the second and third rows together. `detect.py` lets `verdict` stay `human` with one
stray section on purpose, because a long human document usually has one; `all_sections_human` is the
stricter field the loop is supposed to use, and `grade_evals.py` read the looser one. That never bit the
eval set, because all 12 drafts score in one piece and neither field exists on a single-section result. It
bites on the long documents the skill actually runs on, which is the only place `all_sections_human` was
ever going to differ from `verdict`.

`voice_drift` is the plainest: SKILL.md has required it since the metric landed, and nothing has ever
measured it. The guardrail was real and unenforced.

**What changed.** The verdict check is now SKILL.md's whole first bullet: the document verdict, plus
`all_sections_human` when the text split into sections, plus no section reading `ai` outside docs. A text
short enough to score in one piece has neither field and is judged on its verdict alone, which is every
eval draft today -- all 12 are a single section, so this clause is currently vacuous on the eval set and
correct for real documents. Drift is a check, and a run with no drift reported fails it rather than
passing. The code-block check runs in every genre and the links check in docs and `both`, both
unconditional, so a docs run that adds no links records that it was checked instead of silently skipping
it. Grading also scores with the case's genre instead of letting `detect` guess it again, so the verdict
and the length bound can no longer be judged as different genres in the same run. A scorer result with no
verdict, which is what `detect` returns for a docs text with under 120 words of prose once code and markup
are removed, fails the verdict check instead of raising. Base reached that too, and raised; forcing the
genre only added a way in, a docs case whose final dropped every code block.

**The first version of this broke something, and review caught it.** It gated the code-block check on
docs and `both`, on the reading that a prose case collecting that check was an oddity. It was the opposite.
`facts()` deliberately leaves whatever sits inside a code block to this check, so it is the only fact check
a block gets, in any genre: a prose rewrite that appended a fenced block holding an invented
`rate = 0.0742` scored 7 of 7, with `added` empty and `length_ratio` 1.0. At the base commit the same run
failed. A prose draft cannot hold a fence in the first place (`has_code()` routes it to docs), so in prose
the check fires on a block the rewrite added, which is the case worth catching, and on an indented passage
(an address, a quote) that the rewrite touches at all. Rewording one is a real catch, because nothing else
reads that text. Reflowing or un-indenting one is a false alarm, accepted because the loop sees it in
`--compare` and SKILL.md now tells it to leave those passages as they are.

**How `both` was settled.** No `both` case exists in `evals/`, so these rows were latent, but the first
version still disagreed on three of them. `both` now takes the prose rule for stray sections and the docs
rules for links and length, with RoBERTa as before. That was fixed by correcting the spec, not the code:
the code was already right, because a `both` document is prose with headings and half of its verdict is
the docs blend, link credit included. SKILL.md step 6 now names `both` on each of those bullets. A `both`
case would carry 9 checks, and a test builds one to pin that.

The grader files now say the same things: `01` states the full rule in both variants,
`08-voice-close-to-draft.md` is new in all twelve cases, `09-no-links-added.md` is new in the four docs
cases, and the prose length grader says "prose" because that is what `length_ratio` measures.

**The guard against this happening again** is two tests. `test_each_genre_gets_the_checks_its_graders_describe`
counts the grader files for every case and the checks `grade_evals.py` produces for it, and fails if they
differ. Its first version looped over two named cases, and review showed a third case could lose a grader
file and a fourth gain one with the suite still green; it reads all twelve now. Counting is not enough on
its own, because grader 08 could say 0.25 against a code bound of 0.22 and still pass it, so
`test_every_threshold_a_check_uses_is_the_one_its_grader_states` checks that the length bounds, the drift
bound, the RoBERTa cut and the one-in-100 spelling budget appear in the grader files that state them.

Grader 06 now states that budget. SKILL.md documented it in the first version and the grader file kept
saying "no misspellings" outright. That was one of two rows able to disagree on today's eval set; the other
is the facts rows, below, which are now a stated difference rather than an unnoticed one. Grader 07
is in every case and says "fenced or indented", because `code_blocks()` compares both.

One rule here is a spec extension rather than an alignment: drift joined the docs list of things that
cannot be traded for a pass at step 8. It follows from drift being a pass condition at all, but it is new.

**One difference is deliberate.** `missing` and `added` are read two ways on purpose. The loop at step 6
reads both lists with judgement, because `compare()` lists ordinary words: a saved with-skill run that turned
"message me" into "DM me" lists `added: ['DM']`, and reworded headings and table cells show up the same way.
Grading fails on any entry, in the code and in graders 03 and 04, which now say so outright -- before, a
judge reading "shows no facts missing" could go either way on an ordinary word. Making the loop mechanical
would push it to undo rewording like "DM me" to clear a list, which costs the writing; giving grading
judgement would make it unrepeatable. So grading is stricter than the loop by design, and a `grading.json`
fail on one of these rows is worth reading before it is treated as a failed rewrite. (The "DM" run fails on
drift too, at 0.241, so it does not pass either way.)

**Denominators move again.** Prose and docs cases both go from 6 checks to 8. With the earlier
RoBERTa change that is the second move in two days, so: the 208 `grading.json` files under
`~/.cache/humanize/workspace/` carry totals of 6 and 7. The 48 sevens are the docs gradings: `docs-1` and
`docs-2`, quoted in this file as 48/56, 55/56 and 78/112, and `iteration-voice`, behind "all 7 checks" in
the section on rewriting against the function-word detector. None of those are comparable with anything
graded after 2026-11-14. The
prose `summary` sums were never quoted here, so nothing else needs restating.

**Still spec-only, and fine that way.** The editor read-through at step 8, "each claim as strong as
before", keeping the genre and register, and inventing no anecdotes or version history are judgement
calls that live in "Rules for the rewrite". `--compare` cannot see "is one of" softened to "can be", and
no check will. They are not drift between the three paths; they are the part a person or a judge does.

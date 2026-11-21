# Rewrite guide

Read this before the first rewrite round. It covers what the detectors react to and what to do instead.

Write for the reader first. A lower score bought with a stiff or odd phrase is a bad trade: people notice it faster than detectors do. In a blind comparison, judges preferred a plain rewrite over score-chasing rewrites 21 votes to 3, even though the score-chasing versions kept the facts better.

## What gets flagged

- **Word choice.** The tell list in `scripts/detect.py`: delve, crucial, robust, landscape, foster, seamless, journey, showcase, "it's worth noting", "plays a key role", "whether you're", "excited to share". One is noise. Five in a paragraph is a signature.
- **Even rhythm.** Model sentences cluster at 12-28 words with similar lengths (`sent_len_cv` low, `sent_mid_band` high). People write a four-word sentence, then a forty-word one.
- **Stock shapes.** "It's not X, it's Y". Lists of exactly three. Colon reveals ("The result: ..."). Em dashes. Openers like Moreover, Additionally, Ultimately. A closing sentence that sums up what was just said.
- **Predictability.** The Binoculars score. A sentence where every next word is the obvious next word gets the "too predictable" flag. Generic claims are predictable. Specific ones aren't.
- **Missing human texture.** No first person where a person would use it, no asides in brackets, no specific numbers or names. Contractions don't help on their own: casual model output is full of them.

## Moves that work

1. **General to specific.** "improves performance significantly" becomes "cut the build from 9 minutes to 2". Only use specifics that are already in the source. If there are none, make the claim smaller and plainer. Never invent one.
2. **Break the rhythm.** Join two medium sentences into one longer one with a clause, then follow with a short one. A fragment now and then is fine.
3. **Drop the frame.** "It's not about speed, it's about trust" becomes "Speed matters less than whether people trust it", or just the second half.
4. **Two or four, not three.** Or one, if one is the real point.
5. **Cut the throat-clearing and the wrap-up.** The first sentence makes a point. The last sentence carries the last real piece of information, not a summary of the others.
6. **Plain verbs.** use, help, show, make, get. Not utilize, leverage, empower, foster, showcase.
7. **Commas, full stops or brackets instead of em dashes.**
8. **Say who.** "It is recommended that you" becomes "I'd" or "most people".
9. **Let a few sentences start with And, But or So.** Not every one.
10. **Layout.** The detectors mostly ignore it, but readers don't. Keep layout that helps the reader. A list that organises information they'll scan or act on stays a list: a coverage plan, steps, dates, options, prices. Turning that into paragraphs makes it harder to use, and judges marked it down every time. But don't rebuild a kept list into matching lines ("Priya for X. / Tom for Y. / Lee for Z."). People's bullets are uneven: one is a fragment, one runs to two sentences. Drop layout that's decoration or a model habit: bold section headers on a Reddit comment or social post, a tidy list of exactly three "lessons" or "takeaways", a "Spoiler:" or "The result:" punchline on its own line, a closing call-to-action stacked with emoji. Keep an email's greeting and sign-off.
11. **Keep the genre.** An abstract stays formal: vary the rhythm and cut the tells, but don't add "honestly" or "lol". A Reddit reply should actually sound like Reddit: "imo", "tbh", "fwiw", "oh and", a comma splice, a number written as "~3 months" are all normal there, used once or twice where they fit. An email keeps its greeting if it had one.
12. **Keep the person.** If the source is first person, stay first person. If it isn't, don't make up a narrator with experiences.
13. **Give it a voice.** Blind judges kept picking rewrites with small human turns of phrase, the kind of thing in "if the printer cooperates", "so nobody gets blindsided" or "which, fair enough". Those carry tone, not facts, so add them where the author plausibly would, once or twice. The line is information: a new number, event, reason or detail ("it took about ten seconds", "my manager said") is invention, even when it sounds like voice.

## Skeletons readers notice

These often pass the detector and still read as AI to a person. Rewrite them even when no sentence is flagged.

- **Signposting the structure.** "In this post I'll walk through...", "We'll start with... then move on to...", "Key takeaways include", "Let's break it down". Say the content and drop the map of it.
- **Polished aphorisms.** A neat line that sounds quotable: "time is the one thing you can't buy back", "the part nobody talks about", "the writing is on the wall". Say the plain point, or cut it if the sentence before already made it.
- **Boilerplate openers and closers.** "I'm writing to express my interest", "I am confident I would be a great fit", "I look forward to the opportunity to contribute". Open with the specific thing and close the way the genre normally closes.
- **Keeping every sentence in the draft's order.** A person retelling the same facts starts somewhere else, merges two points, or leaves out the setup.

Keep how strongly each thing is claimed. "Our findings suggest" doesn't become "Because". "Usually" doesn't disappear. A rewrite that sounds human but overclaims is worse than the draft.

## When nothing is flagged but the score is still high

The rest of the signal is document-wide: how predictable the whole text is to a language model. That's most of the blend's weight. What moves it:

- Put back the concrete detail the source already has (the name, the number, the actual example) wherever the text went general.
- Cut sentences that restate the one before. Predictable text is often padded text, and cutting is the fastest way down.
- Lead with the most concrete point instead of the setup.
- Vary sentence length harder: one very short sentence, then a long one with a clause in it.
- Don't reach for rarer words ("procure" for "get", "commence" for "start"). Blind judges spotted exactly this and called it "a synonym-swap pass". Rewrite the sentence around what it says instead.

Watch for the model's own idea of "sounding human", because it's a fingerprint too. In the benchmark, rewrites that stalled had three things in common:

- **Vocabulary that never repeats** (`mattr` high). Models cycle synonyms: the app, the platform, the tool. People say "the app" three times. Reuse the plain noun.
- **Every sentence short and punchy** (`sent_len_mean` around 11 words against about 21 in human text). People explaining something run long, with commas and a "because" or "which" in the middle. Keep a few short ones for effect, not all of them.
- **Only tiny words.** Cutting "utilize" is right. Cutting every word over two syllables isn't. Keep the precise longer word where it's the right one.

What doesn't move it and makes the text worse: expanding contractions, adding slang, padding, extra hedges. The blend doesn't count contractions or slang at all.

## Technical docs

Docs break the usual rules. In about 300 human READMEs from before 2022, people wrote "simply", "easily", "allows you to", "please", "for example" and "e.g." far more often than Claude does. So swapping those words out doesn't make a doc read as human.

The docs detector masks every content word and keeps only function words and punctuation, so a doc's subject, names and code can't move its score. What it sees is grammar:

- **People's docs** use "will", "be", "to", "of", "more", "also", "some", "you can", "can be" and "we": future tense, passives, infinitives and small hedges.
- **Recent AI docs** drop those and lean on comma joins (", and", ", so", ", which", ", or"), sentences opening on "The", "A" or a bare noun, and words like "one", "every", "each", "no", "never" and "same".

Plain present tense and active voice are how good docs are written, and that's most of what scores as AI here. Readers ranked every passing version below the draft, so reach the bar with the moves that cost least. Use `voice_pushes_ai` to see what each section needs:

- **Change how sentences open.** Openers like "The", "A" and a bare noun push toward AI. "This", "For", "If you", "By default" and "There" don't, but only in moderation: use one eight times and it becomes the next push. Reuse the plain noun rather than "it". Don't front a clause ("To cap them, use..."), because the comma it adds costs more than the new opener saves.
- **Rewrite comma joins, but don't chop.** ", and", ", so", ", which", ", or" and ", not" are among the strongest AI terms. Split one when it holds two separate thoughts, or say it another way ("because", "to"). A paragraph of short even sentences lost to everything else in the blind tests, and readers called it machine-written.
- **Drop words the sentence doesn't need.** "every", "one", "same", "own", "still", "through", "before" and "them" lean AI. Keep "no" and "never" when they state a guarantee: "It never raises" is a claim, and its strength is a fact.
- **Use the small words people use.** "you can", "also", "some", "more", "just", "but", "this", "to" and "of", where the sentence wants them anyway. Don't hedge a firm claim with "might" or "some". Only use "we" if the doc already does: readers disliked a "We" laid over a neutral doc.
- **"will" and "be" are fine in moderation.** Readers grumbled at them but preferred them to chopped sentences. They fit best on things that happen later, such as a retry or a timeout. Keep tutorials in the imperative: don't turn "Create the client once" into "A client should be created once".
- **Avoid phrasing no maintainer would use.** "To find out which of X and Y to read" and "as well as" read as synonym swaps. If a fix sounds like that, try a different one.

Don't add links: `--compare` reports `links_added`, and a round that adds any fails.

What Claude's docs lean on, for a reader:

- **Signposting the reader:** "This guide covers", "you'll", "In this section". Human READMEs rarely announce themselves.
- **Contrast framing:** "instead of", "rather than", "without X". Fine once; in every paragraph it's a pattern.
- **"Handles" and friends:** "X handles retries for you", "takes care of". Say what it does: "X retries a failed request three times".
- **Even, complete coverage:** every option explained in the same shape, every section the same length. Real READMEs are lumpy. They go deep on the tricky option and give the obvious one a single line.

What human docs have that AI docs mostly don't: the reason behind a design choice, a known limitation, a "this used to be X" note, a pointer to an issue. Keep those when the source has them, and never invent them.

Leave code blocks, commands, API names, flags, version numbers, file paths and tables exactly as they are. Rewrite the sentences around them.

**Don't pad.** In the first docs benchmark the loop passed the detector by making READMEs wordier, and blind judges preferred a two-line edit almost every time. The things they called out:

- **Explanatory asides:** "since that's usually what you want here", "(or anything else it depends on)". If the draft didn't explain it, don't.
- **Lead-ins turned into sentences:** "Install it:" before a code block is how READMEs talk. Don't rewrite it as "You can install it with the following command."
- **Short fragments stretched out:** "Read-only. Nothing is written to disk." is a maintainer's voice. Leave lines like that alone even if a sentence near them is flagged.

To move a flagged sentence without adding words: say it in fewer, plainer words, join it to the sentence before when they're about the same thing, or reuse the noun the doc already uses instead of a new one.

## Don't

- Don't add typos, hidden characters or look-alike letters, and don't add slang the writer and the genre wouldn't use ("lol" in a cover letter, "no cap" from someone who writes in full sentences). They make the text worse, and current detectors look for exactly those tricks. The casual markers a genre normally uses, like "imo" on Reddit, aren't tricks.
- Don't invent facts, numbers, names, quotes, anecdotes or experiences. `--compare` lists new numbers and names under `added`.
- Don't drop facts. `--compare` lists them under `missing`.
- Don't swap one tell for its cousin (crucial to vital to essential). Rephrase the whole sentence.
- Don't touch clean sentences in later rounds. Only rewrite what's flagged. Every extra edit is another chance to drift from the original.

## Example

This shows the moves, not a pass. Both versions are under 80 words, too short to score reliably, and the rewrite still scores as AI on the blend. Getting under the bar usually takes the full loop.

Before:

> In today's fast-paced world, effective time management is more crucial than ever. Whether you're a busy professional or a student, mastering this skill can unlock your full potential. It's not just about doing more — it's about doing what matters. This guide will explore practical strategies, real-world examples, and actionable tips. By implementing these techniques, you can achieve a healthier work-life balance. Ultimately, time management is a journey, not a destination.

After:

> Most time-management advice is about squeezing more into a day. This guide is about the opposite: working out which tasks you can drop. If you're juggling a job, classes or both, start with the section on weekly reviews. It's the one people actually keep doing after the first month.

The rewrite dropped "real-world examples" and "work-life balance" claims it couldn't back up, kept the audience, and added nothing that wasn't implied. It still has one colon. That's fine. One tell isn't a pattern.

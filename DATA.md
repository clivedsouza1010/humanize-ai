# Models and training data

This repo's code is under the MIT licence in [LICENSE](LICENSE). That licence covers the fitted statistics described below as well, but only as far as the author holds rights in them. Models and datasets keep their own terms.

## Models

`scripts/setup.sh` downloads three models from Hugging Face onto your machine. None of them ship in this repo. Each one is pinned to a commit.

| model | licence | commit |
|---|---|---|
| [Qwen/Qwen2.5-1.5B](https://huggingface.co/Qwen/Qwen2.5-1.5B) | Apache-2.0 | `8faed761d45a263340a0528343f099c05c9a4323` |
| [Qwen/Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) | Apache-2.0 | `989aa7980e4cf806f80c7fef2b1adb7bc71aa306` |
| [fakespot-ai/roberta-base-ai-text-detection-v1](https://huggingface.co/fakespot-ai/roberta-base-ai-text-detection-v1) | Apache-2.0 | `f9cdb14d1f8b105f597d80fa7b56f20c6ea0e9db` |

## What ships from the training data

No dataset is redistributed here. There are short quotes in `bench/REPORT.md`, and `bench/provenance_test.py` copies a few pull-request template lines from the projects it names. Apart from those, no text from these sources is in the repo. What does ship was fitted on that text:

- `scripts/blend.json`, and any versions `retrain.py` saves in `scripts/blend-history/`: logistic coefficients, function-word n-gram weights, cut-offs per register and percentile tables of scores.
- `scripts/words.txt`: every lowercase word seen three or more times across the training rows, leaving out labelled texts. The facts check in `--compare` uses it.
- `bench/metrics.md`, `bench/REPORT.md` and `SKILL.md`: accuracy figures per source, and a few short quotes for commentary.

## Training data

| source | used as | licence or terms |
|---|---|---|
| [RAID](https://huggingface.co/datasets/liamdugan/raid) | human and AI text across several registers | MIT on its dataset card. Its human news text is 2004-05 BBC copy, and the original BBC dataset is offered for non-commercial research use. Its book text is plot summaries from Wikipedia (the CMU Book Summary Dataset), CC BY-SA. |
| [HC3](https://huggingface.co/datasets/Hello-SimpleAI/HC3), reddit_eli5 | human Reddit answers and ChatGPT answers | CC BY-SA 4.0. HC3 lists the ELI5 source as BSD. |
| [AESLC](https://huggingface.co/datasets/Yale-LILY/aeslc) | human email (Enron) | Listed as unknown on its dataset card. |
| Hacker News, through Algolia's HN Search API, with account ages from the official API | human forum comments and posts | Y Combinator's terms of use. |
| Wikipedia, revisions from 2023 on | human article prose | CC BY-SA 3.0 or 4.0, depending on when the text was written. |
| npm package READMEs | human docs | Each package's own licence, or none. |
| GitHub docs from public repos | human docs, and AI-credited docs | Each repo's own licence, or none. |
| Claude-written samples | AI prose and docs, and the eval drafts in `evals/` | Generated for this project. |
| Labels the maintainer supplied | human or AI, as stated by the author | The maintainer's own; only salted ids of them ship. |

Earlier versions were also trained on 300 Yelp reviews. No detector fitted on those reviews ships: on 2026-11-15 the prose detector was refit without them and the versions fitted with them were removed. There are still pooled figures from that time in the dated sections of `bench/REPORT.md`, but none of them are about the reviews.

If you hold rights in one of these sources and want it out of the fitted statistics, open an issue.

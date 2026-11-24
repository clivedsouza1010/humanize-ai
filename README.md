# humanize-ai

humanize-ai is a Claude Code skill that checks whether writing will read as AI-written and shows what pushed the score up and why. It can also rewrite the draft in rounds until its local detectors read it as human and the facts still match. It's an early project with one maintainer.

## What it is, and why it exists

A single score from a detector can't tell you what to change, and the rewrite that brings it down is often worse to read. That is the gap humanize-ai was built for. Its detectors run on your machine and each flag comes with a reason. Its blind tests also shaped how the rewrites work. People rated score-chasing rewrites below plain ones, which is why a reader's view is the first test of a round and the score is the second.

Use it on your own posts, docs and emails, where AI help is allowed, or to see where detectors go wrong. A rewrite does not change the rules of a school, employer, journal or event that bans AI help or asks for it to be disclosed.

## The problem it solves

Text written with AI help tends to carry habits readers notice, like the same openers, a tidy list of three, "it's not X, it's Y" and sentences of the same length. If you ask a model to "make it sound human", it will often trade one set of habits for another or drop a fact without saying so.

To score a draft, humanize-ai picks a detector by genre. For prose there is a model that combines 26 signals from two small Qwen language models and from writing style, plus a separate RoBERTa detector as a second opinion. For technical docs only function words and punctuation are read. This means a doc's subject, names and code can't move the score. Each rewrite is then checked against the draft for missing or added facts, length, changed code blocks and new links. A round passes only if the detector reads it as human and none of those checks fail.

Any score here is a statistical guess and not proof of who wrote something. It will flag some human writing. Turnitin, GPTZero and other detectors are trained differently and can disagree. Most AI docs from 2025 will get past the docs detector, because it reads the voice coding agents have had since early 2026. [metrics.md](plugin/skills/humanize-ai/references/metrics.md) has the current accuracy figures and `bench/REPORT.md` explains them.

## Installation

Install the plugin:

```bash
claude plugin install humanize-ai --marketplace clivedsouza1010/humanize-ai
```

Updates are manual: `claude plugin update humanize-ai@humanize-ai`.

On first use, Claude runs `setup.sh` after telling you. Setup will make a Python environment in `~/.cache/humanize/venv`, install pinned packages and download three models, about 6.7 GB. It needs Python 3.11 or newer (`PYTHON` picks the interpreter) and works on Apple Silicon, an NVIDIA GPU or the CPU.

Then Claude starts the scorer, which keeps the models loaded on `127.0.0.1:8765` so a check takes under a second instead of about 15. It stops when idle for 15 minutes. Each run's draft and rewrite are kept in `~/.cache/humanize/data/runs.jsonl`.

To work on humanize-ai, clone it and link the skill:

```bash
git clone https://github.com/clivedsouza1010/humanize-ai ~/humanize-ai
mkdir -p ~/.claude/skills
ln -s ~/humanize-ai/plugin/skills/humanize-ai ~/.claude/skills/
bash ~/.claude/skills/humanize-ai/scripts/setup.sh
```

## Starter examples

You can ask Claude Code "Does this README sound like AI?", "Which docs in this repo sound AI-written?" or "Humanize the talk abstract in `abstract.txt`."

To run the detector yourself, set these once per shell:

```bash
PY=~/.cache/humanize/venv/bin/python
D=~/.claude/skills/humanize-ai/scripts/detect.py   # clone
D=$(ls -t ~/.claude/plugins/cache/humanize-ai/humanize-ai/*/skills/humanize-ai/scripts/detect.py | head -1)   # plugin
```

To score a file:

```bash
$PY $D draft.txt --heldout
```

You get a `verdict` such as `human`, `unclear` or `ai`, an `ai_probability`, and the reason behind each flag.

To check that a rewrite kept the facts:

```bash
$PY $D final.txt --compare draft.txt
```

To score every tracked `.md`, `.mdx` and `.txt` file:

```bash
$PY $D --scan ~/dev/my-repo --out scan.json
```

## Contributing

Bugs and questions go in GitHub issues; open one before a larger change.

Tests are plain scripts; run each from its own folder:

```bash
cd ~/humanize-ai/bench && $PY grade_evals_test.py
```

If your change moves the detector's numbers, add the before and after to `bench/REPORT.md`.

There is one fixed rule: the detector must never be trained on its own verdicts, on humanized rewrites, or on human-labelled text screened by its own score, because that would teach it to agree with itself. Retrains go through `bench/retrain.py`, which only replaces a detector that holds up against the one in use and keeps the old version for rollback.

## Code of conduct

This project follows the [Contributor Covenant 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). Report problems to the maintainer privately, not in a public issue.

## License

MIT. See [LICENSE](LICENSE). For the terms of the models and training data, see [DATA.md](DATA.md).

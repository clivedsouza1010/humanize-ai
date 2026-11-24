# humanize-ai

This is a Claude Code skill to check if some writing will read as AI-written and to show what pushed the score up. It can also rewrite a draft in rounds until its local detectors read it as human and the facts still match.

## Use it

You can ask Claude Code:

- "Does this README sound like AI?"
- "Which docs in this repo sound AI-written?"
- "Humanize the talk abstract in `abstract.txt`."

## What it runs

For the first check, Claude will tell you and then run `setup.sh`. This will make a Python environment in `~/.cache/humanize/venv`, install pinned packages from PyPI and download three models from Hugging Face, to a total of about 6.7 GB. You will need Python 3.11 or newer.

After setup, scoring will be done on your machine by a small scorer on `127.0.0.1:8765`. This will stop when idle for 15 minutes. None of the scripts will send your drafts anywhere. Claude will read them as part of your session.

The draft and the rewrite of each run will be kept in `~/.cache/humanize/data/runs.jsonl`. To clear them, you can delete the file.

## What a score means

A score is a statistical guess and not proof of who wrote something. Some human writing will be flagged and other detectors can disagree. If a school, employer or journal bans AI help or asks for it to be disclosed, a rewrite will not change the rules.

Accuracy figures, source and issues: https://github.com/clivedsouza1010/humanize-ai

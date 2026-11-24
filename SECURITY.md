# Security

## Supported versions

Only the latest commit on `main` gets fixes.

## Reporting a problem

Use **Report a vulnerability** on the repo's Security tab. It opens a private report. Please don't open a public issue for a security problem. I aim to reply within 7 days.

## What's in scope

- The local scorer (`detect.py --serve`) on `127.0.0.1:8765`.
- `setup.sh` and what it installs or downloads.
- File handling in `--scan`, `--compare` and `--batch`.
- Anything in the scripts that sends a draft off your machine. Nothing should: scoring runs locally, with Hugging Face set to offline mode. Claude itself will still read the draft as part of your Claude Code session.

## What's out of scope

- Detector accuracy and false alarms. Those are normal issues.
- Bugs in the upstream models or Python packages. Please report those upstream.

## How it's meant to work

Scoring stays on your machine. The scorer will only accept JSON posted straight to `127.0.0.1` or `localhost` on its own port, with a declared length. It turns away any request with an `Origin` header and any body over 2 MB.

Models are loaded as safetensors at pinned commits, with no remote code.

Each run's full draft and rewrite are kept in `~/.cache/humanize/data/runs.jsonl` on your machine and go nowhere else. To clear them, delete the file. You can also set `HUMANIZE_RUNS` to a different path.

# Keep what each humanize run saw, so the skill accumulates evidence instead of opinions.
# A run is never training data. Its draft has an author only the user can state, and its rewrite
# was written by this skill, so neither may reach the detector except through label.py.
# Usage: record.py add --draft FILE --rewrite FILE --genre G --before F --after F --rounds N
#        record.py queue [N]
#        record.py stats
import argparse
import hashlib
import json
import os
import statistics
import sys

STORE = os.environ.get("HUMANIZE_RUNS") or os.path.expanduser("~/.cache/humanize/data/runs.jsonl")
MIN_RUNS = 6
DRIFT = 0.15


def load(store):
    if not os.path.exists(store):
        return []
    return [json.loads(line) for line in open(store) if line.strip()]


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def add(args):
    draft = open(args.draft).read().strip()
    rewrite = open(args.rewrite).read().strip()
    runs = load(args.store)

    fingerprint = (sha(draft), sha(rewrite), args.before, args.after)
    for run in runs:
        if (run["draft_sha"], run["rewrite_sha"], run["before"], run["after"]) == fingerprint:
            print(f"already recorded as {run['id']}")
            return

    row = {
        "id": f"{args.at.replace(':', '').replace('-', '')}-{sha(draft)[:6]}",
        "at": args.at,
        "genre": args.genre,
        "draft": draft,
        "rewrite": rewrite,
        "draft_sha": sha(draft),
        "rewrite_sha": sha(rewrite),
        "words": len(draft.split()),
        "before": args.before,
        "after": args.after,
        "rounds": args.rounds,
        "heldout": args.heldout,
        "moves": [m.strip() for m in args.moves.split(",") if m.strip()] if args.moves else [],
        "note": args.note,
        # Filled in only by a person, through label.py. Never by a run.
        "label": None,
        "labelled_as": None,
    }
    os.makedirs(os.path.dirname(args.store) or ".", exist_ok=True)
    with open(args.store, "a") as f:
        f.write(json.dumps(row) + "\n")
    print(f"recorded {row['id']}  {args.genre}  {args.before:.2f} -> {args.after:.2f} in {args.rounds} round(s)")


def queue(args):
    waiting = [r for r in load(args.store) if r["label"] is None]
    if not waiting:
        print("nothing waiting to be labelled")
        return

    print(f"{len(waiting)} run(s) whose author only you can state. Label the draft, never the rewrite:\n")
    for run in sorted(waiting, key=lambda r: r["at"], reverse=True)[: args.limit]:
        excerpt = " ".join(run["draft"].split())[:110]
        print(f"  {run['id']}  {run['at'][:10]}  {run['genre']:<5} {run['before']:.2f} -> {run['after']:.2f}  {run['words']}w")
        print(f"      {excerpt}...\n")
    print("If you know who wrote one of these drafts:")
    print("  label.py add FILE --human|--ai --note \"...\"")


def stats(args):
    runs = load(args.store)
    by_genre = {}
    for run in runs:
        by_genre.setdefault(run["genre"], []).append(run)

    reportable = {g: rs for g, rs in by_genre.items() if len(rs) >= MIN_RUNS}
    if not reportable:
        have = ", ".join(f"{g}: {len(rs)}" for g, rs in sorted(by_genre.items())) or "none"
        print(f"not enough runs yet to show a trend. Need {MIN_RUNS} in a genre, have {have}.")
        return

    print(f"{'genre':<6} {'runs':>5} {'baseline':>9} {'recent':>7} {'change':>7}")
    drifted = []
    for genre, rs in sorted(reportable.items()):
        rs.sort(key=lambda r: r["at"])
        half = len(rs) // 2
        baseline = statistics.median(r["before"] for r in rs[:half])
        recent = statistics.median(r["before"] for r in rs[half:])
        change = recent - baseline
        flag = "  drift" if abs(change) >= DRIFT else ""
        if flag:
            drifted.append((genre, change))
        print(f"{genre:<6} {len(rs):>5} {baseline:>9.2f} {recent:>7.2f} {change:>+7.2f}{flag}")

    for genre, change in drifted:
        if change < 0:
            print(f"\ndrift in {genre}: incoming drafts score {abs(change):.2f} lower than they used to.")
            print("That is what a stale detector looks like - the voice it was fit on has moved on.")
            print("Refresh the AI side and retrain: bench/fetch_github_docs.py ai, then retrain.py")
        else:
            print(f"\ndrift in {genre}: incoming drafts score {change:.2f} higher than they used to.")
            print("Either the drafts really are more machine-like, or the detector has grown trigger-happy.")
            print("Check false alarms on known human text before trusting it: bench/holdouts.py, if you have the held-out docs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default=STORE)
    sub = parser.add_subparsers(dest="command", required=True)

    a = sub.add_parser("add", help="record one humanize run")
    a.add_argument("--draft", required=True)
    a.add_argument("--rewrite", required=True)
    a.add_argument("--genre", required=True)
    a.add_argument("--before", type=float, required=True)
    a.add_argument("--after", type=float, required=True)
    a.add_argument("--rounds", type=int, required=True)
    a.add_argument("--heldout", type=float)
    a.add_argument("--moves")
    a.add_argument("--note")
    a.add_argument("--at", default=None)
    a.set_defaults(run=add)

    q = sub.add_parser("queue", help="drafts waiting for an author you can state")
    q.add_argument("limit", nargs="?", type=int, default=10)
    q.set_defaults(run=queue)

    s = sub.add_parser("stats", help="score drift over time, which is how staleness shows up")
    s.set_defaults(run=stats)

    args = parser.parse_args()
    if getattr(args, "at", None) is None and args.command == "add":
        import datetime

        args.at = datetime.datetime.now().replace(microsecond=0).isoformat()
    args.run(args)


if __name__ == "__main__":
    sys.exit(main())

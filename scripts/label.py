# Save a text whose author you know, so the next retrain can learn from it. Labels come only from the user.
# Usage: label.py add FILE (--human | --ai) [--genre docs|prose] [--note TEXT]
#        label.py list
#        label.py remove ID
import argparse
import datetime
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detect import MIN_DOC_WORDS, WORD, canon, pick_genre, prepare, split_sentences, style_features  # noqa: E402

STORE = os.path.expanduser("~/.cache/humanize/data/feedback.jsonl")
# which training rows build_set.py makes: docs sections, one prose row, or both
DOMAIN = {"docs": "docs", "prose": "feedback", "both": "both"}


def guess_genre(text, path):
    # the route detect.py takes, so the label trains the blend that actually scores this text
    genre = pick_genre(text, "auto", path)
    if genre == "both":
        prose = canon(prepare(text))
        if len(WORD.findall(prose)) < MIN_DOC_WORDS or style_features(prose)["first_person_rate"] >= 1.0:
            genre = "prose"
    return genre


def load():
    return [json.loads(line) for line in open(STORE)] if os.path.exists(STORE) else []


def save(items):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w") as f:
        for item in items:
            f.write(json.dumps(item) + "\n")
    os.replace(tmp, STORE)


def main():
    parser = argparse.ArgumentParser(description="label texts for the humanize detector")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("file")
    who = add.add_mutually_exclusive_group(required=True)
    who.add_argument("--human", action="store_true", help="a person wrote it without AI help")
    who.add_argument("--ai", action="store_true", help="an AI wrote it, edited or not")
    add.add_argument("--genre", choices=["docs", "prose", "both"])
    add.add_argument("--note", default="")
    sub.add_parser("list")
    remove = sub.add_parser("remove")
    remove.add_argument("id")
    args = parser.parse_args()

    items = load()
    if args.command == "add":
        text = open(args.file).read()
        if not split_sentences(canon(text)):
            sys.exit(f"nothing to label in {args.file}")
        genre = args.genre or guess_genre(text, args.file)
        item = {
            "id": hashlib.sha1(text.encode()).hexdigest()[:10],
            "text": text,
            "label": 0 if args.human else 1,
            "domain": DOMAIN[genre],
            "origin": os.path.abspath(args.file),
            "note": args.note,
            "labelled_at": datetime.date.today().isoformat(),
        }
        # labelling the same text again replaces the old label
        items = [i for i in items if i["id"] != item["id"]] + [item]
        save(items)
        print(f"saved {item['id']}: {'human' if args.human else 'AI'} {genre}, {len(text.split())} words, {len(items)} labels in total")
    elif args.command == "remove":
        kept = [i for i in items if i["id"] != args.id]
        save(kept)
        print(f"removed {len(items) - len(kept)} label(s)")
    else:
        for i in items:
            print(f"{i['id']}  {'human' if i['label'] == 0 else 'AI   '}  {i['domain']:<8}  {len(i['text'].split()):>6} words  {i['labelled_at']}  {i['origin']}  {i['note']}")
        print(f"{len(items)} labels ({sum(1 for i in items if i['label'] == 0)} human, {sum(1 for i in items if i['label'] == 1)} AI)")


if __name__ == "__main__":
    main()

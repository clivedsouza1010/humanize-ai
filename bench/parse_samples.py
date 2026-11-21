# Turn writing-agent reports into the job shape import_default_samples.py already reads.
# The agents are Explore type so they don't inherit a CLAUDE.md, which means they can't write
# files; their text arrives in the report and lands here.
# Usage: parse_samples.py OUT.json --model haiku --kind prose REPORT.txt [REPORT.txt ...]
#        parse_samples.py OUT.json --model opus --kind docs --register marketing REPORT.txt
import argparse
import json
import os
import re
import sys

# Agents close the block with two or three angle brackets. Both are the same token.
BLOCK = re.compile(r"<<<PIECE\s+genre=([a-z-]+)\s*>>>\n(.*?)\n<<<END>{2,3}", re.S)
MIN_WORDS = 60


def pieces(paths):
    found, dropped = [], 0
    for path in paths:
        for genre, text in BLOCK.findall(open(path).read()):
            text = text.strip()
            if len(text.split()) < MIN_WORDS:
                dropped += 1
                continue
            found.append((genre, text))
    return found, dropped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out")
    parser.add_argument("--model", required=True)
    parser.add_argument("--kind", required=True, choices=["prose", "docs"])
    parser.add_argument("--register", default="default")
    parser.add_argument("--batch", default="1")
    parser.add_argument("reports", nargs="+")
    args = parser.parse_args()

    found, dropped = pieces(args.reports)
    if dropped:
        print(f"dropped {dropped} piece(s) under {MIN_WORDS} words")
    if not found:
        sys.exit("no pieces found; refusing to write an empty job")

    if args.kind == "docs":
        items = [{"text": text, "doc_type": genre} for genre, text in found]
    else:
        items = [{"text": text, "genre": genre} for genre, text in found]

    # import_default_samples.py reads the register out of key.split("-")[1]
    job = {"model": args.model, "kind": args.kind, "key": f"{args.kind}-{args.register}-{args.batch}", "items": items}

    existing = json.load(open(args.out))["result"] if os.path.exists(args.out) else []
    json.dump({"result": existing + [job]}, open(args.out, "w"), indent=1)
    print(f"{len(items)} piece(s) from {args.model} ({args.kind}) -> {args.out}")


if __name__ == "__main__":
    main()

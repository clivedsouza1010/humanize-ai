# What each promotion did to the false-alarm rate on the held-out human docs, which is the number the gate's
# sixth check reads. Scores the same docs with several saved blends, so a tolerance comes from measurement
# rather than a guess, and so a regression can be traced to the promotion that caused it.
# Usage: python score_blend_versions.py [VERSION ...]   (default: every saved version, oldest first)
import json, os, sys
import numpy as np
BENCH = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(BENCH), "scripts")
sys.path.insert(0, BENCH)
sys.path.insert(0, SCRIPTS)
from build_set import doc_rows
from detect import MIN_VERDICT_WORDS, canon, link_excess, voice_score, voice_terms

D = os.path.expanduser("~/.cache/humanize/data/github")
HIST = os.path.join(SCRIPTS, "blend-history")
BLEND = os.path.join(SCRIPTS, "blend.json")
read = lambda n: [json.loads(l) for l in open(os.path.join(D, n))]


from holdouts import human_holdout, rates  # noqa: E402


def main():
    items = human_holdout(D)
    asked = sys.argv[1:]
    saved = sorted(f[:-5] for f in os.listdir(HIST) if f.endswith(".json")) if os.path.isdir(HIST) else []
    versions = asked or saved + ["now"]
    print(f"{len(items)} held-out human docs, scored by each saved blend")
    print(f"\n{'blend':<18} {'docs':>5} {'called AI':>10} {'sections':>9} {'change':>8}")
    last = None
    for v in versions:
        path = BLEND if v == "now" else os.path.join(HIST, f"{v}.json")
        if not os.path.exists(path):
            print(f"{v:<18} no such version")
            continue
        blend = json.load(open(path)).get("docs", {})
        # a version from before the docs blend carried an ngram table cannot be scored this way
        if "ngram" not in blend:
            print(f"{v:<18} no docs ngram table, nothing to score")
            continue
        n, called, sections = rates(blend, items)
        print(f"{v:<18} {n:>5} {called:>10.3f} {sections:>9.3f} {'' if last is None else f'{called - last:+.3f}':>8}")
        last = called


if __name__ == "__main__":
    main()

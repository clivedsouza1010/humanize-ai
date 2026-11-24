# Score docs that never trained: the check on false alarms for people writing after 2023, and on AI text
# from outside the training sources. bench/retrain.py imports rates() and human_holdout() from here, so
# the gate's sixth check and this table are the same measurement rather than two that can drift apart.
# Usage: python holdouts.py [DATA_DIR]
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "plugin", "skills", "humanize-ai", "scripts"))
from build_set import doc_rows  # noqa: E402
from detect import canon, link_excess, load_blends, voice_score, voice_terms  # noqa: E402

# a document counts as AI when a quarter of its words sit in sections at 0.5 or more, the rule detect.py applies
DOC_SHARE = 0.25
DOC_MIN_WORDS = 120
SECTION_MIN_WORDS = 80
MAX_SECTIONS = 6


def prob(blend, row):
    table = blend["ngram"]
    z = voice_score(voice_terms(canon(row["text"]), table["closed"]), table) - blend["link_credit"] * link_excess(row["ext_rate"], blend["link_cap"])
    return 1 / (1 + np.exp(-z))


def called_ai(sections):
    counted = [(p, n) for p, n in sections if n >= DOC_MIN_WORDS] or sections
    return sum(n for p, n in counted if p >= 0.5) / max(sum(n for _, n in counted), 1) >= DOC_SHARE


def scored(blend, items):
    # each document as its section scores, dropping sections too short to judge and documents left with none
    out = []
    for item in items:
        doc = [(prob(blend, r), len(r["text"].split())) for r in doc_rows(item["text"], 0, "", "", "", "")[:MAX_SECTIONS]
               if len(r["text"].split()) >= SECTION_MIN_WORDS]
        if doc:
            out.append(doc)
    return out


def rates(blend, items):
    # documents scored, the share called AI, and the share of sections flagged
    docs = scored(blend, items)
    if not docs:
        return 0, None, None
    sections = [p for doc in docs for p, _ in doc]
    return len(docs), float(np.mean([called_ai(d) for d in docs])), float(np.mean(np.array(sections) >= 0.5))


def human_holdout(github):
    # The strongest human provenance in the repo that never trains: docs a project gained after it banned AI
    # contributions, and the docs a disclosure project already had on the day its policy took effect. The
    # date-window batch is deliberately left out — a window is not provenance, so a rise there could as
    # easily be AI being caught, and this set has to mean false alarms and nothing else.
    read = lambda name: [json.loads(line) for line in open(os.path.join(github, name))]
    out = []
    for policies, docs in (("policies.json", "policy.jsonl"), ("policies-train.json", "policy-train.jsonl")):
        if not (os.path.exists(os.path.join(github, docs)) and os.path.exists(os.path.join(github, policies))):
            continue
        kinds = {p["repo"]: p["kind"] for p in json.load(open(os.path.join(github, policies)))["projects"]}
        out += [i for i in read(docs) if kinds.get(i["repo"]) == "ban"]
    control = os.path.join(github, "pr-control.jsonl")
    if os.path.exists(control):
        out += [i for i in read("pr-control.jsonl") if i["before"] != "2022-11-01"]
    return out


def main():
    data = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.cache/humanize/data")
    github = os.path.join(data, "github")
    missing = [n for n in ("recent.jsonl", "policies.json", "policy.jsonl") if not os.path.exists(os.path.join(github, n))]
    if missing:
        sys.exit(f"holdouts.py scores the maintainer's held-out docs in {github}, which don't ship with the skill; "
                 f"missing: {', '.join(missing)}")
    blend = load_blends("docs")["docs"]
    read = lambda name: [json.loads(line) for line in open(os.path.join(github, name))]
    show = lambda name, items: print("| {} | {} | {:.3f} | {:.3f} |".format(name, *rates(blend, items)))
    recent = read("recent.jsonl")
    kinds = {p["repo"]: p["kind"] for p in json.load(open(os.path.join(github, "policies.json")))["projects"]}
    policy = read("policy.jsonl")
    print("| docs | docs scored | called AI | sections flagged |\n|---|---|---|---|")
    show("new docs, Jun 2024 to Jun 2025", [i for i in recent if i["window"] == "2024"])
    show("projects that ban AI, 2024-26", [i for i in policy if kinds[i["repo"]] == "ban"])
    show("projects that require AI disclosure, 2025-26", [i for i in policy if kinds[i["repo"]] == "disclosure"])
    # the 2026-11-11 batch, kept back for the same reason: a disclosure rule permits AI, so its window is a mixture
    train = os.path.join(github, "policy-train.jsonl")
    if os.path.exists(train):
        more_kinds = {p["repo"]: p["kind"] for p in json.load(open(os.path.join(github, "policies-train.json")))["projects"]}
        more = read("policy-train.jsonl")
        show("more projects that ban AI, 2025-26", [i for i in more if more_kinds[i["repo"]] == "ban"])
        show("more that require AI disclosure, 2025-26", [i for i in more if more_kinds[i["repo"]] == "disclosure"])
    if os.path.exists(os.path.join(github, "homebrew-disclosed.jsonl")):
        show("Homebrew PRs that disclosed AI, 2026", [i for i in read("homebrew-disclosed.jsonl") if i["label"] == "ai"])
    # The docs each disclosure project had on the day its policy took effect. These never train, and they
    # are what makes a flag rate on one of those projects readable: it runs from 0.000 to 0.417 across them,
    # so a pooled number says nothing. pr-docs.jsonl itself trains now, and its before-training numbers are
    # in REPORT.md rather than here, because a holdout cannot be text the detector learned from.
    control = os.path.join(github, "pr-control.jsonl")
    if os.path.exists(control):
        own = [i for i in read("pr-control.jsonl") if i["before"] != "2022-11-01"]
        show("disclosure projects' own docs, the day the policy took effect", own)
        print("\nthe same docs per project, which is the only way the rate is readable")
        print("| docs | docs scored | called AI | sections flagged |\n|---|---|---|---|")
        for repo in sorted({i["repo"] for i in own}):
            show(repo.split("/")[-1], [i for i in own if i["repo"] == repo])
    # what the gate's sixth check reads, pooled over both kinds, so the refusal can be reproduced by hand
    both = human_holdout(github)
    n, called, sections = rates(blend, both)
    print(f"\nthe gate's sixth check reads these {n} docs pooled: {called:.3f} called AI, {sections:.3f} of sections flagged")


if __name__ == "__main__":
    main()

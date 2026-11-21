# Make AI docs on the same projects as the human ones, so a project's topic can't give the label away.
# Usage: python paired_docs.py briefs DATA_DIR BATCHES [PER_BATCH]   write briefs for the writing agents
#        python paired_docs.py import DATA_DIR WORKFLOW_OUTPUT.json  save what they wrote to github/paired.jsonl
import html
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from detect import WORD, doc_prose  # noqa: E402

# the doc types the wild AI set is short of
MIX = {"readme": 0.3, "package-readme": 0.16, "contributing": 0.16, "changelog": 0.12, "blog": 0.12, "guide": 0.08, "security": 0.06}
MAX_REPO_BRIEFS = 2
MIN_WORDS = 200


def headings(markdown):
    # fences first, or a shell comment reads as a heading
    text = re.sub(r"(?ms)^(```|~~~).*?^\1", "", markdown)
    return [h.strip(" #") for h in re.findall(r"(?m)^#{2,6} .+$", text)][:12]


def briefs(data_dir, batches, per_batch):
    rng = random.Random(41)
    docs = [json.loads(line) for line in open(os.path.join(data_dir, "github", "human.jsonl"))]
    rng.shuffle(docs)
    wanted = {kind: round(share * batches * per_batch) for kind, share in MIX.items()}
    picked, per_repo = [], {}
    for doc in docs:
        kind = doc["doc_type"]
        if wanted.get(kind, 0) == 0 or per_repo.get(doc["repo"], 0) >= MAX_REPO_BRIEFS:
            continue
        prose = doc_prose(doc["text"])
        if len(WORD.findall(prose)) < MIN_WORDS:
            continue
        picked.append({"project": doc["repo"], "path": doc["path"], "doc_type": kind, "intro": " ".join(prose.split()[:45]),
                       # half get the human doc's outline, half decide their own
                       "outline": headings(doc["text"]) if len(picked) % 2 == 0 else []})
        wanted[kind] -= 1
        per_repo[doc["repo"]] = per_repo.get(doc["repo"], 0) + 1
    print(f"{len(picked)} briefs, short by {wanted}")
    rng.shuffle(picked)
    os.makedirs(os.path.join(data_dir, "round"), exist_ok=True)
    for n in range(batches):
        chunk = [dict(item, id=i) for i, item in enumerate(picked[n::batches])]
        json.dump(chunk, open(os.path.join(data_dir, "round", f"briefs-{n}.json"), "w"), indent=1)


def imported(data_dir, output):
    made = 0
    with open(os.path.join(data_dir, "github", "paired.jsonl"), "w") as out:
        for job in json.load(open(output))["result"]:
            brief = {b["id"]: b for b in json.load(open(os.path.join(data_dir, "round", f"briefs-{job['batch']}.json")))}
            for item in job["docs"]:
                source = brief[item["id"]]
                out.write(json.dumps({"repo": source["project"], "path": source["path"], "doc_type": source["doc_type"],
                                      "tool": f"claude-{job['model']}", "outlined": bool(source["outline"]), "text": html.unescape(item["text"])}) + "\n")
                made += 1
    print(f"github/paired.jsonl: {made} docs")


if __name__ == "__main__":
    if sys.argv[1] == "briefs":
        briefs(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 14)
    else:
        imported(sys.argv[2], sys.argv[3])

# Merge RAID, HC3 Reddit, Enron emails, Hacker News, Wikipedia, docs and Claude samples into one labelled set with a fixed split.
# Usage: python build_set.py DATA_DIR OUT.jsonl
import glob
import hashlib
import json
import os
import random
import re
import sys

import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "plugin", "skills", "humanize-ai", "scripts"))
from detect import MIN_VERDICT_WORDS, WORD, canon, doc_prose, doc_sections, external_link_rate, prepare, split_sentences  # noqa: E402
from fetch_github_docs import doc_type  # noqa: E402

# tokenizer and markup residue that only HC3's human answers carry
HC3_RESIDUE = re.compile(r"URL_\d|\* \*|\[ |\] \(|\w / \w|(^|\s)' \S|\b(do|does|did|is|are|was|ca|wo|could|would|should) nt\b| ’")
# chat-model preambles that echo the prompt; only AI rows have them
ECHO = re.compile(r"^\s*(sure|certainly|of course|absolutely|great question)\b[,!.]|^\s*here('s| is)\b[^.!?]*:|^\s*(title|abstract|introduction)\s*:", re.I)
# `spaced markup` needs a word beside the stars. Bare `* *` also reads cron lines, C comments and email
# dividers, which both labels write, and the gate cannot ask anyone to clean those out.
ARTIFACTS = {"URL_n": r"URL_\d", "literal \\n": r"\\n", "spaced markup": r"\*\s\*(?=\w)|(?<=\w)\*\s\*",
             "carriage return": "\r", "space before punctuation": r"\s[.,;](?=\s|$)"}
# markup that survived extraction would label old human READMEs for free
DOC_ARTIFACTS = {"reference badge": r"!\[[^\]]*\]\[[^\]]*\]", "indented code": r"(?m)^( {4}|\t)\S", "copyright": r"(?i)copyright|©",
                 "setext underline": r"(?m)^(=+|-+)\s*$", "pipe table": r"(?m)^\s*\|.*\|\s*$"}


# One label carrying ten times the other is format, not voice. The set itself runs 3.94 human rows to
# every AI row (9,971 to 2,528 on 2026-11-13), so a pattern both labels write at the same rate lands
# nowhere near ten and the ratio has room to move before anyone has to touch this number.
# The test used to be min == 0, which stayed quiet on the spacing gap: pooled over prose and docs it
# read human 53, ai 2, and those two AI rows were enough to wave through a 48-to-0 split in prose.
def one_sided(counts):
    return max(counts) >= 5 and min(counts) < max(counts) / 10


# A space before punctuation ("the place .") is a typing and extraction habit, not a voice: it sat on
# 1.75% of human prose rows and 0.00% of AI rows, which let the detector read spacing as a label.
# Same rule as detect.py's docs path, applied here to every source and both labels at once.
PUNCT_GAP = re.compile(r"[ \t]+([.,;:!?])(?=\s|$|[\"')\]])")
# AESLC splits one sentence per line, so a typed "..." or a stray "?" lands on a line of its own.
# A line that goes on to carry text is left alone: ": text" opening a paragraph is doc_prose
# dropping a bold label, or AESLC breaking after "P.S.", and both labels have those.
LONE_PUNCT = re.compile(r"(?<!\n)\n[ \t]*([.,;:!?]+)[ \t]*(?=\n|$)")
# nothing in English opens a line on a comma, so these come back even with text behind them
LINE_PUNCT = re.compile(r"\n[ \t]*([.,;])(?=\s|$|[\"')\]])")
CLITIC = re.compile(r"[ \t]+(n't|'s|'re|'ve|'ll|'d|'m)\b", re.I)


def close_gaps(text):
    # the lookahead only closes a gap before punctuation that ends a word, so ".env" stays whole
    text = LINE_PUNCT.sub(r"\1", LONE_PUNCT.sub(r"\1", PUNCT_GAP.sub(r"\1", text)))
    return CLITIC.sub(r"\1", text)


# fit.py trains on the first 4 sections of a doc; a few more keep the whole-document table honest
MAX_GITHUB_SECTIONS = 6
# docs from these windows never train: some are AI-assisted, and they're the check on false alarms for people writing after 2023
KEPT_BACK = {"2024", "policy"}
# a pull request that declared whether AI wrote it carries its own label
PROVENANCE = {"ai": 1, "human": 0}
# The pull-request-labelled docs train, by the maintainer's choice on 2026-11-11. Nothing is held back here now:
# the 41 AI docs were the only controlled read in the repo on recent AI docs, and training on them spends
# that. The before-training numbers are in REPORT.md, and the 168 pre-policy control docs in
# pr-control.jsonl stay out of the set, so bench/holdouts.py still has a baseline for these nine projects.
PR_HELD_BACK = set()


def detokenize(text):
    # HC3 human answers are space-tokenized ("you 're", "end .") which would give the label away
    text = re.sub(r'" ([^"]*?) "', r'"\1"', text)
    text = re.sub(r"\( ([^)]*?) \)", r"(\1)", text)
    text = close_gaps(re.sub(r" %", "%", text))
    text = re.sub(r"(\w) - (\w)", r"\1-\2", text)
    text = re.sub(r"# (\d)", r"#\1", text)
    text = re.sub(r"\$ (\d)", r"$\1", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def words_ok(text):
    return 60 <= len(text.split()) <= 350


def hc3_rows(path, n, rng):
    lines = open(path).read().splitlines()
    rng.shuffle(lines)
    rows = []
    for line in lines:
        item = json.loads(line)
        human = [detokenize(a) for a in item["human_answers"] if not HC3_RESIDUE.search(a)]
        human = [a for a in human if words_ok(a)]
        bot = [a.replace("\\n", "\n").replace("\r", "").strip() for a in item["chatgpt_answers"]]
        bot = [a for a in bot if words_ok(a)]
        if not human or not bot:
            continue
        group = f"hc3:{item['question'][:120]}"
        rows.append({"text": human[0], "label": 0, "source": "hc3", "model": "human", "domain": "reddit", "group": group})
        rows.append({"text": bot[0], "label": 1, "source": "hc3", "model": "chatgpt", "domain": "reddit", "group": group})
        if len(rows) >= 2 * n:
            break
    return rows


def parquet_rows(path, column, n, rng, source, domain, fix=lambda t: t):
    texts = [fix(t) for t in pq.read_table(path, columns=[column]).column(column).to_pylist()]
    texts = [t.strip() for t in texts if t and words_ok(t)]
    rng.shuffle(texts)
    return [{"text": t, "label": 0, "source": source, "model": "human", "domain": domain, "group": f"{source}:{i}"} for i, t in enumerate(texts[:n])]


def doc_rows(markdown, label, source, model, group, register):
    # human and AI docs go through the same steps: markdown to prose, then every ~300-word section, numbered
    sections = [s for s in doc_sections(doc_prose(markdown)) if len(s.split()) >= 40]
    # 'group' keeps a repo together for the split; 'doc' tells its files apart, and the link rate is the whole doc's
    doc, ext_rate = hashlib.sha1(markdown.encode()).hexdigest()[:12], external_link_rate(markdown)
    return [{"text": s, "label": label, "source": source, "model": model, "domain": "docs", "group": group, "doc": doc, "ext_rate": ext_rate,
             "section": i, "register": register} for i, s in enumerate(sections)]


def ai_doc_rows(item, source, group, register):
    rows = doc_rows(item["text"], 1, source, item["model"], group, register)
    for row in rows:
        row["doc_type"] = item.get("doc_type", "readme")
    return rows


def github_rows(path, label, source):
    # one repo stays on one side of the split, because a project's docs share a voice
    rows = []
    for line in open(path):
        item = json.loads(line)
        # label None means the row says which side it is on, from what its pull request declared
        side = PROVENANCE[item["provenance"]] if label is None else label
        # a provenance row keeps the type its fetcher gave it. Re-deriving it here would drop the docs a
        # project-wide policy covers but the path rule does not know about, like OWASP's cheatsheets/.
        if label is None:
            if item["repo"] in PR_HELD_BACK:
                continue
        elif not doc_type(item["path"]) or item.get("window") in KEPT_BACK:
            continue
        # only the AI side of a provenance source trains: its human side is one doc, which is not a label
        if label is None and side == 0:
            continue
        model = item.get("tool") or ("declared-ai" if side else "human")
        made = doc_rows(item["text"], side, source, model, f"gh:{item['repo']}", item["doc_type"])[:MAX_GITHUB_SECTIONS]
        rows += [row | {"doc_type": item["doc_type"], "repo": item["repo"], "date": item.get("date")} for row in made]
    return rows


def main():
    data_dir, out_path = sys.argv[1], sys.argv[2]
    rng = random.Random(11)
    eval_drafts = {canon(open(p).read()) for p in glob.glob(os.path.join(HERE, "..", "evals", "*", "files", "draft.txt"))}
    retired = {line.split()[0] for line in open(os.path.join(HERE, "retired-eval-drafts.txt")) if line.strip() and not line.startswith("#")}
    is_eval = lambda text: canon(text) in eval_drafts or hashlib.sha1(canon(text).encode()).hexdigest() in retired  # noqa: E731

    rows = [json.loads(line) for line in open(os.path.join(data_dir, "raid.jsonl"))]
    for i, row in enumerate(rows):
        row["group"] = f"raid:{i}"
    rows += hc3_rows(os.path.join(data_dir, "reddit_eli5.jsonl"), 150, rng)
    # A pure-human source, so its cap is the one lever that rebalances a set the AI side keeps growing.
    # hc3 is deliberately not raised with it: it yields a chatgpt answer beside every human one.
    rows += parquet_rows(os.path.join(data_dir, "aeslc-test.parquet"), "email_body", 300, rng, "aeslc", "email")
    # Hacker News comments and Ask HN posts from 2024 on, one per author, accounts older than
    # ChatGPT. Every other human source here predates 2023, which put the human side of the set
    # a calendar apart from the AI side. fetch_hn.py has the filters and what they are for.
    hn = os.path.join(data_dir, "hn.jsonl")
    if os.path.exists(hn):
        rows += [json.loads(line) for line in open(hn)]
    # Wikipedia article prose from 2023 on by editors who registered before ChatGPT. The human
    # side's declarative third-person register is 2004 wire copy, and that is the register the
    # detector reads as AI. fetch_wikipedia.py has the filters and what each one is for.
    wikipedia = os.path.join(data_dir, "wikipedia.jsonl")
    if os.path.exists(wikipedia):
        rows += [json.loads(line) for line in open(wikipedia)]
    for name, source in [("npm-docs.jsonl", "npm"), ("npm-docs-popular.jsonl", "npm-popular")]:
        path = os.path.join(data_dir, name)
        if os.path.exists(path):
            for line in open(path):
                item = json.loads(line)
                rows += doc_rows(item["readme"], 0, source, "human", f"npm:{item['name']}", source)
    # claude-*.jsonl were written by agents that had a house style guide; default-*.jsonl by agents without it
    for path in sorted(glob.glob(os.path.join(data_dir, "claude-*.jsonl"))):
        for i, line in enumerate(open(path)):
            if not line.strip():
                continue
            row = json.loads(line)
            group = f"{os.path.basename(path)}:{i}"
            if is_eval(row["text"]):
                continue
            if row.get("domain") == "docs":
                rows += ai_doc_rows(row, "claude", group, "styled")
            else:
                row["group"] = group
                rows.append(row)
    for name, label, source in (("human.jsonl", 0, "gh-human"), ("recent.jsonl", 0, "gh-2023"), ("ai.jsonl", 1, "gh-ai"),
                                ("paired.jsonl", 1, "gh-paired"), ("workhorse.jsonl", 0, "gh-workhorse"),
                                ("pr-docs.jsonl", None, "gh-declared")):
        path = os.path.join(data_dir, "github", name)
        if os.path.exists(path):
            rows += github_rows(path, label, source)
    # texts whose author the user confirmed with label.py
    feedback = os.path.join(data_dir, "feedback.jsonl")
    if os.path.exists(feedback):
        for line in open(feedback):
            item = json.loads(line)
            model = "human" if item["label"] == 0 else "labelled-ai"
            group = f"feedback:{item['id']}"
            made = []
            # a 'both' label is scored by both blends, so it trains both
            if item["domain"] in ("docs", "both"):
                made += doc_rows(item["text"], item["label"], "feedback", model, group, "feedback")
            if item["domain"] != "docs":
                # cut up the way detect.py scores it; under 80 words it gets no verdict, so it can't teach one
                made += [{"text": section, "label": item["label"], "source": "feedback", "model": model,
                          "domain": "feedback", "group": group, "section": i}
                         for i, section in enumerate(doc_sections(prepare(item["text"])))
                         if len(WORD.findall(section)) >= MIN_VERDICT_WORDS]
            if not made:
                print(f"label {item['id']} has too little prose to train on", file=sys.stderr)
            rows += made
    # Each generation round is its own source. Appending to an existing file would read as
    # nothing new to the retrain gate, which only refits a genre that has an unseen source.
    for name, source in (("default-docs.jsonl", "claude-default"), ("default-prose.jsonl", "claude-default"),
                         ("default-prose-2.jsonl", "claude-default-2")):
        path = os.path.join(data_dir, name)
        if not os.path.exists(path):
            continue
        for i, line in enumerate(open(path)):
            row = json.loads(line)
            group = f"{name}:{i}"
            if row["domain"] == "docs":
                rows += ai_doc_rows(row, source, group, row["register"])
            else:
                row |= {"label": 1, "source": source, "group": group}
                rows.append(row)

    # the humanizer evals must never be trained on
    rows = [r for r in rows if not is_eval(r["text"])]
    echo_human = sum(1 for r in rows if r["label"] == 0 and ECHO.search(split_sentences(canon(r["text"]))[0]))
    # the user's own labels stay: they said who wrote it, however it opens
    rows = [r for r in rows if r["source"] == "feedback" or not (r["label"] == 1 and ECHO.search(split_sentences(canon(r["text"]))[0]))]
    print(f"eval drafts excluded: {len(eval_drafts)} (+{len(retired)} retired), human rows matching the echo pattern: {echo_human}", file=sys.stderr)

    # one pass over every row, so no source or label can carry a spacing habit the others lack
    for row in rows:
        row["text"] = close_gaps(row["text"])

    for name, pattern in ARTIFACTS.items():
        counts = [sum(1 for r in rows if r["label"] == label and re.search(pattern, r["text"])) for label in (0, 1)]
        print(f"artifact {name}: human {counts[0]}, ai {counts[1]}", file=sys.stderr)
        if one_sided(counts):
            sys.exit(f"artifact '{name}' is one-sided ({counts[0]} human, {counts[1]} ai); clean it before fitting")
    docs = [r for r in rows if r["domain"] == "docs"]
    for name, pattern in DOC_ARTIFACTS.items():
        counts = [sum(1 for r in docs if r["label"] == label and re.search(pattern, r["text"])) for label in (0, 1)]
        print(f"doc artifact {name}: human {counts[0]}, ai {counts[1]}", file=sys.stderr)
        if max(counts) >= 5:
            sys.exit(f"doc artifact '{name}' survived extraction; fix doc_prose before fitting")

    # a hash of the group decides the split, so adding data never moves an existing row between train and test
    for row in rows:
        if row.get("split") != "extra":
            share = 0.4 if row["source"].startswith("claude") else 0.3
            row["split"] = "test" if int(hashlib.sha1(row["group"].encode()).hexdigest(), 16) % 1000 < share * 1000 else "train"

    with open(out_path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    # the facts check needs to know everyday modern words; the 1934 system dictionary lacks "proud" and "email"
    counts = {}
    for row in rows:
        # the user's own labelled texts stay out, so their project's words never ship in the list
        if row["source"] == "feedback":
            continue
        # only words written in lowercase, so names never make the list
        for word in re.findall(r"(?<![\w'-])[a-z][a-z'-]*[a-z]", canon(row["text"])):
            counts[word] = counts.get(word, 0) + 1
    with open(os.path.join(HERE, "..", "plugin", "skills", "humanize-ai", "scripts", "words.txt"), "w") as f:
        f.write("\n".join(sorted(w for w, n in counts.items() if n >= 3)) + "\n")
    summary = {}
    for row in rows:
        key = (row["source"], row["label"], row["split"])
        summary[key] = summary.get(key, 0) + 1
    for key in sorted(summary):
        print(key, summary[key], file=sys.stderr)


if __name__ == "__main__":
    main()

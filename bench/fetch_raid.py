# Sample human vs chat-model text (no attacks) from RAID's parquet, reading only random row groups.
# Usage: python fetch_raid.py OUT.jsonl [per_domain=120]
import json
import random
import re
import sys

import pyarrow.parquet as pq
from huggingface_hub import HfFileSystem

ROOT = "datasets/liamdugan/raid@~parquet/raid/partial-train"
DOMAINS = ["abstracts", "books", "news"]
CHAT_MODELS = {"chatgpt", "gpt4", "llama-chat", "mistral-chat", "mpt-chat", "cohere-chat"}


def clean(text, domain):
    # abstracts are hard-wrapped at ~80 columns
    if domain == "abstracts":
        text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    words = text.split(" ")
    if len(words) > 320:
        cut = " ".join(words[:320])
        end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
        text = cut[: end + 1] if end > 200 else cut
    return text


def main():
    out_path = sys.argv[1]
    per_domain = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    rng = random.Random(7)
    fs = HfFileSystem()

    groups = {d: [] for d in DOMAINS}
    files = {}
    for path in fs.ls(ROOT, detail=False):
        files[path] = pq.ParquetFile(fs.open(path))
        md = files[path].metadata
        di = [md.schema.column(i).name for i in range(md.num_columns)].index("domain")
        for r in range(md.num_row_groups):
            stats = md.row_group(r).column(di).statistics
            if stats.min == stats.max and stats.min in groups:
                groups[stats.min].append((path, r))

    rows = []
    seen_sources = set()
    for domain in DOMAINS:
        human, ai = [], []
        per_model = {}
        candidates = groups[domain][:]
        rng.shuffle(candidates)
        for path, r in candidates:
            if len(human) >= per_domain and len(ai) >= per_domain:
                break
            table = files[path].read_row_group(r).to_pylist()
            rng.shuffle(table)
            for row in table:
                if row["attack"] != "none" or not row["generation"]:
                    continue
                text = clean(row["generation"], domain)
                if len(text.split()) < 60:
                    continue
                model = row["model"]
                if model == "human" and len(human) < per_domain and row["source_id"] not in seen_sources:
                    seen_sources.add(row["source_id"])
                    human.append({"text": text, "label": 0, "source": "raid", "model": "human", "domain": domain})
                elif model in CHAT_MODELS and row["repetition_penalty"] in ("no", None) and len(ai) < per_domain:
                    # spread AI rows across models
                    if per_model.get(model, 0) >= per_domain // 3:
                        continue
                    per_model[model] = per_model.get(model, 0) + 1
                    ai.append({"text": text, "label": 1, "source": "raid", "model": model, "domain": domain})
        print(f"{domain}: human {len(human)}, ai {len(ai)} {per_model}", file=sys.stderr)
        rows += human + ai

    with open(out_path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    print(f"wrote {len(rows)} rows to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()

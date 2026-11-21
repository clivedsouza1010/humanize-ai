# Turn the default-style writing workflows' output into default-docs.jsonl and default-prose.jsonl.
# Usage: python import_default_samples.py DATA_DIR WORKFLOW_OUTPUT.json [MORE_OUTPUT.json ...]
import json
import os
import sys

REGISTERS = {"default": "default", "marketing": "marketing", "long": "long", "formal": "formal", "personal": "personal"}


def main():
    data_dir = sys.argv[1]
    result = [job for path in sys.argv[2:] for job in json.load(open(path))["result"]]
    docs, prose = [], []
    for job in result:
        model = f"claude-{job['model']}"
        if job["kind"] == "docs":
            register = REGISTERS[job["key"].split("-")[1]]
            for item in job["items"]:
                docs.append({"text": item["text"], "label": 1, "source": "claude-default", "model": model,
                             "domain": "docs", "doc_type": item["doc_type"], "register": register})
        else:
            for item in job["items"]:
                prose.append({"text": item["text"], "label": 1, "source": "claude-default", "model": model, "domain": item["genre"]})
    for name, rows in [("default-docs.jsonl", docs), ("default-prose.jsonl", prose)]:
        with open(os.path.join(data_dir, name), "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        print(f"{name}: {len(rows)} rows")


if __name__ == "__main__":
    main()

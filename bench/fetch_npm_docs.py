# Fetch READMEs of less popular npm packages whose latest release predates ChatGPT, as human-written docs.
# Usage: python fetch_npm_docs.py OUT.jsonl [target=400] [lower|upper]
import json
import random
import sys
import time
import urllib.parse
import urllib.request

KEYWORDS = [
    "parser", "logger", "color", "date", "validation", "cli", "http", "middleware", "markdown", "csv",
    "image", "crypto", "testing", "config", "cache", "queue", "stream", "template", "router", "orm",
    "websocket", "react-component", "webpack-plugin", "eslint-plugin", "graphql", "i18n", "pdf", "email",
    "geolocation", "animation", "chart", "audio", "compression", "diff", "scraper", "oauth", "uuid", "slug",
]
CUTOFF = "2022-06-01"


def get_json(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return json.load(resp)
        except Exception as err:
            print(f"  retry {attempt + 1} {url}: {err}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    return None


def main():
    out_path = sys.argv[1]
    target = int(sys.argv[2]) if len(sys.argv) > 2 else 400
    half = sys.argv[3] if len(sys.argv) > 3 else "lower"
    candidates = {}
    for keyword in KEYWORDS:
        query = urllib.parse.urlencode({"text": f"keywords:{keyword}", "size": 250, "popularity": 0.2, "quality": 0.8, "maintenance": 0.0})
        found = get_json(f"https://registry.npmjs.org/-/v1/search?{query}") or {"objects": []}
        for obj in found["objects"]:
            pkg = obj["package"]
            if pkg.get("date", "9999") < CUTOFF and not pkg["name"].startswith("@types/"):
                candidates[pkg["name"]] = obj["score"]["detail"]["popularity"]
        time.sleep(0.2)
    # popular READMEs are polished but may be memorised by the language model, so the two halves are fetched separately
    ranked = sorted(candidates, key=candidates.get)
    pool = ranked[: len(ranked) // 2] if half == "lower" else ranked[len(ranked) // 2 :]
    random.Random(3).shuffle(pool)
    print(f"{len(candidates)} pre-{CUTOFF} packages, sampling from the {half} popularity half ({len(pool)})", file=sys.stderr)

    kept = 0
    with open(out_path, "w") as out:
        for name in pool:
            doc = get_json(f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='@')}")
            if not doc:
                continue
            latest = doc.get("dist-tags", {}).get("latest")
            published = doc.get("time", {}).get(latest, "9999")
            readme = doc.get("readme") or ""
            if published >= CUTOFF or len(readme.split()) < 150:
                continue
            out.write(json.dumps({"name": name, "published": published[:10], "readme": readme}) + "\n")
            kept += 1
            if kept >= target:
                break
            time.sleep(0.1)
    print(f"kept {kept} READMEs", file=sys.stderr)


if __name__ == "__main__":
    main()

# Fetch Hacker News comments and Ask HN posts as recent human prose with an author attached.
# Every other human source here predates ChatGPT (Enron email 2001, Reddit 2022), so the
# human side of the set is old and the AI side is 2026. That gap is what sets the false-alarm floor.
# Usage: python fetch_hn.py OUT.jsonl [--comments 350] [--posts 120]
import argparse
import datetime
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SEARCH = "https://hn.algolia.com/api/v1/search_by_date"
USER = "https://hacker-news.firebaseio.com/v0/user/{}.json"
# detect.py gives no verdict under 80 words, so a shorter comment would teach this about text
# it never judges. Those rows were also what dragged formal human prose toward AI on the first
# try: at a 60-word floor the gate refused, at 100 it passes. REPORT.md has the numbers.
MIN_WORDS, MAX_WORDS = 100, 350
# ChatGPT opened to the public on 2022-11-30. An account older than that was writing here
# before a model could write for it. Not proof, but it is the provenance this source has.
ACCOUNT_BEFORE = 1669766400
# nothing before 2024, so the human side is as recent as the AI side
FLOOR = 1704067200

# the only markup HN emits, and the only entities. Anything else means the format changed.
ENTITIES = [("&#x27;", "'"), ("&#x2F;", "/"), ("&quot;", '"'), ("&gt;", ">"), ("&lt;", "<"), ("&amp;", "&")]
# HN writes '/' as &#x2F;, so a pasted url only looks like one once the entities are resolved
LINK = re.compile(r"https?:|\bwww\.")
CODE = re.compile(r"<pre>|<code>")
DEAD = re.compile(r"^\s*\[(dead|flagged)\]")
QUOTE = re.compile(r"(?m)^\s*>")
MARKUP = re.compile(r"</?[a-z][^>]*>|&\w+;|&#")
# a comment that says a model wrote it is the one thing this source cannot afford to label human
DISCLOSED = re.compile(r"(?i)\b(chat ?gpt|gpt-?[45]|claude|gemini|copilot|llm|an ai)\b[^.]{0,40}\b(wrote|writes|written|generated|drafted|produced)\b"
                       r"|\b(wrote|written|generating|generated|drafted)\b[^.]{0,30}\b(with|by|using)\b[^.]{0,20}\b(chat ?gpt|gpt|claude|gemini|an llm|ai)\b")


def to_text(html):
    text = html.replace("<p>", "\n\n")
    text = re.sub(r"</?i>", "", text)
    for entity, char in ENTITIES:
        text = text.replace(entity, char)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def reject(html):
    if CODE.search(html):
        return "code"
    if DEAD.search(html):
        return "dead"
    text = to_text(html)
    if LINK.search(text):
        return "link"
    if QUOTE.search(text):
        return "quote"
    if MARKUP.search(text):
        return "markup"
    if not MIN_WORDS <= len(text.split()) <= MAX_WORDS:
        return "length"
    if DISCLOSED.search(text):
        return "disclosed"
    return None


def account_ok(created):
    return created is not None and created < ACCOUNT_BEFORE


def row(author, kind, text, epoch):
    return {"text": text, "label": 0, "source": "hn", "model": "human",
            "domain": "forum" if kind == "comment" else "ask",
            # one author stays on one side of the split, the way one repo does for docs
            "group": f"hn:{author.lower()}", "author": author,
            "date": datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).strftime("%Y-%m-%d")}


def body(hit):
    return hit.get("comment_text") or hit.get("story_text") or ""


def collect(hits, kind, trusted):
    rows, seen, counts = [], set(), {}
    def drop(reason):
        counts[reason] = counts.get(reason, 0) + 1
    for hit in hits:
        author = (hit.get("author") or "").strip()
        if not author or author.lower() in seen:
            drop("dupe")
            continue
        reason = reject(body(hit))
        if reason:
            drop(reason)
            continue
        if not trusted(author):
            drop("account")
            continue
        seen.add(author.lower())
        rows.append(row(author, kind, to_text(body(hit)), hit["created_at_i"]))
    return rows, counts


def get(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == 3:
                print(f"giving up on {url[:80]}: {exc}", file=sys.stderr)
                return None
    return None


def account_created(author):
    page = get(USER.format(urllib.request.quote(author)))
    return page.get("created") if isinstance(page, dict) else None


def search(tag, before, floor, per_page=1000):
    url = f"{SEARCH}?tags={tag}&hitsPerPage={per_page}&numericFilters=created_at_i<{before},created_at_i>{floor}"
    page = get(url)
    return page.get("hits", []) if isinstance(page, dict) else []


def warm(hits, workers=8):
    # look the authors up once, concurrently, and only for hits whose text already passed
    names, seen = [], set()
    for hit in hits:
        author = (hit.get("author") or "").strip()
        if author and author.lower() not in seen and not reject(body(hit)):
            seen.add(author.lower())
            names.append(author)
    with ThreadPoolExecutor(workers) as pool:
        ages = dict(zip(names, pool.map(account_created, names)))
    return lambda author: account_ok(ages.get(author))


def anchors(now, floor, count):
    # Walking straight back from today would take the whole sample out of one news cycle.
    # Start from evenly spaced points instead, so the rows span 2024 to now.
    step = (now - floor) // count
    return [now - i * step for i in range(count)]


def harvest(tag, kind, target, windows=8):
    rows, seen = [], set()
    per = -(-target // windows)
    for anchor in anchors(int(datetime.datetime.now().timestamp()), FLOOR, windows):
        before, got = anchor, 0
        while got < per and before > FLOOR:
            hits = search(tag, before, FLOOR)
            if not hits:
                break
            oldest = min(h["created_at_i"] for h in hits)
            for start in range(0, len(hits), 300):
                chunk = hits[start:start + 300]
                found, counts = collect(chunk, kind, warm(chunk))
                found = [r for r in found if r["group"] not in seen][:per - got]
                seen.update(r["group"] for r in found)
                rows += found
                got += len(found)
                print(f"{kind} {datetime.date.fromtimestamp(chunk[-1]['created_at_i'])}: kept {len(found)} "
                      f"(total {len(rows)}), dropped {dict(sorted(counts.items()))}", file=sys.stderr)
                if got >= per:
                    break
            before = oldest - 1
    return rows[:target]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out")
    parser.add_argument("--comments", type=int, default=350)
    parser.add_argument("--posts", type=int, default=120)
    args = parser.parse_args()

    rows = harvest("comment", "comment", args.comments) + harvest("ask_hn", "ask", args.posts)
    if not rows:
        sys.exit("fetched nothing; refusing to write an empty file")
    with open(args.out, "w") as f:
        for item in rows:
            f.write(json.dumps(item) + "\n")
    by_kind = {}
    for item in rows:
        by_kind[item["domain"]] = by_kind.get(item["domain"], 0) + 1
    words = sorted(len(r["text"].split()) for r in rows)
    print(f"\n{len(rows)} rows from {len({r['group'] for r in rows})} authors -> {args.out}")
    print(f"by genre: {by_kind}; words {words[0]}-{words[-1]}, median {words[len(words) // 2]}")
    print(f"dates {min(r['date'] for r in rows)} to {max(r['date'] for r in rows)}")


if __name__ == "__main__":
    main()

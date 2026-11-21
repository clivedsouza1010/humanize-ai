# Fetch English Wikipedia article prose as recent formal human writing with an editor attached.
# The human side of the prose set is third-person declarative text written in 2004, and that is the
# register the detector gets wrong: 42% of RAID's human news reads as AI against 4% for abstracts.
# This is the same register written in 2023-2026, by named accounts opened before ChatGPT shipped.
# Usage: python fetch_wikipedia.py OUT.jsonl [--rows 300] [--per-editor 4]
import argparse
import datetime
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://en.wikipedia.org/w/api.php"
# Wikimedia's policy wants the client named; a default urllib agent gets 403.
AGENT = "humanize-bench/0.1 (local AI-text-detector training set; serial, honours maxlag)"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# Serial is not the same as polite. Back-to-back calls earn a 429 that outlives the run, and the
# penalty then reads as a source with nothing in it. Measured, so do not retune it on a hunch:
# 1s throttles immediately, 3s gave 36 throttles and 4 rows in half an hour, 6s gave none and 12
# rows. The backoff more than eats whatever a shorter interval buys. Two clients on one IP share
# the budget, so run this alone.
MIN_INTERVAL = 6.0
# how long to wait after each 429, in seconds. The last of these is minutes, on purpose: once the
# limiter is unhappy it stays unhappy, and a short retry just tells it the same thing again.
BACKOFF = (15, 30, 60, 120, 240)

# ChatGPT opened to the public on 2022-11-30. An account older than that, with this many edits
# behind it, has a writing record from before a model could have written for it. Not proof, but
# it is the provenance this venue has, and it is the same argument fetch_hn.py makes.
REGISTERED_BEFORE = "2022-11-30T00:00:00Z"
MIN_EDITCOUNT = 20000
# nothing before 2023, so the human side is as recent as the AI side
FLOOR = "2023-01-01T00:00:00Z"
# Whose prose it is no longer rests on this: added_lines() only takes lines that are wholly new,
# so the structure settles it. What this floor does is spend the API budget well, and the two
# filters either side of it cost very different amounts: an edit skipped for size is free, because
# the size arrived with the contributions call, while an edit that turns out to add no new
# paragraph costs a compare call to find out. So the floor wants to sit well above one paragraph
# (~8 bytes per word of wikitext), high enough that a qualifying edit probably does contain one.
# Measured: at 1200 the fetcher spent 16 calls per kept row and at 4000 it spent more, because
# edit size does not predict whether a paragraph was added. What predicts it is the page-creation
# flag, so the sort below leads with that and this floor is back to roughly two paragraphs.
MIN_SIZEDIFF = 1500
# detect.py gives no verdict under 80 words, so a shorter row would teach this about text it never
# judges. The HN round found the floor matters more than the source: 60 words failed the gate, 100
# passed. REPORT.md has the sweep.
MIN_WORDS, MAX_WORDS = 100, 350
# Rendering is an API call per candidate and an anonymous client gets a few hundred an hour, so
# everything decidable from the raw wikitext is decided first. Templates and links only ever
# shrink on render, so a line under this can never reach MIN_WORDS.
CANDIDATE_WORDS = 105
# at most this many renders per revision: if the first two lines are no good, the next edit is
# cheaper to try than the third line
RENDERS_PER_EDIT = 2
# citation templates render to markers that the sup-strip removes, so they are not a problem.
# Any other template is, and it would be rejected after rendering anyway - so reject it before.
CITATION = re.compile(r"(?i)\{\{\s*(sfn|sfnp|cite|citation|r|refn?|efn|harv|harvnb|harvtxt|page needed|"
                      r"citation needed|cn|better source|clarify|who|when|according to whom)\b")
# a critical-reception paragraph can be three-quarters review quotation, which teaches the critics
MAX_QUOTED = 0.30
# encyclopedic prose is genuinely date-dense; this blocks timeline and statistics dumps, not years
MAX_DIGITS = 0.06

# a summary saying the editor moved, reverted or tidied someone else's words, rather than wrote.
# Stems take any suffix ("Reverted good faith edits"); the short ones need whole-word boundaries.
JANITORIAL = re.compile(r"(?i)\b(?:revert|rv|undo|undid|restor|copy ?-? ?edit|typo|spell|grammar|punctuat|"
                        r"merg|split|mov(?:e|ed|es|ing)|renam|redirect|hotcat|awb|wpcleaner|twinkle|"
                        r"remov|delet|disambig|categor|infobox|wikif|clean ?-? ?up|fix|date ?format|archiv)"
                        r"|\b(?:ce|rm|rvv|url|isbn|doi)\b")
# an edit summary that names a model at all goes, whatever it claims about it. The summary is a
# line long, so there is no context to read and nothing to lose by being blunt here.
MODEL_NAMED = re.compile(r"(?i)\b(?:chat ?gpt|gpt-?[0-9]|claude|gemini|copilot|llm|ai)\b")
# the one thing this source cannot afford to label human
DISCLOSED = re.compile(r"(?i)\b(chat ?gpt|gpt-?[45]|claude|gemini|copilot|llm|an ai)\b[^.]{0,40}"
                       r"\b(wrote|writes|written|generated|drafted|produced)\b"
                       r"|\b(wrote|written|generating|generated|drafted)\b[^.]{0,30}\b(with|by|using)\b"
                       r"[^.]{0,20}\b(chat ?gpt|gpt|claude|gemini|an llm|ai)\b")

DIFF_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S)
ADDED_CELL = re.compile(r'<td[^>]*class="[^"]*diff-addedline[^"]*"[^>]*>(.*?)</td>', re.S)
DELETED_CELL = re.compile(r'<td[^>]*class="[^"]*diff-deletedline[^"]*"[^>]*>(.*?)</td>', re.S)
# an empty cell opposite means the whole line is new, rather than a line with words changed in it
EMPTY_CELL = re.compile(r'class="[^"]*diff-empty')
CHANGED = re.compile(r"<ins\b")
TAG = re.compile(r"<[^>]+>")
# Block elements close a sentence, inline ones sit inside it. Replacing both with a space is what
# turned "[[Foo]]." into "Foo .", which 1.75% of the human rows in this set carry and none of the
# AI rows do. Replacing both with nothing instead welds "One.</p><p>Two." into "One.Two.".
BLOCK_TAG = re.compile(r"</?(?:p|div|br|li|tr|td|h[1-6])\b[^>]*>", re.I)
# whole elements, not their tags: a stripped table leaves a wall of numbers behind
BLOCK_WHOLE = [re.compile(rf"<{tag}\b[^>]*>.*?</{tag}>", re.S) for tag in
               ("table", "ul", "ol", "dl", "blockquote", "figure", "style",
                "h1", "h2", "h3", "h4", "h5", "h6")]
# a reference marker sits mid-sentence, so it goes without leaving a space behind it
INLINE_WHOLE = [re.compile(rf"<{tag}\b[^>]*>.*?</{tag}>", re.S) for tag in ("sup",)]
# the safety net, and the same rule detect.py already applies to docs
PUNCT_GAP = re.compile(r"\s+([.,;:!?)](?=\s|$|[.,;:!?)\"'\u2019]))")
CLITIC = re.compile(r"\s+('s|'re|'ve|'ll|'d|n't|\u2019s)\b")
# the parse call disables these, but strip the text form too so a stray one can never survive
NOISE = re.compile(r"\[(edit|citation needed|\d+)\]")
# the nbsp and thin spaces {{convert}} emits are already \s, so the final collapse eats
# them. These are the ones it misses, and an invisible character is a one-sided giveaway.
ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\u00ad\ufeff]")
# Wikipedia's style guide mandates an en dash in ranges and between paired names, so these
# rows carry them at 9.4% against 1.2% of the AI rows - an eight-fold enrichment, and a house
# format rather than a voice. Mapped to a hyphen, which leaves the words alone. The better fix
# is to normalise it on both sides of the whole set at once; REPORT.md says so.
EN_DASH = re.compile(r"\u2013")

NOT_PROSE = re.compile(r"^\s*(\*|#|\||!|:|;|=|\{\{|\}\}|\[\[\s*(File|Image|Category)\s*:|<)")
MARKUP = re.compile(r"</?[a-z][^>]*>|&\w+;|&#")
# a diff cell cut mid-template leaves the braces behind, and brackets are never in clean prose here
WIKITEXT = re.compile(r"\{\{|\}\}|\[|\]|'''|~~~")
# scripts the AI side never writes in. A native-name gloss would teach script, not voice, so the
# row goes rather than the gloss - stripping it would alter the sentence the editor wrote.
NON_LATIN = re.compile(r"[\u0370-\u1cff\u1f00-\u1fff\u2e80-\uffff]")
# The one unambiguous lead marker: life dates straight after the subject's name. Everything
# else the formula does is also ordinary encyclopedic prose. A subject-initial definition
# ("Name is a ...") opens 7.7% of the human prose rows already in the set and 5.5% of the AI
# rows, so it does not separate the classes, and cutting it from one source only would make
# it an AI-leaning cue in exactly the direction this source exists to fix.
LEAD_DATES = re.compile(r"\(\s*(?:born\s+\d{4}|(?:c\.\s*)?\d{4}\s*[-\u2013\u2014]\s*)")
# a bare year in brackets is a date reference, not a lead, so the range or "born" is required
TITLE_TAIL = re.compile(r"\s*\([^)]*\)$")
# how far into the row the marker has to be: the formula is the opening of the first sentence
LEAD_REACH = 90
# Split on the marks and take the odd segments. Matching an opening mark to any later mark
# counted the plain prose BETWEEN two quotations as quoted, which turned MAX_QUOTED into a screen
# against quoting twice - and so cut reported speech and attribution out of the human class only.
QUOTE_MARK = re.compile(r"[\"\u201c\u201d]")
WORD = re.compile(r"\S+")


def tenure_ok(editor):
    since = editor.get("registration")
    return (bool(since) and since < REGISTERED_BEFORE
            and editor.get("editcount", 0) >= MIN_EDITCOUNT
            and "bot" not in editor.get("groups", [])
            and not editor.get("blockid"))


def janitorial(summary, created=False):
    # The tidying patterns answer "did this editor write these words or move someone else's".
    # A new article has no earlier prose to revert, merge or recategorise, so for a creation the
    # question is already settled and the patterns only cost yield. A summary naming a model
    # still rules the edit out either way.
    if MODEL_NAMED.search(summary):
        return True
    return not created and bool(JANITORIAL.search(summary))


def strip_cell(cell):
    return re.sub(r"\s+", " ", html.unescape(TAG.sub("", cell))).strip()


def added_lines(body):
    # Only lines that are wholly new. A cell for a partly edited line holds the ENTIRE new line
    # with just the changed words in <ins>, so taking it would harvest paragraphs the editor never
    # wrote and stamp them with their name and this year's date, which is the whole provenance
    # claim gone. A moved paragraph looks new too, so drop anything deleted elsewhere in the diff.
    moved = {strip_cell(cell).lower() for row in DIFF_ROW.findall(body)
             for cell in DELETED_CELL.findall(row)}
    lines = []
    for row in DIFF_ROW.findall(body):
        if not EMPTY_CELL.search(row):
            continue
        for cell in ADDED_CELL.findall(row):
            if CHANGED.search(cell):
                continue
            line = strip_cell(cell)
            if line.lower() not in moved:
                lines.append(line)
    return lines


def strip_citations(line):
    # remove whole citation templates, braces and all, so what is left says whether any OTHER
    # template is in the line. Templates nest, so this counts depth rather than matching a regex.
    out, i = [], 0
    while i < len(line):
        if line.startswith("{{", i):
            depth, j = 0, i
            while j < len(line):
                if line.startswith("{{", j):
                    depth, j = depth + 1, j + 2
                elif line.startswith("}}", j):
                    depth, j = depth - 1, j + 2
                    if depth == 0:
                        break
                else:
                    j += 1
            out.append(" " if CITATION.match(line[i:j]) else line[i:j])
            i = j
        else:
            out.append(line[i])
            i += 1
    return "".join(out)


def raw_ok(line):
    # the same screens as reject(), run on the wikitext, for the ones that survive rendering
    if "{{" in strip_citations(line):
        return False
    if NON_LATIN.search(line) or quoted_share(line) > MAX_QUOTED:
        return False
    return len(line.split()) >= CANDIDATE_WORDS


def prose_line(line):
    line = line.strip()
    return bool(line) and not NOT_PROSE.match(line)


def to_text(markup):
    for pattern in BLOCK_WHOLE:
        markup = pattern.sub("\n", markup)
    for pattern in INLINE_WHOLE:
        markup = pattern.sub("", markup)
    text = html.unescape(TAG.sub("", BLOCK_TAG.sub("\n", markup)))
    text = EN_DASH.sub("-", ZERO_WIDTH.sub("", NOISE.sub("", text)))
    text = re.sub(r"\s+", " ", text).strip()
    return CLITIC.sub(r"\1", PUNCT_GAP.sub(r"\1", text))


def quoted_share(text):
    words = WORD.findall(text)
    if not words:
        return 0.0
    parts = QUOTE_MARK.split(text)
    inside = sum(len(WORD.findall(part)) for i, part in enumerate(parts) if i % 2)
    return inside / len(words)


def is_lead(text, title):
    # the dates have to belong to the subject, so the words before them must name it
    name = {w.lower() for w in TITLE_TAIL.sub("", title).split() if len(w) >= 4}
    if not name:
        return False
    hit = LEAD_DATES.search(text[:LEAD_REACH])
    return bool(hit) and bool(name & {w.lower() for w in WORD.findall(text[:hit.start()])})


def reject(text, title=""):
    # last line of defence for the extraction gap. If some tag shape gets past to_text, the row
    # does not ship: a space before a full stop appears on the human side of this set and nowhere
    # on the AI side, so one would teach the detector the format instead of the voice.
    if PUNCT_GAP.search(text) or CLITIC.search(text):
        return "spacing"
    if MARKUP.search(text):
        return "markup"
    if WIKITEXT.search(text):
        return "wikitext"
    if NON_LATIN.search(text):
        return "script"
    if quoted_share(text) > MAX_QUOTED:
        return "quoted"
    if is_lead(text, title):
        return "lead"
    if sum(c.isdigit() for c in text) / max(len(text), 1) > MAX_DIGITS:
        return "digits"
    if not MIN_WORDS <= len(text.split()) <= MAX_WORDS:
        return "length"
    if DISCLOSED.search(text):
        return "disclosed"
    return None


def row(editor, title, revid, timestamp, text):
    return {"text": text, "label": 0, "source": "wikipedia", "model": "human", "domain": "encyclopedia",
            # one editor stays on one side of the split, the way one repo does for docs
            "group": f"wp:{editor['name'].lower()}", "author": editor["name"], "date": timestamp[:10],
            # enough to pull the diff back up and check the row by hand
            "title": title, "revid": revid,
            "editor_since": editor.get("registration"), "editor_edits": editor.get("editcount")}


def windows(start, end, count):
    newest = datetime.datetime.strptime(start, STAMP)
    oldest = datetime.datetime.strptime(end, STAMP)
    step = (newest - oldest) / count
    edges = [newest - i * step for i in range(count + 1)]
    return [(edges[i].strftime(STAMP), edges[i + 1].strftime(STAMP)) for i in range(count)]


def offset(index, count):
    # every editor starts at a different window, or the whole sample bunches into one month
    return index % count


_last_call = [0.0]


def pace():
    wait = MIN_INTERVAL - (time.monotonic() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.monotonic()


def call(params, post=False):
    # GET for the reads. Wikimedia rate-limits anonymous POSTs hard enough that a burst of them
    # earns a 429 within seconds, which reads as a slow fetcher rather than a blocked one. Only
    # parse has to POST, because a rendered paragraph overflows a query string and comes back 414.
    query = urllib.parse.urlencode({**params, "format": "json", "formatversion": "2", "maxlag": "5"})
    for attempt in range(len(BACKOFF) + 1):
        pace()
        try:
            request = (urllib.request.Request(API, data=query.encode(), headers={"User-Agent": AGENT})
                       if post else urllib.request.Request(f"{API}?{query}", headers={"User-Agent": AGENT}))
            with urllib.request.urlopen(request, timeout=30) as response:
                page = json.load(response)
        except urllib.error.HTTPError as exc:
            # back off and keep going on a 429; anything else will not fix itself
            if exc.code not in (429, 503) or attempt == len(BACKOFF):
                print(f"giving up on {params['action']}: {exc}", file=sys.stderr)
                return {}
            # say so. A 429 that succeeds on retry leaves no trace otherwise, and a throttled
            # run then reads as a fetcher that cannot find anything rather than a slow one.
            print(f"throttled on {params['action']}, waiting {BACKOFF[attempt]}s", file=sys.stderr)
            time.sleep(BACKOFF[attempt])
            continue
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == len(BACKOFF):
                print(f"giving up on {params['action']}: {exc}", file=sys.stderr)
                return {}
            time.sleep(2 ** attempt)
            continue
        if page.get("error", {}).get("code") in ("maxlag", "ratelimited"):
            time.sleep(5)
            continue
        return page
    return {}


def editors(pages=8):
    # a 500-change page costs about 30 seconds, so this is roughly three minutes of setup
    # before the first row. The per-editor calls that follow answer in a tenth of that.
    names, cont = [], {}
    for _ in range(pages):
        page = call({"action": "query", "list": "recentchanges", "rcnamespace": "0", "rctype": "edit",
                     "rclimit": "500", "rcshow": "!bot|!minor|!anon", "rcprop": "user|timestamp", **cont})
        changes = page.get("query", {}).get("recentchanges", [])
        names += [c["user"] for c in changes if c.get("user")]
        cont = page.get("continue", {})
        if not cont:
            break
    # recentchanges only keeps 30 days, so it picks the editors; usercontribs does the dates
    return list(dict.fromkeys(names))


def trusted(names, batch=40):
    kept = []
    for start in range(0, len(names), batch):
        page = call({"action": "query", "list": "users", "ususers": "|".join(names[start:start + batch]),
                     "usprop": "registration|editcount|groups|blockinfo"})
        kept += [u for u in page.get("query", {}).get("users", []) if tenure_ok(u)]
    return kept


def contributions(name, start, end):
    # Page creations only. Every line of a new article is the creator's prose, so a compare call
    # on one almost always yields a row, and the provenance needs no argument at all. Asking for
    # every edit instead meant 11 API calls per kept row, most of them spent finding out that a
    # large edit added a table. The cost is that the source is now new articles rather than all
    # recent Wikipedia prose - a narrower slice, and REPORT.md says so.
    # 150 of the newest in the window is plenty; an editor only needs per_editor rows.
    page = call({"action": "query", "list": "usercontribs", "ucuser": name, "ucnamespace": "0",
                 "ucstart": start, "ucend": end, "ucdir": "older", "uclimit": "150", "ucshow": "new|!minor",
                 "ucprop": "ids|title|timestamp|comment|sizediff|flags"})
    return page.get("query", {}).get("usercontribs", [])


def paragraph(edit, counts):
    page = call({"action": "compare", "fromrev": str(edit["revid"]), "torelative": "prev", "prop": "diff"})
    lines = added_lines(page.get("compare", {}).get("body", ""))
    renders = 0
    for line in lines:
        if not prose_line(line) or not raw_ok(line):
            continue
        if renders >= RENDERS_PER_EDIT:
            break
        renders += 1
        rendered = call({"action": "parse", "text": line, "title": edit["title"], "contentmodel": "wikitext",
                         "prop": "text", "disablelimitreport": "1", "disableeditsection": "1",
                         "disabletoc": "1"}, post=True).get("parse", {}).get("text", "")
        text = to_text(rendered)
        reason = reject(text, edit["title"])
        if reason:
            counts[reason] = counts.get(reason, 0) + 1
            continue
        return text
    return None


def harvest(target, per_editor, window_count=8, tries=2, pages=8, partial=None):
    pool = trusted(editors(pages))
    print(f"{len(pool)} editors past the tenure screen", file=sys.stderr)
    if not pool:
        sys.exit("no editors came back; the API is refusing us, so there is nothing to harvest")
    found, counts, skipped, titles = [], {}, {}, set()
    slices = windows(datetime.datetime.now(datetime.timezone.utc).strftime(STAMP), FLOOR, window_count)
    for index, editor in enumerate(pool):
        if len(found) >= target:
            break
        kept = 0
        # Two windows each. Most editors have no qualifying creation in a given window and a
        # window costs a call to find that out, so searching one editor harder is the most
        # expensive thing this loop does. Breadth beats depth, and the date spread comes from
        # the rotating offset across the pool rather than from any one editor covering it.
        # not from one editor covering the whole range, so this costs calls and not coverage.
        for turn in range(tries):
            if kept >= per_editor:
                break
            start, end = slices[(offset(index, window_count) + turn) % window_count]
            # biggest creation first: more prose in it, and per_editor is met sooner
            edits = sorted(contributions(editor["name"], start, end),
                           key=lambda e: -(e.get("sizediff") or 0))
            for edit in edits:
                if kept >= per_editor:
                    break
                # count what the edit-level filters drop too. Rejects after rendering were the
                # only thing reported, so an editor yielding nothing looked the same whether the
                # filters were working or the fetcher was broken.
                if edit.get("sizediff") is None or edit["sizediff"] < MIN_SIZEDIFF:
                    skipped["small"] = skipped.get("small", 0) + 1
                    continue
                if janitorial(edit.get("comment", ""), created=bool(edit.get("new"))):
                    skipped["janitorial"] = skipped.get("janitorial", 0) + 1
                    continue
                if edit["title"] in titles:
                    skipped["seen"] = skipped.get("seen", 0) + 1
                    continue
                text = paragraph(edit, counts)
                if not text:
                    skipped["no prose added"] = skipped.get("no prose added", 0) + 1
                    continue
                titles.add(edit["title"])
                made = row(editor, edit["title"], edit["revid"], edit["timestamp"], text)
                found.append(made)
                kept += 1
                if partial:
                    with open(partial, "a") as f:
                        f.write(json.dumps(made) + "\n")
        print(f"{editor['name']}: kept {kept} (total {len(found)}) | edits skipped "
              f"{dict(sorted(skipped.items()))} | rows rejected {dict(sorted(counts.items()))}",
              file=sys.stderr)
    return found[:target]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out")
    parser.add_argument("--rows", type=int, default=300)
    parser.add_argument("--per-editor", type=int, default=4)
    # each page of recent changes costs about 30 seconds, so a small run wants fewer of them
    parser.add_argument("--pages", type=int, default=8)
    args = parser.parse_args()

    # rows land here as they are found, so a stopped or failed run keeps what it got
    partial = args.out + ".partial"
    open(partial, "w").close()
    rows = harvest(args.rows, args.per_editor, pages=args.pages, partial=partial)
    if len(rows) < args.rows // 2:
        sys.exit(f"only {len(rows)} rows; kept them in {partial} rather than writing a set this thin")
    os.replace(partial, args.out)
    words = sorted(len(r["text"].split()) for r in rows)
    print(f"{len(rows)} rows, {len({r['group'] for r in rows})} editors, "
          f"median {words[len(words) // 2]} words, {min(r['date'] for r in rows)} to "
          f"{max(r['date'] for r in rows)} -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()

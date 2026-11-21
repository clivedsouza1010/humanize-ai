# Fetch docs from GitHub to train on: human docs from TypeScript, React and Next.js repos as they stood before ChatGPT,
# and docs written in a commit that credits an AI tool.
# Usage: python fetch_github_docs.py human OUT.jsonl [repos=400] [--wait SECONDS] [--besides DONE.jsonl]
#        python fetch_github_docs.py ai OUT.jsonl [--wait SECONDS]
#        python fetch_github_docs.py recent OUT.jsonl WINDOWS.txt [--besides DONE.jsonl]
#            docs a repo gained in a date window; lines read: repo start end label [cap]
#        python fetch_github_docs.py pr OUT.jsonl PROJECTS.txt [--besides DONE.jsonl]
#            docs from merged pull requests that declared whether AI wrote them; lines read: repo effective [pages]
# One request at a time on purpose: this runs on the user's token, and GitHub's secondary limits trip on bursts.
import argparse
import collections
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import provenance

CUTOFF = "2022-11-01"
SEARCH_GAP = 30
CORE_GAP = 0.8
RAW_GAP = 0.2
TOPICS = ["react", "nextjs", "typescript", "react-hooks", "nodejs", "graphql", "tailwindcss", "component-library", "orm", "cli"]
BANDS = ["30..200", "200..1000", "1000..5000", ">5000"]
# projects known for docs people wrote and maintained by hand, whatever a topic search turns up
CURATED = """vercel/next.js reactjs/reactjs.org vercel/swr TanStack/query TanStack/table pmndrs/zustand pmndrs/jotai pmndrs/react-spring
reduxjs/redux reduxjs/redux-toolkit remix-run/remix remix-run/react-router trpc/trpc prisma/docs prisma/prisma colinhacks/zod
react-hook-form/react-hook-form mui/material-ui chakra-ui/chakra-ui radix-ui/website tailwindlabs/tailwindcss.com vitejs/vite
vitest-dev/vitest storybookjs/storybook testing-library/testing-library-docs microsoft/TypeScript-Website microsoft/playwright
cypress-io/cypress-documentation apollographql/apollo-client nestjs/docs.nestjs.com typeorm/typeorm vuejs/docs nuxt/nuxt withastro/docs
supabase/supabase strapi/documentation payloadcms/payload directus/directus calcom/cal.com i18next/react-i18next nextauthjs/next-auth
vercel/turbo vercel/vercel ianstormtaylor/slate facebook/docusaurus facebook/lexical mobxjs/mobx statelyai/xstate formatjs/formatjs
framer/motion react-navigation/react-navigation expo/expo mswjs/msw unjs/nitro pnpm/pnpm yarnpkg/berry typescript-eslint/typescript-eslint""".split()
# the JavaScript workhorses the TypeScript topic search cannot see, plus the separate repos that hold their docs
CURATED += """Automattic/mongoose Leaflet/Leaflet Modernizr/Modernizr PrismJS/prism alpinejs/alpine angular/angular avajs/ava axios/axios axios/axios-docs
babel/babel babel/website browserify/browserify caolan/async chaijs/chai chalk/chalk chartjs/Chart.js d3/d3 date-fns/date-fns debug-js/debug
ember-learn/guides-source emberjs/ember.js eslint/eslint evanw/esbuild expressjs/body-parser expressjs/express expressjs/expressjs.com
expressjs/morgan fastify/fastify graphql/graphql-js graphql/graphql.github.io gulpjs/gulp h5bp/html5-boilerplate
handlebars-lang/handlebars.js hapijs/hapi.dev highlightjs/highlight.js hotwired/turbo iamkun/dayjs immutable-js/immutable-js
jaredhanson/passport jashkenas/backbone jashkenas/underscore jasmine/jasmine jestjs/jest jquery/api.jquery.com jquery/jquery
jquery/jquery-ui jquery/learn.jquery.com karma-runner/karma knex/knex knockout/knockout koajs/koa lerna/lerna less/less-docs lodash/lodash
markedjs/marked mochajs/mocha moment/moment moment/momentjs.com mongodb/node-mongodb-native mrdoob/three.js nodejs/node nodejs/nodejs.org
nodemailer/nodemailer npm/cli nrwl/nx parcel-bundler/website pinojs/pino postcss/postcss preactjs/preact-www prettier/prettier pugjs/pug
puppeteer/puppeteer ramda/ramda redis/node-redis requirejs/requirejs rollup/rollup sass/sass-site select2/select2 sequelize/sequelize
sindresorhus/execa sindresorhus/got sinonjs/sinon socketio/socket.io socketio/socket.io-website sveltejs/svelte terser/terser
tj/commander.js twbs/bootstrap videojs/video.js webdriverio/webdriverio webpack/webpack webpack/webpack.js.org winstonjs/winston yargs/yargs""".split()
TOOLS = {
    "claude": ['"Generated with Claude Code"', '"Co-Authored-By: Claude"'],
    "cursor": ['"cursoragent@cursor.com"', '"Co-authored-by: Cursor"'],
    "copilot": ['"Co-authored-by: Copilot"', '"copilot-swe-agent"'],
    "codex": ['"Co-authored-by: Codex"', '"chatgpt-codex-connector"'],
    "devin": ['"devin-ai-integration"'],
    "gemini": ['"Co-authored-by: Gemini"', '"gemini-code-assist"'],
}
TARGETS = {"claude": 500, "cursor": 300, "copilot": 300, "codex": 200, "devin": 100, "gemini": 100}
WORDS = ["README", "docs", "documentation", "guide", "changelog", "contributing"]
MONTHS = [f"{y}-{m:02d}" for y in (2025, 2026) for m in range(1, 13) if f"{y}-{m:02d}" >= "2025-03" and f"{y}-{m:02d}" <= "2026-10"]
LANGUAGES = {"TypeScript", "JavaScript", "MDX"}
MIN_AI_STARS = 1
MAX_AI_REPO_DOCS = 3
MAX_SEARCHES = 120
RECENT_GAP = 0.4
RECENT_CAP = 6
PR_GAP = 1.5
PR_PAGE = 25
MAX_PR_PAGES = 14
# one maintainer can account for most of a project's pull requests, so cap what any one repo and any
# one pull request contribute: a pull request that adds twelve pages is still one act of writing
MAX_PR_DOCS = 15
MAX_DOCS_PER_PR = 3
PR_QUERY = """
query($q: String!, $after: String) {
  search(query: $q, type: ISSUE, first: %d, after: $after) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes { ... on PullRequest {
      number author { login } mergedAt body
      mergeCommit { oid }
      commits(first: 40) { nodes { commit { message } } }
      files(first: 100) { nodes { path additions changeType } }
    } }
  }
}""" % PR_PAGE
AGENT_FILE = re.compile(r"(?i)(?:^|/)(?:claude\.md|agents\.md|gemini\.md|\.cursorrules|\.cursor/|copilot-instructions\.md)")

# agent instructions, work logs and plans are a different genre from the docs people read, so neither side keeps them
SKIP_PATH = re.compile(
    r"(?:^|/)(?:node_modules|vendor|third[-_]party|examples?|templates?|fixtures?|tests?|__tests__|\.changeset|\.claude|\.cursor|\.agents?|\.ai|\.github/"
    r"(?:ISSUE_TEMPLATE|agents|prompts|instructions)|ai[-_]docs|memory[-_]bank|plans?|specs?|rfcs?|adrs?|archive|reports?|research|notes|prompts?|tasks?|prd|"
    r"internal|i18n|locales?|translations?|zh|zh-cn|zh-hans|zh-tw|ja|ko|fr|es|de|pt|pt-br|ru|it|tr|vi|id)(?:/|$)", re.I)
SKIP_NAME = re.compile(r"(?i)^(?:claude|agents?|gemini|copilot|\.cursorrules|code[-_]of[-_]conduct|license|pull_request_template)\b|summary|report|plan\b|status|audit|todo|roadmap|analysis|review")
TRANSLATED = re.compile(r"[-_.](?:zh|cn|zh-cn|zh-tw|pt|pt-br|ja|jp|ko|kr|es|fr|de|ru|it|tr|vi)\.mdx?$")
GENERATED = re.compile(r"(?i)auto-?generated|automatically generated|do not edit|this file is generated|api-documenter|typedoc|\nDefined in:")
BOILERPLATE = re.compile(
    r"(?i)bootstrapped with \[?create|getting started with create react app|this template (?:should help|provides a minimal)|contributor covenant|"
    r"use this section to tell people|you can start editing the page by modifying")
WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
STOPWORDS = {"the", "and", "to", "of", "a", "in", "is", "you", "for", "that", "it", "with", "this", "on", "be", "are", "can", "or"}
REPO_NAME = re.compile(r"^[\w.-]+/[\w.-]+$")
_last = {}


def log(message):
    print(message, file=sys.stderr, flush=True)


def pace(kind, gap):
    wait = _last.get(kind, 0) + gap - time.time()
    if wait > 0:
        time.sleep(wait)
    _last[kind] = time.time()


def gh(path, params=(), gap=CORE_GAP, kind="core"):
    args = ["gh", "api", "-X", "GET", path] + [item for key, value in params for item in ("-f", f"{key}={value}")]
    backoff = 180
    for _ in range(6):
        pace(kind, gap)
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode == 0:
            return json.loads(result.stdout)
        output = (result.stdout + result.stderr).lower()
        if "rate limit" in output or "abuse" in output:
            log(f"rate limited on {path}, waiting {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 3600)
        elif "http 404" in output or "http 409" in output or "http 451" in output or "http 422" in output:
            return None
        else:
            log(f"failed {path}: {output[:200]}")
            time.sleep(20)
    return None


def graphql(query, gap=2, **variables):
    args = ["gh", "api", "graphql", "-f", f"query={query}"] + [item for key, value in variables.items() for item in ("-f", f"{key}={value}")]
    for _ in range(5):
        pace("core", gap)
        result = subprocess.run(args, capture_output=True, text=True)
        try:
            body = json.loads(result.stdout)
        except json.JSONDecodeError:
            log(f"graphql failed: {result.stderr[:200]}")
            time.sleep(120)
            continue
        if body.get("data"):
            return body["data"]
        log("graphql: " + json.dumps(body.get("errors", body))[:200])
        time.sleep(30)
    return None


def repo_info(names):
    # GraphQL takes 40 repos a request, far cheaper than one REST call each
    info = {}
    names = [n for n in names if REPO_NAME.match(n)]
    for start in range(0, len(names), 40):
        chunk = names[start : start + 40]
        fields = "nameWithOwner stargazerCount isFork isArchived createdAt primaryLanguage { name }"
        parts = []
        for i, name in enumerate(chunk):
            owner, repo = name.split("/")
            parts.append(f'r{i}: repository(owner: "{owner}", name: "{repo}") {{ {fields} }}')
        data = graphql("query { " + " ".join(parts) + " }")
        if not data:
            continue
        for found in data.values():
            if found:
                info[found["nameWithOwner"]] = found
    return info


def raw(repo, sha, path):
    pace("raw", RAW_GAP)
    url = f"https://raw.githubusercontent.com/{repo}/{sha}/{urllib.parse.quote(path)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.read(400_000).decode("utf-8")
    except Exception as err:
        log(f"  no {url}: {err}")
        return None


def doc_type(path):
    name = path.rsplit("/", 1)[-1]
    low = name.lower()
    if not low.endswith((".md", ".mdx")) or SKIP_PATH.search(path) or SKIP_NAME.search(low) or TRANSLATED.search(low):
        return None
    stem = low.rsplit(".", 1)[0]
    depth = path.count("/")
    if stem == "readme":
        return "readme" if depth == 0 else ("package-readme" if re.match(r"(?i)(packages|libs|apps|modules)/", path) else "readme-sub")
    if stem == "contributing":
        return "contributing"
    if stem in ("changelog", "changes", "history", "releases", "release-notes", "release_notes"):
        return "changelog"
    if stem == "security":
        return "security"
    if re.search(r"(?i)(?:^|/)(?:blog|posts|articles)/", path):
        return "blog"
    if re.search(r"(?i)(?:^|/)(?:docs?|documentation|guides?|tutorials?|website|site|content|pages|src/content|src/pages)/", path):
        return "guide"
    return None


def usable(text):
    words = WORD.findall(text)
    if len(words) < 150:
        return False
    letters = [c for c in text if c.isalpha()]
    # English only: the blends were never fitted on anything else
    if sum(c.isascii() for c in letters) / max(len(letters), 1) < 0.9:
        return False
    if sum(w.lower() in STOPWORDS for w in words) / len(words) < 0.15:
        return False
    return not (GENERATED.search(text[:1500]) or "\nDefined in:" in text or BOILERPLATE.search(text))


def fingerprint(text):
    return hashlib.sha1(re.sub(r"\W+", " ", text.lower())[:400].encode()).hexdigest()


def load_done(path):
    rows = [json.loads(line) for line in open(path)] if os.path.exists(path) else []
    return rows, {fingerprint(r["text"]) for r in rows}


def find_repos(want, rng):
    stars = {name: None for name in CURATED}
    for topic in TOPICS:
        for band in BANDS:
            query = f"language:TypeScript topic:{topic} stars:{band} created:<2021-11-01 fork:false"
            found = gh("search/repositories", [("q", query), ("per_page", 100)], SEARCH_GAP / 3, "search") or {"items": []}
            for item in found["items"]:
                stars[item["full_name"]] = item["stargazers_count"]
            log(f"{query}: {len(found['items'])}, {len(stars)} repos so far")
    rest = sorted(name for name in stars if name not in CURATED)
    rng.shuffle(rest)
    return CURATED + rest[: max(want - len(CURATED), 0)], stars


def human(out_path, want, besides=()):
    rng = random.Random(23)
    rows, seen = load_done(out_path)
    done_repos = {r["repo"] for r in rows}
    # a batch written to its own file becomes its own source, which is what lets the gate judge it;
    # --besides keeps it from re-fetching, and re-storing, what an earlier file already holds
    for path in besides:
        old, old_seen = load_done(path)
        done_repos |= {r["repo"] for r in old}
        seen |= old_seen
    repos, stars = find_repos(want, rng)
    caps = {"readme": 1, "package-readme": 2, "readme-sub": 1, "contributing": 1, "changelog": 1, "security": 1, "blog": 3}
    kept = 0
    with open(out_path, "a") as out:
        for n, repo in enumerate(repos):
            if repo in done_repos:
                continue
            head = gh(f"repos/{repo}/commits", [("until", f"{CUTOFF}T00:00:00Z"), ("per_page", 1)])
            if not head:
                continue
            sha, date = head[0]["sha"], head[0]["commit"]["committer"]["date"][:10]
            tree = gh(f"repos/{repo}/git/trees/{sha}", [("recursive", 1)])
            if not tree:
                continue
            by_type = {}
            for entry in tree.get("tree", []):
                kind = doc_type(entry["path"]) if entry["type"] == "blob" else None
                if kind:
                    by_type.setdefault(kind, []).append(entry["path"])
            for kind, paths in by_type.items():
                rng.shuffle(paths)
                cap = caps.get(kind, 15 if repo in CURATED else 6)
                taken = 0
                for path in paths[: cap * 3]:
                    if taken >= cap:
                        break
                    text = raw(repo, sha, path)
                    if not text or not usable(text) or fingerprint(text) in seen:
                        continue
                    seen.add(fingerprint(text))
                    out.write(json.dumps({"repo": repo, "path": path, "sha": sha, "date": date, "stars": stars.get(repo), "doc_type": kind, "text": text}) + "\n")
                    out.flush()
                    taken += 1
                    kept += 1
            log(f"{n + 1}/{len(repos)} {repo} @ {date}: {kept} docs kept")
    log(f"done: {kept} new docs")


def snapshot(repo, date, cache={}):
    if (repo, date) not in cache:
        head = gh(f"repos/{repo}/commits", [("until", f"{date}T00:00:00Z"), ("per_page", 1)], RECENT_GAP)
        tree = gh(f"repos/{repo}/git/trees/{head[0]['sha']}", [("recursive", 1)], RECENT_GAP) if head else None
        cache[(repo, date)] = (head[0]["sha"], {e["path"]: e["sha"] for e in tree["tree"] if e["type"] == "blob"}) if tree else None
    return cache[(repo, date)]


def recent(out_path, windows, besides=()):
    # a doc that wasn't in the repo at the start of a window was written inside it; files that only moved keep their blob, so they don't count
    rows, seen = load_done(out_path)
    done = {(r["repo"], r["window"]) for r in rows}
    # a held-back file passed here keeps its repos and its texts out: a hard fork shares docs with its
    # parent while GitHub reports neither as a fork, and the same text on both sides is the worst case
    skip_repos = set()
    for path in besides:
        old, old_seen = load_done(path)
        skip_repos |= {r["repo"] for r in old}
        seen |= old_seen
    jobs = [line.split() for line in open(windows) if line.strip()]
    kept = 0
    with open(out_path, "a") as out:
        for n, (repo, start, end, label, *rest) in enumerate(jobs):
            if (repo, label) in done or repo in skip_repos:
                continue
            cap = int(rest[0]) if rest else RECENT_CAP
            before, after = snapshot(repo, start), snapshot(repo, end)
            if not before or not after:
                continue
            sha, files = after
            old_blobs = set(before[1].values())
            agent_files = any(AGENT_FILE.search(path) for path in files)
            by_type = {}
            for path, blob in files.items():
                # a project-wide policy covers every doc, wherever that project keeps them
                kind = doc_type(path) or ("guide" if rest and path.endswith((".md", ".mdx")) and not SKIP_PATH.search(path) and not SKIP_NAME.search(path.rsplit("/", 1)[-1]) and not TRANSLATED.search(path) else None)
                if kind and path not in before[1] and blob not in old_blobs:
                    by_type.setdefault(kind, []).append(path)
            for kind, paths in by_type.items():
                taken = 0
                for path in sorted(paths, key=lambda p: fingerprint(p))[: cap * 3]:
                    if taken >= cap:
                        break
                    text = raw(repo, sha, path)
                    if not text or not usable(text) or fingerprint(text) in seen:
                        continue
                    seen.add(fingerprint(text))
                    out.write(json.dumps({"repo": repo, "path": path, "sha": sha, "window": label, "start": start, "end": end, "doc_type": kind,
                                          "agent_files": agent_files, "text": text}) + "\n")
                    out.flush()
                    taken += 1
                    kept += 1
            log(f"{n + 1}/{len(jobs)} {repo} {label}: {kept} docs kept")
    log(f"done: {kept} new docs")


def pr_docs(pr):
    # the markdown a pull request touched. A project-wide policy covers every doc, wherever the project
    # keeps them, so this takes any markdown the other sides would accept by path.
    for entry in pr["files"]["nodes"] or []:
        path = entry["path"]
        name = path.rsplit("/", 1)[-1]
        kind = doc_type(path) or ("guide" if path.endswith((".md", ".mdx")) and not SKIP_PATH.search(path)
                                 and not SKIP_NAME.search(name) and not TRANSLATED.search(name) else None)
        if kind and entry["changeType"] != "DELETED":
            yield path, kind, entry["additions"]


def file_tool(repo, path, oid):
    # whether the commit that wrote this file credits a tool. The declaration in a pull request covers
    # the whole branch; this says whether a tool touched this page. The newest commit to touch the path
    # is the right one to read either way: on a squash merge the branch's commit ids are gone from the
    # history and GitHub has folded the branch's messages, trailers and all, into the squash.
    history = gh(f"repos/{repo}/commits", [("path", path), ("sha", oid), ("per_page", 1)])
    return provenance.tool_evidence([history[0]["commit"]["message"]]) if history else None


def prs(out_path, projects, besides=()):
    # Docs from merged pull requests that said whether AI wrote them. Only worth doing in a project whose
    # policy makes contributors declare: see provenance.py for what counts as a declaration either way.
    rows, seen = load_done(out_path)
    done = {r["repo"] for r in rows}
    per_repo = collections.Counter((r["repo"], r["provenance"]) for r in rows)
    # unlike the other sides, --besides here only keeps texts out, not repos: revisiting a repo the
    # window method already read is the whole point, since this reads the same docs with a real label
    for path in besides:
        seen |= load_done(path)[1]
    jobs = [line.split() for line in open(projects) if line.strip()]
    kept = collections.Counter()
    with open(out_path, "a") as out:
        for n, (repo, effective, *rest) in enumerate(jobs):
            if repo in done:
                continue
            pages = int(rest[0]) if rest else MAX_PR_PAGES
            query = f"repo:{repo} is:pr is:merged merged:>={effective} sort:updated-desc"
            after, scanned = None, 0
            declared, dropped, channels = collections.Counter(), collections.Counter(), collections.Counter()
            for _ in range(pages):
                page = (graphql(PR_QUERY, PR_GAP, q=query, **({"after": after} if after else {})) or {}).get("search")
                if not page:
                    break
                for pr in page["nodes"]:
                    if not pr or not pr.get("mergeCommit"):
                        continue
                    scanned += 1
                    messages = [c["commit"]["message"] for c in pr["commits"]["nodes"]]
                    label, why, channel = provenance.read(pr["body"], messages, (pr["author"] or {}).get("login"))
                    declared[label] += 1
                    channels[channel or "nothing"] += 1
                    if label == "unknown" or per_repo[(repo, label)] >= MAX_PR_DOCS:
                        continue
                    taken = 0
                    for path, kind, additions in pr_docs(pr):
                        if taken >= MAX_DOCS_PER_PR or per_repo[(repo, label)] >= MAX_PR_DOCS:
                            break
                        text = raw(repo, pr["mergeCommit"]["oid"], path)
                        if not text:
                            dropped["gone"] += 1
                            continue
                        if not usable(text):
                            dropped["not prose"] += 1
                            continue
                        if fingerprint(text) in seen:
                            dropped["already held"] += 1
                            continue
                        # the declaration is the whole pull request's, so it only speaks for a file the
                        # pull request wrote: an edit to a page carries someone else's words
                        if additions < 0.8 * len(text.splitlines()):
                            dropped["only edited"] += 1
                            continue
                        seen.add(fingerprint(text))
                        out.write(json.dumps({"repo": repo, "path": path, "sha": pr["mergeCommit"]["oid"], "pr": pr["number"],
                                              "merged": (pr["mergedAt"] or "")[:10], "author": (pr["author"] or {}).get("login"),
                                              "effective": effective, "doc_type": kind, "provenance": label, "why": why,
                                              "channel": channel,
                                              "file_tool": file_tool(repo, path, pr["mergeCommit"]["oid"]),
                                              "additions": additions, "text": text}) + "\n")
                        out.flush()
                        per_repo[(repo, label)] += 1
                        kept[label] += 1
                        taken += 1
                if not page["pageInfo"]["hasNextPage"]:
                    break
                after = page["pageInfo"]["endCursor"]
            # a run that keeps nothing should say which rule ate the docs, not leave it to be guessed
            log(f"{n + 1}/{len(jobs)} {repo}: {scanned} merged PRs, declared {dict(declared)}, "
                f"from {dict(channels)}, kept {per_repo[(repo, 'ai')]} ai {per_repo[(repo, 'human')]} human, "
                f"dropped {dict(dropped)}")
    log(f"done: {dict(kept)}")


def credits_tool(message, tool):
    low = message.lower()
    return any(q.strip('"').lower() in low for q in TOOLS[tool])


def ai(out_path):
    rng = random.Random(29 + sum(1 for _ in open(out_path)) if os.path.exists(out_path) else 29)
    rows, seen = load_done(out_path)
    counts = {tool: sum(r["tool"] == tool for r in rows) for tool in TOOLS}
    per_repo = {}
    for r in rows:
        per_repo[r["repo"]] = per_repo.get(r["repo"], 0) + 1
    tried_commits, info = set(), {}
    searches = 0
    with open(out_path, "a") as out:
        while searches < MAX_SEARCHES and any(counts[t] < TARGETS[t] for t in TOOLS):
            for tool in TOOLS:
                if counts[tool] >= TARGETS[tool]:
                    continue
                phrase, word, month = rng.choice(TOOLS[tool]), rng.choice(WORDS), rng.choice(MONTHS)
                query = f"{phrase} {word} committer-date:{month}"
                found = gh("search/commits", [("q", query), ("per_page", 100)], SEARCH_GAP, "search")
                searches += 1
                items = (found or {}).get("items", [])
                hits = [(i["repository"]["full_name"], i["sha"], i["commit"]["message"], i["commit"]["committer"]["date"][:10]) for i in items if not i["repository"].get("fork")]
                hits = [h for h in hits if h[1] not in tried_commits and credits_tool(h[2], tool)]
                info |= repo_info(sorted({h[0] for h in hits} - set(info)))
                fresh = 0
                for repo, sha, _message, date in hits:
                    meta = info.get(repo)
                    tried_commits.add(sha)
                    if not meta or meta["isFork"] or meta["stargazerCount"] < MIN_AI_STARS or (meta["primaryLanguage"] or {}).get("name") not in LANGUAGES:
                        continue
                    if per_repo.get(repo, 0) >= MAX_AI_REPO_DOCS:
                        continue
                    commit = gh(f"repos/{repo}/commits/{sha}")
                    for entry in (commit or {}).get("files", []):
                        kind = doc_type(entry["filename"])
                        if not kind or entry["status"] not in ("added", "modified") or per_repo.get(repo, 0) >= MAX_AI_REPO_DOCS:
                            continue
                        text = raw(repo, sha, entry["filename"])
                        if not text or not usable(text) or fingerprint(text) in seen:
                            continue
                        # a file only counts if this commit wrote nearly all of it, otherwise the label covers someone else's words
                        if entry["additions"] < 0.8 * len(text.splitlines()):
                            continue
                        seen.add(fingerprint(text))
                        out.write(json.dumps({"repo": repo, "path": entry["filename"], "sha": sha, "date": date, "stars": meta["stargazerCount"],
                                              "language": meta["primaryLanguage"]["name"], "created": meta["createdAt"][:10], "doc_type": kind,
                                              "tool": tool, "status": entry["status"], "text": text}) + "\n")
                        out.flush()
                        per_repo[repo] = per_repo.get(repo, 0) + 1
                        counts[tool] += 1
                        fresh += 1
                log(f"[{searches}] {query}: {len(hits)} commits, {fresh} docs; {counts}")
    log(f"done after {searches} searches: {counts}")


def main():
    parser = argparse.ArgumentParser(description="fetch training docs from GitHub")
    parser.add_argument("side", choices=["human", "ai", "recent", "pr"])
    parser.add_argument("out")
    parser.add_argument("repos", nargs="?", default="400", help="repo count for human, windows file for recent, projects file for pr")
    parser.add_argument("--wait", type=int, default=0, help="seconds to wait first, to let a rate limit clear")
    parser.add_argument("--besides", metavar="FILE", action="append", default=[],
                        help="skip repos and texts this file already holds, so a new out file is a clean new source")
    args = parser.parse_args()
    time.sleep(args.wait)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    if args.side == "human":
        human(args.out, int(args.repos), args.besides)
    elif args.side == "recent":
        recent(args.out, args.repos, args.besides)
    elif args.side == "pr":
        prs(args.out, args.repos, args.besides)
    else:
        ai(args.out)


if __name__ == "__main__":
    main()

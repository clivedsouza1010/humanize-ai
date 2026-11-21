# A project's own docs from before its AI policy existed: the control for whether a high flag rate is
# about who wrote the text or about how that project writes.
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_github_docs as G

# bench/holdouts.py and the gate's held-out docs check both read this path, and nothing reads any other.
# It used to write bench/control.jsonl, so the file the sixth check depends on could not be rebuilt.
GITHUB = os.path.expanduser("~/.cache/humanize/data/github")
OUT = os.path.join(GITHUB, "pr-control.jsonl")
POLICIES = [os.path.join(GITHUB, name) for name in ("policies.json", "policies-train.json")]
# The nine projects whose docs pull requests carried a disclosure, and how many docs to take from each.
# threat-dragon has only 4 that qualify and hister 12; the caps are what the 168-doc holdout was built with.
DISCLOSURE = [("NixOS/nix", 14), ("OWASP/CheatSheetSeries", 20), ("OWASP/threat-dragon", 14),
              ("agones-dev/agones", 14), ("asciimoo/hister", 12), ("earthaccess-dev/earthaccess", 14),
              ("open-logic/open-logic", 14), ("trickstercache/trickster", 14), ("wagtail/wagtail", 14)]
# the extra pre-ChatGPT snapshot for the three projects old enough to have one; holdouts.py filters these out
BEFORE_CHATGPT = [("OWASP/CheatSheetSeries", "2022-11-01", 20), ("trickstercache/trickster", "2022-11-01", 14),
                  ("wagtail/wagtail", "2022-11-01", 14)]


# Each project is snapshotted on the day its own policy took effect. That date is read from the policy
# files rather than copied here, because a hardcoded list is what silently lost six of the twelve jobs.
def jobs(policy_files=POLICIES):
    effective = {}
    for path in policy_files:
        if os.path.exists(path):
            for project in json.load(open(path))["projects"]:
                effective[project["repo"]] = project["effective"]
    missing = [repo for repo, _ in DISCLOSURE if repo not in effective]
    if missing:
        sys.exit(f"no policy date for {', '.join(missing)}: fetch policies.json and policies-train.json first")
    return BEFORE_CHATGPT + [(repo, effective[repo], cap) for repo, cap in DISCLOSURE]


def fetch():
    seen = set()
    with open(OUT, "w") as out:
        for repo, date, cap in jobs():
            head = G.gh(f"repos/{repo}/commits", [("until", f"{date}T00:00:00Z"), ("per_page", 1)])
            if not head:
                print(f"  no commits for {repo} before {date}"); continue
            sha = head[0]["sha"]
            tree = G.gh(f"repos/{repo}/git/trees/{sha}", [("recursive", 1)])
            # the same relaxed rule pr_docs uses, so the control and the labelled docs are the same kind of thing
            def kind(path):
                name = path.rsplit("/", 1)[-1]
                return G.doc_type(path) or ("guide" if path.endswith((".md", ".mdx")) and not G.SKIP_PATH.search(path)
                                            and not G.SKIP_NAME.search(name) and not G.TRANSLATED.search(name) else None)
            paths = [e["path"] for e in (tree or {}).get("tree", []) if e["type"] == "blob" and kind(e["path"])]
            paths.sort(key=G.fingerprint)
            kept = 0
            for path in paths:
                if kept >= cap:
                    break
                text = G.raw(repo, sha, path)
                if not text or not G.usable(text) or G.fingerprint(text) in seen:
                    continue
                seen.add(G.fingerprint(text))
                out.write(json.dumps({"repo": repo, "before": date, "path": path, "text": text}) + "\n")
                kept += 1
            print(f"{repo} before {date}: {kept} of {len(paths)} docs", flush=True)


if __name__ == "__main__":
    fetch()

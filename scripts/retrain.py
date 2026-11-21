# Learn from new labels and datasets: rebuild the data, refit a candidate, and promote it only if it holds up.
# Usage: retrain.py                    rebuild, refit, and promote each genre that has new data and holds up
#        retrain.py --force docs --note "why"   promote that genre (or all) even if the gate says no
#        retrain.py --history          list past versions
#        retrain.py --rollback V       put version V back
import argparse
import collections
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

import numpy as np
from sklearn.metrics import roc_auc_score

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(SKILL, "bench"))
import fit as F  # noqa: E402
from holdouts import human_holdout, rates  # noqa: E402
from detect import MIN_VERDICT_WORDS  # noqa: E402

DATA = os.path.expanduser("~/.cache/humanize/data")
BLEND = os.path.join(HERE, "blend.json")
CANDIDATE = os.path.join(HERE, "blend-candidate.json")
METRICS = os.path.join(SKILL, "bench", "metrics.md")
HISTORY = os.path.join(HERE, "blend-history")
LOG = os.path.join(HISTORY, "log.jsonl")
# the training corpus is the maintainer's own and isn't shipped with the skill
CORPUS = ("raid.jsonl", "reddit_eli5.jsonl", "aeslc-test.parquet")
# a candidate may lose this much, averaged over 20 paired re-splits of the rows the current detector knows, and still be promoted
MAX_AUROC_DROP = 0.005
MAX_FLAGGED_RISE = 0.01
MAX_CAUGHT_DROP = 0.02
# a new batch's own human rows may flag this much above the pooled rate before the batch is suspect
MAX_NEW_FLAGGED_EXCESS = 0.03
# below this many judgeable human rows a batch's rate is noise: clean batches cross the line 6% of the time
# at 200-249 rows and 21% at 150-199, against 1% at 250 and up
MIN_NEW_HUMANS = 250
# How much more of the held-out human docs a candidate may call AI. These never train and their provenance
# is a ban on AI contributions or a snapshot predating the project's policy, so a rise there is a false
# alarm and nothing else. 0.01 is about three documents of 275, and it is a real move rather than noise:
# bench/score_blend_versions.py reads the number off every saved blend, and five consecutive versions held
# it at 0.091 before the workhorse batch took it to 0.105 and the 41 declared-AI docs to 0.127. The gate's
# own human_flagged saw 0.001 of that, because it is pooled over thousands of pre-2023 docs.
MAX_HOLDOUT_RISE = 0.01
# below this many documents the pooled rate turns on single documents
MIN_HOLDOUT_DOCS = 100
# The one refusal --force cannot override. Every other reason is a cost the gate priced and a person can
# decide to pay; this one means the candidate was refit from rows the current detector already knows, so
# there is no measurement to accept -- promoting it just moves the blend around by chance.
NOT_JUDGED = ["no new data"]


def pool(rows, genre):
    # the rows fit.py trains this genre on
    rows = [r for r in rows if r["split"] != "extra" and F.GENRES[genre]["belongs"](r)]
    if genre == "docs":
        rows = [r for r in rows if r.get("section", 0) < F.DOC_SECTIONS_TRAINED and F.words(r) >= F.DOC_MIN_WORDS]
    return rows


def paired(genre, rows, current, candidate, is_new):
    # one split misled this gate in both directions, so fit both setups on the same 20 re-splits and score the same rows
    cfg = F.GENRES[genre]
    setups = {"current": ([r for r in rows if not is_new(r)], current.get("c", candidate["c"]), current["features"]),
              "candidate": (rows, candidate["c"], candidate["features"])}
    # Count the rows the rate is actually taken on, not every row in the pool: a batch of short posts
    # can bring 300 rows and be judged on far fewer. Sources with nothing judgeable are still listed, at 0.
    new_sources = {r["source"] for r in rows if is_new(r) and r["label"] == 0}
    new_humans = collections.Counter(r["source"] for r in rows if is_new(r) and r["label"] == 0
                                     and r["features"]["n_words"] >= MIN_VERDICT_WORDS)
    report = {}
    for name, (known, c, names) in setups.items():
        known_ids = {id(r) for r in known}
        aurocs, flagged, caught, new_ai, new_human = [], [], [], [], []
        by_source = collections.defaultdict(list)
        for seed in range(20):
            train, test = F.resplit(rows, seed)
            test = [r for r in test if r["features"]["n_words"] >= MIN_VERDICT_WORDS]
            scaler, model = F.fit([r for r in train if id(r) in known_ids], names, c, cfg["clamp"])
            old = [r for r in test if not is_new(r)]
            probs = F.predict(scaler, model, old, names)
            y = np.array([r["label"] for r in old])
            aurocs.append(roc_auc_score(y, probs))
            flagged.append((probs[y == 0] >= 0.5).mean())
            caught.append((probs[y == 1] >= 0.5).mean())
            new = [r for r in test if is_new(r)]
            if new:
                new_probs = F.predict(scaler, model, new, names)
                new_ai += [p >= 0.5 for p, r in zip(new_probs, new) if r["label"] == 1]
                for prob, row in zip(new_probs, new):
                    if row["label"] == 0:
                        new_human.append(prob >= 0.5)
                        by_source[row["source"]].append(prob >= 0.5)
        ai_rate = float(np.mean(new_ai)) if new_ai else None
        human_rate = float(np.mean(new_human)) if new_human else None
        report[name] = {"auroc": float(np.mean(aurocs)), "human_flagged": float(np.mean(flagged)), "ai_caught": float(np.mean(caught)),
                        "new_ai_caught": ai_rate, "new_human_flagged": human_rate,
                        # per source as well as pooled: one clean source beside a bad one hides it in the average
                        "new_human_by_source": {s: {"flagged": float(np.mean(by_source[s])) if by_source[s] else None,
                                                    "humans": new_humans[s]} for s in sorted(new_sources)},
                        # both sides count the same, or the side with more rows would decide it
                        "new_right": float(np.mean([v for v in (ai_rate, None if human_rate is None else 1 - human_rate) if v is not None])) if new_ai or new_human else None}
    return report


def reasons_to_keep(cur, cand):
    # why the current detector stays; an empty list promotes the candidate
    reasons = []
    if cand["auroc"] < cur["auroc"] - MAX_AUROC_DROP:
        reasons.append(f"AUROC fell {cur['auroc']:.3f} -> {cand['auroc']:.3f}")
    if cand["human_flagged"] > cur["human_flagged"] + MAX_FLAGGED_RISE:
        reasons.append(f"more human text flagged {cur['human_flagged']:.3f} -> {cand['human_flagged']:.3f}")
    if cand["ai_caught"] < cur["ai_caught"] - MAX_CAUGHT_DROP:
        reasons.append(f"less AI caught {cur['ai_caught']:.3f} -> {cand['ai_caught']:.3f}")
    if cur["new_right"] is not None and cand["new_right"] < cur["new_right"]:
        reasons.append(f"does worse on the new data {cur['new_right']:.3f} -> {cand['new_right']:.3f}")
    # a batch whose own human rows flag well above the pool is either mislabelled or a register this can't read
    for source, m in cand.get("new_human_by_source", {}).items():
        if m["flagged"] is None or m["humans"] < MIN_NEW_HUMANS:
            continue
        if m["flagged"] > cand["human_flagged"] + MAX_NEW_FLAGGED_EXCESS:
            reasons.append(f"flags {source}'s own human rows {m['flagged']:.3f} against {cand['human_flagged']:.3f} "
                           f"on the rest ({m['humans']} rows)")
    # the one check read on text outside the split: the gate's own false-alarm figure is pooled over
    # thousands of pre-2023 docs, so a few hundred recent ones cannot move it however badly they go
    held = cand.get("holdout")
    if held and held["docs"] >= MIN_HOLDOUT_DOCS and cur.get("holdout"):
        if held["flagged"] > cur["holdout"]["flagged"] + MAX_HOLDOUT_RISE:
            reasons.append(f"calls more held-out human docs AI {cur['holdout']['flagged']:.3f} -> "
                           f"{held['flagged']:.3f} ({held['docs']} docs that never train)")
    return reasons


def decide(report_g):
    # one genre's verdict: which new sources are too thin to judge, and why the current detector would stay
    cand = report_g["candidate"]
    thin = [f"{s} ({m['humans']})" for s, m in cand.get("new_human_by_source", {}).items() if m["humans"] < MIN_NEW_HUMANS]
    held = cand.get("holdout")
    if held and 0 < held["docs"] < MIN_HOLDOUT_DOCS:
        thin.append(f"the held-out human docs ({held['docs']})")
    return thin, reasons_to_keep(report_g["current"], cand)


def holdout_rates(blends, items):
    # the same measurement bench/holdouts.py prints, taken on the blend that would actually ship
    out = {}
    for name, blend in blends.items():
        docs, flagged, sections = rates(blend, items)
        out[name] = {"docs": docs, "flagged": flagged, "sections": sections}
    return out


def merged_metrics(promoted, kept):
    # fit.py writes a header and then one '## ' block per genre, in GENRES order
    head, *blocks = re.split(r"(?m)^(?=## )", open(os.path.join(SKILL, "bench", "metrics-candidate.md")).read())
    fresh = dict(zip(F.GENRES, blocks))
    if not kept:
        return head + "".join(fresh.values())
    old = dict(zip(F.GENRES, re.split(r"(?m)^(?=## )", open(METRICS).read())[1:]))
    note = f"This retrain promoted {', '.join(promoted)}. {', '.join(kept)} stayed as it was, so its section is from the fit before.\n\n"
    return head + note + "".join(fresh[g] if g in promoted else old[g] for g in F.GENRES)


def log(entry):
    os.makedirs(HISTORY, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def archive(note):
    os.makedirs(HISTORY, exist_ok=True)
    version = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy(BLEND, os.path.join(HISTORY, f"{version}.json"))
    # the metrics travel with the blend, so a rollback brings back the numbers that describe it
    if os.path.exists(METRICS):
        shutil.copy(METRICS, os.path.join(HISTORY, f"{version}.md"))
    log({"version": version, "archived": datetime.datetime.now().isoformat(timespec="seconds"), "note": note})
    return version


# Which genres this run installs, and which --force asked for and cannot have.
def promote_list(genres, forced, why_not):
    promoted = [g for g in genres if g not in why_not or (g in forced and why_not[g] != NOT_JUDGED)]
    declined = [g for g in genres if g in forced and why_not.get(g) == NOT_JUDGED]
    return promoted, declined


def unseen(row, labels, sources):
    # a row the current detector never trained on: an unseen label, or a whole new dataset
    if row["source"] == "feedback":
        return F.label_digest(row["group"].split(":", 1)[1]) not in labels
    return row["source"] not in sources


def main():
    parser = argparse.ArgumentParser(description="retrain the humanize detector from labels")
    parser.add_argument("--force", nargs="?", const="all", choices=["all", *F.GENRES], help="promote this genre even if the gate says no")
    parser.add_argument("--note", default="", help="why, saved in the version log (say why when you --force)")
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--rollback", metavar="VERSION")
    args = parser.parse_args()

    if args.history:
        for line in open(LOG) if os.path.exists(LOG) else []:
            print(line.strip())
        return
    if args.rollback:
        source = os.path.join(HISTORY, f"{args.rollback}.json")
        if not os.path.exists(source):
            versions = sorted(f[:-5] for f in os.listdir(HISTORY) if f.endswith(".json")) if os.path.isdir(HISTORY) else []
            sys.exit(f"no version {args.rollback}; saved versions: {', '.join(versions) or 'none'}")
        archive(f"replaced by rollback to {args.rollback}")
        shutil.copy(source, BLEND)
        if os.path.exists(source[:-5] + ".md"):
            shutil.copy(source[:-5] + ".md", METRICS)
        print(f"blend.json is now version {args.rollback}")
        return

    missing = [name for name in CORPUS if not os.path.exists(os.path.join(DATA, name))]
    if missing:
        sys.exit(f"retraining needs the training corpus in {DATA}, which isn't shipped with the skill; missing: {', '.join(missing)}. "
                 "Labels you saved stay saved.")
    py = sys.executable
    dataset, features, previous = (os.path.join(DATA, n) for n in ("dataset.jsonl", "features.jsonl", "features-prev.jsonl"))
    # the batch step may load the models, so free the scorer's copy first; it restarts on next use
    subprocess.run(["pkill", "-f", "detect.py --serve"])
    subprocess.run([py, os.path.join(SKILL, "bench", "build_set.py"), DATA, dataset], check=True)
    # features.jsonl is this script's own output; a first run has none and scores every row
    if os.path.exists(features):
        shutil.copy(features, previous)
    reuse = ["--reuse", previous] if os.path.exists(previous) else []
    subprocess.run([py, os.path.join(HERE, "detect.py"), "--batch", dataset, "--out", features, *reuse], check=True)
    candidate_metrics = os.path.join(SKILL, "bench", "metrics-candidate.md")
    subprocess.run([py, os.path.join(SKILL, "bench", "fit.py"), features, CANDIDATE, candidate_metrics], check=True, stdout=subprocess.DEVNULL)

    rows = [json.loads(line) for line in open(features)]
    current, candidate = json.load(open(BLEND)), json.load(open(CANDIDATE))
    # scored once for both setups, outside the split, because none of it is in the dataset at all
    held = human_holdout(os.path.join(DATA, "github"))
    forced = list(F.GENRES) if args.force == "all" else [args.force] if args.force else []
    report, why_not = {}, {}
    show = lambda v: "-" if v is None else f"{v:.3f}"
    print(f"\n{'genre':<6} {'version':<10} {'AUROC':>6} {'human flagged':>14} {'AI caught':>10} {'new AI caught':>14} {'new human flagged':>18}   (mean of 20 paired re-splits)")
    for genre in F.GENRES:
        labels, sources = set(current[genre].get("labels", [])), set(current[genre]["sources"])
        is_new = lambda r: unseen(r, labels, sources)  # noqa: B023
        rows_g = pool(rows, genre)
        if not any(is_new(r) for r in rows_g):
            # nothing new to learn, and refitting anyway only moves it around by chance
            print(f"{genre:<6} no new data, stays as it is")
            why_not[genre] = list(NOT_JUDGED)
            continue
        report[genre] = paired(genre, rows_g, current[genre], candidate[genre], is_new)
        # Docs only, for two reasons: the held-out set is documentation and prose has no equivalent that
        # never trains, and the prose blend carries no ngram table at all, so rates() would raise on it.
        if genre == "docs" and held:
            for name, m in holdout_rates({"current": current[genre], "candidate": candidate[genre]}, held).items():
                report[genre][name]["holdout"] = m
        for name, m in report[genre].items():
            print(f"{genre:<6} {name:<10} {m['auroc']:>6.3f} {m['human_flagged']:>14.3f} {m['ai_caught']:>10.3f} {show(m['new_ai_caught']):>14} {show(m['new_human_flagged']):>18}")
        before, after = (report[genre][n].get("holdout") for n in ("current", "candidate"))
        if before and after:
            print(f"{genre:<6} held-out human docs called AI {before['flagged']:.3f} -> {after['flagged']:.3f}"
                  f"   ({after['docs']} docs that never train, bench/holdouts.py prints the same number)")
        thin, reasons = decide(report[genre])
        # say which new sources are too thin to judge rather than passing them in silence
        if thin:
            print(f"{genre:<6} too few human rows to judge: {', '.join(thin)}")
        if reasons:
            why_not[genre] = reasons

    labels = sum(1 for _ in open(os.path.join(DATA, "feedback.jsonl"))) if os.path.exists(os.path.join(DATA, "feedback.jsonl")) else 0
    entry = {"run": datetime.datetime.now().isoformat(timespec="seconds"), "labels": labels, "report": report, "note": args.note}
    promoted, force_declined = promote_list(F.GENRES, forced, why_not)
    kept = [g for g in F.GENRES if g not in promoted]
    for genre in force_declined:
        print(f"\n--force does not apply to {genre}: no new data, so there is no candidate to accept.")
    for genre in kept:
        if why_not[genre] != NOT_JUDGED:
            print(f"\nKept the current {genre} detector:\n- " + "\n- ".join(why_not[genre]))
            print(f'The new data stays saved. To accept this anyway: retrain.py --force {genre} --note "why"')
    if not promoted:
        log(entry | {"promoted": [], "why_not": why_not})
        return
    version = archive("replaced by retrain")
    metrics = merged_metrics(promoted, kept)
    blend = {g: (candidate if g in promoted else current)[g] for g in F.GENRES}
    with open(BLEND + ".tmp", "w") as f:
        json.dump(blend, f, indent=1)
    os.replace(BLEND + ".tmp", BLEND)
    with open(METRICS, "w") as f:
        f.write(metrics)
    log(entry | {"promoted": promoted, "previous": version, "forced": [g for g in promoted if g in why_not]})
    print(f"\nPromoted {', '.join(promoted)}. The previous detector is saved as {version} (retrain.py --rollback {version}).")


if __name__ == "__main__":
    main()

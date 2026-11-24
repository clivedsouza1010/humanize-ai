# Fit one logistic blend per genre (prose, technical docs), measure each honestly, write both to the paths given.
# Installing the result is bench/retrain.py's job, not this script's.
# Usage: python fit.py FEATURES.jsonl BLEND_OUT.json METRICS_OUT.md
import datetime
import functools
import hashlib
import json
import math
import os
import secrets
import sys

import numpy as np
from scipy.optimize import minimize, minimize_scalar
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler, normalize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "plugin", "skills", "humanize-ai", "scripts"))
from detect import (KNOWN_TEXT_TOP1, MIN_VERDICT_WORDS, RECALLED, REGISTERS, STRUCTURAL_FLAGS, canon, link_excess, prepare,  # noqa: E402
                    sentence_flags, split_sentences, voice_score, voice_terms)

# a label id is a hash of the labelled text, so anyone with a public copy of that text could match it;
# salting with a value that never leaves this machine keeps blend.json from saying which texts were labelled
SALT_FILE = os.path.expanduser("~/.cache/humanize/label-salt")


@functools.lru_cache
def _salt(path):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
                f.write(secrets.token_hex(16))
        except FileExistsError:
            pass  # another process made it first; use theirs
    salt = open(path).read().strip()
    if not salt:
        sys.exit(f"{path} is empty; restore it from a backup, or delete it to start a new salt (every label then counts as new once)")
    return salt


def label_digest(label_id):
    return hashlib.sha1(f"{_salt(SALT_FILE)}:{label_id}".encode()).hexdigest()[:10]


def seen_labels(rows):
    return sorted({label_digest(r["group"].split(":", 1)[1]) for r in rows if r["source"] == "feedback"})


LM = ["binoculars", "fast_detectgpt", "log_ppl", "log_ppl_observer", "x_entropy", "surprisal_std", "top1_frac", "top10_frac",
      "sentence_bino_std", "sentence_bino_min"]
STYLE = [
    "tell_rate", "em_dash_rate", "has_contrast", "triad_rate", "transition_rate", "colon_rate",
    "sent_len_mean", "sent_len_cv", "sent_mid_band", "sent_len_max", "repeated_starts",
    "first_person_rate", "paren_rate", "digit_rate", "mattr", "word_len",
]
# no contraction or slang counts: they tracked register, not authorship, and the rewrite loop gamed them
FAMILY = {"chatgpt": "openai", "gpt4": "openai", "llama-chat": "meta", "mistral-chat": "mistral", "mpt-chat": "mosaic",
          "cursor": "cursor", "copilot": "copilot", "codex": "codex", "devin": "devin", "gemini": "gemini"}
HUMAN_PASS_QUANTILE = 0.80
# Which human writing a prose text is compared against, by the domain its training rows carry.
# Docs are left out on purpose: their bar is "where only 2% of AI sections fall", not a human quantile.
REGISTER_OF = {"news": "news", "abstracts": "academic", "abstract": "academic", "books": "literary", "fiction": "literary",
               "email": "email", "reddit": "forum", "forum": "forum", "ask": "forum",
               "encyclopedia": "encyclopedia"}
assert set(REGISTER_OF.values()) == set(REGISTERS), "fit.py and detect.py disagree about the registers"
REGISTER_CUT_QUANTILE = 0.90
# under this many human rows the quantile is mostly noise, so that register keeps the pooled cut
MIN_REGISTER_HUMANS = 60
SENTENCE_MIN_WORDS = 12
C_GRID = [0.1, 0.5, 2.0, 5.0]
# AI tells may only push toward AI; a negative weight would let a rewrite pass by adding them
TELL_FEATURES = {"tell_rate", "has_contrast", "transition_rate", "em_dash_rate", "triad_rate"}
DOC_SECTIONS_TRAINED = 4
DOC_MIN_WORDS = 120
# function words, punctuation and a mask for everything else: what the docs detector reads
VOICE = ["ngram"]
CLOSED = set(open(os.path.join(HERE, "closed-words.txt")).read().split())
VOICE_MIN_GROUPS = 10
LINK_CAP = 0.5
# agents with a brief and no web, so their docs have no links for a reason that says nothing about who writes them
LINK_SOURCES = {"gh-human", "gh-2023", "npm", "npm-popular", "gh-ai"}
# 0.5 here stands for 0.7 on the fitted odds: on docs from projects that ban AI that takes false alarms from 20% to 10%, and past 0.7 catches fall faster
CUT_SHIFT = math.log(0.7 / 0.3)
# one shared blend let READMEs drag the boundary for prose, so docs and prose are fitted apart
GENRES = {
    "prose": {"title": "Prose (essays, posts, emails, reviews, news, abstracts)", "belongs": lambda r: r["domain"] != "docs",
              "features": STYLE + LM, "c": None, "clamp": TELL_FEATURES, "bar": "human_q80"},
    # on docs the model scores drift with the calendar and style alone can't tell 2022 people from 2026 agents; function words can
    "docs": {"title": "Technical docs (READMEs, guides, API pages)", "belongs": lambda r: r["domain"] == "docs",
             "features": VOICE, "c": 3.0, "clamp": TELL_FEATURES | {"colon_rate", "first_person_rate"}, "bar": "ai_2pct"},
}


class Model:
    def __init__(self, coef, intercept):
        self.coef_ = np.array([coef])
        self.intercept_ = np.array([intercept])

    def predict_proba(self, xs):
        p = 1 / (1 + np.exp(-(xs @ self.coef_[0] + self.intercept_[0])))
        return np.column_stack([1 - p, p])


def family(row):
    if row["model"].startswith("claude"):
        return "anthropic"
    return FAMILY.get(row["model"], "other" if row["label"] == 1 else "human")


def words(row):
    return len(row["text"].split())


def matrix(rows, names):
    return np.array([[row["features"][n] for n in names] for row in rows]), np.array([row["label"] for row in rows])


_terms = {}


def row_terms(row):
    if row["text"] not in _terms:
        _terms[row["text"]] = voice_terms(canon(row["text"]), CLOSED)
    return _terms[row["text"]]


def fit_voice(rows, c):
    terms = [row_terms(r) for r in rows]
    y = np.array([r["label"] for r in rows])
    seen = ({}, {})
    for row, row_counts in zip(rows, terms):
        for term in row_counts:
            seen[row["label"]].setdefault(term, set()).add(row["group"])
    # a term has to show up in many groups on each side, so one project's habits can't get in
    keep = {t for t, groups in seen[0].items() if len(groups) >= VOICE_MIN_GROUPS and len(seen[1].get(t, ())) >= VOICE_MIN_GROUPS}
    vectorizer = DictVectorizer(dtype=np.float32)
    x = normalize(vectorizer.fit_transform([{t: 1 + math.log(n) for t, n in row_counts.items() if t in keep} for row_counts in terms]))
    model = LogisticRegression(C=c, class_weight="balanced", solver="liblinear", max_iter=200, tol=1e-3).fit(x, y)
    z = model.decision_function(x)
    real = np.array([r["source"] in LINK_SOURCES for r in rows])
    excess = np.array([link_excess(r["ext_rate"], LINK_CAP) for r in rows])[real]
    y_real, z_real = y[real], z[real]
    s = 2 * y_real - 1
    w = np.where(y_real == 1, len(y_real) / (2 * max(y_real.sum(), 1)), len(y_real) / (2 * max(len(y_real) - y_real.sum(), 1)))
    credit = minimize_scalar(lambda v: np.sum(w * np.logaddexp(0, -s * (z_real - v * excess))), bounds=(0, 10), method="bounded").x if y_real.sum() else 0.0
    return {"closed": CLOSED, "weights": dict(zip(vectorizer.feature_names_, model.coef_[0].tolist())),
            "intercept": float(model.intercept_[0]) - CUT_SHIFT, "link_credit": float(credit)}


def fit(rows, names, c, clamp=()):
    if names == VOICE:
        return fit_voice(rows, c), None
    # sklearn's balanced logistic regression, written out so some weights can be held at zero or above
    x, y = matrix(rows, names)
    scaler = StandardScaler().fit(x)
    xs = scaler.transform(x)
    w = np.where(y == 1, len(y) / (2 * y.sum()), len(y) / (2 * (len(y) - y.sum())))
    s = 2 * y - 1

    def loss(theta):
        coef, b = theta[:-1], theta[-1]
        m = s * (xs @ coef + b)
        p = 1 / (1 + np.exp(m))
        grad_z = -w * s * p
        f = c * np.sum(w * np.logaddexp(0, -m)) + 0.5 * coef @ coef
        return f, np.append(c * xs.T @ grad_z + coef, c * grad_z.sum())

    bounds = [(0, None) if n in clamp else (None, None) for n in names] + [(None, None)]
    res = minimize(loss, np.zeros(len(names) + 1), jac=True, method="L-BFGS-B", bounds=bounds)
    return scaler, Model(res.x[:-1], res.x[-1])


def predict(scaler, model, rows, names):
    if names == VOICE:
        # fit() hands back the table in the scaler's place
        z = np.array([voice_score(row_terms(r), scaler) - scaler["link_credit"] * link_excess(r["ext_rate"], LINK_CAP) for r in rows])
        return 1 / (1 + np.exp(-z))
    x, _ = matrix(rows, names)
    return model.predict_proba(scaler.transform(x))[:, 1]


def folds(train, seed):
    y = np.array([r["label"] for r in train])
    return StratifiedGroupKFold(5, shuffle=True, random_state=seed).split(np.zeros(len(train)), y, [r["group"] for r in train])


def choose_c(train, cfg):
    y = np.array([r["label"] for r in train])
    scores = {}
    for c in C_GRID:
        correct = 0
        for seed in range(3):
            for tr, va in folds(train, seed):
                s, m = fit([train[i] for i in tr], cfg["features"], c, cfg["clamp"])
                correct += ((predict(s, m, [train[i] for i in va], cfg["features"]) >= 0.5) == (y[va] == 1)).sum()
        scores[c] = correct / (3 * len(train))
    return max(scores, key=scores.get), scores


def oof_probs(train, cfg, c, seeds=5):
    y = np.array([r["label"] for r in train])
    oof = np.zeros((seeds, len(train)))
    for seed in range(seeds):
        for tr, va in folds(train, seed):
            s, m = fit([train[i] for i in tr], cfg["features"], c, cfg["clamp"])
            oof[seed, va] = predict(s, m, [train[i] for i in va], cfg["features"])
    return oof[:, y == 0].ravel(), oof[:, y == 1].ravel(), oof


def register_of(row):
    return REGISTER_OF.get(row.get("domain"))


def register_thresholds(train, oof):
    # One cut cannot mean one thing across registers: 0.5 sits at the 63rd percentile of news writers'
    # scores and above nearly all literary ones, so news prose gets flagged 37% of the time and books almost never.
    # Each register with human writing of its own gets the cut and bar its own writers put there.
    out = {}
    for name in sorted(set(REGISTER_OF.values())):
        humans = [i for i, r in enumerate(train) if r["label"] == 0 and register_of(r) == name]
        if len(humans) < MIN_REGISTER_HUMANS:
            continue
        scores = oof[:, humans].ravel()
        out[name] = {"threshold_ai": float(np.quantile(scores, REGISTER_CUT_QUANTILE)),
                     "threshold_human": float(np.quantile(scores, HUMAN_PASS_QUANTILE)),
                     "human_reference": np.quantile(scores, np.linspace(0, 1, 101)).tolist(),
                     "humans": len(humans)}
    return out


def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan")
    p, d = k / n, 1 + z * z / n
    centre, half = (p + z * z / (2 * n)) / d, z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return centre - half, centre + half


def rate(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.3f} ({lo:.2f}-{hi:.2f})" if n else "-"


def table_row(name, scores, labels, cut):
    pred = scores >= cut
    ai, human = labels == 1, labels == 0
    acc = (pred == ai).mean()
    return f"| {name} | {acc:.3f} | {rate(int(pred[ai].sum()), int(ai.sum()))} | {rate(int(pred[human].sum()), int(human.sum()))} | {roc_auc_score(labels, scores):.3f} |"


def resplit(rows, seed):
    rng = np.random.default_rng(seed)
    # one draw per group: a repo with rows from two sources would otherwise get two chances at the test side
    share = {}
    for row in rows:
        share[row["group"]] = max(share.get(row["group"], 0.0), 0.4 if row["source"].startswith("claude") else 0.3)
    groups = sorted(share)
    test_groups = {g for g, draw in zip(groups, rng.random(len(groups))) if draw < share[g]}
    return [r for r in rows if r["group"] not in test_groups], [r for r in rows if r["group"] in test_groups]


def doc_verdict(sections, probs, threshold_human):
    # the same rule analyse_document() applies: share of words in AI sections; short and known-text sections don't decide
    scored = [(p, r["features"]["n_words"]) for p, r in zip(probs, sections)
              if r["features"]["n_words"] >= MIN_VERDICT_WORDS and r["features"]["top1_frac"] < KNOWN_TEXT_TOP1]
    counted = [(p, n) for p, n in scored if n >= DOC_MIN_WORDS] or scored
    if not counted:
        return None
    total = sum(n for _, n in counted)
    ai_share = sum(n for p, n in counted if p >= 0.5) / max(total, 1)
    not_human = sum(n for p, n in counted if p >= threshold_human) / max(total, 1)
    if ai_share >= 0.25:
        return "ai"
    return "human" if not_human < 0.5 and max(p for p, _ in counted) < 0.9 else "unclear"


def flag_support(rows):
    # per-sentence AI rate over human rate for each structural habit; under 10 AI hits there's nothing to go on
    hits = {name: [0, 0] for name in STRUCTURAL_FLAGS}
    sentences = [0, 0]
    for r in rows:
        for sentence in split_sentences(canon(prepare(r["text"]))):
            sentences[r["label"]] += 1
            for name in set(sentence_flags(sentence)) & set(STRUCTURAL_FLAGS):
                hits[name][r["label"]] += 1
    return {name: 0.0 if ai < 10 else (ai / sentences[1]) / max(human / sentences[0], 1e-9) for name, (human, ai) in hits.items()}


def sentence_lift(rows, cut):
    # how much likelier an AI sentence is to fall under the cut than a human one
    under = {0: [], 1: []}
    for r in rows:
        under[r["label"]] += [ce / xe < cut for n, ce, xe in r["sentences"] if n >= SENTENCE_MIN_WORDS and xe]
    return np.mean(under[1]) / max(np.mean(under[0]), 1e-9)


def fit_genre(cfg, rows, all_sections, extra, out):
    names = cfg["features"]
    train = [r for r in rows if r["split"] == "train"]
    # detect.py gives no verdict under 80 words, so those rows can train but aren't scored
    test = [r for r in rows if r["split"] == "test" and r["features"]["n_words"] >= MIN_VERDICT_WORDS]
    y_train = np.array([r["label"] for r in train])
    y_test = np.array([r["label"] for r in test])
    c, c_scores = cfg["c"], None
    if not c:
        c, c_scores = choose_c(train, cfg)
    out += [f"## {cfg['title']}", "", f"{len(rows)} rows ({len(train)} train, {len(test)} test), {len(names)} features. Regularisation C = {c}"
            + (", picked by grouped 5-fold CV on train (" + ", ".join(f"C={k}: {v:.3f}" for k, v in c_scores.items()) + ")." if c_scores else ", fixed; moving it changed almost nothing."), ""]

    scaler, model = fit(train, names, c, cfg["clamp"])
    test_probs = predict(scaler, model, test, names)
    out += ["### Held-out test split", "", "AI caught and human flagged are at probability 0.5, with 95% Wilson intervals.", "",
            "| detector | accuracy | AI caught | human flagged | AUROC |", "|---|---|---|---|---|"]
    bino_train = -np.array([r["features"]["binoculars"] for r in train])
    best = max(np.unique(bino_train), key=lambda cut: ((bino_train >= cut) == (y_train == 1)).mean())
    # lower Binoculars means more machine-like, so negate it and use the best train cut
    out.append(table_row("Binoculars alone (best train cut)", -np.array([r["features"]["binoculars"] for r in test]), y_test, best))
    out.append(table_row("fakespot RoBERTa alone", np.array([r["features"]["heldout_roberta"] for r in test]), y_test, 0.5))
    if names != STYLE:
        for name, subset in [("style only", STYLE), ("LM only", LM), ("style + LM", STYLE + LM)][: 3 if names == VOICE else 2]:
            s, m = fit(train, subset, c, cfg["clamp"])
            out.append(table_row(name, predict(s, m, test, subset), y_test, 0.5))
    out.append(table_row("**blend**", test_probs, y_test, 0.5))

    oof_human, oof_ai, oof = oof_probs(train, cfg, c)
    registers = register_thresholds(train, oof)
    if cfg["bar"] == "human_q80":
        threshold_human = float(np.quantile(oof_human, HUMAN_PASS_QUANTILE))
        bar_note = f"the {int(HUMAN_PASS_QUANTILE * 100)}th percentile of out-of-fold human training scores"
    else:
        # a bar where only 2% of AI sections pass; the human 80th percentile here was unreachable without gaming
        threshold_human = float(min(max(np.quantile(oof_ai, 0.02), np.quantile(oof_human, HUMAN_PASS_QUANTILE)), 0.5))
        bar_note = "the score below which only 2% of out-of-fold AI training sections fall"
    out += ["", "### By source (held-out test)", "",
            f"'reads human' means probability under threshold_human = {threshold_human:.3f}, {bar_note}. "
            f"Out of fold, {(oof_human < threshold_human).mean():.0%} of human and {(oof_ai < threshold_human).mean():.1%} of AI training texts are under it. "
            "That's the bar the rewrite loop aims for.", "",
            "| source / model or register | label | flagged as AI (>= 0.5) | reads human |", "|---|---|---|---|"]
    key_of = (lambda r: (r["source"], r.get("register", r["model"]), r["label"])) if names == VOICE else (lambda r: (r["source"], r["model"], r["label"]))
    for key in sorted({key_of(r) for r in test}):
        probs = np.array([p for r, p in zip(test, test_probs) if key_of(r) == key])
        out.append(f"| {key[0]} / {key[1]} | {'AI' if key[2] else 'human'} | {rate(int((probs >= 0.5).sum()), len(probs))} | {rate(int((probs < threshold_human).sum()), len(probs))} |")

    if registers:
        out += ["", "### Per-register cuts (held-out test)", "",
                f"A register's cut is the score {round((1 - REGISTER_CUT_QUANTILE) * 100)}% of its own human writers land above out of fold, "
                f"and its bar the score {round(HUMAN_PASS_QUANTILE * 100)}% of them land under. `detect.py --register NAME` uses that pair. "
                "Without it the pooled 0.5 and bar above apply, and so they do for the registers with no human writing here "
                "(reviews, blog posts, cover letters, talk abstracts, social posts).", "",
                "| register | human rows | cut | bar | human flagged 0.5 -> cut | AI rows | AI caught 0.5 -> cut |", "|---|---|---|---|---|---|---|"]

        def move(probs, cut):
            return "-" if not len(probs) else f"{(probs >= 0.5).mean():.3f} -> {(probs >= cut).mean():.3f}"

        for name, bars in registers.items():
            cut = bars["threshold_ai"]
            picked = [(p, r["label"]) for p, r in zip(test_probs, test) if register_of(r) == name]
            human = np.array([p for p, label in picked if label == 0])
            ai = np.array([p for p, label in picked if label == 1])
            out.append(f"| {name} | {len(human)} | {cut:.3f} | {bars['threshold_human']:.3f} | {move(human, cut)} | "
                       f"{len(ai)} | {move(ai, cut)} |")

    if all_sections:
        test_groups = {r["group"] for r in test}
        docs = {}
        for r in all_sections:
            if r["group"] in test_groups:
                docs.setdefault(r.get("doc", r["group"]), []).append(r)
        doc_keys = {g: key_of(sections[0]) for g, sections in docs.items()}
        verdicts = {}
        for g, sections in docs.items():
            probs = predict(scaler, model, sections, names)
            verdicts[g] = doc_verdict(sections, probs, threshold_human)
        out += ["", "### Whole documents (held-out test)", "",
                "Every section of each held-out document, combined the way the skill does it: 'ai' when at least a quarter of the words sit in sections at 0.5 or more, "
                "'human' when under half the words sit in sections over the bar and no section scores 0.9 or more.", "",
                "| source / register | label | documents | verdict ai | verdict human |", "|---|---|---|---|---|"]
        for key in sorted(set(doc_keys.values())):
            gs = [g for g, k in doc_keys.items() if k == key]
            n_ai = sum(1 for g in gs if verdicts[g] == "ai")
            n_human = sum(1 for g in gs if verdicts[g] == "human")
            out.append(f"| {key[0]} / {key[1]} | {'AI' if key[2] else 'human'} | {len(gs)} | {rate(n_ai, len(gs))} | {rate(n_human, len(gs))} |")

    if names == VOICE:
        held = [r for r in all_sections if r["group"] in {t["group"] for t in test} and r["features"]["n_words"] >= MIN_VERDICT_WORDS]
        p_held = predict(scaler, model, held, names)
        y_held = np.array([r["label"] for r in held])
        n_held = np.array([r["features"]["n_words"] for r in held])
        out += ["", "### By section length (held-out test)", "", "One figure hides this: the shorter the section, the more often a person gets flagged.", "",
                "| words | human flagged | AI caught |", "|---|---|---|"]
        for lo, hi in [(80, 120), (120, 200), (200, 300), (300, 10000)]:
            band = (n_held >= lo) & (n_held < hi)
            human, ai = p_held[band & (y_held == 0)], p_held[band & (y_held == 1)]
            out.append(f"| {lo}-{'' if hi == 10000 else hi - 1} | {rate(int((human >= 0.5).sum()), len(human))} | {rate(int((ai >= 0.5).sum()), len(ai))} |")
        dated = [(r["date"][:4] + ("H1" if r["date"][5:7] < "07" else "H2"), p) for r, p in zip(test, test_probs) if r["source"] == "gh-ai" and r.get("date")]
        human = test_probs[y_test == 0]
        out += ["", "### AI-credited docs by date (held-out test)", "", "What this table reads arrived around the start of 2026, so older AI text mostly gets past it.", "",
                "| half-year | AI caught | AUROC vs test humans |", "|---|---|---|"]
        for half in sorted({h for h, _ in dated}):
            probs = np.array([p for h, p in dated if h == half])
            out.append(f"| {half} | {rate(int((probs >= 0.5).sum()), len(probs))} | {roc_auc_score(np.r_[np.ones(len(probs)), np.zeros(len(human))], np.r_[probs, human]):.3f} |")

    if extra:
        p_extra = predict(scaler, model, extra, names)
        out += ["", "AI-written guides, API pages, migration notes, FAQs, design notes and release notes, never trained on. "
                "There are no human docs of these kinds in the data, so false alarms on them are unmeasured.", "",
                "| source / doc type | flagged as AI (>= 0.5) | reads human |", "|---|---|---|"]
        for key in sorted({(r["source"], r["doc_type"]) for r in extra}):
            sel = np.array([(r["source"], r["doc_type"]) == key for r in extra])
            out.append(f"| {key[0]} / {key[1]} | {rate(int((p_extra[sel] >= 0.5).sum()), int(sel.sum()))} | {rate(int((p_extra[sel] < threshold_human).sum()), int(sel.sum()))} |")

    labelled = [r for r in rows if r["source"] == "feedback"]
    if labelled:
        # the fairest test here: text from a project it has never seen, whose author the user confirmed
        s, m = fit([r for r in train if r["source"] != "feedback"], names, c, cfg["clamp"])
        right = (predict(s, m, labelled, names) >= 0.5) == (np.array([r["label"] for r in labelled]) == 1)
        out += ["", "### Your labelled texts, trained without any of them", "",
                f"{int(right.sum())}/{len(right)} sections right = {right.mean():.3f}."]

    out += ["", "### 20 random re-splits", "", "One split can be lucky. These are mean and 5th-95th percentile over 20 grouped re-splits.", "",
            "| metric | mean | 5th-95th percentile |", "|---|---|---|"]
    stats = {"accuracy": [], "AI caught": [], "human flagged": [], "AUROC": [], "Claude caught": []}
    for seed in range(20):
        tr, te = resplit(rows, seed)
        te = [r for r in te if r["features"]["n_words"] >= MIN_VERDICT_WORDS]
        s, m = fit(tr, names, c, cfg["clamp"])
        p = predict(s, m, te, names)
        y = np.array([r["label"] for r in te])
        claude = np.array([r["source"].startswith("claude") for r in te])
        stats["accuracy"].append(((p >= 0.5) == (y == 1)).mean())
        stats["AI caught"].append((p[y == 1] >= 0.5).mean())
        stats["human flagged"].append((p[y == 0] >= 0.5).mean())
        stats["AUROC"].append(roc_auc_score(y, p))
        stats["Claude caught"].append((p[claude] >= 0.5).mean())
    for name, values in stats.items():
        out.append(f"| {name} | {np.mean(values):.3f} | {np.quantile(values, 0.05):.3f}-{np.quantile(values, 0.95):.3f} |")

    families = sorted({family(r) for r in rows if r["label"] == 1})
    if len(families) > 1:
        out += ["", "### Model families it never saw", "",
                "Each row trains without that family's AI text, then scores all of that family's rows. This is the closest thing here to 'a new model came out'.", "",
                "| left out | AI caught at 0.5 | reads human | AUROC vs test humans |", "|---|---|---|---|"]
        human_test = [r for r in test if r["label"] == 0]
        for fam in families:
            held = [r for r in rows if r["label"] == 1 and family(r) == fam]
            s, m = fit([r for r in train if family(r) != fam], names, c, cfg["clamp"])
            p_ai, p_h = predict(s, m, held, names), predict(s, m, human_test, names)
            auroc = roc_auc_score([1] * len(p_ai) + [0] * len(p_h), np.concatenate([p_ai, p_h]))
            out.append(f"| {fam} | {rate(int((p_ai >= 0.5).sum()), len(p_ai))} | {rate(int((p_ai < threshold_human).sum()), len(p_ai))} | {auroc:.3f} |")
    else:
        out += ["", f"All AI text here comes from one model family ({families[0]}), so there's no unseen-family test for this genre."]

    sentence_scores = [ce / xe for r in train if r["label"] == 0 for n_words, ce, xe in r["sentences"] if n_words >= SENTENCE_MIN_WORDS and xe]
    ai_sentences = [ce / xe for r in train if r["label"] == 1 for n_words, ce, xe in r["sentences"] if n_words >= SENTENCE_MIN_WORDS and xe]
    cut = float(np.quantile(sentence_scores, 0.05))
    lift_train, lift_test = sentence_lift(train, cut), sentence_lift(test, cut)
    # the flag drives rewrites, so drop it where it lands on human sentences about as often as AI ones
    sentence_cut = cut if min(lift_train, lift_test) >= 2 else None
    recalled_ai = sum(1 for x in ai_sentences if x < RECALLED)
    support_train, support_test = flag_support(train), flag_support(test)
    # a flag has to hold on held-out text as well, or it's a quirk of the training rows
    support = {name: min(support_train[name], support_test[name]) for name in support_train}
    out += ["", "### Settings written to blend.json", "",
            (f"- {len(scaler['weights'])} function-word terms and a link credit of {scaler['link_credit']:.2f}" if names == VOICE else
             f"- features: style + language model; never negative: {', '.join(sorted(cfg['clamp']))}"),
            f"- threshold_ai = 0.5, threshold_human = {threshold_human:.3f}"
            + (", and a cut and bar of its own for " + ", ".join(f"{k} ({v['threshold_ai']:.2f}/{v['threshold_human']:.2f})"
                                                                 for k, v in registers.items()) if registers else ""),
            f"- 'too predictable' at binoculars < {cut:.3f} flags {np.mean(np.array(sentence_scores) < cut):.0%} of human and {np.mean(np.array(ai_sentences) < cut):.0%} of AI training sentences of {SENTENCE_MIN_WORDS}+ words; "
            f"AI/human lift {lift_train:.2f} train, {lift_test:.2f} test, so it is {'kept' if sentence_cut is not None else 'turned off (needs 2 or more on both)'}",
            f"- 'recalled' (binoculars < {RECALLED}): {recalled_ai} AI training sentences fall under it{'; lower RECALLED in detect.py' if recalled_ai else ''}",
            "- habit flags, AI/human rate per sentence on train / test (a flag shows when both are 1.25 or more): "
            + ", ".join(f"{name} {support_train[name]:.2f} / {support_test[name]:.2f}" for name in support),
            "", "Largest weights (+ pushes toward AI):", ""]
    weights = scaler["weights"].items() if names == VOICE else zip(names, model.coef_[0])
    for name, weight in sorted(weights, key=lambda t: -abs(t[1]))[:20 if names == VOICE else 10]:
        out.append(f"- {name}: {weight:+.2f}")
    out.append("")

    # the table's own score is the logit, so the linear part just passes it through
    linear = {"mean": [0.0], "scale": [1.0], "coef": [1.0], "intercept": 0.0} if names == VOICE else {
        "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(), "coef": model.coef_[0].tolist(), "intercept": float(model.intercept_[0])}
    blend = {
        "features": names,
        **linear,
        "threshold_ai": 0.5,
        "threshold_human": threshold_human,
        "registers": registers,
        "human_reference": np.quantile(oof_human, np.linspace(0, 1, 101)).tolist(),
        "sentence_binoculars_cut": sentence_cut,
        "sentence_min_words": SENTENCE_MIN_WORDS,
        "flag_support": support,
        "c": c,
        # what this fit could see, so the next retrain knows which rows are new
        "labels": seen_labels(rows),
        "sources": sorted({r["source"] for r in rows} - {"feedback"}),
    }
    if names == VOICE:
        blend |= {"ngram": {"closed": sorted(scaler["closed"]), "intercept": scaler["intercept"],
                            "weights": {t: round(w, 4) for t, w in scaler["weights"].items()}},
                  "link_credit": scaler["link_credit"], "link_cap": LINK_CAP}
    return blend, list(zip(test, test_probs))


def main():
    # Both output paths are required. They used to default to the live blend.json and metrics.md, so a
    # bare `fit.py features.jsonl` installed the live detector with none of retrain.py's checks run and no
    # archived version to go back to. That was the last line of the rerun recipe in bench/REPORT.md.
    if len(sys.argv) < 4:
        sys.exit("usage: fit.py FEATURES.jsonl BLEND_OUT.json METRICS_OUT.md\n"
                 "to refit the detector people actually use, run bench/retrain.py: it fits a candidate, puts it\n"
                 "through the gate, and archives the version it replaces so you can roll back")
    blend_file, metrics_file = sys.argv[2], sys.argv[3]
    rows = [json.loads(line) for line in open(sys.argv[1])]
    # AI docs of kinds no human doc covers are only ever scored, never trained or re-split on
    extra = [r for r in rows if r["split"] == "extra"]
    rows = [r for r in rows if r["split"] != "extra"]
    out = ["# Detector metrics", "", f"Generated {datetime.date.today()} by bench/fit.py from {len(rows)} rows.", ""]

    # layout must not move a prose score: the blend only ever sees canon(text)
    for row in [r for r in rows if r["domain"] != "docs"][:300]:
        text = row["text"]
        assert canon(text.replace(". ", ".\n\n")) == canon(text) == canon(text.replace("\n", " ")), "canon() is not layout-blind"
    out += ["Layout check passed: adding or removing paragraph breaks leaves the scored prose unchanged.", ""]

    blends, predictions = {}, []
    for genre, cfg in GENRES.items():
        genre_rows = [r for r in rows if cfg["belongs"](r)]
        all_sections = []
        if genre == "docs":
            # train and score sections the way they're used: the first few of each doc, each long enough to judge
            all_sections = genre_rows
            genre_rows = [r for r in genre_rows if r.get("section", 0) < DOC_SECTIONS_TRAINED and words(r) >= DOC_MIN_WORDS]
        genre_extra = [r for r in extra if cfg["belongs"](r) and words(r) >= DOC_MIN_WORDS]
        blends[genre], preds = fit_genre(cfg, genre_rows, all_sections, genre_extra, out)
        predictions += preds

    tmp = blend_file + ".tmp"
    with open(tmp, "w") as f:
        json.dump(blends, f, indent=1)
    os.replace(tmp, blend_file)

    pred_path = sys.argv[1].replace(".jsonl", "") + ".pred.jsonl"
    with open(pred_path, "w") as f:
        for row, prob in predictions:
            f.write(json.dumps({k: row.get(k) for k in ("text", "label", "source", "model", "domain", "register")} | {"ai_probability": float(prob)}) + "\n")

    text = "\n".join(out) + "\n"
    with open(metrics_file, "w") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()

# Score text for AI-writing signals: style tells, Binoculars (Qwen2.5-1.5B base vs instruct), and a fitted blend.
import argparse
import bisect
import collections
import json
import math
import os
import re
import statistics
import sys

from markdown_it import MarkdownIt

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

HERE = os.path.dirname(os.path.abspath(__file__))
BLEND_FILE = os.path.join(HERE, "blend.json")
OBSERVER = "Qwen/Qwen2.5-1.5B"
PERFORMER = "Qwen/Qwen2.5-1.5B-Instruct"
HELDOUT = "fakespot-ai/roberta-base-ai-text-detection-v1"
# the exact versions setup.sh downloads, so an upstream push can't change the scores
REVISIONS = {OBSERVER: "8faed761d45a263340a0528343f099c05c9a4323", PERFORMER: "989aa7980e4cf806f80c7fef2b1adb7bc71aa306",
             HELDOUT: "f9cdb14d1f8b105f597d80fa7b56f20c6ea0e9db"}
MAX_TOKENS = 512
PORT = int(os.environ.get("HUMANIZE_PORT", "8765"))
IDLE_SECONDS = 15 * 60
MAX_BODY = 2_000_000
NOT_OURS = ("If it's an old scorer, stop it with pkill -f 'detect.py --serve' and run start-scorer.sh again. "
            "If another app holds the port, set HUMANIZE_PORT to a free one for both.")
CODE_MTIME = os.path.getmtime(__file__)
QUOTES = str.maketrans("“”‘’", "\"\"''")

TELLS = [
    (r"\bdelv(e|es|ed|ing)\b", "delve"),
    (r"\btapestr(y|ies)\b", "tapestry"),
    (r"\btestament to\b", "testament to"),
    (r"\bintricat(e|ely|acies)\b", "intricate"),
    (r"\bpivotal\b", "pivotal"),
    (r"\bcrucial(ly)?\b", "crucial"),
    (r"\bseamless(ly)?\b", "seamless"),
    (r"\brobust\b", "robust"),
    (r"\bleverag(e|es|ed|ing)\b", "leverage"),
    (r"\bharness(es|ed|ing)? the (power|potential)\b", "harness the power"),
    (r"\bunlock(s|ed|ing)? (the|your|its|their|our) (full )?(potential|power)\b", "unlock the potential"),
    (r"\belevat(e|es|ed|ing)\b", "elevate"),
    (r"\bfoster(s|ed|ing)? (a|an|the) (sense|culture|environment|community)\b", "foster a sense of"),
    (r"\bbolster(s|ed|ing)?\b", "bolster"),
    (r"\bnavigat(e|es|ed|ing) (the|this|these|their|your|our)\b", "navigate the"),
    (r"\blandscape\b", "landscape"),
    (r"\brealm\b", "realm"),
    (r"\bembark(s|ed|ing)?\b", "embark"),
    (r"\bvibrant\b", "vibrant"),
    (r"\bbustling\b", "bustling"),
    (r"\bnestled\b", "nestled"),
    (r"\bmeticulous(ly)?\b", "meticulous"),
    (r"\bcomprehensive\b", "comprehensive"),
    (r"\bnuanced?\b", "nuance"),
    (r"\bmultifaceted\b", "multifaceted"),
    (r"\bparamount\b", "paramount"),
    (r"\bunderscor(e|es|ed|ing)\b", "underscore"),
    (r"\bshowcas(e|es|ed|ing)\b", "showcase"),
    (r"\bstreamlin(e|es|ed|ing)\b", "streamline"),
    (r"\bempower(s|ed|ing|ment)?\b", "empower"),
    (r"\bholistic\b", "holistic"),
    (r"\bsynerg(y|ies|istic)\b", "synergy"),
    (r"\bcutting[- ]edge\b", "cutting-edge"),
    (r"\bgame[- ]chang(er|ing)\b", "game-changer"),
    (r"\bever[- ](evolving|changing)\b", "ever-evolving"),
    (r"\bfast[- ]paced\b", "fast-paced"),
    (r"\b(it's|it is) (worth|important to) (noting|note|remember)\b", "it's worth noting"),
    (r"\bplays? an? (crucial|vital|key|pivotal|significant|important) role\b", "plays a key role"),
    (r"\b(serves|stands) as an?\b", "serves as"),
    (r"\ba (myriad|plethora) of\b", "a myriad of"),
    (r"\bnot only\b[^.!?]{1,80}\bbut also\b", "not only...but also"),
    (r"\bwhether you're\b", "whether you're"),
    (r"\b(dive|diving|dives) (into|deep)\b|\bdeep[- ]dive\b", "dive into"),
    (r"\bresonat(e|es|ed|ing)\b", "resonate"),
    (r"\bcaptivat(e|es|ed|ing)\b", "captivating"),
    (r"\benhanc(e|es|ed|ing|ement)\b", "enhance"),
    (r"\b(innovative|transformative)\b", "innovative"),
    (r"\bpav(e|es|ed|ing) the way\b", "pave the way"),
    (r"\bkey takeaways?\b", "key takeaway"),
    (r"\bhere's the (thing|kicker|catch|deal)\b", "here's the thing"),
    (r"\b(thrilled|excited|delighted|humbled|proud) to (announce|share)\b", "excited to share"),
    (r"\bhope this (email|message|note) finds you\b", "hope this finds you"),
    (r"\bfeel free to\b", "feel free to"),
    (r"\blook no further\b", "look no further"),
    (r"\bgenuine(ly)?\b", "genuinely"),
    (r"\bquietly\b", "quietly"),
    (r"\bload[- ]bearing\b", "load-bearing"),
    (r"\bwhen it comes to\b", "when it comes to"),
    (r"\bin today's\b", "in today's"),
    (r"\bcommitment to\b", "commitment to"),
    (r"\b(unwavering|invaluable|indispensable)\b", "invaluable"),
    (r"\bjourney\b", "journey"),
    (r"\b(insights?|actionable)\b", "insights"),
    (r"\bensur(e|es|ed|ing)\b", "ensure"),
    (r"\b(essential|vital) (for|to)\b", "essential for"),
    (r"\bthe (real|true) (magic|power|value|win|story)\b", "the real magic"),
    (r"\bthat's (the|where the) (point|magic|whole point)\b", "that's the point"),
    (r"^(sure|certainly|absolutely|of course|great question)\b[,!.]", "assistant opener"),
    (r"\bi hope (this|that) helps\b", "I hope this helps"),
    (r"\blet me know if you have any\b", "let me know if you have any"),
    (r"\bin conclusion\b", "in conclusion"),
]
TELLS = [(re.compile(p, re.I), name) for p, name in TELLS]
TRANSITION_START = re.compile(
    r"^(furthermore|moreover|additionally|notably|importantly|ultimately|overall|in conclusion|in summary|"
    r"in essence|in addition|that said|however(?=,)|as a result|consequently|by contrast|first|second|finally)\b",
    re.I,
)
# run on the whole text so "This isn't X. It's Y." is caught across the sentence break
CONTRAST = [
    re.compile(r"\b(?:it's|it is|this is|that's|that is)\s+not\s+(?:just\s+|only\s+|merely\s+|simply\s+)?(?:about\s+)?[^.!?;]{1,60}?[,—–-]\s*(?:it's|it is|but)\b", re.I),
    re.compile(r"\b(?:isn't|aren't|wasn't)\s+(?:just\s+|only\s+|merely\s+|really\s+)?(?:about\s+)?[^.!?;]{1,50}?[.—–]\s*(?:it's|it is|they're|this is)\b", re.I),
    re.compile(r"\bnot because\b[^.!?]{1,60}\bbut because\b", re.I),
    re.compile(r"\bnot (?:just |only |merely )?(?:a |an |the )?\w+(?: \w+)?, but (?:a |an |the )?\w+", re.I),
    re.compile(r"\bNo [^.!?]{1,30}\. No [^.!?]{1,30}\."),
]
TRIAD = re.compile(r"\b[\w'-]+(?: [\w'-]+){0,3}, [\w'-]+(?: [\w'-]+){0,3}, ?(?:and|or) [\w'-]+|\b[\w'-]+, [\w'-]+,? (?:and|or) [\w'-]+", re.I)
ITEM_SPLIT = re.compile(r"\s*,\s*(?:(?:and|or)\s+)?|\s+(?:and|or)\s+", re.I)
STRUCTURAL_FLAGS = ("stock opener", "list of three", "em dash", "colon reveal")
# the actual next word is the model's top guess almost every time: recalled or self-repeating text
KNOWN_TEXT_TOP1 = 0.82
# no AI training sentence of 12+ words scores under this, so it marks quoted or standard wording, not a writer's choice
RECALLED = 0.30
MIN_VERDICT_WORDS = 80
DRIFT_SMOOTH = 0.5
# A caller can name the register a prose text belongs to, and each one is judged against its own
# writers. One cut can't mean one thing: 0.5 sits at the 63rd percentile of news writers' scores
# and above nearly all literary ones. Only registers with human text to compare against are here.
REGISTERS = ("academic", "email", "encyclopedia", "forum", "literary", "news")
STRUCTURE = re.compile(r"(?m)^#{1,6} \S|^\S.*\n(?:={3,}|-{3,})[ \t]*$")
# GitHub community-health files are docs whatever their content; any other .md may be a post or a draft
COMMUNITY_DOC = re.compile(
    r"(?i)(?:^|/)(?:\.github/.+|(?:readme|changelog|changes|history|release[-_]?notes|contributing"
    r"|code[-_]of[-_]conduct|security|support|governance|maintainers)(?:\.[a-z]{2}(?:-[a-z]{2,4})?)?"
    r"\.(?:md|mdx|markdown|rst|txt))$")
LICENCE_HEADING = re.compile(r"(?i)^\W*licen[cs](?:e|ing)(?:\W*$|\s*[(\[\]:]|\s+[-–—]\s|\s+(?:and|&|&amp;)\s)")
# a real front matter block starts with a key on the very next line; otherwise it is a horizontal rule
FRONT_MATTER = re.compile(r"\A\s*---\n(?=\S).*?\n---[ \t]*\n", re.S)
INLINE_LINK = re.compile(r"!?\[([^\]]*)\]\([^)\s]+\)")
# MDX and docs-site syntax that isn't prose: module lines, ':::note' fences and '{{...}}' embeds
SITE_SYNTAX = re.compile(r"""(?m)^[ \t]*(?:import\s.+\sfrom\s+['"].+|import\s+['"].+|export\s+(?:default|const|function|\{).*|:::.*|\{\{.*\}\})[ \t]*$""")
FIRST_PERSON = re.compile(r"\bI\b(?!\.\w)|\bI'(?:m|ve|d|ll)\b|\b(?i:me|my|mine)\b")
WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
ABBREV = re.compile(r"(\b(?i:mr|mrs|ms|dr|prof|st|jr|sr|vs|etc|e\.g|i\.e|a\.m|p\.m|fig|approx|inc|ltd|co)|\b[A-Z]|\b(?i:no))\.$")
# split before any token that contains a letter or digit, so sentences starting with `@scope/pkg`, `.env` or `--flag` split too
SPLIT = re.compile(r"(?<=[.!?])[\"')\]]?\s+(?=\w|\.\w|[^\s.,;:!?…)\]}]\S*?\w|[-•*]\s+\w)")
LIST_MARKER = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+")


MD = MarkdownIt("commonmark").enable("table")
# markdown_it 2.2.0 reads a footnote definition as a link reference, so "[^1]: Title: words" hands its URL
# parser a scheme with no host and that throws. Footnote text is prose, so drop the marker and try again.
FOOTNOTE_DEF = re.compile(r"(?m)^[ \t]*\[\^[^\]]+\]:[ \t]*")


def parse_md(text):
    try:
        return MD.parse(text)
    except Exception:
        pass
    try:
        return MD.parse(FOOTNOTE_DEF.sub("", text))
    except Exception as err:
        print(f"markdown unreadable, skipping it: {err}", file=sys.stderr)
        return []
SECTION_WORDS = 300
CLAUSE = re.compile(r"(?<=[.!?])\s+|\n+")
CHUNK = re.compile(r"[^\s,;:()]+|[,;:(]")
PLAIN_WORD = re.compile(r"[A-Za-z][a-z]*(?:[-'][a-z]+)*$")
WORD_EDGE = "\"'`*_[]{}<>.!?)"
MARKS = {"<s>", "#", ",", ";", ":", "("}
URL_START = re.compile(r"(?i)[a-z][a-z0-9+.-]*:|//")
MIN_DOC_WORDS = 120
BOILERPLATE = re.compile(r"(?i)copyright|©|permission is hereby granted|the software is provided|all rights reserved")


def is_markdown(text):
    if any(t.type == "table_open" for t in parse_md(FRONT_MATTER.sub("", text))):
        return True
    return bool(re.search(r"(?m)^\s*(```|~~~)|^#{1,6} \S|^\S.*\n(?:={3,}|-{3,})[ \t]*$|^\s*\|.*\|\s*$|\n\s*\n(?: {4}|\t)\S"
                          r"|<!--[\s\S]*?-->|(?<![\w*])\*\*[^*\s](?:[^*\n]*[^*\s])?\*\*", text))


def has_code(text):
    body = FRONT_MATTER.sub("", text)
    tokens = parse_md(body)
    fenced = any(t.type in ("fence", "table_open") for t in tokens)
    indented = any(t.type == "code_block" for t in tokens)
    # in plain text an indented block is an address or a quote, not code
    return fenced or len(re.findall(r"(?m)^\s*\|.*\|\s*$", body)) >= 2 or (indented and bool(STRUCTURE.search(body)))


def inline_text(token):
    parts, skip = [], 0
    for child in token.children or []:
        if child.type == "link_open" and child.markup == "autolink":
            skip += 1
        elif child.type == "link_close" and skip:
            skip -= 1
        elif skip or child.type in ("image", "html_inline"):
            continue
        elif child.type == "text" or (child.type == "code_inline" and re.search(r"\w", child.content)):
            parts.append(child.content)
        elif child.type == "code_inline":
            parts.append(f"`{child.content}`")
        elif child.type in ("softbreak", "hardbreak"):
            parts.append(" ")
    return "".join(parts)


def is_label_only(tok, para):
    # nav rows ('Docs · npm · Demo'), back-to-top links and bold pseudo-headings ('**Params**') are markup, not sentences
    kids = tok.children or []
    link = emphasis = 0
    has_text = text_outside_link = text_outside_emphasis = False
    for c in kids:
        if c.type == "link_open":
            link += 1
        elif c.type == "link_close":
            link -= 1
        elif c.type in ("strong_open", "em_open"):
            emphasis += 1
        elif c.type in ("strong_close", "em_close"):
            emphasis -= 1
        elif c.type in ("text", "code_inline") and c.content.strip():
            has_text = True
            text_outside_link |= not link and bool(re.search(r"[A-Za-z0-9]", c.content))
            text_outside_emphasis |= not emphasis
    if not has_text:
        return False
    link_only = not text_outside_link and any(c.type == "link_open" for c in kids)
    bold_only = not text_outside_emphasis and not (len(para.split()) >= 5 and re.search(r"[.!?][\"')\]]*$", para))
    return link_only or bold_only


def doc_prose(markdown, skipped=None):
    # the detector reads prose: only paragraph text survives, and every paragraph and list item ends as a sentence
    tokens = parse_md(site_free(markdown))
    paragraphs, in_table, in_list, licence_level = [], 0, 0, None
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            # a licence section is legal text, not the author's prose
            level = int(tok.tag[1])
            if licence_level is None or level <= licence_level:
                licence_level = level if LICENCE_HEADING.search(tokens[i + 1].content) else None
        elif tok.type == "table_open":
            in_table += 1
        elif tok.type == "table_close":
            in_table -= 1
        elif tok.type in ("bullet_list_open", "ordered_list_open"):
            in_list += 1
        elif tok.type in ("bullet_list_close", "ordered_list_close"):
            in_list -= 1
        elif tok.type == "inline" and in_table and skipped is not None:
            cell = inline_text(tok)
            if len(cell.split()) >= 6:
                skipped["words in tables"] += len(WORD.findall(cell))
        elif tok.type == "html_block" and skipped is not None:
            skipped["words in HTML comments"] += sum(len(WORD.findall(m)) for m in re.findall(r"<!--(.*?)-->", tok.content, re.S))
        elif tok.type == "inline" and not in_table and licence_level is None and tokens[i - 1].type == "paragraph_open":
            para = inline_text(tok)
            para = re.sub(r"\[![A-Z]+\]|\[\^[^\]]+\]|:[a-z0-9_+-]+:", "", para)
            # only close the gap before punctuation that ends a word, so `.env` doesn't glue onto the word before it
            para = re.sub(r"\s+([.,;:!?])(?=\s|$|[\"')\]])", r"\1", re.sub(r"\s+", " ", para)).strip()
            # tables of contents and one-line feature bullets are navigation, not prose
            if not para or (in_list and len(para.split()) < 6) or BOILERPLATE.search(para) or is_label_only(tok, para):
                continue
            # a lead-in left on ':' would swallow the next paragraph's first sentence once canon() flattens the text
            para = re.sub(r":(?=[\"')\]]*$)", ".", para)
            if not re.search(r"[.!?;][\"')\]]*$", para):
                para += "."
            paragraphs.append(para)
    return "\n\n".join(paragraphs)


def prepare(text, skipped=None):
    # plain text keeps its lines; only link syntax would otherwise reach the scorer as a URL
    return doc_prose(text, skipped) if is_markdown(text) else INLINE_LINK.sub(r"\1", text)


def code_blocks(markdown):
    blocks = collections.Counter()
    for tok in parse_md(markdown):
        if tok.type in ("fence", "code_block"):
            body = "\n".join(line.rstrip() for line in tok.content.strip("\n").splitlines())
            blocks[(tok.info.split()[0] if tok.info.strip() else "", body)] += 1
    return blocks


def doc_sections(prose, size=SECTION_WORDS):
    # cut long paragraphs at sentence ends, then split into roughly equal sections of about `size` words
    units = []
    for para in [p.strip() for p in re.split(r"\n\s*\n", prose) if p.strip()]:
        if len(para.split()) <= size:
            units.append(para)
            continue
        current = []
        for sentence in split_sentences(para):
            current.append(sentence)
            if len(" ".join(current).split()) >= size // 2:
                units.append(" ".join(current))
                current = []
        if current:
            units.append(" ".join(current))
    total = sum(len(u.split()) for u in units)
    count = max(1, round(total / size))
    target = total / count
    sections, current, words = [], [], 0
    for unit in units:
        # keep every section inside the 512-token window the language model reads (about 1.3 tokens a word)
        if current and len(" ".join(current + [unit]).split()) > 390:
            sections.append("\n\n".join(current))
            current = []
        current.append(unit)
        words += len(unit.split())
        if words >= target * (len(sections) + 1) and len(sections) < count - 1:
            sections.append("\n\n".join(current))
            current = []
    if current:
        sections.append("\n\n".join(current))
    return sections


def canon(text):
    # every score is taken on one flat line: in the training data, layout said more about
    # where a text came from than about who wrote it
    text = text.translate(QUOTES).replace("\r", "\n")
    text = re.sub(r"^\s*subject:[^\n]*\n", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text):
    sentences = []
    for block in re.split(r"\n+", text):
        block = LIST_MARKER.sub("", block.strip())
        if not block:
            continue
        merged = []
        prev = ""
        for part in SPLIT.split(block):
            part = LIST_MARKER.sub("", part)
            if re.fullmatch(r"\d{1,2}[.)]", part):
                continue
            if merged and ABBREV.search(prev) and not (prev.lower().endswith("no.") and not part[:1].isdigit()):
                merged[-1] += " " + part
            else:
                merged.append(part)
            prev = part
        sentences += [p.strip() for p in merged if p.strip()]
    return sentences


def sentence_spans(text):
    spans = []
    cursor = 0
    for sentence in split_sentences(text):
        match = re.compile(r"\s+".join(map(re.escape, sentence.split()))).search(text, cursor)
        start, end = (match.start(), match.end()) if match else (cursor, cursor + len(sentence))
        spans.append((start, end, sentence))
        cursor = end
    return spans


def mattr(words, window=50):
    if len(words) < window:
        return len(set(words)) / max(len(words), 1)
    ratios = []
    for i in range(0, len(words) - window + 1, 5):
        ratios.append(len(set(words[i : i + window])) / window)
    return sum(ratios) / len(ratios)


def contrast_spans(text):
    return [m.span() for pattern in CONTRAST for m in pattern.finditer(text)]


def triads(sentence):
    # "ά, έ or ί" or "h, d, and w" lists characters, not a rhetorical list of three
    return [m for m in TRIAD.findall(sentence) if any(len(i.split()[-1]) > 1 for i in ITEM_SPLIT.split(m) if i.strip())]


def sentence_flags(sentence):
    flags = [name for pattern, name in TELLS if pattern.search(sentence)]
    if TRANSITION_START.search(sentence):
        flags.append("stock opener")
    if triads(sentence):
        flags.append("list of three")
    if "—" in sentence or " – " in sentence or " -- " in sentence:
        flags.append("em dash")
    if re.search(r":\s+\S", sentence) and not sentence.rstrip().endswith(":"):
        flags.append("colon reveal")
    return flags


def style_features(flat):
    words = [w.lower() for w in WORD.findall(flat)]
    n_words = max(len(words), 1)
    per100 = 100.0 / n_words
    sentences = split_sentences(flat)
    n_sent = max(len(sentences), 1)
    lengths = [len(WORD.findall(s)) for s in sentences] or [0]
    mean_len = statistics.mean(lengths)

    tell_hits = 0
    triad_hits = 0
    transition_hits = 0
    colon_hits = 0
    for s in sentences:
        tell_hits += sum(1 for pattern, _ in TELLS if pattern.search(s))
        triad_hits += len(triads(s))
        transition_hits += 1 if TRANSITION_START.search(s) else 0
        colon_hits += 1 if re.search(r":\s+\S", s) else 0
    starts = [s.split()[0].lower() for s in sentences if s.split()]

    return {
        "n_words": len(words),
        "tell_rate": tell_hits * per100,
        "em_dash_rate": (flat.count("—") + flat.count(" – ") + flat.count(" -- ")) * per100,
        # a yes/no signal: one "it's not X, it's Y" shouldn't be able to flip a verdict alone
        "has_contrast": 1.0 if contrast_spans(flat) else 0.0,
        "triad_rate": triad_hits / n_sent,
        "transition_rate": transition_hits / n_sent,
        "colon_rate": colon_hits / n_sent,
        "sent_len_mean": mean_len,
        "sent_len_cv": statistics.pstdev(lengths) / mean_len if mean_len else 0.0,
        "sent_mid_band": sum(1 for n in lengths if 12 <= n <= 28) / n_sent,
        "sent_len_max": max(lengths),
        "repeated_starts": 1 - len(set(starts)) / len(starts) if starts else 0.0,
        "first_person_rate": len(FIRST_PERSON.findall(flat)) * per100,
        "paren_rate": flat.count("(") * per100,
        "digit_rate": len(re.findall(r"\d+", flat)) * per100,
        "mattr": mattr(words),
        "word_len": sum(len(w) for w in words) / n_words,
    }


class Scorer:
    def __init__(self, heldout=False):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
        dtype = torch.float32 if self.device == "cpu" else torch.float16
        self.tokenizer = AutoTokenizer.from_pretrained(OBSERVER, revision=REVISIONS[OBSERVER])
        self.observer = AutoModelForCausalLM.from_pretrained(OBSERVER, revision=REVISIONS[OBSERVER], dtype=dtype).to(self.device).eval()
        self.performer = AutoModelForCausalLM.from_pretrained(PERFORMER, revision=REVISIONS[PERFORMER], dtype=dtype).to(self.device).eval()
        self.heldout = None
        if heldout:
            from transformers import AutoModelForSequenceClassification

            self.heldout_tok = AutoTokenizer.from_pretrained(HELDOUT, revision=REVISIONS[HELDOUT])
            self.heldout = AutoModelForSequenceClassification.from_pretrained(HELDOUT, revision=REVISIONS[HELDOUT]).to(self.device).eval()

    def lm(self, flat):
        torch = self.torch
        enc = self.tokenizer(flat, return_tensors="pt", truncation=True, max_length=MAX_TOKENS, return_offsets_mapping=True)
        offsets = enc.pop("offset_mapping")[0].tolist()
        enc = {k: v.to(self.device) for k, v in enc.items()}
        with torch.inference_mode():
            obs_logits = self.observer(**enc).logits[0, :-1].float()
            perf_logits = self.performer(**enc).logits[0, :-1].float()
        targets = enc["input_ids"][0, 1:]
        perf_logp = torch.log_softmax(perf_logits, -1)
        obs_p = torch.softmax(obs_logits, -1)
        token_ce = -perf_logp.gather(-1, targets[:, None])[:, 0]
        token_x = -(obs_p * perf_logp).sum(-1)
        # Fast-DetectGPT: how far the text's log-likelihood sits above what sampling would give, in standard deviations
        token_var = (obs_p * perf_logp.pow(2)).sum(-1) - token_x.pow(2)
        fast_detectgpt = float((token_x - token_ce).mean() / token_var.mean().clamp_min(1e-6).sqrt())
        obs_ce = -torch.log_softmax(obs_logits, -1).gather(-1, targets[:, None])[:, 0]
        ranks = (perf_logits > perf_logits.gather(-1, targets[:, None])).sum(-1)
        token_ce = token_ce.cpu().tolist()
        token_x = token_x.cpu().tolist()
        ranks = ranks.cpu().tolist()
        n = max(len(token_ce), 1)
        log_ppl = sum(token_ce) / n
        x_ent = sum(token_x) / n
        feats = {
            "binoculars": log_ppl / x_ent if x_ent else 0.0,
            "fast_detectgpt": fast_detectgpt,
            "log_ppl": log_ppl,
            "log_ppl_observer": float(obs_ce.mean()),
            "x_entropy": x_ent,
            "surprisal_std": statistics.pstdev(token_ce) if len(token_ce) > 1 else 0.0,
            "top1_frac": sum(1 for r in ranks if r == 0) / n,
            "top10_frac": sum(1 for r in ranks if r < 10) / n,
        }
        per_token = []
        for i in range(len(token_ce)):
            # token i+1 is predicted at position i; byte-level tokens start on the space before the word
            start, end = offsets[i + 1]
            while start < end - 1 and flat[start].isspace():
                start += 1
            per_token.append((start, token_ce[i], token_x[i]))
        return feats, per_token

    def heldout_prob(self, flat):
        torch = self.torch
        enc = self.heldout_tok(flat, return_tensors="pt", truncation=True, max_length=512).to(self.device)
        with torch.inference_mode():
            probs = torch.softmax(self.heldout(**enc).logits[0].float(), -1).cpu().tolist()
        labels = {str(name).lower(): int(idx) for idx, name in self.heldout.config.id2label.items()}
        return probs[labels.get("ai", 1)]


def sentence_scores(flat, per_token):
    scores = []
    for start, end, sentence in sentence_spans(flat):
        ce = [c for pos, c, _ in per_token if start <= pos < end]
        xe = [x for pos, _, x in per_token if start <= pos < end]
        scores.append((start, end, sentence, len(WORD.findall(sentence)), sum(ce), sum(xe), len(ce)))
    return scores


def sentence_spread(scores):
    # people write some sentences that are easy to predict and some that aren't; models are more even
    values = [ce / xe for _, _, _, _, ce, xe, n_tokens in scores if n_tokens >= 8 and xe]
    if len(values) < 2:
        return {"sentence_bino_std": 0.0, "sentence_bino_min": values[0] if values else 1.0}
    return {"sentence_bino_std": statistics.pstdev(values), "sentence_bino_min": min(values)}


def site_free(markdown):
    return SITE_SYNTAX.sub("", FRONT_MATTER.sub("", markdown))


def skeleton(flat, closed):
    tokens = []
    for sentence in CLAUSE.split(flat):
        tokens.append("<s>")
        for i, chunk in enumerate(CHUNK.findall(sentence)):
            if chunk in ",;:(":
                tokens.append(chunk)
                continue
            word = chunk.strip(WORD_EDGE)
            if not word:
                continue
            pronoun = word == "I" or word.startswith("I'")
            # names and code all become '#', so they can't tell one project from another
            tokens.append(word.lower() if PLAIN_WORD.match(word) and (word.islower() or i == 0 or pronoun) else "#")
    return [t if t in closed or t in MARKS else "_" for t in tokens]


def voice_terms(flat, closed):
    tokens = skeleton(flat, closed)
    terms = collections.Counter(t for t in tokens if t != "<s>")
    terms.update(" ".join(tokens[i:i + 2]) for i in range(len(tokens) - 1))
    return terms


def voice_score(terms, table):
    hits = [(table["weights"][t], 1 + math.log(n)) for t, n in terms.items() if t in table["weights"]]
    norm = math.sqrt(sum(v * v for _, v in hits)) or 1.0
    return sum(w * v for w, v in hits) / norm + table["intercept"]


def voice_drift(original, rewrite, closed):
    # how far the rewrite's function words have moved from the draft's, in nats
    # the draft is the reference: what costs is mass the rewrite puts on patterns the draft never used
    draft = voice_terms(canon(prepare(original)), closed)
    new = voice_terms(canon(prepare(rewrite)), closed)
    vocab = set(draft) | set(new)
    if not vocab:
        return 0.0
    # a rewrite always holds terms the draft lacks, and those are the ones worth pricing,
    # so both sides are smoothed instead of letting the divergence run to infinity
    draft_total = sum(draft.values()) + DRIFT_SMOOTH * len(vocab)
    new_total = sum(new.values()) + DRIFT_SMOOTH * len(vocab)
    drift = 0.0
    for term in vocab:
        q = (new.get(term, 0) + DRIFT_SMOOTH) / new_total
        p = (draft.get(term, 0) + DRIFT_SMOOTH) / draft_total
        drift += q * math.log(q / p)
    return drift


def voice_pushes(terms, table, top=8):
    # what's pushing a section toward AI, strongest first, so a rewrite has something to aim at when no sentence is flagged
    known = [(table["weights"][t], 1 + math.log(n), t, n) for t, n in terms.items() if t in table["weights"]]
    norm = math.sqrt(sum(v * v for _, v, _, _ in known)) or 1.0
    hits = sorted(((w * v / norm, t, n) for w, v, t, n in known if w > 0 and (t == "<s> _" or any(p not in ("<s>", "_", "#") for p in t.split()))), reverse=True)
    return [f"{t.replace('<s>', '(sentence start)').replace('#', '(name)').replace('_', '...')} x{n} (+{push:.2f})" for push, t, n in hits[:top]]


def external_links(markdown):
    # links that leave the repo; badges, anchors and relative links don't count
    links = 0
    for token in parse_md(site_free(markdown)):
        kids = token.children or []
        for i, kid in enumerate(kids):
            if kid.type == "link_open" and not (i + 1 < len(kids) and kids[i + 1].type == "image") and URL_START.match(kid.attrGet("href") or ""):
                links += 1
    return links


def external_link_rate(markdown):
    return external_links(markdown) * 100 / max(len(site_free(markdown).split()), 1) if is_markdown(markdown) else 0.0


def link_excess(rate, cap):
    return max(0.0, math.log1p(rate) - math.log1p(cap))


def blend_prob(features, blend):
    # people link out and agents mostly don't; this can only lower a score, so it clears some human docs and never flags one
    z = blend["intercept"] - blend.get("link_credit", 0.0) * link_excess(features.get("ext_rate", 0.0), blend.get("link_cap", 0.0))
    for name, coef, mean, scale in zip(blend["features"], blend["coef"], blend["mean"], blend["scale"]):
        z += coef * (features[name] - mean) / scale
    return 1 / (1 + math.exp(-z))


def load_blends(genre):
    if not os.path.exists(BLEND_FILE):
        return {}
    with open(BLEND_FILE) as f:
        blends = json.load(f)
    # blend.json from before genres were split holds one blend for everything
    if "features" in blends:
        return {"prose": blends}
    chosen = {g: blends[g] for g in (["prose", "docs"] if genre == "both" else [genre])}
    for blend in chosen.values():
        if "ngram" in blend:
            blend["ngram"]["closed"] = set(blend["ngram"]["closed"])
    return chosen


def blend_bars(blend, register):
    # that register's own cut, bar and human reference, or the blend's pooled ones when it has none
    return blend.get("registers", {}).get(register) or blend


def text_verdict(probs, bars):
    # with two blends, "ai" needs either one and "human" needs both
    if any(p >= bars[g]["threshold_ai"] for g, p in probs.items()):
        return "ai"
    if all(p < bars[g]["threshold_human"] for g, p in probs.items()):
        return "human"
    return "unclear"


def pick_genre(text, genre, path=None):
    if genre != "auto":
        return genre
    # GitHub community-health files are docs whatever their content; any other .md may be a post or a draft
    if path and COMMUNITY_DOC.search(path):
        return "docs"
    if has_code(text):
        return "docs"
    # headings but no code: a blog post or a code-free doc page, so score it both ways. A link or a '--' signature isn't structure
    return "both" if STRUCTURE.search(FRONT_MATTER.sub("", text)) else "prose"


def analyse_document(text, scorer, heldout=False, genre="auto", path=None, register=None):
    genre = pick_genre(text, genre, path)
    skipped = collections.Counter()
    ext_rate = external_link_rate(text)
    prose = prepare(text, skipped)
    n_words = len(WORD.findall(prose))
    if n_words == 0 or (genre == "docs" and n_words < MIN_DOC_WORDS):
        return {"words": n_words, "genre": genre, "warning": "too little prose to score once code and markup are removed"}
    # the docs blend only ever saw sections of 120+ words; below that it reads short human text as AI
    if genre == "both" and n_words < MIN_DOC_WORDS:
        genre = "prose"
    blends = load_blends(genre)
    kept = {k: v for k, v in skipped.items() if v}
    not_read = {"not_read": kept} if kept else {}
    sections = doc_sections(prose)
    named = {"register": register} if register else {}
    if len(sections) <= 1:
        return analyse(prose, scorer, blends, heldout, ext_rate, register) | {"genre": genre} | named | not_read
    results = [analyse(section, scorer, blends, heldout, ext_rate, register) for section in sections]
    words = sum(r["words"] for r in results)
    result = {"words": words, "genre": genre, "document": True, "sections": []} | named | not_read
    for bar in ("human_bar", "ai_bar"):
        if seen := {r[bar] for r in results if bar in r}:
            result[bar] = min(seen)
    # recalled text says nothing about who wrote the sections around it, and short sections swing too much to decide alone
    scored = [r for r in results if r.get("verdict") not in (None, "known text")]
    counted = [r for r in scored if r["words"] >= MIN_DOC_WORDS] or scored
    if any(r.get("verdict") == "known text" for r in results):
        result["contains_known_text"] = True
    if not counted:
        if result.get("contains_known_text"):
            result["verdict"] = "known text"
    else:
        counted_words = sum(r["words"] for r in counted)
        result["ai_share"] = round(sum(r["words"] for r in counted if r["verdict"] == "ai") / max(counted_words, 1), 2)
        result["ai_probability"] = max(r["ai_probability"] for r in counted)
        not_human = sum(r["words"] for r in counted if r["verdict"] != "human") / max(counted_words, 1)
        # the rewrite loop wants every section under the bar; the verdict alone tolerates one stray section
        result["all_sections_human"] = all(r["verdict"] == "human" for r in counted)
        if result["ai_share"] >= 0.25:
            result["verdict"] = "ai"
        # a long human doc can hold one stray section, but rarely one at 0.9
        elif not_human < 0.5 and result["ai_probability"] < 0.9:
            result["verdict"] = "human"
        else:
            result["verdict"] = "unclear"
    # the same sections the verdict comes from. A section too short to decide, or one of known text, does
    # not get to settle the second opinion either: this used to max over every section, so a 90-word
    # heading block could hold a long document's number on its own.
    if heldout and counted and all("heldout_roberta" in r for r in counted):
        result["heldout_roberta"] = max(r["heldout_roberta"] for r in counted)
    for i, r in enumerate(results):
        r["section"] = i
        r["starts"] = " ".join(sections[i].split()[:12])
        result["sections"].append(r)
    result["flagged_sentences"] = sum(r["flagged_sentences"] for r in results)
    return result


def analyse(text, scorer, blends, heldout=False, ext_rate=0.0, register=None):
    flat = canon(text)
    feats = style_features(flat)
    # the docs blend never saw first-person writing; on emails it mistakes short sentences for AI docs
    if len(blends) > 1 and feats["first_person_rate"] >= 1.0:
        blends = {g: b for g, b in blends.items() if g != "docs"}
    pushes = []
    if "ngram" in blends.get("docs", {}):
        table = blends["docs"]["ngram"]
        terms = voice_terms(flat, table["closed"])
        feats["ngram"] = voice_score(terms, table)
        feats["ext_rate"] = ext_rate
        pushes = voice_pushes(terms, table)
    per_token = []
    if scorer and flat:
        lm_feats, per_token = scorer.lm(flat)
        feats.update(lm_feats)
    scores = sentence_scores(flat, per_token)
    if scorer and flat:
        feats.update(sentence_spread(scores))
    result = {"words": feats["n_words"]}
    if pushes:
        result["voice_pushes_ai"] = pushes
    if blends and scorer and flat and feats["n_words"] >= MIN_VERDICT_WORDS:
        probs = {g: blend_prob(feats, b) for g, b in blends.items()}
        bars = {g: blend_bars(b, register) for g, b in blends.items()}
        top, prob = max(probs.items(), key=lambda kv: kv[1])
        result["ai_probability"] = round(prob, 3)
        result["human_bar"] = round(bars[top]["threshold_human"], 3)
        result["ai_bar"] = round(bars[top]["threshold_ai"], 3)
        result["verdict"] = text_verdict(probs, bars)
        if len(probs) > 1:
            result["by_genre"] = {g: round(p, 3) for g, p in probs.items()}
        reference = bars[top]["human_reference"]
        result["more_ai_like_than_human_samples"] = f"{round(100 * bisect.bisect_left(reference, prob) / len(reference))}%"
        if feats["top1_frac"] >= KNOWN_TEXT_TOP1:
            result["verdict"] = "known text"
            result["note"] = ("the models predict almost every word: a widely published text (licence, code of conduct, "
                              "famous quote) or text that repeats itself; that says nothing about who wrote it")
    if "binoculars" in feats:
        result["binoculars"] = round(feats["binoculars"], 4)
    if heldout and scorer and scorer.heldout is not None:
        result["heldout_roberta"] = round(scorer.heldout_prob(flat), 3)
    if feats["n_words"] < MIN_VERDICT_WORDS:
        # no AI training text is this short, and on short held-out prose the blend calls most AI human
        result["warning"] = f"under {MIN_VERDICT_WORDS} words: no verdict, only the sentence flags mean anything"
    result["signals"] = {k: round(v, 3) for k, v in feats.items() if k != "n_words"}

    # a sentence-level habit only counts as a flag in a genre where the training AI text shows it more than people do
    support = {}
    for b in blends.values():
        for name, ratio in b.get("flag_support", {}).items():
            support[name] = max(support.get(name, 0.0), ratio)
    # with two blends, 'too predictable' needs both genres to back it
    cuts = [b.get("sentence_binoculars_cut") for b in blends.values()]
    cut = min(cuts) if cuts and None not in cuts else (0.8 if not blends else None)
    min_words = next(iter(blends.values()))["sentence_min_words"] if blends else 12
    contrasts = contrast_spans(flat)
    sentences = []
    for i, (start, end, sentence, n_words, ce, xe, n_tokens) in enumerate(scores):
        flags = sentence_flags(sentence)
        if any(s < end and e > start for s, e in contrasts):
            flags.append("not-X-but-Y frame")
        entry = {"i": i, "text": sentence, "flags": flags}
        if support:
            entry["flags"] = [f for f in flags if f not in STRUCTURAL_FLAGS or support.get(f, 0.0) >= 1.25]
            if habits := [f for f in flags if f not in entry["flags"]]:
                entry["habits"] = habits
        if n_tokens >= 4 and xe:
            entry["binoculars"] = round(ce / xe, 3)
            if n_words >= min_words and entry["binoculars"] < RECALLED:
                # quoted, standard or repeated wording: not something the writer chose
                entry["recalled"] = True
                entry["flags"] = []
            elif cut is not None and n_words >= min_words and entry["binoculars"] < cut:
                entry["flags"].append("too predictable")
        sentences.append(entry)
    result["sentences"] = sentences
    result["flagged_sentences"] = sum(1 for s in sentences if s["flags"])
    return result


NUMBER_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
                "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "twenty": "20", "hundred": "100", "thousand": "1000"}
SUFFIXES = [("ies", "y"), ("es", ""), ("s", ""), ("ed", ""), ("ed", "e"), ("ing", ""), ("ing", "e"), ("ly", ""), ("ly", "e"),
            ("ier", "y"), ("iest", "y"), ("er", ""), ("er", "e"), ("est", ""), ("est", "e")]
_DICT = [w.strip() for w in open("/usr/share/dict/words")] if os.path.exists("/usr/share/dict/words") else []
_CORPUS_WORDS = os.path.join(HERE, "words.txt")
DICT_LOWER = {w for w in _DICT if w[:1].islower()}
if os.path.exists(_CORPUS_WORDS):
    DICT_LOWER |= {w.strip() for w in open(_CORPUS_WORDS)}
DICT_CAP = {w for w in _DICT if w[:1].isupper()}


def common_word(word):
    if "-" in word:
        return all(common_word(part) for part in word.split("-") if part)
    if word.lower() in DICT_LOWER:
        return True
    w = re.sub(r"(n't|'s|'re|'ll|'ve|'d|'m)$", "", word.lower())
    if word in DICT_CAP and w not in DICT_LOWER:
        return False
    stems = {w} | {w[: -len(a)] + b for a, b in SUFFIXES if w.endswith(a)}
    # dropped -> dropp -> drop, bigger -> bigg -> big
    stems |= {s[:-1] for s in stems if len(s) > 2 and s[-1] == s[-2]}
    return any(s in DICT_LOWER for s in stems)


def fact_text(text):
    text = text.replace("**", "").translate(QUOTES)
    return re.sub(r"(\d)\s*(per ?cent|percent)\b", r"\1%", text)


def strip_code(markdown):
    lines = markdown.splitlines()
    for tok in parse_md(markdown):
        if tok.type in ("fence", "code_block") and tok.map:
            for n in range(*tok.map):
                lines[n] = ""
    return "\n".join(lines)


def facts(text):
    # code blocks are checked whole by compare(), so facts come from the prose around them
    text = fact_text(strip_code(text))
    found = {m.replace(",", "") for m in re.findall(r"\d[\d,.:/%]*\d%?|\d%?", text)}
    found |= {u.rstrip(".,;:!?)'\"") for u in re.findall(r"https?://\S+", text)}
    found |= set(re.findall(r"\S+@\S+\.\w+|[@#]\w+|`[^`\n]+`|\"[^\"\n]{3,80}\"", text))
    for sentence in split_sentences(text):
        start = True
        for tok in sentence.split():
            word = re.sub(r"'s$", "", tok.strip(".,;:!?()\"'*-"))
            if len(word) > 1 and word[0].isupper() and word.lower() not in ("i'm", "i've", "i'd", "i'll"):
                # a capital at the start of a sentence is only a name if it isn't an everyday word
                if not start or not common_word(word):
                    found.add(word)
            start = tok.endswith(":") or tok in ("-", "*", "•")
    return found


def present(fact, text):
    text = fact_text(text)
    # `name` in the prose of one version and name inside a code block of the other is the same reference
    if fact.startswith("`") and fact.endswith("`") and fact[1:-1] in text:
        return True
    if fact[0].isdigit():
        if re.search(r"(?<![\d.])" + re.escape(fact) + r"(?![\d]|\.\d)", text.replace(",", "")):
            return True
        return any(re.search(r"\b" + w + r"\b", text, re.I) for w, d in NUMBER_WORDS.items() if d == fact)
    if re.search(r"(?<!\w)" + re.escape(fact) + r"(?!\w)", text):
        return True
    # "Attendees" opening a sentence in one version and "attendees" mid-sentence in the other is the same word
    return fact[:1].isupper() and not fact.isupper() and re.search(r"(?<!\w)" + re.escape(fact) + r"(?!\w)", text, re.I) is not None


def compare(original, rewrite):
    before, after = facts(original), facts(rewrite)
    result = {
        "missing": sorted(f for f in before - after if not present(f, rewrite)),
        "added": sorted(f for f in after - before if not present(f, original)),
        "length_ratio": round(len(WORD.findall(prepare(rewrite))) / max(len(WORD.findall(prepare(original))), 1), 2),
    }
    # the rewrite loop has no other anchor to the draft's voice, so price the move away from it
    ngram = load_blends("docs").get("docs", {}).get("ngram")
    if ngram:
        result["voice_drift"] = round(voice_drift(original, rewrite, ngram["closed"]), 3)
    # adding links would walk a doc past the link credit without changing a word of it
    links_added = external_links(rewrite) - external_links(original)
    if links_added > 0:
        result["links_added"] = links_added
    # in docs, code is the part a rewrite must never touch; fence style and trailing spaces don't count as changes
    blocks_before, blocks_after = code_blocks(original), code_blocks(rewrite)
    if blocks_before or blocks_after:
        result["code_blocks_changed"] = sum((blocks_before - blocks_after).values())
        result["code_blocks_added"] = sum((blocks_after - blocks_before).values())
    return result


def ask_server(text, heldout, genre="auto", path=None, register=None):
    import urllib.error
    import urllib.request

    body = json.dumps({"text": text, "heldout": heldout, "genre": genre, "path": path, "register": register}).encode()
    if len(body) > MAX_BODY:
        # the scorer refuses it, so score it here instead, as if no scorer were running
        return None
    request = urllib.request.Request(f"http://127.0.0.1:{PORT}/score", data=body, headers={"Content-Type": "application/json"})
    # no proxy handler: one set in the environment or the system settings would otherwise get the draft
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=300) as resp:
            result = json.load(resp)
    except urllib.error.HTTPError as err:
        body = err.read()[:300]
        # the scorer itself answers 500 when scoring raises, and that isn't a port problem
        if b'"server": "humanize"' in body:
            sys.exit(f"scorer on port {PORT} answered {err.code}: {body!r}")
        sys.exit(f"port {PORT} answered {err.code}: {body!r}. {NOT_OURS}")
    except urllib.error.URLError as err:
        if isinstance(err.reason, ConnectionRefusedError):
            return None
        sys.exit(f"scorer on port {PORT} failed: {err.reason!r}")
    if result.get("server") != "humanize" or result.get("code_mtime") != CODE_MTIME:
        sys.exit(f"port {PORT} is not this humanize scorer or it runs older detect.py code. {NOT_OURS}")
    return result


def refuse(path, headers):
    # any web page can POST text/plain here without a preflight, and a rebinding DNS name can reach it too;
    # only this machine's own clients, which send JSON straight to 127.0.0.1, get a score
    if path != "/score":
        return 404
    if headers.get("Origin") or headers.get("Host") not in (f"127.0.0.1:{PORT}", f"localhost:{PORT}"):
        return 403
    if not (headers.get("Content-Type") or "").startswith("application/json"):
        return 415
    length = headers.get("Content-Length")
    if length is None:
        return 411
    # isdigit also turns away "-1", which rfile.read would take as "read to the end"
    if not length.isdigit():
        return 400
    return 413 if int(length) > MAX_BODY else None


def serve():
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, HTTPServer

    last_request = [time.time()]
    state = {}

    class Handler(BaseHTTPRequestHandler):
        timeout = 10  # a client that opens a connection and stalls is dropped instead of holding the only thread

        def do_POST(self):
            refused = refuse(self.path, self.headers)
            if refused:
                return self.send_error(refused)
            try:
                req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                # re-read blend.json every time so a refit takes effect without a restart
                result = analyse_document(req["text"], state["scorer"], req.get("heldout", False), req.get("genre", "auto"), req.get("path"), req.get("register"))
                payload, code = {"server": "humanize", "code_mtime": CODE_MTIME, **result}, 200
            except Exception as err:
                payload, code = {"server": "humanize", "error": repr(err)}, 500
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            last_request[0] = time.time()

        def log_message(self, *args):
            pass

    # bind before loading so a second --serve fails fast; single-threaded so requests queue instead of sharing GPU memory
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    state["scorer"] = Scorer(heldout=True)
    last_request[0] = time.time()

    def stop_when_idle():
        while time.time() - last_request[0] < IDLE_SECONDS:
            time.sleep(15)
        server.shutdown()

    threading.Thread(target=stop_when_idle, daemon=True).start()
    print(f"scorer ready on 127.0.0.1:{PORT}, stops after {IDLE_SECONDS // 60} idle minutes", file=sys.stderr, flush=True)
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="AI-text detector")
    parser.add_argument("file", nargs="?", help="text file to score (default: stdin)")
    parser.add_argument("--fast", action="store_true", help="style signals only, no language models")
    parser.add_argument("--heldout", action="store_true", help="also run the separate RoBERTa detector")
    parser.add_argument("--genre", choices=["auto", "prose", "docs", "both"], default="auto",
                        help="which blend to use; auto picks from the file name and content")
    parser.add_argument("--register", choices=REGISTERS,
                        help="judge prose against this register's writers instead of all of them; leave it off if unsure")
    parser.add_argument("--compare", metavar="ORIGINAL", help="check FILE keeps the facts in ORIGINAL")
    parser.add_argument("--serve", action="store_true", help="keep the models loaded for other detect.py calls")
    parser.add_argument("--batch", metavar="JSONL", help="add features to every row of a JSONL file")
    parser.add_argument("--out", metavar="JSONL", help="output path for --batch")
    parser.add_argument("--reuse", metavar="JSONL", help="with --batch, copy model scores from an earlier output for unchanged text")
    parser.add_argument("--scan", metavar="DIR", help="score every tracked .md, .mdx and .txt file in a folder")
    args = parser.parse_args()

    if args.scan:
        scan(args.scan, args.heldout, args.out, args.fast, args.genre, args.register)
        return

    if args.compare:
        with open(args.compare) as f:
            original = f.read()
        with open(args.file) as f:
            rewrite = f.read()
        print(json.dumps(compare(original, rewrite), indent=2))
        return
    if args.serve:
        serve()
        return

    if args.batch:
        old = {}
        if args.reuse:
            for line in open(args.reuse):
                row = json.loads(line)
                old[row["text"]] = row
        scorer = None
        rows = [json.loads(line) for line in open(args.batch)]
        reused = 0
        with open(args.out, "w") as out:
            for n, row in enumerate(rows):
                flat = canon(prepare(row["text"]))
                feats = style_features(flat)
                prev = old.get(row["text"])
                # model scores carry over only when the scored text can't have changed (no markup removed, now or then)
                # and the sentences still split the same way
                if (prev and flat == canon(row["text"]) and prev["features"]["n_words"] == feats["n_words"]
                        and [n for n, _, _ in prev["sentences"]] == [len(WORD.findall(s)) for s in split_sentences(flat)]):
                    feats.update({k: v for k, v in prev["features"].items() if k not in feats})
                    row["sentences"] = prev["sentences"]
                    reused += 1
                else:
                    scorer = scorer or Scorer(heldout=True)
                    lm_feats, per_token = scorer.lm(flat)
                    feats.update(lm_feats)
                    scores = sentence_scores(flat, per_token)
                    feats.update(sentence_spread(scores))
                    feats["heldout_roberta"] = scorer.heldout_prob(flat)
                    row["sentences"] = [[n_words, ce, xe] for _, _, _, n_words, ce, xe, _ in scores]
                row["features"] = feats
                out.write(json.dumps(row) + "\n")
                if n % 100 == 0:
                    print(f"{n}/{len(rows)} ({reused} reused)", file=sys.stderr, flush=True)
        print(f"done: {len(rows)} rows, {reused} reused", file=sys.stderr)
        return

    text = open(args.file).read() if args.file else sys.stdin.read()
    if not args.fast:
        result = ask_server(text, args.heldout, args.genre, args.file, args.register)
        if result is not None:
            result.pop("server", None)
            result.pop("code_mtime", None)
            print(json.dumps(result, indent=2))
            return
    scorer = None if args.fast else Scorer(heldout=args.heldout)
    print(json.dumps(analyse_document(text, scorer, args.heldout, args.genre, args.file, args.register), indent=2))


def scan(folder, heldout, out, fast=False, genre="auto", register=None):
    import subprocess

    # -z, because git quotes any path that isn't plain ASCII
    listed = subprocess.run(["git", "-C", folder, "ls-files", "-z", "--", "*.md", "*.mdx", "*.txt"], capture_output=True, text=True)
    paths = [p for p in listed.stdout.split("\0") if p] if listed.returncode == 0 else []
    if listed.returncode != 0:
        skip = {".git", "node_modules", "dist", "build", ".next", ".venv"}
        for root, dirs, names in os.walk(folder):
            dirs[:] = [d for d in dirs if d not in skip]
            paths += [os.path.relpath(os.path.join(root, n), folder) for n in names if n.endswith((".md", ".mdx", ".txt"))]
    scorer, results = None, {}
    print(f"{'file':<48} {'genre':<6} {'words':>6} {'verdict':<11} {'AI prob':>7} {'flagged':>7}")
    inside = os.path.realpath(folder) + os.sep
    for path in sorted(paths):
        full = os.path.join(folder, path)
        # a tracked symlink can point anywhere on the machine, and scan.json would carry what it read;
        # a pipe or device would hang the read
        if not os.path.realpath(full).startswith(inside) or not os.path.isfile(full):
            results[path] = {"error": "skipped: a symlink, or not a regular file inside the folder"}
            print(f"{path[-48:]:<48} skipped: symlink or not a regular file")
            continue
        try:
            text = open(full, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError) as err:
            results[path] = {"error": repr(err)}
            print(f"{path[-48:]:<48} could not read: {type(err).__name__}")
            continue
        result = None if fast else ask_server(text, heldout, genre, path, register)
        if result is None:
            scorer = scorer or (None if fast else Scorer(heldout=heldout))
            result = analyse_document(text, scorer, heldout, genre, path, register)
        result.pop("server", None)
        result.pop("code_mtime", None)
        results[path] = result
        prob = f"{result['ai_probability']:.2f}" if "ai_probability" in result else "-"
        print(f"{path[-48:]:<48} {result['genre']:<6} {result['words']:>6} {result.get('verdict', '-'):<11} {prob:>7} "
              f"{result.get('flagged_sentences', 0):>7}")
    if out:
        with open(out, "w") as f:
            json.dump(results, f, indent=2)
    print("\nA verdict is a statistical guess about the text, not proof of who wrote it.")


if __name__ == "__main__":
    main()

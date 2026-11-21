# Read a merged pull request's own evidence and say whether AI wrote what it changed.
#
# What this is worth, measured: against an independent reader working from the same evidence on 363 pull
# requests from 21 projects, it agrees on 359. Every verdict it issues matches: 42 of 42 from a trailer,
# 97 of 97 from a description. All four misses are pull requests it calls undeclared and the reader calls
# AI, so it under-claims rather than mislabels, and nothing it says is AI was called human or the reverse.
# Read that number for what it is: the first pass scored 292 of 363, and the patterns here were fixed
# against these same projects, so a template nobody here has seen will do worse. The failures were real
# classes, not one-offs - a negation hidden by markdown emphasis, a negation inside a pasted prompt, a box
# that only agrees to the policy, a trailer in the description rather than the commit - and each has a test.
# read() reports which channel decided, so a caller can require the structured one.
#
# It also only means anything in a project whose policy makes contributors declare: the duty to declare is
# what turns a quiet pull request into a claim. Even then only an explicit "no AI" counts as human here,
# because silence is as likely to be someone ignoring the rule. And a declaration is not proof: three docs
# whose pull requests ticked "no AI" flag as AI where the same project's earlier docs do not.
import re

# product names, safe to look for anywhere
TOOL = re.compile(r"(?i)\b(?:claude|anthropic|chatgpt|openai|codex|copilot|cursor|gemini|devin|jules|aider|windsurf|"
                  r"cline|roo ?code|opencode|deepseek|qwen|kimi|grok|llama|tabnine|codeium|sourcegraph|amp|glm|kiro|"
                  r"mistral vibe|hermes agent|github models|gpt-? ?\d)\b")
# generic words for the same thing; only trustworthy inside a sentence that is declaring something
AI_WORD = re.compile(r"(?i)\b(?:ai|a\.i\.|ais|llm|llms|genai|gen-ai|generative|agentic|machine[- ]generated)\b")
# addresses the tools commit under, for a trailer whose value names no product
AI_MAIL = re.compile(r"(?i)@anthropic\.com|@openai\.com|copilot@github\.com|@cursor\.com|vibe@mistral\.ai|"
                     r"devin-ai-integration|@google\.com>|noreply@google")
# accounts that open pull requests on their own. dependabot and renovate are bots too, and write no prose.
AI_BOT = {"copilot-swe-agent", "copilot", "devin-ai-integration", "cursoragent", "chatgpt-codex-connector",
          "claude", "claude-bot", "google-labs-jules", "gemini-code-assist", "sweep-ai", "codegen-sh"}
# trailer keys a project uses to credit a tool. Co-authored-by also credits people, so the value decides.
TRAILER = re.compile(r"(?im)^[ \t>*`_-]*(co-?authored-by|assisted-by|generated-by|generated-with|genai|gen-ai|"
                     r"ai-assisted|ai-tool|ai)[ \t]*:[ \t]*(.+?)[ \t\r]*$")
# the badge the tools write into a commit body without a trailer key
STAMP = re.compile(r"(?i)generated with \[?(?:claude code|cursor|codex|copilot|gemini)|🤖 generated with")
COMMENT = re.compile(r"<!--.*?-->", re.S)
# "_not_" hides a negation from \bnot\b, because _ counts as a word character
EMPHASIS = re.compile(r"[*_`]+")
# markup and stray carriage returns around a trailer's value
BORDER = "`*_ \t\r"
# a claim is its first sentence. The rest can be anything, including a pasted prompt, and a "doesn't"
# inside that prompt used to turn "I have used AI tools to generate the contents" into a denial.
CLAIM = re.compile(r"^[^.!?\n]*")
HEADING = re.compile(r"(?im)^\s{0,3}(?:#{1,6}\s|\*\*[^*\n]+\*\*:?\s*$)")
# a heading or bold label that opens the part of the description where AI use goes
AI_SECTION = re.compile(r"(?i)\bai (?:usage|statement|disclosure|use|assistance)\b|\bdisclosure on gen-?ai\b|"
                        r"\bgenerative ai\b|\bai[- ]assisted\b|\bai tools?\b|\bai acknowledg|\bdid you use ai\b")
BOX = re.compile(r"(?m)^[ \t>]*[-*+]?[ \t]*(?:[-*+][ \t]*)?\[([ xX])\][ \t]*(.+?)[ \t]*$")
# "AI Statement is included" only says a statement exists, so it votes for neither side. Nor does
# "I have disclosed AI tool usage below, or confirmed that no AI tools were used", which offers both
# answers in one line and so says only that the contributor ticked the compliance box.
META_BOX = re.compile(r"(?i)^(?:the )?(?:ai|gen-?ai|generative ai)[- ]?(?:statement|policy|disclosure|section)\b"
                      r".{0,40}\b(?:is |has |been )?(?:included|completed|provided|filled|read|attached)\b"
                      r"|\b(?:disclosed|declared|stated|confirmed)\b.{0,70}\b(?:or|and)\b.{0,50}\b(?:no|not|none)\b"
                      # "Confirm you have read our AI policy", "I have read and agree to be bound by the AI / LLM
                      # policy": agreeing to a rule is not saying what went into the contribution. Anchored at the
                      # front, so a real claim that happens to mention the guidelines later still counts.
                      r"|^(?:confirm|you have read|i have read|i read|i (?:have )?agree|i acknowledge|i accept)\b"
                      # "any use of AI has been declared in this pull request" promises there is a declaration
                      # somewhere; it is not itself one
                      r"|^any\b.{0,70}\b(?:has|have) been (?:declared|disclosed)\b"
                      # "If AI tools were used: I have disclosed the tool below" is conditional on the thing
                      # being asked about, so it answers nothing
                      r"|^if\b.{0,50}\b(?:ai|gen-?ai|llm)s?\b")
NEGATED = re.compile(r"(?i)\b(?:does not|do not|don't|doesn't|did not|didn't|was not|wasn't|were not|no|none|not|"
                     r"without|never|n/a|nil|zero)\b")
# people answer an empty AI section with one of these and nothing else
NOTHING = re.compile(r"(?i)^(?:none|no|n|n/?a|nil|nope|none\.?|no ai|not applicable|-{1,3}|—)[.!]?$")
# agones asks "Did you use AI tools in preparing this PR?" and people answer with one letter
AFFIRMED = re.compile(r"(?i)^(?:y|yes|yep|yeah|true)[.!]?$")
SAYS_AI = re.compile(r"(?i)\b(?:extensive|limited|partial|some|significant|heavy|minor|light)[ \t]+use of\b|"
                     r"\bused?\b[^\n]{0,60}\bto (?:write|draft|generate|help|suggest|review|revise|edit|fix|uncover|"
                     r"explore|translate|summari[sz]e|prepare|understand|identify|investigate)|"
                     r"\bused?\b[^\n]{0,40}\bfor (?:the |this )?(?:draft|writing|implementation|analysis|docs|autocompletion)|"
                     r"\b(?:was|were|is)\s+(?:used|generated|written|drafted|produced|assisted|prepared)\b|"
                     r"\b(?:i|we)\s+(?:have\s+|had\s+)?(?:used|asked|pointed|prompted|ran)\b|"
                     r"\b(?:assisted|generated|written|drafted|revised|rewritten|prepared)\s+(?:with|by|using|in)\b|"
                     r"\bthis (?:pr|contribution|change|commit)\s+(?:used|includes?|does include)\b|"
                     r"\bdoes include\b|\bai[- ]assisted\b|\b(?:with|using) (?:the )?(?:help|assistance|aid) (?:of|from|in)\b")
SAYS_NO_AI = re.compile(r"(?i)\bno (?:generative |gen-?ai |)?ai\b[^.\n]{0,30}\b(?:was|were|is|used|involved)|"
                        r"\bwithout (?:any |the use of )?(?:generative )?(?:ai|llm)|\bdoes not include\b|"
                        r"\bentirely (?:by hand|without ai|human)|\b(?:all|fully) human[- ](?:written|authored)|"
                        r"\bno (?:generative )?ai\b(?!\w)|\b(?:did|do|does|have|has)\s+not\s+use\b|"
                        r"\bno ai-generated content\b")


# the preposition right before a tool's name: "the grunt work done by GPT-6.1 Sol", "authored this using Codex"
BY_TOOL = re.compile(r"(?i)\b(?:by|using|via|with)\s+(?:the\s+)?$")
# what a tool is said to have done, right after its name: "Claude found this issue and made the fix"
TOOL_DID = re.compile(r"(?i)^\W{0,3}(?:\w+\s){0,3}?(?:found|wrote|made|drafted|generated|fixed|suggested|helped|"
                      r"did|produced|authored|flagged|implemented|reviewed|rewrote)\b")


def plain(text):
    # markdown emphasis off, so a negation inside _underscores_ is still a word
    return EMPHASIS.sub(" ", text)


def tool_claim(line):
    # the line names a tool and says that tool did some of the work. "I authored this using OpenAI Codex"
    # counts; "this adds support for the Claude API" does not.
    found = TOOL.search(line)
    if not found:
        return False
    return bool(BY_TOOL.search(line[max(0, found.start() - 30) : found.start()]) or TOOL_DID.search(line[found.end() :]))


def tool_evidence(commits, author=None, body=""):
    # a trailer, a tool's own badge or a tool's account. Some projects want the trailer in the description
    # rather than the commit, so both are read: it is the same structured line either way.
    if author and (author.lower().removesuffix("[bot]") in AI_BOT or (author.endswith("[bot]") and TOOL.search(author))):
        return f"opened by {author}"
    for message in list(commits) + ([body] if body else []):
        found = STAMP.search(message)
        if found:
            return found.group(0).strip()
        for key, value in TRAILER.findall(message):
            if TOOL.search(value) or AI_MAIL.search(value):
                return f"{key}: {value.strip(BORDER)}"[:90]
    return None


def sections(body):
    # the lines under each AI heading, up to the next heading of any kind
    out = []
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if not (HEADING.match(line + "\n") and AI_SECTION.search(line)):
            continue
        block = []
        for later in lines[i + 1 :]:
            if HEADING.match(later + "\n"):
                break
            block.append(later)
        out.append("\n".join(block).strip())
    return out


def votes(body):
    # every declaration in the description, as yes-AI and no-AI counts
    yes = no = 0
    for mark, raw in BOX.findall(body):
        text = plain(raw)
        if not (AI_WORD.search(text) or TOOL.search(text)) or META_BOX.search(text):
            continue
        if mark.strip().lower() != "x":
            continue
        # the claim is the first sentence; a negation later in the line can belong to anything
        claim = CLAIM.match(text).group(0)
        if SAYS_NO_AI.search(claim) or NEGATED.search(claim):
            no += 1
        else:
            yes += 1
    stripped = BOX.sub("", body)
    for raw in stripped.splitlines():
        line = plain(raw).strip(" \t>-")
        if not line or not (AI_WORD.search(line) or TOOL.search(line)):
            continue
        if SAYS_NO_AI.search(line):
            no += 1
        elif SAYS_AI.search(line) or tool_claim(line):
            yes += 1
    for block in sections(body):
        if not block.strip() or BOX.search(block):
            continue            # an unanswered template, or a checkbox one the loop above already read
        block = plain(block)
        first = block.splitlines()[0].strip(" \t>-")
        if NOTHING.match(first):
            no += 1
        elif AFFIRMED.match(first):
            yes += 1
        elif not (AI_WORD.search(block) or TOOL.search(block)):
            continue            # the section is last in most templates, so it swallows whatever follows
        # the section is there for one purpose, so any other answer in it is a declaration, which catches
        # tools nothing here has a name for. Anything the lines above can read is left to them, since
        # they are the ones that check for a no before they count a yes.
        elif not SAYS_AI.search(block) and not SAYS_NO_AI.search(block):
            yes += 1
    return yes, no


def read(body, commits, author=None):
    # Returns (label, why, channel). ai: the tools left a mark, or the author said so. human: the author
    # explicitly said no AI, and nothing contradicts it. unknown: silence, an unanswered template, or a
    # description that says both. channel is "commit" when a trailer or a tool's account decided it,
    # "description" when the text did, and None when nothing was declared: see the note at the top for
    # how far each of those can be trusted.
    found = tool_evidence(commits, author, body or "")
    if found:
        return "ai", found, "trailer"
    yes, no = votes(COMMENT.sub("", body or ""))
    if yes and not no:
        return "ai", "the description says so", "description"
    if no and not yes:
        return "human", "the description says no AI was used", "description"
    if yes and no:
        return "unknown", "the description says both", "description"
    return "unknown", "nothing declared", None

---
type: llm
focus: trace
weight: 1
---

detect.py --compare reports no links_added: final.txt has no more external links than draft.txt. Links are counted, not URLs, so a second link to a URL draft.txt already links counts as added; badges, #anchors and relative links are not counted at all

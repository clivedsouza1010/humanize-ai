---
type: llm
focus: trace
weight: 1
---

final.txt gets verdict "human" from scripts/detect.py, and if it scored in sections, all_sections_human is true. In docs an entry in sections[] that reads "ai" does not fail the round by itself; it fails only by making all_sections_human false

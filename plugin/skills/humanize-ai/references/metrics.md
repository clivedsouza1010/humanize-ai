# Detector metrics

Generated 2026-11-15 by bench/fit.py from 12199 rows.

Layout check passed: adding or removing paragraph breaks leaves the scored prose unchanged.

This refit replaced prose only, without the Yelp reviews it used to train on. docs stayed as it was, so its section is from the fit before.

## Prose (essays, posts, emails, reviews, news, abstracts)

2118 rows (1441 train, 644 test), 26 features. Regularisation C = 5.0, picked by grouped 5-fold CV on train (C=0.1: 0.861, C=0.5: 0.871, C=2.0: 0.878, C=5.0: 0.882).

### Held-out test split

AI caught and human flagged are at probability 0.5, with 95% Wilson intervals.

| detector | accuracy | AI caught | human flagged | AUROC |
|---|---|---|---|---|
| Binoculars alone (best train cut) | 0.705 | 177/331 = 0.535 (0.48-0.59) | 36/313 = 0.115 (0.08-0.16) | 0.768 |
| fakespot RoBERTa alone | 0.738 | 211/331 = 0.637 (0.58-0.69) | 49/313 = 0.157 (0.12-0.20) | 0.790 |
| style only | 0.694 | 233/331 = 0.704 (0.65-0.75) | 99/313 = 0.316 (0.27-0.37) | 0.775 |
| LM only | 0.790 | 245/331 = 0.740 (0.69-0.78) | 49/313 = 0.157 (0.12-0.20) | 0.870 |
| **blend** | 0.852 | 283/331 = 0.855 (0.81-0.89) | 47/313 = 0.150 (0.11-0.19) | 0.943 |

### By source (held-out test)

'reads human' means probability under threshold_human = 0.290, the 80th percentile of out-of-fold human training scores. Out of fold, 80% of human and 4.6% of AI training texts are under it. That's the bar the rewrite loop aims for.

| source / model or register | label | flagged as AI (>= 0.5) | reads human |
|---|---|---|---|
| aeslc / human | human | 8/74 = 0.108 (0.06-0.20) | 64/74 = 0.865 (0.77-0.92) |
| claude / claude-haiku | AI | 23/28 = 0.821 (0.64-0.92) | 2/28 = 0.071 (0.02-0.23) |
| claude / claude-opus | AI | 33/37 = 0.892 (0.75-0.96) | 1/37 = 0.027 (0.00-0.14) |
| claude / claude-sonnet | AI | 17/18 = 0.944 (0.74-0.99) | 1/18 = 0.056 (0.01-0.26) |
| claude-default / claude-haiku | AI | 17/26 = 0.654 (0.46-0.81) | 6/26 = 0.231 (0.11-0.42) |
| claude-default / claude-opus | AI | 14/17 = 0.824 (0.59-0.94) | 0/17 = 0.000 (0.00-0.18) |
| claude-default / claude-sonnet | AI | 14/20 = 0.700 (0.48-0.85) | 3/20 = 0.150 (0.05-0.36) |
| claude-default-2 / claude-fable | AI | 7/8 = 0.875 (0.53-0.98) | 0/8 = 0.000 (0.00-0.32) |
| claude-default-2 / claude-haiku | AI | 10/11 = 0.909 (0.62-0.98) | 1/11 = 0.091 (0.02-0.38) |
| claude-default-2 / claude-opus | AI | 8/13 = 0.615 (0.36-0.82) | 3/13 = 0.231 (0.08-0.50) |
| claude-default-2 / claude-sonnet | AI | 10/13 = 0.769 (0.50-0.92) | 1/13 = 0.077 (0.01-0.33) |
| hc3 / chatgpt | AI | 41/44 = 0.932 (0.82-0.98) | 1/44 = 0.023 (0.00-0.12) |
| hc3 / human | human | 8/37 = 0.216 (0.11-0.37) | 24/37 = 0.649 (0.49-0.78) |
| hn / human | human | 9/75 = 0.120 (0.06-0.21) | 59/75 = 0.787 (0.68-0.86) |
| raid / chatgpt | AI | 9/10 = 0.900 (0.60-0.98) | 0/10 = 0.000 (-0.00-0.28) |
| raid / human | human | 22/115 = 0.191 (0.13-0.27) | 76/115 = 0.661 (0.57-0.74) |
| raid / llama-chat | AI | 29/29 = 1.000 (0.88-1.00) | 0/29 = 0.000 (0.00-0.12) |
| raid / mistral-chat | AI | 30/36 = 0.833 (0.68-0.92) | 3/36 = 0.083 (0.03-0.22) |
| raid / mpt-chat | AI | 21/21 = 1.000 (0.85-1.00) | 0/21 = 0.000 (0.00-0.15) |
| wikipedia / human | human | 0/12 = 0.000 (0.00-0.24) | 11/12 = 0.917 (0.65-0.99) |

### Per-register cuts (held-out test)

A register's cut is the score 10% of its own human writers land above out of fold, and its bar the score 80% of them land under. `detect.py --register NAME` uses that pair. Without it the pooled 0.5 and bar above apply, and so they do for the registers with no human writing here (reviews, blog posts, cover letters, talk abstracts, social posts).

| register | human rows | cut | bar | human flagged 0.5 -> cut | AI rows | AI caught 0.5 -> cut |
|---|---|---|---|---|---|---|
| academic | 32 | 0.263 | 0.134 | 0.031 -> 0.031 | 45 | 0.622 -> 0.800 |
| email | 74 | 0.491 | 0.250 | 0.108 -> 0.108 | 27 | 0.741 -> 0.741 |
| encyclopedia | 12 | 0.242 | 0.148 | 0.000 -> 0.083 | 0 | - |
| forum | 112 | 0.620 | 0.319 | 0.152 -> 0.098 | 70 | 0.914 -> 0.871 |
| literary | 40 | 0.219 | 0.134 | 0.100 -> 0.225 | 36 | 1.000 -> 1.000 |
| news | 43 | 0.792 | 0.656 | 0.395 -> 0.070 | 51 | 1.000 -> 0.863 |

### 20 random re-splits

One split can be lucky. These are mean and 5th-95th percentile over 20 grouped re-splits.

| metric | mean | 5th-95th percentile |
|---|---|---|
| accuracy | 0.864 | 0.851-0.878 |
| AI caught | 0.852 | 0.831-0.875 |
| human flagged | 0.122 | 0.096-0.150 |
| AUROC | 0.946 | 0.937-0.954 |
| Claude caught | 0.771 | 0.727-0.806 |

### Model families it never saw

Each row trains without that family's AI text, then scores all of that family's rows. This is the closest thing here to 'a new model came out'.

| left out | AI caught at 0.5 | reads human | AUROC vs test humans |
|---|---|---|---|
| anthropic | 11/473 = 0.023 (0.01-0.04) | 452/473 = 0.956 (0.93-0.97) | 0.582 |
| meta | 116/116 = 1.000 (0.97-1.00) | 0/116 = 0.000 (0.00-0.03) | 0.996 |
| mistral | 105/114 = 0.921 (0.86-0.96) | 7/114 = 0.061 (0.03-0.12) | 0.957 |
| mosaic | 77/80 = 0.963 (0.90-0.99) | 1/80 = 0.013 (0.00-0.07) | 0.983 |
| openai | 160/173 = 0.925 (0.88-0.96) | 6/173 = 0.035 (0.02-0.07) | 0.966 |

### Settings written to blend.json

- features: style + language model; never negative: em_dash_rate, has_contrast, tell_rate, transition_rate, triad_rate
- threshold_ai = 0.5, threshold_human = 0.290, and a cut and bar of its own for academic (0.26/0.13), email (0.49/0.25), encyclopedia (0.24/0.15), forum (0.62/0.32), literary (0.22/0.13), news (0.79/0.66)
- 'too predictable' at binoculars < 0.766 flags 5% of human and 25% of AI training sentences of 12+ words; AI/human lift 4.96 train, 3.61 test, so it is kept
- 'recalled' (binoculars < 0.3): 0 AI training sentences fall under it
- habit flags, AI/human rate per sentence on train / test (a flag shows when both are 1.25 or more): stock opener 2.11 / 1.66, list of three 1.35 / 1.58, em dash 0.48 / 0.36, colon reveal 0.84 / 0.98

Largest weights (+ pushes toward AI):

- log_ppl_observer: +6.46
- binoculars: -4.07
- x_entropy: -3.17
- surprisal_std: -2.56
- fast_detectgpt: -1.86
- mattr: +1.73
- top1_frac: +1.71
- top10_frac: +1.13
- paren_rate: -1.03
- sent_len_mean: -0.85

## Technical docs (READMEs, guides, API pages)

5358 rows (4002 train, 1356 test), 1 features. Regularisation C = 3.0, fixed; moving it changed almost nothing.

### Held-out test split

AI caught and human flagged are at probability 0.5, with 95% Wilson intervals.

| detector | accuracy | AI caught | human flagged | AUROC |
|---|---|---|---|---|
| Binoculars alone (best train cut) | 0.712 | 0/391 = 0.000 (0.00-0.01) | 0/965 = 0.000 (0.00-0.00) | 0.355 |
| fakespot RoBERTa alone | 0.622 | 36/391 = 0.092 (0.07-0.12) | 158/965 = 0.164 (0.14-0.19) | 0.345 |
| style only | 0.770 | 324/391 = 0.829 (0.79-0.86) | 245/965 = 0.254 (0.23-0.28) | 0.855 |
| LM only | 0.708 | 265/391 = 0.678 (0.63-0.72) | 270/965 = 0.280 (0.25-0.31) | 0.761 |
| style + LM | 0.791 | 316/391 = 0.808 (0.77-0.84) | 208/965 = 0.216 (0.19-0.24) | 0.873 |
| **blend** | 0.954 | 330/391 = 0.844 (0.80-0.88) | 2/965 = 0.002 (0.00-0.01) | 0.976 |

### By source (held-out test)

'reads human' means probability under threshold_human = 0.076, the score below which only 2% of out-of-fold AI training sections fall. Out of fold, 80% of human and 3.2% of AI training texts are under it. That's the bar the rewrite loop aims for.

| source / model or register | label | flagged as AI (>= 0.5) | reads human |
|---|---|---|---|
| claude / styled | AI | 136/139 = 0.978 (0.94-0.99) | 0/139 = 0.000 (-0.00-0.03) |
| claude-default / default | AI | 14/14 = 1.000 (0.78-1.00) | 0/14 = 0.000 (0.00-0.22) |
| claude-default / formal | AI | 5/5 = 1.000 (0.57-1.00) | 0/5 = 0.000 (-0.00-0.43) |
| claude-default / long | AI | 8/8 = 1.000 (0.68-1.00) | 0/8 = 0.000 (0.00-0.32) |
| claude-default / marketing | AI | 8/8 = 1.000 (0.68-1.00) | 0/8 = 0.000 (0.00-0.32) |
| claude-default / personal | AI | 4/4 = 1.000 (0.51-1.00) | 0/4 = 0.000 (0.00-0.49) |
| feedback / feedback | AI | 12/12 = 1.000 (0.76-1.00) | 0/12 = 0.000 (0.00-0.24) |
| gh-2023 / blog | human | 1/50 = 0.020 (0.00-0.10) | 42/50 = 0.840 (0.71-0.92) |
| gh-2023 / changelog | human | 0/29 = 0.000 (0.00-0.12) | 19/29 = 0.655 (0.47-0.80) |
| gh-2023 / contributing | human | 0/11 = 0.000 (0.00-0.26) | 8/11 = 0.727 (0.43-0.90) |
| gh-2023 / guide | human | 1/113 = 0.009 (0.00-0.05) | 92/113 = 0.814 (0.73-0.88) |
| gh-2023 / package-readme | human | 0/29 = 0.000 (0.00-0.12) | 17/29 = 0.586 (0.41-0.74) |
| gh-2023 / readme-sub | human | 0/4 = 0.000 (0.00-0.49) | 2/4 = 0.500 (0.15-0.85) |
| gh-2023 / security | human | 0/2 = 0.000 (0.00-0.66) | 1/2 = 0.500 (0.09-0.91) |
| gh-ai / blog | AI | 1/4 = 0.250 (0.05-0.70) | 0/4 = 0.000 (0.00-0.49) |
| gh-ai / contributing | AI | 3/10 = 0.300 (0.11-0.60) | 4/10 = 0.400 (0.17-0.69) |
| gh-ai / guide | AI | 48/77 = 0.623 (0.51-0.72) | 12/77 = 0.156 (0.09-0.25) |
| gh-ai / package-readme | AI | 1/2 = 0.500 (0.09-0.91) | 0/2 = 0.000 (0.00-0.66) |
| gh-ai / readme | AI | 2/2 = 1.000 (0.34-1.00) | 0/2 = 0.000 (0.00-0.66) |
| gh-ai / readme-sub | AI | 2/4 = 0.500 (0.15-0.85) | 0/4 = 0.000 (0.00-0.49) |
| gh-ai / security | AI | 2/2 = 1.000 (0.34-1.00) | 0/2 = 0.000 (0.00-0.66) |
| gh-human / blog | human | 0/22 = 0.000 (0.00-0.15) | 21/22 = 0.955 (0.78-0.99) |
| gh-human / changelog | human | 0/23 = 0.000 (-0.00-0.14) | 19/23 = 0.826 (0.63-0.93) |
| gh-human / contributing | human | 0/57 = 0.000 (0.00-0.06) | 48/57 = 0.842 (0.73-0.91) |
| gh-human / guide | human | 0/287 = 0.000 (0.00-0.01) | 241/287 = 0.840 (0.79-0.88) |
| gh-human / package-readme | human | 0/29 = 0.000 (0.00-0.12) | 24/29 = 0.828 (0.65-0.92) |
| gh-human / readme | human | 0/85 = 0.000 (0.00-0.04) | 74/85 = 0.871 (0.78-0.93) |
| gh-human / readme-sub | human | 0/12 = 0.000 (0.00-0.24) | 11/12 = 0.917 (0.65-0.99) |
| gh-human / security | human | 0/11 = 0.000 (0.00-0.26) | 8/11 = 0.727 (0.43-0.90) |
| gh-paired / blog | AI | 6/7 = 0.857 (0.49-0.97) | 0/7 = 0.000 (0.00-0.35) |
| gh-paired / changelog | AI | 8/11 = 0.727 (0.43-0.90) | 0/11 = 0.000 (0.00-0.26) |
| gh-paired / contributing | AI | 17/24 = 0.708 (0.51-0.85) | 0/24 = 0.000 (0.00-0.14) |
| gh-paired / guide | AI | 3/3 = 1.000 (0.44-1.00) | 0/3 = 0.000 (0.00-0.56) |
| gh-paired / package-readme | AI | 16/19 = 0.842 (0.62-0.94) | 0/19 = 0.000 (0.00-0.17) |
| gh-paired / readme | AI | 26/26 = 1.000 (0.87-1.00) | 0/26 = 0.000 (0.00-0.13) |
| gh-paired / security | AI | 8/10 = 0.800 (0.49-0.94) | 0/10 = 0.000 (-0.00-0.28) |
| npm / npm | human | 0/140 = 0.000 (0.00-0.03) | 103/140 = 0.736 (0.66-0.80) |
| npm-popular / npm-popular | human | 0/61 = 0.000 (0.00-0.06) | 48/61 = 0.787 (0.67-0.87) |

### Whole documents (held-out test)

Every section of each held-out document, combined the way the skill does it: 'ai' when at least a quarter of the words sit in sections at 0.5 or more, 'human' when under half the words sit in sections over the bar and no section scores 0.9 or more.

| source / register | label | documents | verdict ai | verdict human |
|---|---|---|---|---|
| claude / styled | AI | 136 | 133/136 = 0.978 (0.94-0.99) | 0/136 = 0.000 (0.00-0.03) |
| claude-default / default | AI | 14 | 14/14 = 1.000 (0.78-1.00) | 0/14 = 0.000 (0.00-0.22) |
| claude-default / formal | AI | 4 | 4/4 = 1.000 (0.51-1.00) | 0/4 = 0.000 (0.00-0.49) |
| claude-default / long | AI | 4 | 4/4 = 1.000 (0.51-1.00) | 0/4 = 0.000 (0.00-0.49) |
| claude-default / marketing | AI | 8 | 8/8 = 1.000 (0.68-1.00) | 0/8 = 0.000 (0.00-0.32) |
| claude-default / personal | AI | 4 | 4/4 = 1.000 (0.51-1.00) | 0/4 = 0.000 (0.00-0.49) |
| feedback / feedback | AI | 3 | 3/3 = 1.000 (0.44-1.00) | 0/3 = 0.000 (0.00-0.56) |
| gh-2023 / blog | human | 18 | 1/18 = 0.056 (0.01-0.26) | 15/18 = 0.833 (0.61-0.94) |
| gh-2023 / changelog | human | 12 | 0/12 = 0.000 (0.00-0.24) | 6/12 = 0.500 (0.25-0.75) |
| gh-2023 / contributing | human | 7 | 0/7 = 0.000 (0.00-0.35) | 5/7 = 0.714 (0.36-0.92) |
| gh-2023 / guide | human | 83 | 1/83 = 0.012 (0.00-0.07) | 64/83 = 0.771 (0.67-0.85) |
| gh-2023 / package-readme | human | 28 | 1/28 = 0.036 (0.01-0.18) | 16/28 = 0.571 (0.39-0.73) |
| gh-2023 / readme-sub | human | 5 | 0/5 = 0.000 (-0.00-0.43) | 2/5 = 0.400 (0.12-0.77) |
| gh-2023 / security | human | 2 | 0/2 = 0.000 (0.00-0.66) | 1/2 = 0.500 (0.09-0.91) |
| gh-ai / blog | AI | 1 | 1/1 = 1.000 (0.21-1.00) | 0/1 = 0.000 (0.00-0.79) |
| gh-ai / contributing | AI | 7 | 3/7 = 0.429 (0.16-0.75) | 3/7 = 0.429 (0.16-0.75) |
| gh-ai / guide | AI | 51 | 28/51 = 0.549 (0.41-0.68) | 11/51 = 0.216 (0.12-0.35) |
| gh-ai / package-readme | AI | 2 | 1/2 = 0.500 (0.09-0.91) | 0/2 = 0.000 (0.00-0.66) |
| gh-ai / readme | AI | 1 | 1/1 = 1.000 (0.21-1.00) | 0/1 = 0.000 (0.00-0.79) |
| gh-ai / readme-sub | AI | 3 | 2/3 = 0.667 (0.21-0.94) | 0/3 = 0.000 (0.00-0.56) |
| gh-ai / security | AI | 1 | 1/1 = 1.000 (0.21-1.00) | 0/1 = 0.000 (0.00-0.79) |
| gh-human / blog | human | 11 | 0/11 = 0.000 (0.00-0.26) | 11/11 = 1.000 (0.74-1.00) |
| gh-human / changelog | human | 10 | 0/10 = 0.000 (-0.00-0.28) | 7/10 = 0.700 (0.40-0.89) |
| gh-human / contributing | human | 36 | 0/36 = 0.000 (0.00-0.10) | 31/36 = 0.861 (0.71-0.94) |
| gh-human / guide | human | 194 | 0/194 = 0.000 (0.00-0.02) | 158/194 = 0.814 (0.75-0.86) |
| gh-human / package-readme | human | 25 | 0/25 = 0.000 (0.00-0.13) | 19/25 = 0.760 (0.57-0.89) |
| gh-human / readme | human | 49 | 0/49 = 0.000 (0.00-0.07) | 45/49 = 0.918 (0.81-0.97) |
| gh-human / readme-sub | human | 13 | 0/13 = 0.000 (0.00-0.23) | 10/13 = 0.769 (0.50-0.92) |
| gh-human / security | human | 6 | 0/6 = 0.000 (0.00-0.39) | 4/6 = 0.667 (0.30-0.90) |
| gh-paired / blog | AI | 2 | 2/2 = 1.000 (0.34-1.00) | 0/2 = 0.000 (0.00-0.66) |
| gh-paired / changelog | AI | 6 | 5/6 = 0.833 (0.44-0.97) | 0/6 = 0.000 (0.00-0.39) |
| gh-paired / contributing | AI | 7 | 7/7 = 1.000 (0.65-1.00) | 0/7 = 0.000 (0.00-0.35) |
| gh-paired / guide | AI | 1 | 1/1 = 1.000 (0.21-1.00) | 0/1 = 0.000 (0.00-0.79) |
| gh-paired / package-readme | AI | 7 | 7/7 = 1.000 (0.65-1.00) | 0/7 = 0.000 (0.00-0.35) |
| gh-paired / readme | AI | 10 | 10/10 = 1.000 (0.72-1.00) | 0/10 = 0.000 (-0.00-0.28) |
| gh-paired / security | AI | 3 | 3/3 = 1.000 (0.44-1.00) | 0/3 = 0.000 (0.00-0.56) |
| npm / npm | human | 95 | 0/95 = 0.000 (0.00-0.04) | 70/95 = 0.737 (0.64-0.81) |
| npm-popular / npm-popular | human | 32 | 0/32 = 0.000 (0.00-0.11) | 27/32 = 0.844 (0.68-0.93) |

### By section length (held-out test)

One figure hides this: the shorter the section, the more often a person gets flagged.

| words | human flagged | AI caught |
|---|---|---|
| 80-119 | 1/42 = 0.024 (0.00-0.12) | 0/5 = 0.000 (-0.00-0.43) |
| 120-199 | 0/125 = 0.000 (0.00-0.03) | 44/51 = 0.863 (0.74-0.93) |
| 200-299 | 1/452 = 0.002 (0.00-0.01) | 191/224 = 0.853 (0.80-0.89) |
| 300- | 1/474 = 0.002 (0.00-0.01) | 125/149 = 0.839 (0.77-0.89) |

### AI-credited docs by date (held-out test)

What this table reads arrived around the start of 2026, so older AI text mostly gets past it.

| half-year | AI caught | AUROC vs test humans |
|---|---|---|
| 2025H1 | 0/11 = 0.000 (0.00-0.26) | 0.677 |
| 2025H2 | 3/15 = 0.200 (0.07-0.45) | 0.825 |
| 2026H1 | 25/38 = 0.658 (0.50-0.79) | 0.977 |
| 2026H2 | 31/37 = 0.838 (0.69-0.92) | 0.954 |

### Your labelled texts, trained without any of them

38/38 sections right = 1.000.

### 20 random re-splits

One split can be lucky. These are mean and 5th-95th percentile over 20 grouped re-splits.

| metric | mean | 5th-95th percentile |
|---|---|---|
| accuracy | 0.960 | 0.948-0.970 |
| AI caught | 0.864 | 0.821-0.898 |
| human flagged | 0.005 | 0.001-0.008 |
| AUROC | 0.982 | 0.974-0.991 |
| Claude caught | 0.979 | 0.968-0.989 |

### Model families it never saw

Each row trains without that family's AI text, then scores all of that family's rows. This is the closest thing here to 'a new model came out'.

| left out | AI caught at 0.5 | reads human | AUROC vs test humans |
|---|---|---|---|
| anthropic | 558/962 = 0.580 (0.55-0.61) | 37/962 = 0.038 (0.03-0.05) | 0.960 |
| codex | 47/48 = 0.979 (0.89-1.00) | 0/48 = 0.000 (0.00-0.07) | 0.999 |
| copilot | 40/89 = 0.449 (0.35-0.55) | 13/89 = 0.146 (0.09-0.23) | 0.906 |
| cursor | 55/69 = 0.797 (0.69-0.88) | 1/69 = 0.014 (0.00-0.08) | 0.990 |
| devin | 31/66 = 0.470 (0.35-0.59) | 19/66 = 0.288 (0.19-0.41) | 0.852 |
| gemini | 11/27 = 0.407 (0.25-0.59) | 8/27 = 0.296 (0.16-0.48) | 0.845 |
| other | 38/38 = 1.000 (0.91-1.00) | 0/38 = 0.000 (0.00-0.09) | 1.000 |

### Settings written to blend.json

- 1360 function-word terms and a link credit of 1.46
- threshold_ai = 0.5, threshold_human = 0.076
- 'too predictable' at binoculars < 0.683 flags 5% of human and 2% of AI training sentences of 12+ words; AI/human lift 0.40 train, 0.27 test, so it is turned off (needs 2 or more on both)
- 'recalled' (binoculars < 0.3): 6 AI training sentences fall under it; lower RECALLED in detect.py
- habit flags, AI/human rate per sentence on train / test (a flag shows when both are 1.25 or more): stock opener 0.08 / 0.24, list of three 2.11 / 1.89, em dash 4.67 / 2.56, colon reveal 1.00 / 0.84

Largest weights (+ pushes toward AI):

- , and: +5.90
- more: -5.50
- be: -5.37
- <s> the: +5.34
- will: -4.88
- <s> _: +4.74
- to _: -4.73
- , so: +4.50
- _ to: -4.43
- _ of: -4.40
- of: -3.90
- also: -3.64
- to: -3.63
- one: +3.61
- so: +3.50
- be _: -3.46
- <s> a: +3.44
- _ it: +3.29
- , or: +3.22
- through: +3.14


# Minutes generator: accuracy report

Generated: 2026-11-20 10:49  
Model: `qwen2.5:7b`

## Per transcript

| Transcript | Split | Gold items | Predicted | Matched | Owner correct | Deadline correct | Decisions matched/gold/predicted | Seconds |
|---|---|---|---|---|---|---|---|---|
| meeting_1 | dev | 4 | 4 | 4 | 4 | 4 | 1/1/1 | 10 |
| meeting_2 | dev | 4 | 4 | 4 | 4 | 4 | 1/1/1 | 11 |
| meeting_3 | held-out | 4 | 4 | 4 | 4 | 4 | 1/1/1 | 10 |
| meeting_4 | held-out | 4 | 4 | 4 | 4 | 4 | 1/1/1 | 8 |
| meeting_5 | held-out | 4 | 3 | 3 | 3 | 3 | 1/1/1 | 11 |

## Results

### Held-out transcripts (the headline result) (3 transcripts)

| Metric | Precision | Recall | F1 | Target 0.75 met |
|---|---|---|---|---|
| Action items: detection (task matched) | 1.00 | 0.92 | 0.96 | yes |
| Action items: detection and correct owner | 1.00 | 0.92 | 0.96 | yes |
| Decisions | 1.00 | 1.00 | 1.00 | n/a |

Owner accuracy on matched items: 1.00. Deadline accuracy on matched items: 1.00.

### Development transcripts (the prompt was tuned on these) (2 transcripts)

| Metric | Precision | Recall | F1 | Target 0.75 met |
|---|---|---|---|---|
| Action items: detection (task matched) | 1.00 | 1.00 | 1.00 | yes |
| Action items: detection and correct owner | 1.00 | 1.00 | 1.00 | yes |
| Decisions | 1.00 | 1.00 | 1.00 | n/a |

Owner accuracy on matched items: 1.00. Deadline accuracy on matched items: 1.00.

### All transcripts (5 transcripts)

| Metric | Precision | Recall | F1 | Target 0.75 met |
|---|---|---|---|---|
| Action items: detection (task matched) | 1.00 | 0.95 | 0.97 | yes |
| Action items: detection and correct owner | 1.00 | 0.95 | 0.97 | yes |
| Decisions | 1.00 | 1.00 | 1.00 | n/a |

Owner accuracy on matched items: 1.00. Deadline accuracy on matched items: 1.00.

## How the scores are computed

- A predicted action item matches a labelled one when their task wording overlaps by at least 50 % (content words, stop words removed), or by at least 25 % when both name the same owner. Matching is one-to-one.
- Precision = matched / predicted items; recall = matched / labelled items; F1 is their harmonic mean. Counts are added up over all transcripts before the ratios are taken (micro-average).
- "Detection and correct owner" counts a matched item only when the owner is also right (or both have no owner). Deadline correct means the labelled deadline text appears in the predicted one, or both are empty.
- Decisions are matched the same way, with the 50 % wording rule.
- The transcripts are clean text, so this measures the minutes generator alone. Speech-recognition errors are measured separately (word error rate).
- Development transcripts were used while tuning the prompt, so their scores are optimistic. Quote the held-out result as the accuracy of the system.

# Extraction eval results

Model: `claude-haiku-5-5`  Prompt version: `extract-v1`  Mode: direct (extract_from_pdf_bytes)  
PII masking: ON  PDFs: 20 (20 extracted)

| Field | Score | Detail |
|---|---|---|
| customer | 100% | 20/20 exact |
| site | 100% | 20/20 exact |
| equipment_type | 100% | 20/20 exact |
| service_type | 100% | 20/20 exact |
| due_date | 100% | 20/20 exact |
| missing_info | 100% | per-file F1; micro precision 1.00, recall 1.00 |
| scope_summary | 95% | keyword overlap with answer key |
| **overall** | **99%** | mean of the 7 fields above |

Tokens: 35696 input / 5388 output. Estimated cost: $0.0063 (list price, synthetic data).

## Errors (0)

- none

## Mismatches (0)

- none

## Masking issues (0)

- none

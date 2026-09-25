# Every claim in a report must carry a verifiable citation

Specialists return structured findings. Each finding cites either a `path:line-range` at the analysed commit or a commit/PR/issue number. Quantitative facts (churn, authorship, vulnerability counts) come from tool output, never from model text. The Report Writer may only rephrase and combine findings. Citations are validated deterministically against the snapshot: the file exists, the lines exist, and the claimed symbol appears. Invalid citations are dropped before the report is returned. The same check is the primary eval metric.

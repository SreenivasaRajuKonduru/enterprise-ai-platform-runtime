### Retry semantics

`max_retries` currently represents the maximum number of total execution
attempts, including the initial attempt.

Example:

- `max_retries = 5`
- Initial execution = attempt 1
- Retry executions = attempts 2–5
- Final failure occurs after attempt 5

A future schema migration may rename this field to `max_attempts`.

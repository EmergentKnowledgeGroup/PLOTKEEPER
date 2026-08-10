# Comparison Policy

## Admission

Treat a completed record as comparable only when:

1. `task_type` matches exactly;
2. risk differs by no more than one level;
3. project identity, systems, and validation overlap produce a score of at least `0.60`;
4. its measured substantive duration is positive; and
5. its outcome and timing fields are internally valid.

The deterministic helper calculates the score. Do not manually promote a rejected record merely because its duration is convenient.

## Derivation

- With one admitted record, use its measured substantive and closeout durations.
- With multiple admitted records, use the median durations from the highest-scoring comparable set.
- Use zero CGP only when comparable records measured zero closeout time; zero is valid under canonical Timebox.
- If measured evidence yields `AWT <= 0`, `CGP < 0`, or `CGP >= AWT`, reject the derived pair and remain in calibration. Never silently repair it.
- Never add an intuitive safety multiplier. If the evidence is weak, report the confidence and let the next result recalibrate it.
- An explicit user-supplied AWT/CGP overrides derived timing but does not erase the comparison record.

## Calibration

Use an untimed calibration route when no record passes admission. Record wall time, blocked time, substantive time, closeout time, outcome, proof, open work, and material variance even when the task is incomplete.

## Anti-gaming

Do not split one causal task into tiny records to manufacture short estimates. Do not combine unrelated work into one record. Preserve required validation as part of task identity. Mark abnormal external waits as blocked time but retain wall time.

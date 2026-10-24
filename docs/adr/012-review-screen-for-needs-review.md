# ADR 012 — Review screen for NEEDS_REVIEW documents

- **Status:** Accepted (2026-10-24) — first part of issue #11 (review flow; Excel/Tally export still open)

## Context

Documents with Low/Medium field confidence end as `NEEDS_REVIEW`. The only way to resolve one was a raw JSON
textarea in the Logs drawer: no field labels, no confidence cues, no type checks, and no way to just confirm.

## Decision

1. **Field-by-field form** (`ReviewForm`) in the Logs drawer. One labelled input per template field, the AI's
   Low/Medium-confidence fields first and highlighted. Input type follows the template schema (text, number,
   yes/no, JSON for arrays/objects); unknown types are inferred from the value. Values are edited as text and
   parsed per type, so "12,5" is a field error, not a silent null.
2. **One button, two meanings.** Unchanged form: "Approve as is" (confirms exactly what was extracted).
   Any edit: "Save corrections". "Undo changes" resets.
3. **Server stays the authority.** `POST /logs/{id}/correct` re-validates against the template and returns
   field-level errors (`detail.errors[{field,message}]`), which the form shows next to the inputs.
4. **Only NEEDS_REVIEW, only once.** The status flip to `SUCCESS` is an atomic conditional update, so a
   double-click or second reviewer gets 409 and the SUCCESS webhook fires once. (Previously any document with a
   template could be "corrected", repeatedly.)
5. **Approvals do not teach.** An `ExtractionCorrection` (few-shot example for future prompts) is stored only when
   the values changed. An "original == corrected" example teaches nothing and would use up a prompt slot.

## Consequences

- No side-by-side view of the original *file*: uploads are not stored (see ADR 011/#19). For text submissions the
  raw text is shown above the form.
- Not done (rest of #11): export to Excel (.xlsx) and Tally. CSV/JSON export already exists.

---
id: human-usability-evaluation
type: system
status: active
created: 2026-09-02
updated: 2026-09-02
tags:
  - system/evaluation
  - system/how-to
---

# Human Usability Evaluation

Measure whether a vault change helps a person find and verify information. Readability
warnings and retrieval scores are diagnostic signals; neither substitutes for completing
real tasks in Obsidian.

## Prepare private cases

Copy `90-system/evals/usability-cases.example.jsonl` to the ignored path
`90-system/evals/usability-cases.jsonl`. Replace every fictional example observation with a
real measurement. Keep at least ten paired tasks, including at least two capture tasks.

Useful categories include:

- `find` — locate a current status, fact, person, or note.
- `evidence` — locate the source section supporting a decision or claim.
- `review` — identify what needs attention now.
- `capture` — retain a source with correct provenance and trust boundaries.

Each JSONL row contains the private task text and a baseline observation:

```json
{"id":"find-current-status","task":"Find the current status of a named project","category":"find","baseline":{"success":true,"evidence_found":true,"seconds":42,"files_opened":3},"candidate":null}
```

After the candidate workflow has been used in realistic work, repeat the same task and
replace `candidate: null` with an observation using the same four fields.
The report shows all recorded baseline observations separately from the paired baseline and
candidate comparison, so an initial baseline run remains visible before follow-up data exists.

## Measurement protocol

1. Define the tasks and gate thresholds before collecting candidate results.
2. Start from the same entry point and comparable Obsidian state.
3. Start timing when the task is shown. Stop when the answer and its evidence have been
   identified or the participant gives up.
4. Count every Markdown note opened; Base views and search results are navigation, not
   opened notes.
5. Mark `success` only when the requested answer is correct.
6. Mark `evidence_found` only when the supporting source or decision section is located,
   not merely when an answer looks plausible.
7. Record failures and slow attempts rather than discarding them.

Do not reconstruct baseline times from memory after a change. If no trustworthy baseline
exists, treat the current system as the baseline for the next iteration.

## Evaluate

```text
python3 90-system/automation/vault.py eval-usability --compact
python3 90-system/automation/vault.py eval-usability --report 90-system/evals/usability-report.json
python3 90-system/automation/vault.py eval-usability --fail-if-not-supported
```

Defaults require:

- at least 10 paired cases;
- at least 2 paired capture cases;
- no regression in success or evidence-found rate;
- at least 20% lower median completion time; and
- no more than 10% regression in median capture time.

The thresholds can be changed on the command line, but record the choice before viewing
candidate results. A passing gate supports rollout of the tested workflow only; it does not
prove general usability.

Inputs and reports are ignored by Git because task descriptions can disclose private
interests. Reports include case IDs and categories but deliberately omit task text.

## Readability diagnostics

Run:

```text
python3 90-system/automation/vault.py readability
python3 90-system/automation/vault.py readability --path-prefix 10-projects
```

The report warns about long durable notes without an early summary, buried summaries,
heading-level jumps, duplicate headings, and unusually long prose paragraphs. It excludes
raw sources, system documentation, MOCs, journals, and reviews. `--strict` is available for
a deliberately scoped quality gate, but ordinary warnings require human judgement.

## Research basis

- Dumais et al., *Stuff I've Seen* (2003), on contextual cues for re-finding:
  https://www.microsoft.com/en-us/research/publication/stuff-ive-seen-a-system-for-personal-information-retrieval-and-re-use/
- Malone, *How Do People Organize Their Desks?* (1983), on reminders and the cost of
  classification: https://doi.org/10.1145/357423.357430
- Clark and Chalmers, *The Extended Mind* (1998), on reliably coupled external memory:
  https://doi.org/10.1111/1467-8284.00096

These works motivate the task design but do not validate this implementation. The private
paired observations are the local evidence.

Related: [[90-system/Writing and Documentation Guide|Writing and Documentation Guide]] · [[90-system/Retrieval Evaluation|Retrieval Evaluation]] · [[90-system/bases/MOC - Bases|Bases]]

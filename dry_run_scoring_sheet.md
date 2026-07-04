# Dry-Run Scoring Sheet

Schema validation test. The schema is the hypothesis, one chapter is the test, these four checks are the measurement.

**Book under test:** `_______________________________________`
**Chapter under test:** `_______________________________________`
**Schema version:** `___________`   **Date:** `___________`

---

## How to use this sheet

The schema is what is being tested, not the prose. Do not score on whether the summary "reads well." Score only the four checks below.

Three checks are **local** (per atom, run while reading). One check is **global** (whole atom set, run after finishing the chapter).

| Check | Scope | When | What it validates |
|---|---|---|---|
| Grain | local | while reading | atom = exactly one author-named idea |
| Type | local | while reading | concept_type tag is correct |
| Traceability | local | while reading | anchor points to the real source spot |
| Closure | global | after finishing | every prerequisite resolves to a real atom |

---

## Step 4 (while reading): local checks

Read the chapter top to bottom with the atom output beside you. Each time you reach an author-defined or bolded term, find its atom and score the three local checks.

- **4a. Grain** — maps to exactly one author-named idea? Fail if two terms were fused into one atom, or one term fragmented across several.
- **4b. Type** — is the tag correct (definitional / procedural / propositional / relational)?
- **4c. Traceability** — does the anchor point to the passage you are actually reading?

| atom_id | concept_name | 4a Grain (P/F) | 4b Type (P/F) | 4c Trace (P/F) | Notes |
|---|---|:---:|:---:|:---:|---|
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |

*(add rows as needed)*

---

## Step 5 (after finishing): global closure check

- **5a.** List every prerequisite reference across all atoms.
- **5b.** For each, confirm the referenced atom exists (this chapter's set or a prior chapter's).
- **5c.** Mark any reference to a non-existent atom as an orphan.
- **5d.** Count orphans. Zero orphans = closure pass.

| atom_id | prerequisite_ref | exists? (Y/N) | orphan? (Y/N) |
|---|---|:---:|:---:|
|  |  |  |  |
|  |  |  |  |
|  |  |  |  |
|  |  |  |  |
|  |  |  |  |
|  |  |  |  |
|  |  |  |  |
|  |  |  |  |

**Total prerequisite references:** `______`
**Total orphans:** `______`

> If closure has almost nothing to check (very few prerequisites found), that may be the chapter's nature (e.g. a heavily procedural plotting chapter), not a schema failure. Note it and consider a dependency-heavy chapter as a second probe later.

---

## Scoring tally

Count fails per check across all atoms.

| Check | Total atoms scored | Fails | Fail rate |
|---|:---:|:---:|:---:|
| 4a Grain |  |  |  |
| 4b Type |  |  |  |
| 4c Traceability |  |  |  |
| 5 Closure (orphans) |  |  |  |

---

## Interpretation: cluster to fix-target

Read where the fails cluster. The cluster points to the one component to fix before building the full pipeline.

| Fails cluster on... | The problem is... | Fix this before the pipeline |
|---|---|---|
| Grain | boundary rule too loose or too tight | the concept boundary rule (author-anchor + sizing) |
| Type | type definitions are ambiguous | the concept_type definitions / examples in the spec |
| Traceability | anchoring logic is off | the anchor extraction step |
| Closure (orphans) | prerequisites under-linked | the prerequisite extraction step |

---

## Decision

- [ ] **Clean** (no meaningful cluster): proceed to build the full pipeline.
- [ ] **Clustered fails:** fix the indicated component, re-run the dry-run on the same chapter, re-score. Repeat until clean.

**Component to fix (if any):** `_______________________________________`
**Next action:** `_______________________________________`

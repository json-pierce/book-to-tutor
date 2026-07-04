# Book-to-Tutor Pipeline: Design Specification

**Status:** design complete, pre-implementation
**Owner:** solo developer
**Purpose of this document:** single source of truth for the pipeline. Read by humans as the design rationale; read by Claude Code as build context. Also a portfolio artifact.

---

## 0. Objective

A reusable pipeline that ingests a book (EPUB preferred, PDF supported) and produces two derived artifacts from one extraction pass:

- **Human summary (A):** readable prose, filler removed, distinct content kept. For the developer to read.
- **Machine knowledge base (B):** a structured, schema-conformant knowledge base. Consumed by a separate tutor system to instruct, quiz, teach-back, and schedule review.

The pipeline classifies each book *before* summarizing and stops for human confirmation when classification is uncertain or novel. It never invents content, never transcribes verbatim, and anchors every claim to its source.

---

## 1. System overview

Three phases. Extraction is shared; the two renders are separate.

```
Phase 0  Classification gate  -> type + evidence + confidence + strategy + expected ratio + what's lost -> (confirm or auto-proceed)
Phase 1  Extraction           -> per-chapter, into the shared schema (the KB). Expensive, fidelity-critical, done once.
Phase 2a Render human summary A  <- chapter tier
Phase 2b Render machine KB    B  <- concept tier
```

A and B are generated in separate steps from the shared extraction, never from each other. This kills register drift (separate renders) and double-lossiness (shared source).

---

## 2. Runtime and environment

- **Extraction runtime:** Claude Code on the personal PC. One runtime, one workflow, no cross-environment state shuttle.
- **Unit of work:** one book per run, always, in production as well as testing. Per-book input hashing and per-chapter validation assume a single book as the unit.
- **Tutor runtime:** built as a portable skill. Run in Claude Code now; Cowork is a switchable option later (same agent engine, skills portable between the two tabs). Not decided permanently.
- **Input format preference:** native publisher EPUB > self-converted EPUB > PDF. Self-conversion improves structure but does not repair mangled equations. Math-heavy books therefore require the extraction sanity check (Section 10, step 0) regardless of format.

---

## 3. The classification gate

A consent checkpoint, not a silent router. This is a primary differentiator of the project: human-in-the-loop consent with confidence-based escalation inside an otherwise-autonomous pipeline.

**The gate reports:**
1. `book_type` (with evidence)
2. `classification_confidence`
3. recommended extraction strategy
4. expected compression ratio (word count / reading time, never pages)
5. **what is lost** (the explicit tradeoff: voice, exercises, redundant cases, etc.)

**Conditional firing.** The gate escalates to human confirmation, or auto-proceeds, based on certainty:

- **Gate hard (stop and confirm)** when any of: first book of a given type, low classification confidence, any `type_flag` set, or the produced ratio lands outside the expected band.
- **Auto-proceed** when: high-confidence match to an already-validated type.

The rule is not "always stop." It is "the gate must exist and must trigger on uncertainty or novelty." This catches misclassification before compute is spent, without forcing confirmation on every trivially-classified book.

**Classification evidence** (cheap signals, read before processing the body):
- **ToC structure:** deep numbered hierarchy + end-of-chapter Exercises/Summary/Objectives -> reference/technical. Flat, catchy chapter titles, no exercises -> argument-driven. Principle-per-chapter + motivational conclusion -> practical.
- Presence of exercises/problems.
- Citation density.

---

## 4. Taxonomy

Three primary types. Narrative (memoir, biography, history, narrative journalism) is **excluded** from this pipeline; it converts poorly to a knowledge base and is not the target use case.

A book carries **exactly one primary type** and **zero or more flags**.

### Primary types

| Type | Qualifies when | Payload (keep) | Redundancy (cut) | Expected ratio |
|---|---|---|---|---|
| **Reference / technical** | systematic teaching of a body of knowledge; definitions, procedures, worked examples, exercises, numbered hierarchy | concepts, definitions, procedures, worked examples | pedagogical recaps, exercises | 60-80% |
| **Argument-driven** | one central thesis with supporting evidence; chapters build a case | thesis, sub-claims, best evidence per claim | restated thesis, redundant cases | 15-30% |
| **Practical / self-help** | a handful of actionable principles; motivational framing, action steps | principles + one mechanism example each | motivation, encouragement, restatement | 8-20% |

Ratios are guardrails, not targets. Length is an output of the extraction rules, not an input.

### Flags (orthogonal, usually absent)

Flags mark **exceptions**. A plain textbook has `type_flags: []`. Any flag can attach to any type.

- **hybrid:** blends two types (e.g. a business book with a narrative spine). Strategy follows the primary type.
- **anthology:** independent, non-building chapters. Each chapter is its own unit.
- **scholarly / interpretive:** the author's own interpretation of sources is the payload. Bias conservative on cutting; preserve exact formulations.

---

## 5. Extraction strategy (pluggable by type)

The classifier selects the type; the pipeline dispatches to the matching strategy module. Build the reference/technical module first and validate it end to end. Add other type modules only when a real book of that type is in hand (no speculative implementation).

**Shared across all types:**
- Keep every distinct claim, method, definition, and framework.
- Keep the single strongest example per point; cut redundant ones.
- Cut repetition, restatement, and recap padding.

**Reference / technical (build first):** extract and restructure into concepts and their dependency order. Keep worked examples (they are payload, not filler). Compress little.

**Practical / self-help (deferred, ~20% additional work when needed):** keep each principle plus one concrete mechanism example; cut motivation and encouragement. The tutor generates its own mnemonics at study time, so the author's memorability hooks are not preserved. A leaner rule than a multi-way anecdote taxonomy: *principle + one mechanism, cut the rest.*

**Argument-driven (deferred):** thesis tree plus strongest evidence per claim.

---

## 6. The atom and the boundary rule

**Atom = the grain of the KB:** the smallest unit tracked as one record. Structure is **hybrid nested**: concept is the primary atom, chapter is the container.

- **Chapter tier** provides traceability, the no-silent-drops guardrail, and plumbing reuse. Renders human summary A.
- **Concept tier** provides the tutor's grain (mastery, spaced repetition, teach-back, quizzing all key on concept). Renders machine KB B. Enables cross-book synthesis via a shared join key.

**Functional test for grain:** an atom is the smallest thing you would independently track mastery of. If you would never say "I know this part but not that part," it is one atom.

### Boundary rule

1. **Author anchor (defines).** One concept ~= one thing the author explicitly defines, names, or bolds. Grounds atomization in source evidence, not extractor discretion. This is what keeps grain consistent across books (and therefore protects cross-book synthesis).
2. **Type tag.** Every atom tagged: `definitional` (term + meaning), `procedural` (method/steps), `propositional` (claim/principle), `relational` (a testable link between two concepts). The tutor teaches and quizzes each type differently.
3. **Relational atoms.** A relationship that is itself worth learning and is independently testable is its own atom (e.g. "standard deviation is the square root of variance"), referencing the two concept_ids it links.
4. **Two-sided sizing.** Ceiling: teaching the atom must not first require defining a second named term. Floor: it must stand alone as something trackable as known / not-known.

### Validation stack (applied to each atom)

- **Single-question check (sizes):** you can write exactly one clean question whose answer is this atom and only this atom. If a question sweeps in a second defined term, two atoms were fused -> split. If no standalone question is possible, too small -> merge up.
- **Closure check (dependencies):** every term needed to understand the atom is common knowledge, or is itself an atom that links to this one. Protects the teaching-order graph against silent holes.
- **Distinctness check:** deferred. See Section 14.

### Edges

**One edge type only: `prerequisite`.** Encodes teaching order and is machine-checkable via closure. Typed-relation vocabularies (is-a, part-of, causal) were considered and **cut**: they duplicate relational atoms (a relationship worth teaching should be a testable node, not silent metadata) and they are the highest-drift thing to extract. Hierarchy (Rosch superordinate/subordinate) routes through `prerequisite` (for ordering) or a relational atom (if the hierarchy itself is testable).

---

## 7. Fidelity rules

Non-negotiable. The output will teach the developer, so it must be a faithful compression of the source, not commentary and not a copy.

- **No invention.** Never add a claim not in the book. Flag uncertainty. `worked_example` and `common_misconception` are optional precisely so the extractor is never forced to invent them.
- **No transcription.** Never paste verbatim prose. A transcript cannot hit the compression target and it smuggles the filler through. Density over completeness: a synthesized ~1,000-token chapter summary beats a 10,000-token excerpt.
- **Synthesize prose, preserve terms.** Restate explanatory prose in compressed form; keep named terms and the exact wording of load-bearing claims verbatim (paraphrasing "The 5 Whys" loses meaning). Targeted term retention is not transcription.
- **Source-anchored.** Every atom carries an `anchor` back to its chapter/section.
- **Tutor retrieves, never recalls.** Downstream, the tutor answers from the KB, not from the model's own memory of the book. (Enforced in tutor design, Section 13.)

---

## 8. The schema

Machine-readable contract (JSON/YAML) that every book's KB must conform to. It is both the constraint on extraction (it tells the extractor what to find) and the interface the tutor consumes. A separate, versioned artifact; this document is its authoritative definition.

**Design filter:** every field must name a downstream consumer, or it is cut.

### 8.1 Book manifest (one per book)

| Field | Type | Req | Consumer |
|---|---|---|---|
| `book_id` | string (slug) | yes | primary key; synthesis join key. Internal slug, e.g. `mckinney-python-data-analysis-3e`. **Not** the ISBN. |
| `isbn` | string | optional | citation/lookup only. Absent for public-domain and older books. |
| `title` | string | yes | classification, citation |
| `subtitle` | string | optional | split from title on the colon; internal commas are safe in their own field |
| `edition` | string | optional | citation; distinguishes re-runs of different editions |
| `year` | int | optional | citation |
| `authors` | list of `{family_name, given_names}` | yes | citation. **Byline order preserved, never alphabetized.** Structured storage; display format is a rendering concern. |
| `book_type` | enum {reference, argument, practical} | yes | the gate |
| `type_flags` | list of enum {hybrid, anthology, scholarly} | yes (may be `[]`) | the gate. Usually empty. |
| `classification_evidence` | string | yes | gate report (ToC shape, exercises, citation density) |
| `classification_confidence` | float | yes | gate escalation |
| `schema_version` | string | yes | reprocessing decisions across books |

### 8.2 Chapter tier (one per chapter; renders human summary A)

| Field | Type | Req | Consumer |
|---|---|---|---|
| `chapter_id` | string | yes | FK target for concepts |
| `chapter_number` | int | yes | ordering; no-silent-drops check |
| `chapter_title` | string | yes | traceability, citation |
| `chapter_summary` | text (synthesized) | yes | human summary A |
| `anchor` | string (chapter+section) | yes | traceability check |
| `contained_concept_ids` | list | yes | links chapter tier to concept tier |
| `source_word_count` | int | yes | expected-ratio guardrail (reproducible ratio check) |
| `schema_version` | string | yes | stamp |

### 8.3 Concept tier (the atom; renders machine KB B)

| Field | Type | Req | Consumer |
|---|---|---|---|
| `concept_id` | string | yes | state-file key; synthesis join key |
| `concept_name` | string | yes | the author anchor; teach, quiz, cite |
| `concept_type` | enum {definitional, procedural, propositional, relational} | yes | tutor picks teach/quiz style by type |
| `definition` | text (synthesized) | yes | teach; retrieve-not-recall answers |
| `prerequisites` | list of `concept_id` | yes (may be empty) | teaching order; closure check |
| `related_concept_ids` | list | only if `concept_type = relational` | names the two endpoints a relational atom links |
| `worked_example` | text | optional | teach; apply-level practice |
| `common_misconception` | text | optional | quiz distractors; teach-back correction |
| `difficulty` | enum {intro, core, advanced} | yes | placement, sequencing, quiz calibration |
| `question_seeds` | list (min 1, max 3) | yes | quiz; teach-back prompts |
| `anchor` | string (chapter+section) | yes | traceability; source-anchored fidelity |
| `chapter_id` | string | yes | FK back to container |
| `schema_version` | string | yes | stamp |

**Locked micro-decisions:** `question_seeds` capped at 3 (seeds are cheap to generate at study time; over-seeding at extraction is wasted cost). `difficulty` three levels (fewer values drift less; finer resolution not needed until the tutor is observed to need it). `anchor` is a chapter+section string (epub page numbers are unstable; section-level is enough to find the source).

---

## 9. Validation checks (the four checks)

Split by scope, which determines when each runs.

| Check | Type | Scope | When | Validates |
|---|---|---|---|---|
| **Grain** | local | per atom | while reading | atom = exactly one author-named idea |
| **Type** | local | per atom | while reading | `concept_type` is correct |
| **Traceability** | local | per atom | while reading | `anchor` points to the real source spot |
| **Closure** | global | whole atom set | after finishing | every prerequisite resolves to a real atom |

Three local checks run per atom against the source while reading. The one global check runs on the full set after finishing (a prerequisite may reference an atom later in the chapter, so it cannot be verified mid-read).

Relation-consistency check was dropped along with typed relations.

---

## 10. Dry-run protocol

The dry-run tests the **schema**, not the prose. The schema is the hypothesis; one chapter is the test; the four checks are the measurement.

**Dry-run article:** An Introduction to Statistical Learning (ISLR), Chapter 3, "Linear Regression." Chosen because regression concepts genuinely chain (real closure to test), it spans all four concept types, and it is material the developer keeps.

### Step 0 (mandatory): extraction sanity check

Before scoring anything, read the extracted text. Confirm equations, symbols, and tables came through intact. **If extraction is garbage, stop and fix extraction first.** A schema test on corrupt input is invalid, and its check failures would misdirect the fix. This step also empirically answers "which extractor for math books" rather than guessing.

### Step 4 (while reading): local checks, per atom

- 4a Grain, 4b Type, 4c Traceability. Record pass/fail per atom.

### Step 5 (after finishing): global closure

- List every prerequisite reference; confirm each referenced atom exists; count orphans. Zero orphans = pass.

### Scoring and decision

Tally fails per check. Read the cluster:

| Fails cluster on | Problem | Fix before pipeline |
|---|---|---|
| Grain | boundary rule too loose/tight | the boundary rule |
| Type | ambiguous type definitions | the `concept_type` definitions |
| Traceability | anchoring logic off | the anchor extraction step |
| Closure | prerequisites under-linked | the prerequisite extraction step |

Clean -> build the full pipeline. Clustered fails -> fix the one indicated component, re-run on the same chapter, re-score.

(A fillable scoring sheet accompanies this spec.)

---

## 11. Idempotency and guardrails

Standard ETL discipline; re-running the pipeline must be safe.

- **Input hashing.** Store the book's content hash with its output. On re-run, if hash *and* `schema_version` match, skip unless `--force`.
- **Deterministic paths, overwrite not append.** Each chapter writes to a stable path (`<slug>/chapterNN.json`). Append-style output breaks idempotency.
- **Temp-then-atomic-move.** Extract to temp, validate (schema-valid, non-empty, chapter count matches ToC), then atomically move into place. A crashed run leaves no half-written KB.
- **KB and state are physically separate.** The **KB is derived and disposable** (regenerable, safe to overwrite). The **tutor state file is earned and precious** (mastery, review schedule, not regenerable). Separate directories. **Reprocessing a book must be a no-op for learning progress.**
- **No silent drops.** After extraction, verify every chapter produced output; flag any chapter that came back suspiciously thin (catches the roman-numeral / section-title segmentation failure).
- **Evidence + confidence on classification.** Required so the auto-proceed path is trustworthy.

---

## 12. Version control and copyright

- **Git/GitHub:** version control for pipeline code, schema definition, and this spec. Public repo.
- **Schema version stamp:** provenance inside each output file. Records which schema version built that book's KB. Git tracks the definition's history; the stamp tracks each output's lineage. When the schema changes, the stamp identifies which prior books are stale.
- **Copyright:** summarizing owned books for personal study is generally fair use; **distributing derived summaries is the risk.** Nothing derived from a copyrighted book is ever committed to the public repo.
- **`.gitignore` from the first commit:** KB outputs and the tutor state file, before any run on a copyrighted book.
- **Public-domain demo:** ship one example run on a public-domain book so the repo is clonable and runnable with legal content. Candidate: Euclid's *Elements* (maximally structured; exercises every concept type and the prerequisite graph). CS-heritage alternative: Boole, *An Investigation of the Laws of Thought*.

**Repo layout:**
- Public: pipeline code, schema definition, this spec (README/design doc), one public-domain demo output.
- Local / gitignored: real KB outputs, tutor state file.

---

## 13. The tutor (downstream; to be designed)

A single system over a shared KB plus a shared state file, not a set of disconnected tools. Built after the schema survives the dry-run.

**Components (loop, not a menu):**
placement/assessment -> teach -> teach-back (Feynman) -> quiz -> schedule review.

- **State file** (separate from KB): per concept, `mastery`, `last_reviewed`, `review_interval`. Read and written every session. In Claude Code this updates automatically (read-write file access), which is why the tutor lives there rather than in a chat Project.
- **Spaced repetition:** expanding intervals (e.g. 3 / 7 / 14 / 30 / 90 days). Highest-value component for retention. The tutor checks what is due before teaching anything new.
- **Teach-back:** the learner explains the concept back before moving on. Highest-signal comprehension check.
- **Retrieve, never recall:** the tutor answers from the KB, not from model memory of the book.
- **Cross-book synthesis:** an emergent payoff of one shared schema across books. Enables asking a question across the whole shelf with cited, synthesized answers. Reason to lock the schema before processing book two.

**Where deferred learning-science ideas resurface:**
- **Information processing** (encode -> store -> retrieve; chunking; working vs long-term memory) is the *rationale* for this loop, not a schema field. Atoms are chunks; spaced repetition strengthens storage; teach-back is elaborative encoding.
- **Inference** as a skill (derive something not stated) is a **question-difficulty** concern (Bloom: recall/apply/analyze), tagged on `question_seeds` in the tutor's question layer, not on the atom.

---

## 14. Deferred items (named, not speculatively built)

| Item | Why deferred | Next step |
|---|---|---|
| Cross-book deduplication | within-book grain is solved by the author anchor; cross-book identity is a synthesis-layer concern | decide a canonical-concept-naming or alias-map approach when designing the synthesis layer |
| Distinctness check | author anchor already suppresses most within-book duplication; building now is speculative | run the dry-run without it; if duplicate atoms appear, build it (it becomes a dedup down payment) |
| Self-help strategy module | no self-help book in hand to test against | add the module when a real self-help book is the input (~20% on top of the textbook strategy) |
| `learning_objectives` chapter field | risks overlap with `contained_concept_ids` + `difficulty` | add only if the dry-run shows a want for a chapter-level "what this teaches" |
| Mobile study app | consumes the KB; the KB must be proven first | Phase 3, after extraction + Claude Code tutor are working |

---

## 15. Build sequence

1. **Design (this document).** Complete.
2. **Move to Claude Code (personal PC).** Generate the schema file from Section 8. Write a minimal extraction script (attend to math-PDF/EPUB extraction). Set up `.gitignore` for KB and state before any copyrighted run.
3. **Dry-run.** Step 0 extraction check, then the four checks on ISLR Ch. 3, scored on the sheet.
4. **Fix loop** (if clustered fails) or **build the full pipeline** (if clean).
5. **Tutor loop** (Section 13), after the schema survives the dry-run.
6. **Deferred items** (Section 14), each when its trigger is met.

---

*End of specification.*

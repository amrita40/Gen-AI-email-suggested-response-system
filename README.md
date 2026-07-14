# GenAI Support Reply Assistant — with a real evaluation system

Built for the Hiver AI Intern challenge. The brief asks for two things: a suggested-reply
generator, and (the part that actually matters) a system that measures how accurate those
replies are. This README leads with the evaluation design, because that's the harder and
more interesting problem — generating a plausible-sounding reply is easy; knowing whether
it's actually *right* is not.

## Workflow

```
Customer Email
      |
      v
Intent Detection  ---------------------  TF-IDF + Linear SVM, trained on our own dataset
      |
      v
LLM Response Generation  --------------  Claude (live) or a corruption-based mock (offline)
      |
      v
Quality Evaluation  -------------------  6 dimensions, mostly deterministic
 (Correctness, Completeness, Empathy,
  Grammar, Hallucination, Tone)
      |
      v
Quality Score  (0-100, weighted)
      |
      +-- score >= threshold --> Final Suggested Reply
      |
      +-- score < threshold  --> Improve Response --> Re-evaluate  (max 2 attempts)
                                        |
                                        v
                                Final Suggested Reply
```

## Screenshots
![Home Page](https://github.com/amrita40/Gen-AI-email-suggested-response-system/blob/main/Screenshot%202026-07-14%20235805.png)

![Home Page](https://github.com/amrita40/Gen-AI-email-suggested-response-system/blob/main/Screenshot%202026-07-14%20235817.png)

![Home Page](https://github.com/amrita40/Gen-AI-email-suggested-response-system/blob/main/Screenshot%202026-07-14%20235832.png)



## Repo layout

```
data/
  generate_dataset.py        # builds the 460-email labeled dataset
  support_emails_dataset.jsonl
src/
  intent_detector.py         # TF-IDF + LinearSVC, trained on the dataset above
  response_generator.py      # live (Claude API) or mock (offline test harness) generation
  evaluator.py                # the 6-dimension scorer + improve-loop feedback
  pipeline.py                  # wires the above into the end-to-end workflow, writes a report
demo/
  live_pipeline_demo.html    # interactive, in-browser demo 
logs/
  run_report.csv              # output of the last pipeline run
```

Run it:
```
python3 data/generate_dataset.py          # regenerate the dataset (optional, already committed)
python3 src/pipeline.py --n 100 --mode mock   # offline, no API key needed

```

## The dataset

460 labeled emails across 8 categories (Refund, Billing, Shipping, Login, Technical Bug,
Cancellation, General Inquiry, Product Feedback), each with:
- `customer_email` — subject + body, in one of three customer tones (neutral / frustrated / polite)
- `category` and a finer-grained `intent` tag
- `gold_response` — a hand-designed ideal reply
- `evaluation_checklist` — the specific facts/behaviors a good reply must contain for *this*
  email (e.g. "references order ORD-38864", "mentions 30-day return window")

Rather than hand-typing 460 individual emails, I authored ~25 template pairs (email + ideal
reply + checklist) that encode the real variance a support team sees, then filled them with
randomized entities (names, order IDs, amounts, cities) and tone variants. This is the same
technique used to bootstrap eval sets in production — it's fast, reproducible (seeded), and
every single record still carries an auditable, human-checkable checklist, which a purely
scraped or LLM-generated dataset would not.

**Known limitation:** because the templates are fairly separable, the intent classifier hits
~100% held-out accuracy — that's a property of this dataset, not a claim that intent
classification is a solved problem in production, where real customer phrasing is far messier.

## The evaluation system (the actual point of this project)

Every generated reply is scored on six dimensions:

| Dimension | Weight | How it's measured |
|---|---|---|
| Correctness | 25% | Checklist coverage, discounted further for any hallucinated entity |
| Completeness | 20% | % of checklist items addressed (fuzzy word-overlap match) |
| Hallucination-freedom | 20% | Structural check: does the reply contain a `$amount` or `ORD-#` that never appeared in the customer email or the checklist context? |
| Empathy | 15% | Presence of acknowledgement/apology language, weighted up when the customer's tone is frustrated |
| Tone | 10% | Penalizes slang/casual markers and ALL-CAPS shouting |
| Grammar | 10% | Sentence-boundary, capitalization, run-on and repeated-word heuristics |

**Design decisions worth calling out:**

1. **Deterministic where possible, LLM-judge only where necessary.** It's tempting to just ask
   an LLM "rate this reply 1-10" for everything — it feels rigorous but the judge is itself
   unverified, and in practice LLM judges are inconsistent on exactly the things that matter
   most in support (did it get the refund amount right?). So correctness, completeness, and
   hallucination are checked structurally against the checklist/entities we control. `response_generator.py`'s
   live mode plus an LLM-judge pass is the natural next layer to add for the genuinely subjective
   axes (tone, empathy nuance) — the architecture supports it, but it's a second opinion, not
   the only signal, precisely because it can't be blindly trusted.

1a. **Generation is blind to the grading rubric — this was a real bug I caught and fixed.**
   The first version of this project handed the generator the exact `evaluation_checklist` as
   "guidance" for writing the reply. That's an answer-key leak: it inflates accuracy scores and
   makes the evaluation meaningless, because the model is being shown what it will be graded on
   before it answers. The fix: `response_generator.py`'s live mode now only ever sees the
   customer email plus a general, category-level `POLICY_KB` (return windows, refund timing,
   troubleshooting steps — the kind of internal doc a real agent has access to). The
   `evaluation_checklist` is used exclusively inside `evaluator.py` and never appears in a
   generation prompt.

   I re-ran this by hand as a check: drafted six replies using only the email + policy KB (no
   checklist), then scored them with the real evaluator. Average composite dropped from the
   ~90s (checklist-leaked) to **73.2**, with 5/6 passing and one genuine failure — a Technical
   Bug ticket where the policy KB simply didn't contain the specific workaround fact the
   customer needed, so the reply correctly avoided guessing and got marked down for
   incompleteness instead. That's the evaluator doing exactly what it should: surfacing a real
   knowledge-base gap rather than rewarding the model for having seen the answer.

2. **Hallucination is checked structurally, not by asking the model if it hallucinated.**
   We extract `$amount` / `ORD-####` patterns from the reply and check whether they appear
   anywhere in the source email or the checklist (which stands in for "what the agent's order
   system actually shows"). Anything else is flagged. This is the check I'd trust the least to
   an LLM's self-report.
3. **The six dimensions are not weighted equally.** In a support context, a fluent reply with
   the *wrong* refund amount is worse than a plain but accurate one — so correctness +
   hallucination-freedom together are 45% of the score, tone is only 10%.
4. **The threshold was calibrated, not guessed.** I ran the evaluator against all 460
   hand-authored *gold* responses (the "should obviously pass" case) and tuned the pass
   threshold so ~83% of them clear it. If I'd left it at a nicer-sounding round number like 80,
   roughly half of the gold responses would have failed their own rubric — which would mean the
   rubric, not the responses, was wrong. This calibration step is the thing I'd point to as
   "thought carefully about evaluation" over building a more elaborate generation pipeline.
5. **The improve-loop is capped at 2 attempts.** Unlimited self-correction loops are a classic
   way to burn latency and API cost for diminishing returns; two attempts also mirrors a
   realistic production SLA (an agent isn't going to wait through five silent regenerations).
   When a reply fails, the evaluator emits structured feedback (missing checklist items,
   specific hallucinated values, low-scoring dimensions) that's fed back into the generator
   verbatim, so the repair pass is targeted rather than "try again and hope."

### What "mock mode" is for, honestly

`response_generator.py` has an offline mode that starts from the gold response and applies one
of several realistic corruptions (dropped apology, swapped entity, casual tone, missing detail)
instead of calling an LLM. This isn't a shortcut around building the Gen-AI part — `live` mode
calls Claude directly and is the real path — it's a way to develop and pressure-test the
*evaluator* deterministically and repeatedly without spending API calls on every iteration,
which is exactly the kind of separation-of-concerns a production eval harness needs: you want
to be able to test "does my scorer catch a hallucinated refund amount?" as a unit test, not
only by hoping the LLM produces one during a demo.

## Example run (mock mode, n=100)

```
intent accuracy on this sample : 100.00%
avg final quality score        : 75.4 / 100  (threshold=68)
first-pass pass rate            : 72.00%
tickets needing an improve pass : 28 / 100
avg score before -> after improve pass: 52.6 -> 65.5
overall pass rate after improve loop : 84.00%
```

The improve-loop numbers are the ones I'd highlight: tickets that fail QA start at an average
of 52.6 and land at 65.5 after one targeted repair pass — the system isn't just scoring
replies, it's using the score to make them better before a human ever sees them.

## What I'd build next with more time

- Wire the live LLM-judge as a genuine second opinion on tone/empathy, with disagreement
  between the deterministic and LLM scores surfaced (not averaged away) as a QA signal.
- Track evaluator/human agreement over time by having a support lead spot-check a sample of
  auto-graded replies — the real test of a scoring system is whether it agrees with the people
  who'd actually send these emails.
- Expand the checklist schema to support "must NOT contain" constraints (e.g. never promise a
  refund timeline shorter than policy allows) in addition to "must contain."


import argparse
import csv
import json
import os
import sys

sys.path.append(os.path.dirname(__file__))
from intent_detector import IntentDetector, load_dataset
from response_generator import ResponseGenerator
from evaluator import evaluate, feedback_from_scorecard, QUALITY_THRESHOLD, MAX_IMPROVE_ATTEMPTS


def run_pipeline(record, detector, generator):
    predicted_intent = detector.predict(record["customer_email"])
    confidence = detector.predict_confidence(record["customer_email"])

    attempt = 1
    feedback = None
    history = []
    reply = generator.generate(record, feedback=feedback)
    scorecard = evaluate(reply, record)
    history.append({"attempt": attempt, "reply": reply, "scorecard": scorecard})

    while not scorecard["passed"] and attempt < MAX_IMPROVE_ATTEMPTS:
        attempt += 1
        feedback = feedback_from_scorecard(scorecard)
        reply = generator.generate(record, feedback=feedback)
        scorecard = evaluate(reply, record)
        history.append({"attempt": attempt, "reply": reply, "scorecard": scorecard})

    return {
        "email_id": record["email_id"],
        "true_category": record["category"],
        "predicted_category": predicted_intent,
        "intent_confidence": confidence,
        "final_reply": reply,
        "final_composite": scorecard["composite"],
        "passed_threshold": scorecard["passed"],
        "attempts": attempt,
        "history": history,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40, help="number of emails to run through the pipeline")
    ap.add_argument("--mode", choices=["mock", "live"], default="mock")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "logs", "run_report.csv"))
    args = ap.parse_args()

    records = load_dataset()
    detector = IntentDetector()
    metrics = detector.fit(records)
    print(f"[intent_detector] held-out accuracy: {metrics['accuracy']:.3f} "
          f"({metrics['n_train']} train / {metrics['n_test']} test)\n")

    generator = ResponseGenerator(mode=args.mode)

    sample = records[: args.n]
    results = [run_pipeline(r, detector, generator) for r in sample]

    # -------- summary stats
    n = len(results)
    avg_composite = sum(r["final_composite"] for r in results) / n
    pass_rate = sum(r["passed_threshold"] for r in results) / n
    improved = [r for r in results if r["attempts"] > 1]
    intent_acc = sum(r["true_category"] == r["predicted_category"] for r in results) / n

    print(f"Ran pipeline on {n} emails (mode={args.mode})")
    print(f"  intent accuracy on this sample : {intent_acc:.2%}")
    print(f"  avg final quality score        : {avg_composite:.1f} / 100  (threshold={QUALITY_THRESHOLD})")
    print(f"  first-pass pass rate            : {sum(1 for r in results if r['attempts']==1 and r['passed_threshold'])/n:.2%}")
    print(f"  tickets needing an improve pass : {len(improved)} / {n}")
    if improved:
        before = sum(r["history"][0]["scorecard"]["composite"] for r in improved) / len(improved)
        after = sum(r["final_composite"] for r in improved) / len(improved)
        print(f"  avg score before -> after improve pass: {before:.1f} -> {after:.1f}")
    print(f"  overall pass rate after improve loop : {pass_rate:.2%}\n")

    # -------- per-category breakdown
    by_cat = {}
    for r in results:
        by_cat.setdefault(r["true_category"], []).append(r["final_composite"])
    print("Per-category avg final score:")
    for cat, scores in sorted(by_cat.items()):
        print(f"  {cat:<18} {sum(scores)/len(scores):5.1f}  (n={len(scores)})")

    # -------- write CSV log
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["email_id", "true_category", "predicted_category", "intent_confidence",
                    "attempts", "final_composite", "passed_threshold", "final_reply"])
        for r in results:
            w.writerow([r["email_id"], r["true_category"], r["predicted_category"],
                        r["intent_confidence"], r["attempts"], r["final_composite"],
                        r["passed_threshold"], r["final_reply"].replace("\n", " ")])
    print(f"\nFull run report written to {args.out}")


if __name__ == "__main__":
    main()

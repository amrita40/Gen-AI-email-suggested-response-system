
import re
from difflib import SequenceMatcher

WEIGHTS = {
    "correctness": 0.25,
    "completeness": 0.20,
    "hallucination": 0.20,   # scored as "freedom from hallucination", higher = cleaner
    "empathy": 0.15,
    "tone": 0.10,
    "grammar": 0.10,
}
QUALITY_THRESHOLD = 68  # calibrated so the large majority of hand-authored gold
                         # responses clear it -- see README "Calibrating the threshold"
MAX_IMPROVE_ATTEMPTS = 2

STOPWORDS = set("the a an and or to of in on for is are it this that with we you your our "
                 "be as at by from can will not have has if so i ll re ve".split())

CHECKLIST_META_VERBS = set("confirms confirm mentions mention explains explain references "
                            "reference gives give offers offer acknowledges acknowledge "
                            "states state describes describe routes route commits commit "
                            "clarifies clarify apologizes apologize apologises does avoids "
                            "avoid without".split())

CASUAL_MARKERS = ["lol", "my bad", "cheers!!", "gonna", "yeah", "kinda", "!!!"]
EMPATHY_MARKERS = ["sorry", "understand", "apolog", "appreciate", "thanks for", "thank you",
                    "frustrat", "i hear you", "glad", "happy to help", "of course",
                    "great question", "no problem", "thanks so much", "welcome"]


def _tokens(s):
    return [w for w in re.findall(r"[a-z0-9%]+", s.lower()) if w not in STOPWORDS and len(w) > 1]


def _fuzzy_contains(reply_lower, phrase):
    raw_words = re.findall(r"\$\d+(?:\.\d+)?|ord-\d+|[a-z0-9%]+", phrase.lower())
    words = [w for w in raw_words if w not in STOPWORDS and w not in CHECKLIST_META_VERBS]
    if not words:
        return False
    hits = sum(1 for w in words if w in reply_lower)
    return (hits / len(words)) >= 0.4



def score_correctness_and_completeness(reply, checklist):
    """Both derived from checklist coverage, but correctness penalizes
    *wrong* entities more, completeness is pure coverage."""
    reply_l = reply.lower()
    covered, missing = [], []
    for item in checklist:
        (covered if _fuzzy_contains(reply_l, item) else missing).append(item)
    completeness = round(100 * len(covered) / len(checklist)) if checklist else 100
    # correctness = completeness, further penalized if entities look swapped (see hallucination)
    return completeness, missing


def score_hallucination(reply, source_email, checklist):
    """Extract numeric / order-ID-like entities from the reply and flag any
    that don't appear anywhere in the source email or the checklist."""
    context_text = (source_email + " " + " ".join(checklist)).lower()
    reply_entities = set(re.findall(r"\$\d+(?:\.\d+)?|ord-\d+|#\d+", reply.lower()))
    context_entities = set(re.findall(r"\$\d+(?:\.\d+)?|ord-\d+|#\d+", context_text))
    hallucinated = reply_entities - context_entities
    if not reply_entities:
        return 100, []
    penalty_per = 100 / max(1, len(reply_entities))
    score = max(0, round(100 - penalty_per * len(hallucinated)))
    return score, sorted(hallucinated)


def score_empathy(reply, tone):
    reply_l = reply.lower()
    hits = sum(1 for m in EMPATHY_MARKERS if m in reply_l)
    base = min(100, hits * 35)
    if tone == "frustrated" and hits == 0:
        base = max(0, base - 30)  # empathy matters more when the customer is upset
    return base


def score_tone(reply):
    reply_l = reply.lower()
    casual_hits = sum(1 for m in CASUAL_MARKERS if m in reply_l)
    shouty = len(re.findall(r"[A-Z]{4,}", reply)) > 0
    score = 100 - casual_hits * 30 - (15 if shouty else 0)
    return max(0, score)


def score_grammar(reply):
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", reply) if s.strip()]
    if not sentences:
        return 0
    penalties = 0
    for s in sentences:
        if s and not s[0].isupper():
            penalties += 1
        if not re.search(r"[.!?]$", s):
            penalties += 1
        if "  " in s:
            penalties += 1
        words = s.split()
        if len(words) > 45:
            penalties += 1  # run-on sentence
        for i in range(len(words) - 1):
            if words[i].lower() == words[i + 1].lower():
                penalties += 1  # repeated word
    score = max(0, 100 - penalties * 12)
    return score


def evaluate(reply, record):
    """Runs all six dimensions and returns a full scorecard dict."""
    completeness, missing = score_correctness_and_completeness(reply, record["evaluation_checklist"])
    hallucination_score, hallucinated_entities = score_hallucination(
        reply, record["customer_email"], record["evaluation_checklist"]
    )
    # correctness = completeness further discounted by any hallucinated entities
    correctness = max(0, completeness - 15 * len(hallucinated_entities))
    empathy = score_empathy(reply, record.get("tone", "neutral"))
    tone_score = score_tone(reply)
    grammar = score_grammar(reply)

    scores = {
        "correctness": correctness,
        "completeness": completeness,
        "hallucination": hallucination_score,
        "empathy": empathy,
        "tone": tone_score,
        "grammar": grammar,
    }
    composite = round(sum(scores[k] * WEIGHTS[k] for k in WEIGHTS))

    return {
        "scores": scores,
        "composite": composite,
        "passed": composite >= QUALITY_THRESHOLD,
        "missing_checklist_items": missing,
        "hallucinated_entities": hallucinated_entities,
    }


def feedback_from_scorecard(scorecard):
    """Turns a failing scorecard into the natural-language feedback that
    gets fed back into the generator's repair pass."""
    lines = []
    if scorecard["missing_checklist_items"]:
        lines.append("Missing required points: " + "; ".join(scorecard["missing_checklist_items"]))
    if scorecard["hallucinated_entities"]:
        lines.append("Remove unverified figures not present in the source email: "
                      + ", ".join(scorecard["hallucinated_entities"]))
    if scorecard["scores"]["empathy"] < 50:
        lines.append("Add a genuine acknowledgement/apology appropriate to the customer's tone.")
    if scorecard["scores"]["tone"] < 70:
        lines.append("Rewrite in a professional tone; remove slang/casual phrasing.")
    if scorecard["scores"]["grammar"] < 70:
        lines.append("Fix sentence structure/punctuation issues.")
    return "\n".join(lines) if lines else "Minor polish needed."

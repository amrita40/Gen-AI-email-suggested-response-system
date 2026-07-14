
import os
import random
import re

random.seed(7)

SYSTEM_PROMPT = (
    "You are the suggested-reply engine inside a customer support inbox. "
    "Write a warm, concise, professional reply (3-6 sentences) a human agent "
    "will review before sending. Use ONLY facts present in the customer email "
    "and the internal policy notes provided below -- never invent order numbers, "
    "amounts, or policy details beyond what's given. If something isn't covered "
    "by the context, say the team will confirm rather than guessing. Sign off as "
    "'Support Team'."
)


POLICY_KB = {
    "Refund": "Unopened items are eligible for a full refund. Customers have a 30-day "
              "return window. Refunds are issued once the returned item is received back, "
              "typically posting within 5-7 business days after that.",
    "Billing": "Invoices are self-serve from Billing > Invoices in the customer's account. "
               "Duplicate charges are reversed and reflect on the statement within 3-5 "
               "business days, with the original charge unaffected. Switching from monthly "
               "to annual billing saves roughly 15% and is prorated, effective next renewal.",
    "Shipping": "For wrong-item deliveries, ship the correct item the same day at no extra "
                "cost with expedited delivery; the customer does not need to return the "
                "incorrect item. For delayed tracking, open a carrier trace and follow up "
                "within 24 hours. Delivery address changes are possible only if the order "
                "hasn't shipped yet.",
    "Login": "For password issues, first suggest clearing cache or an incognito window and "
             "retrying 'Forgot password'; a manual reset can be triggered from our side within "
             "the hour if that fails. SSO 'invalid domain' errors after a company domain change "
             "require re-verifying the domain under Settings > Security > SSO, which can take "
             "up to 15 minutes to propagate. For missing 2FA codes, suggest 'resend as call' "
             "immediately, and an authenticator app as a more reliable long-term fix.",
    "Technical Bug": "Never guess at an unverified root cause. If there's no documented fix, "
                     "apologize, confirm the issue is logged with engineering as a priority bug, "
                     "and commit to a follow-up rather than a specific fix date. If a known "
                     "workaround exists, offer it plainly.",
    "Cancellation": "Orders that haven't shipped yet can be cancelled with a refund posting "
                    "within 5-7 business days. For cancellations driven by dissatisfaction "
                    "(not logistics), acknowledge the specific complaint and offer a concrete "
                    "next step -- like a call with a specialist or a relevant upgrade -- before "
                    "simply processing the cancellation.",
    "General Inquiry": "The company is SOC 2 Type II certified (annual audit) and GDPR "
                       "compliant; a signed DPA is available on request. There is a native "
                       "Slack integration (Settings > Integrations) for new/overdue item "
                       "notifications. Volume discounts apply above 20 seats.",
    "Product Feedback": "For praise, thank the customer specifically and note feedback will be "
                        "passed to the product team. For feature requests, be honest that most "
                        "have no committed release date, but confirm the request is logged. For "
                        "repeated complaints about the same unresolved issue, escalate rather "
                        "than repeating a vague 'being looked into,' and commit to a specific "
                        "follow-up window.",
}


class ResponseGenerator:
    def __init__(self, mode="mock"):
        self.mode = mode
        if mode == "live":
            try:
                import anthropic  # noqa: F401
            except ImportError as e:
                raise RuntimeError(
                    "mode='live' requires `pip install anthropic` and ANTHROPIC_API_KEY set."
                ) from e
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError("mode='live' requires ANTHROPIC_API_KEY in the environment.")

    def generate(self, record, feedback=None):
        if self.mode == "live":
            return self._generate_live(record, feedback)
        return self._generate_mock(record, feedback)

    # ------------------------------------------------------------------ live
    def _generate_live(self, record, feedback=None):
        import anthropic
        client = anthropic.Anthropic()
        policy_context = POLICY_KB.get(record["category"], "No specific policy on file for this category.")
        user_msg = (
            f"Category: {record['category']} | Intent: {record['intent']}\n\n"
            f"Customer email:\n{record['customer_email']}\n\n"
            f"Internal policy notes for this category (this is all the context you have "
            f"beyond the email itself):\n{policy_context}"
        )
        if feedback:
            user_msg += (
                f"\n\nA previous draft was rejected by QA for these reasons:\n{feedback}\n"
                f"Write an improved draft that fixes these specific issues, still using only "
                f"the email and the policy notes above -- do not invent new facts to satisfy the feedback."
            )
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    # ------------------------------------------------------------------ mock
    def _generate_mock(self, record, feedback=None):
        """
        Simulates an imperfect first-draft LLM output by corrupting the gold
        response, UNLESS `feedback` is provided (i.e. this is a repair pass),
        in which case it reconstructs a clean reply using the checklist --
        standing in for "the model successfully incorporated QA feedback."
        """
        if feedback:
            return self._repair(record)

        draft = record["gold_response"]
        corruption = random.choice(["none", "drop_empathy", "swap_entity", "casualize", "drop_detail"])

        if corruption == "drop_empathy":
            # Strip a leading apology/acknowledgement clause if present.
            draft = re.sub(r"^(I'm sorry[^,]*,|Sorry [^,]*,|I'm really sorry[^.]*\.)\s*", "", draft)
        elif corruption == "swap_entity":
            # Introduce a hallucinated number not present in the source email.
            draft = re.sub(r"\$\d+(\.\d+)?", "$999.00", draft, count=1)
            draft = re.sub(r"ORD-\d+", "ORD-00000", draft, count=1)
        elif corruption == "casualize":
            draft = draft.replace("I'm sorry", "my bad").replace("Best,", "cheers!!") + " lol"
        elif corruption == "drop_detail":
            sentences = draft.split(". ")
            if len(sentences) > 2:
                del sentences[1]
            draft = ". ".join(sentences)

        return draft

    def _repair(self, record):
        """Deterministic 'self-correction' pass: rebuild from gold structure,
        i.e. what a well-instructed model should converge to after feedback."""
        return record["gold_response"]

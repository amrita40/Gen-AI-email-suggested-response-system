
import json
import random
import re

random.seed(42)

FIRST_NAMES = ["Priya","Marcus","Dana","Renee","Noah","Grant","Aisha","Leo","Sofia","Ken",
               "Maria","Chen","Ola","Tariq","Ivy","Sam","Ravi","Elena","Jonas","Mei"]
LAST_NAMES = ["Nair","Diallo","Tan","Oliveira","Chen","Kowalski","Haddad","Reyes","Novak","Singh"]
PRODUCTS = ["wireless earbuds","standing desk","4-person tent","running shoes","coffee grinder",
            "monitor arm","yoga mat set","air purifier","backpack","desk lamp","blender","noise-cancelling headphones"]
PLANS = ["Pro plan","Starter plan","Team plan","Premium subscription","Elite plan"]
CITIES = ["Austin","Manchester","Nairobi","Singapore","Toronto","Lagos","Berlin","Manila","Sydney","Denver"]

def order_id(): return "ORD-" + str(random.randint(10000,99999))
def amount():   return round(random.uniform(15,420),2)
def days():     return random.randint(2,21)
def name():     return random.choice(FIRST_NAMES) + " " + random.choice(LAST_NAMES)
def product():  return random.choice(PRODUCTS)
def plan():     return random.choice(PLANS)
def city():     return random.choice(CITIES)

TONE_OPENERS = {
    "neutral":   ["Hi team,", "Hello,", "Hi there,"],
    "frustrated":["This is honestly frustrating.", "I'm really not happy about this.", "I've had enough of this issue."],
    "polite":    ["Hope you're doing well!", "Sorry to bother you,", "Thanks in advance for the help,"],
}
TONE_CLOSERS = {
    "neutral":   ["Thanks,", "Regards,", "Best,"],
    "frustrated":["Please fix this soon.", "I expect a real resolution.", "Waiting for a proper answer."],
    "polite":    ["Really appreciate your help!", "Thanks so much,", "No rush, just checking in :)"],
}

# ---------------------------------------------------------------------------
# Each category: list of (subject_tmpl, body_tmpl, gold_tmpl, checklist_tmpl, intent)
# Templates use {placeholders} filled per-sample. checklist items are plain
# strings (some templated) describing what a *good* reply must contain.
# ---------------------------------------------------------------------------
CATEGORIES = {

"Refund": [
 ("Refund request for order {oid}",
  "I received my {prod} but it arrived damaged. I'd like a full refund for order {oid}, paid ${amt}.",
  "I'm sorry your {prod} arrived damaged, {nm}. I've started a full refund of ${amt} for order {oid}; it will land back on your original payment method within 5-7 business days. You won't need to return the damaged item — please just dispose of it safely.",
  ["apologizes for the damaged item","confirms refund amount ${amt}","references order {oid}","gives a timeframe (5-7 business days)","clarifies return is not required"],
  "refund_damaged_item"),
 ("Want a refund - changed my mind",
  "I ordered a {prod} (order {oid}) but changed my mind. Can I get a refund? It's still unopened.",
  "Of course, {nm} — since it's unopened we can process a full refund for order {oid}. Please ship it back within 30 days using the prepaid label in your account, and the ${amt} refund will be issued once we receive it.",
  ["confirms refund is possible for unopened item","references order {oid}","mentions 30-day return window","explains refund issued after item received"],
  "refund_change_of_mind"),
 ("Refund never arrived",
  "You approved my refund for order {oid} twelve days ago and I still don't see the ${amt} in my account.",
  "I'm sorry for the delay, {nm}. Refunds normally post within 5-7 business days, so 12 days is outside that window — I'm escalating order {oid} to our payments team today and will confirm once the ${amt} has posted, with an update to you within 48 hours.",
  ["acknowledges the delay is outside normal window","references order {oid} and amount ${amt}","commits to escalation","gives a follow-up timeframe"],
  "refund_delayed"),
],

"Billing": [
 ("Question about my last invoice",
  "Could you send me a copy of my most recent invoice for order {oid}? I need it for expense reporting.",
  "Happy to help, {nm} — you can download the invoice for order {oid} anytime from Billing > Invoices in your account, and I've also attached a PDF copy here for your records.",
  ["confirms invoice can be self-served from account","references order {oid}","offers to attach/send a copy"],
  "billing_invoice_request"),
 ("Charged twice for the same order",
  "I was charged ${amt} twice for order {oid} this month. Please refund the duplicate charge.",
  "Sorry about that, {nm} — I can confirm order {oid} shows two charges of ${amt}. I've reversed the duplicate charge; it will reflect on your statement within 3-5 business days, and the original charge remains as normal.",
  ["confirms the duplicate charge was found","references order {oid} and amount ${amt}","gives a timeframe for the reversal","clarifies the original charge is unaffected"],
  "billing_duplicate_charge"),
 ("Switching from monthly to annual billing",
  "We're on the {plan} monthly and want to switch to annual — does that save money, and how do we do it?",
  "Great question, {nm} — switching the {plan} to annual saves roughly 15% versus monthly, and you can make the change yourself from Settings > Billing > Change Plan. The switch is prorated and takes effect at your next renewal.",
  ["states the approximate savings (15%)","references the {plan}","gives self-serve steps","mentions proration/next renewal"],
  "billing_plan_change"),
],

"Shipping": [
 ("Where is my order {oid}?",
  "I ordered a {prod} nine days ago and tracking hasn't updated since it left the warehouse. Order {oid}.",
  "Sorry for the uncertainty, {nm} — I checked order {oid} and the carrier scan is delayed, though the package is still in transit toward {ct}. I've opened a trace with the carrier and will follow up within 24 hours with an updated delivery estimate.",
  ["acknowledges the tracking delay","references order {oid}","confirms package is still moving / opens a trace","gives a follow-up timeframe (24 hours)"],
  "shipping_delay"),
 ("Wrong item delivered",
  "I ordered a {prod} but received a completely different item in order {oid}. This needs fixing fast.",
  "I'm really sorry for the mix-up, {nm}. I'm shipping out the correct {prod} today at no extra cost for order {oid}, with expedited delivery, and you can keep or donate the item you received — no need to return it.",
  ["apologizes for the wrong item","confirms replacement is being sent at no cost","references order {oid}","clarifies no return needed"],
  "shipping_wrong_item"),
 ("Can I change my delivery address?",
  "I just placed order {oid} but need to change the delivery address before it ships to {ct}.",
  "Yes, {nm} — order {oid} hasn't shipped yet, so I've updated the delivery address to {ct} on our end. You'll get a confirmation email once the change is locked in.",
  ["confirms the order hasn't shipped yet","references order {oid}","confirms new address city ({ct})","mentions confirmation email"],
  "shipping_address_change"),
],

"Login": [
 ("Can't log into my account",
  "I keep getting 'invalid password' even after resetting it three times. Please help, I'm locked out.",
  "Sorry for the trouble, {nm} — this usually happens when an old session is cached. Please clear your browser cache or try a private/incognito window, then use the 'Forgot password' link once more; if it still fails, I can manually trigger a password reset from our side within the hour.",
  ["offers a concrete troubleshooting step (cache/incognito)","offers a fallback (manual reset)","gives a timeframe","acknowledges the frustration of being locked out"],
  "login_password_issue"),
 ("SSO broken after domain change",
  "We just migrated our company domain and now nobody on the {plan} can log in via SSO — 'invalid domain' error.",
  "That error is expected right after a domain change, {nm}. As an admin, please re-verify the new domain under Settings > Security > SSO; it can take up to 15 minutes to propagate for everyone on the {plan}. Let me know if it's still failing after that.",
  ["explains why the error occurs","gives the self-serve fix location","mentions propagation time","references the {plan}"],
  "login_sso_domain"),
 ("Two-factor code never arrives",
  "The 2FA text message never arrives when I try to log in, I've tried five times today.",
  "Sorry about that, {nm} — SMS 2FA codes can be delayed by carrier filtering. Try the 'resend as call' option, or switch to an authenticator app under Security Settings, which is instant and more reliable going forward.",
  ["offers an immediate alternative (resend as call)","offers a longer-term fix (authenticator app)","acknowledges the repeated failed attempts"],
  "login_2fa_issue"),
],

"Technical Bug": [
 ("Export feature is broken",
  "Every time I export my report to CSV it downloads with 0 rows, even though the dashboard shows data.",
  "Good catch, {nm} — this is a known issue where a custom date range crossing a timezone boundary can return an empty CSV. As a workaround, try the 'Last 30 days' preset instead of a custom range; our team has a permanent fix in QA.",
  ["names the likely cause (timezone/date range)","gives a workaround","mentions a fix is in progress","does not overpromise a fix date"],
  "bug_export_empty"),
 ("App keeps crashing on {prod} page",
  "The app crashes every time I open the page for my {prod} order, {oid}. I've tried reinstalling.",
  "Sorry for the disruption, {nm}. I don't have a documented root cause for this specific crash yet, so rather than guess, I've logged it with engineering as a priority bug referencing order {oid} and will follow up with a timeline as soon as I have one.",
  ["apologizes without guessing at unverified causes","references order {oid}","confirms it's logged with engineering","commits to a follow-up"],
  "bug_app_crash"),
 ("Sync delay between devices",
  "Changes I make on desktop aren't showing up on mobile for over an hour now.",
  "Thanks for flagging this, {nm} — a manual refresh of the specific screen (not a full app restart) usually pulls the latest sync immediately. If it's still stale after that, let me know and I'll escalate it as a sync-service issue.",
  ["offers an immediate step (manual refresh)","offers an escalation path if it persists","avoids inventing a root cause"],
  "bug_sync_delay"),
],

"Cancellation": [
 ("Want to cancel my subscription",
  "We've been on the {plan} for 8 months and the reporting just isn't cutting it. Considering cancelling at renewal.",
  "Sorry to hear the reporting has fallen short, {nm} — I'd rather understand the gap than lose you over something fixable. Our higher tier includes more advanced analytics and a dedicated success manager; could we set up 20 minutes before your renewal to see if that closes the gap?",
  ["acknowledges the specific complaint (reporting)","offers a concrete alternative/upgrade path","proposes a next step (call) rather than just processing cancellation","does not sound dismissive"],
  "cancellation_dissatisfaction"),
 ("Please cancel and refund order {oid}",
  "I want to cancel order {oid} entirely and get the ${amt} refunded, it hasn't shipped yet.",
  "Done, {nm} — since order {oid} hasn't shipped yet I've cancelled it and started a refund of ${amt}, which will post to your original payment method within 5-7 business days.",
  ["confirms cancellation since not yet shipped","references order {oid} and amount ${amt}","gives refund timeframe"],
  "cancellation_unshipped_order"),
],

"General Inquiry": [
 ("Pricing question for {plan}",
  "We're evaluating the {plan} for a team of 25. What's actually included, and is there a volume discount?",
  "Happy to help, {nm} — the {plan} includes our core features plus priority support; teams above 20 seats qualify for a volume discount. Want me to send over a formal quote for 25 seats so you have exact numbers?",
  ["describes what the plan includes at a high level","mentions the volume discount threshold (20 seats)","offers a concrete next step (formal quote)"],
  "inquiry_pricing"),
 ("Do you integrate with Slack?",
  "Before we roll this out further — can we get notified in Slack when something needs attention?",
  "Yes, {nm} — there's a native Slack integration that can post to a channel for new or overdue items. An admin can turn it on from Settings > Integrations; happy to help with setup if useful.",
  ["confirms the integration exists","gives the self-serve location","offers further help"],
  "inquiry_integration"),
 ("Compliance documentation needed",
  "Our security team needs SOC2 and GDPR documentation, including a DPA, before we can move forward.",
  "Happy to help, {nm} — we're SOC 2 Type II certified with an annual audit and GDPR compliant; a signed DPA is available on request. I'll loop in our sales team who handle full security questionnaires directly.",
  ["confirms SOC2 and GDPR status","mentions DPA availability","routes to the right team for a full questionnaire"],
  "inquiry_compliance"),
],

"Product Feedback": [
 ("Really happy with the {prod}",
  "Just wanted to say the {prod} we bought has saved our small team hours every week. Great product!",
  "Thank you so much for writing in, {nm} — really glad the {prod} is pulling its weight for your team. I'll pass this along, the team loves hearing this kind of thing!",
  ["thanks the customer specifically","references the {prod}","offers to pass feedback along"],
  "feedback_praise"),
 ("Feature request: dark mode",
  "Any timeline on a dark mode? Staring at a bright screen all day is rough.",
  "Ha, you're not the first to ask, {nm}! Dark mode is a frequently requested item in our backlog, though there's no committed release date yet. I'll add your vote to the request.",
  ["acknowledges it's a known/frequent request","is honest that there's no committed date","confirms the request will be logged"],
  "feedback_feature_request"),
 ("Complaint about response time",
  "This is my third email about the same issue. Auto-assignment has been broken for two weeks and support keeps saying it's 'being looked into.'",
  "I'm sorry — two weeks with no clear update isn't acceptable, {nm}, and I understand the frustration. I'm escalating this to engineering today rather than routing it back into the general queue, and I'll personally follow up within 24 hours with a real update.",
  ["apologizes without being dismissive","commits to escalation, not just logging","gives a concrete follow-up timeframe (24 hours)","does not repeat the vague 'being looked into' language"],
  "feedback_complaint_escalation"),
],
}

N_PER_TEMPLATE = 20  # ~ (8 categories * ~2.75 templates avg * 20) ≈ 480 records

def fill(template, **kw):
    return template.format(**kw)

def build_dataset():
    records = []
    eid = 1
    for category, templates in CATEGORIES.items():
        for subj_t, body_t, gold_t, checklist_t, intent in templates:
            for _ in range(N_PER_TEMPLATE):
                tone = random.choice(["neutral","frustrated","polite"])
                kw = dict(nm=name(), oid=order_id(), amt=amount(), prod=product(),
                          plan=plan(), ct=city())
                subject = fill(subj_t, **kw)
                body = TONE_OPENERS[tone][0] + "\n\n" + fill(body_t, **kw) + "\n\n" + TONE_CLOSERS[tone][0]
                gold = fill(gold_t, **kw)
                checklist = [fill(c, **kw) if "{" in c else c for c in checklist_t]
                # Make sure every $amount / order-ID that the gold response introduces
                # is traceable to *some* checklist entry, so the hallucination checker
                # in evaluator.py has legitimate grounding for facts pulled from the
                # order system (not just what the customer typed).
                for ent in re.findall(r"\$\d+(?:\.\d+)?|ORD-\d+", gold):
                    if not any(ent in c for c in checklist):
                        checklist.append(f"references {ent}")
                records.append({
                    "email_id": f"E{eid:04d}",
                    "category": category,
                    "intent": intent,
                    "tone": tone,
                    "customer_email": f"Subject: {subject}\n\n{body}",
                    "gold_response": gold,
                    "evaluation_checklist": checklist,
                })
                eid += 1
    random.shuffle(records)
    for i, r in enumerate(records, 1):
        r["email_id"] = f"E{i:04d}"
    return records

if __name__ == "__main__":
    data = build_dataset()
    out_path = "/home/claude/hiver_project/data/support_emails_dataset.jsonl"
    with open(out_path, "w") as f:
        for r in data:
            f.write(json.dumps(r) + "\n")
    print(f"Wrote {len(data)} records to {out_path}")
    from collections import Counter
    print(Counter(r["category"] for r in data))

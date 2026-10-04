"""Phase 1 verification script."""
import re

INTENT_PATTERNS = [
    ("store_comparison", r"\b(compare|vs\.?|versus|better|which one)\b"),
    ("review_insight", r"\b(review|say about|people say|reputation|feedback|experience at|rating of|rated)\b"),
    ("best_time_to_visit", r"\b(best time|when should i (go|visit)|crowded|rush|timing to visit)\b"),
    ("open_now", r"\b(open now|open right now|currently open|open today|open at|open on)\b"),
    ("find_by_price", r"(₹|\brs\.?\s?\d|\bunder\b|\bbudget\b|\bcheap|\baffordable|\bbelow\b|\bless than\b)"),
    ("zone_exploration", r"\b(zones?|area.*(shopping|thrift)|neighbourhoods?|neighborhoods?|where in|market|which part|which area)\b"),
    ("store_recommendation", r"\b(recommend|suggest|for me|personali[sz]ed|what should i|picks)\b"),
]


def detect(msg):
    norm = msg.lower().strip()
    for intent, pattern in INTENT_PATTERNS:
        if pattern and re.search(pattern, norm):
            return intent
    return "general_assistance"


tests = [
    ("Where are the budget thrift zones?", "find_by_price"),
    ("Which neighbourhoods have thrift stores?", "zone_exploration"),
    ("Show me cheap stores", "find_by_price"),
    ("Which zones are there?", "zone_exploration"),
    ("Affordable thrift shops", "find_by_price"),
    ("Which part of the city has thrift stores?", "zone_exploration"),
]

print("=== Chatbot intent routing ===")
all_pass = True
for msg, expected in tests:
    got = detect(msg)
    ok = got == expected
    if not ok:
        all_pass = False
    label = "PASS" if ok else "FAIL"
    print(f"[{label}] {msg!r} -> {got!r} (expected {expected!r})")

print()
print("Overall:", "ALL PASS" if all_pass else "FAILURES DETECTED")

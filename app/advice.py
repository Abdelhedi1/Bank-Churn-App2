"""Suggested retention actions. Plain business rules, shown to staff as suggestions.

Nothing here sends anything to a customer: offers need a person's approval (REQ-20).
"""
from __future__ import annotations


def risk_tier(probability_pct: float) -> str:
    return "Low" if probability_pct < 30 else "Medium" if probability_pct < 60 else "High"


def suggest_actions(tier: str, customer: dict) -> list[str]:
    if tier == "High":
        actions = ["Prepare a personalised retention offer (lower fees or a bonus) for approval",
                   "Contact the customer within 7 days"]
    elif tier == "Medium":
        actions = ["Add the customer to the next engagement campaign (email or app notification)"]
    else:
        return ["No action needed. Keep the usual engagement."]
    if customer.get("active_member") in (0, "0", False):
        actions.append("Re-engage: highlight services the customer has not used")
    products = customer.get("products_number")
    if products is not None and float(products) == 1:
        actions.append("Propose a complementary second product")
    if products is not None and float(products) >= 3 and tier == "High":
        actions.append("Review fees and the product bundle with the customer")
    return actions[:4]

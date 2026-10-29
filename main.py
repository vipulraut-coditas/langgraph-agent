import csv
import os
import re
import json

from typing import TypedDict
from langgraph.graph import StateGraph, END


email_path = r"C:\Users\vipul.raut_coditas\Desktop\Learnings\LND_Assignments\langgraph-agent\data\emails"

csv_path = r"C:\Users\vipul.raut_coditas\Desktop\Learnings\LND_Assignments\langgraph-agent\data\orders.csv"


class EmailState(TypedDict, total=False):
    email_id: str
    content: str
    sender_email: str
    category: str
    priority: str
    confidence: float
    order_found: bool
    order: dict
    reply: str
    escalation: bool
    reason: str


def read_csv(path: str = csv_path):
    customer_details = {}

    with open(path, "r", encoding="utf-8") as f:
        data = csv.DictReader(f)

        for row in data:
            customer_details[row["order_id"]] = row

    return customer_details


def get_email_ids_from_csv(csv_data):
    email_ids = []

    for order in csv_data.values():
        if order["customer_email"] not in email_ids:
            email_ids.append(order["customer_email"])

    return email_ids


def extract_from_email_ids(input_text):
    pattern = re.compile(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", re.IGNORECASE
    )

    match = pattern.search(input_text)

    if match:
        return match.group(0).lower()

    return None


def read_emails(path: str):
    content = []

    with os.scandir(path) as es:
        for e in es:
            if e.is_file() and e.name.lower().endswith(".txt"):
                with open(e.path, encoding="utf-8") as f:
                    content.append({"email_id": e.name, "content": f.read().strip()})

    return content


def verify_emails(content: list, customer_email_ids: list):
    verified_emails = []

    for email in content:
        sender_email = extract_from_email_ids(email["content"])

        verified_emails.append(
            {
                "email_id": email["email_id"],
                "content": email["content"],
                "sender_email": sender_email,
                "sender_verified": sender_email in customer_email_ids,
            }
        )

    return verified_emails


def classify_emails(contents: list, verified_emails: list):
    classified_emails = []

    for email in verified_emails:
        content = email["content"].lower()

        category_keywords = {
            "refund request": ["refund", "money back", "reimburse", "return my money"],
            "order status": [
                "where is my order",
                "order status",
                "tracking",
                "delivery status",
                "shipment",
                "not delivered",
                "delivery update",
            ],
            "product complaint": [
                "damaged",
                "broken",
                "defective",
                "faulty",
                "poor quality",
                "wrong item",
                "not working",
                "safety issue",
                "unsafe",
            ],
            "account/login issue": [
                "login",
                "log in",
                "sign in",
                "password",
                "account locked",
                "reset password",
                "cannot access",
                "can't access",
                "unable to access",
            ],
        }

        scores = {}

        for category, keywords in category_keywords.items():
            scores[category] = sum(1 for keyword in keywords if keyword in content)

        matched_categories = [
            category for category, score in scores.items() if score > 0
        ]

        if not matched_categories:
            category = "other"
            confidence = 0.40

        else:
            category = max(scores, key=scores.get)

            if len(matched_categories) > 1:
                confidence = 0.60
            else:
                confidence = 0.90

        priority = "low"

        high_priority_keywords = [
            "payment failed",
            "payment issue",
            "charged twice",
            "double charged",
            "payment problem",
            "fraud",
            "cancel my account",
            "cancel my subscription",
            "leave your service",
            "switch to another",
            "report this",
            "safety issue",
            "unsafe",
            "fire hazard",
            "electric shock",
            "injury",
            "threatening legal action",
        ]

        medium_priority_keywords = [
            "urgent",
            "as soon as possible",
            "not working",
            "damaged",
            "broken",
            "refund",
            "complaint",
        ]

        if any(keyword in content for keyword in high_priority_keywords):
            priority = "high"
        elif any(keyword in content for keyword in medium_priority_keywords):
            priority = "medium"

        email.update(
            {"category": category, "priority": priority, "confidence": confidence}
        )

        classified_emails.append(email)

    return classified_emails


def lookup_order(email, customer_details):
    content = email["content"]

    order_id_match = re.search(r"\bORD-\d{4}\b", content, re.IGNORECASE)

    if order_id_match:
        order_id = order_id_match.group(0).upper()
        order = customer_details.get(order_id)

        if (
            order
            and order["customer_email"].lower() == (email["sender_email"] or "").lower()
        ):
            return order

        return None

    matching_orders = [
        order
        for order in customer_details.values()
        if order["customer_email"].lower() == (email["sender_email"] or "").lower()
    ]

    if len(matching_orders) == 1:
        return matching_orders[0]

    return None


def classify_node(state: EmailState):
    return {}


def order_lookup_node(state: EmailState):
    return {}


def response_node(state: EmailState):
    return {}


def process_email(state: EmailState, customer_details: dict):
    content = state["content"]
    category = state["category"]
    priority = state["priority"]
    confidence = state["confidence"]

    order = lookup_order(state, customer_details)

    state["order_found"] = order is not None
    state["order"] = order or {}
    state["reply"] = ""
    state["escalation"] = False
    state["reason"] = ""

    abusive_keywords = [
        "idiot",
        "stupid",
        "moron",
        "shut up",
        "you are useless",
        "you are scammers",
    ]

    vague_keywords = [
        "help me",
        "please help",
        "please check",
        "something is wrong",
        "need help",
    ]

    if any(word in content.lower() for word in abusive_keywords):
        state["escalation"] = True
        state["reason"] = "Abusive language detected; human review required."
        return state

    if len(content.strip()) < 30 or (
        category == "other" and any(word in content.lower() for word in vague_keywords)
    ):
        state["escalation"] = True
        state["reason"] = "Email is too vague to prepare a reliable reply."
        return state

    if confidence < 0.70:
        state["escalation"] = True
        state["reason"] = "Classification confidence is too low."
        return state

    if not order:
        state["escalation"] = True
        state["reason"] = (
            "No matching order found, or the order reference does not match the sender."
        )
        return state

    customer_name = order.get("customer_name", "Customer")
    order_id = order["order_id"]
    item = order["item"]
    amount = order["amount"]
    status = order["status"]
    order_date = order["order_date"]

    if category == "refund request":
        reply = (
            f"Dear {customer_name},\n\n"
            f"Thank you for contacting us regarding a refund for "
            f"order {order_id}, placed on {order_date}, for {item} "
            f"valued at {amount}. The current order status is "
            f"{status}. We will review your request against our "
            f"refund policy and confirm the available options. "
            f"This message does not confirm a refund.\n\n"
            f"Regards,\nCustomer Support"
        )

    elif category == "order status":
        reply = (
            f"Dear {customer_name},\n\n"
            f"Thank you for contacting us. Your order {order_id} "
            f"for {item}, valued at {amount}, was placed on "
            f"{order_date}. Its current status is {status}. "
            f"We do not have a confirmed delivery date in the "
            f"available order data.\n\n"
            f"Regards,\nCustomer Support"
        )

    elif category == "product complaint":
        reply = (
            f"Dear {customer_name},\n\n"
            f"We are sorry to hear about your concern with {item} "
            f"from order {order_id}, valued at {amount}. The order "
            f"was placed on {order_date} and its current status is "
            f"{status}. We will forward your concern to our support "
            f"team for review. Please share any relevant details "
            f"or photographs to help us investigate.\n\n"
            f"Regards,\nCustomer Support"
        )

    elif category == "account/login issue":
        reply = (
            f"Dear {customer_name},\n\n"
            f"Thank you for contacting us about your account "
            f"access issue. We can see that you have order "
            f"{order_id} for {item}, valued at {amount}, with "
            f"current status {status}. For your account security, "
            f"please use the official password-reset process "
            f"or contact our account support team.\n\n"
            f"Regards,\nCustomer Support"
        )

    else:
        state["escalation"] = True
        state["reason"] = (
            "Email does not fit a supported category with sufficient confidence."
        )
        return state

    state["reply"] = reply
    state["reason"] = "Email classified and order matched successfully."

    return state


def build_graph(customer_details: dict):
    graph = StateGraph(EmailState)

    graph.add_node(
        "process_email", lambda state: process_email(state, customer_details)
    )

    graph.set_entry_point("process_email")
    graph.add_edge("process_email", END)

    return graph.compile()


def main():
    customer_details = read_csv()
    customer_email_ids = get_email_ids_from_csv(customer_details)

    content = read_emails(email_path)
    verified_emails = verify_emails(content, customer_email_ids)
    classified_emails = classify_emails(content, verified_emails)

    email_graph = build_graph(customer_details)
    results = []

    for email in classified_emails:
        result = email_graph.invoke(email)

        results.append(
            {
                "email_id": result["email_id"],
                "sender_email": result["sender_email"],
                "category": result["category"],
                "priority": result["priority"],
                "confidence": result["confidence"],
                "order_found": result["order_found"],
                "order": result["order"],
                "reply": result["reply"],
                "escalation": result["escalation"],
                "reason": result["reason"],
            }
        )

    output_path = os.path.join(os.path.dirname(csv_path), "results.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    print(json.dumps(results, indent=4, ensure_ascii=False))
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()

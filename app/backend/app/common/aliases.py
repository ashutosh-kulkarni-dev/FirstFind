"""Display names for reviews."""
import hashlib

# Imported (Google) reviews are shown under a made-up name, not the real
# reviewer's. The name is picked from the review's own id, so a review keeps
# the same name on every page load and every deploy.
_ALIAS_FIRST = ["Aarav", "Aditi", "Akash", "Ananya", "Arjun", "Bhavna", "Chetan", "Deepa",
                "Divya", "Farhan", "Gauri", "Harish", "Ishaan", "Jaya", "Karthik", "Kavya",
                "Lakshmi", "Manoj", "Meera", "Naveen", "Neha", "Nikhil", "Pooja", "Pranav",
                "Priya", "Rahul", "Rekha", "Rohan", "Sahana", "Sanjay", "Shreya", "Sneha",
                "Suresh", "Tanvi", "Tejas", "Uma", "Varun", "Vidya", "Vikram", "Zoya"]
_ALIAS_LAST = "ABCDGHJKMNPRSTV"


def alias_for(store_id, key) -> str:
    seed = f"{store_id}|{key}"
    h = int(hashlib.sha1(seed.encode("utf-8")).hexdigest(), 16)
    first = _ALIAS_FIRST[h % len(_ALIAS_FIRST)]
    last = _ALIAS_LAST[(h // len(_ALIAS_FIRST)) % len(_ALIAS_LAST)]
    return f"{first} {last}."


def reviewer_alias(review) -> str:
    return alias_for(review.store_id, review.external_id or review.id)


def review_display_name(review) -> str:
    """App reviews show the member's own name; imported ones show an alias."""
    if (review.source or "app") == "google":
        return reviewer_alias(review)
    return review.user.name

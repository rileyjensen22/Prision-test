"""A mock work partner with a small bank of public-domain and synthetic tasks."""

from isd.work_rules import Review, review_answer

# Public-domain sentences (Aesop, the US founding documents) and synthetic ones.
_LINES = [
    ("A hare laughed at a tortoise for being slow.", "Aesop (public domain)"),
    ("The tortoise kept walking, one steady step after another.", "Aesop (public domain)"),
    ("Even the smallest friend may be a great help.", "Aesop (public domain)"),
    ("We the People of the United States, in Order to form a more perfect Union", "US, 1787"),
    ("establish Justice, insure domestic Tranquility", "US, 1787"),
    ("Four score and seven years ago our fathers brought forth on this continent", "Lincoln, 1863"),
    ("a new nation, conceived in Liberty", "Lincoln, 1863"),
    ("Congress shall make no law respecting an establishment of religion", "US, 1791"),
    (
        "The right of the people to be secure in their persons, houses, papers, and effects",
        "US, 1791",
    ),
    ("Excessive bail shall not be required, nor excessive fines imposed", "US, 1791"),
    ("Slow and steady can beat quick and careless.", "Aesop (public domain)"),
    ("A lion caught a small mouse and was about to eat her.", "Aesop (public domain)"),
]
_SCENES = [
    (
        "A person counts coins into three equal piles on a table.",
        ["coin", "pile", "count", "money"],
    ),
    (
        "A teacher writes a budget on a whiteboard with income and spending columns.",
        ["budget", "teacher", "board", "money"],
    ),
    (
        "Two hands measure a board with a tape measure before cutting it.",
        ["measure", "board", "tape", "cut"],
    ),
    (
        "A student reads a short book at a desk beside a window.",
        ["read", "book", "student", "desk"],
    ),
    ("A worker sorts boxes by size on a warehouse shelf.", ["box", "sort", "shelf", "worker"]),
    (
        "A cook chops vegetables and puts them into a large pot.",
        ["cook", "vegetable", "pot", "chop"],
    ),
    (
        "A learner fills in a job application form with a pen.",
        ["form", "pen", "application", "fill"],
    ),
    ("A gardener plants seedlings in neat rows of soil.", ["plant", "soil", "row", "garden"]),
]
_OPTIONS = ["statement", "question", "exclamation"]
_SENTENCES = [
    ("The tortoise crossed the line first.", "statement"),
    ("Who will win the race?", "question"),
    ("What a long road this is!", "exclamation"),
    ("The mouse gnawed through the ropes.", "statement"),
    ("Can a small friend be a great help?", "question"),
    ("How quickly the hare ran!", "exclamation"),
    ("Basic courses count toward your points.", "statement"),
    ("Where does the road lead?", "question"),
]


def _scan(text: str) -> str:
    """Make a clean line look like a poor scan, so there is something to correct."""
    swaps = {"l": "1", "o": "0", "e": "c", "m": "rn"}
    out, n = [], 0
    for ch in text:
        if ch in swaps and n % 4 == 0:
            out.append(swaps[ch])
        else:
            out.append(ch)
        n += ch in swaps
    return "".join(out)


class MockJobPartner:
    code = "MOCK_PARTNER"
    name = "Sample Work Partner (demo)"

    def fetch_tasks(self, kind: str, count: int, offset: int) -> list[dict]:
        if kind == "transcription_public_domain":
            bank = [
                {
                    "external_id": f"tr-{i}",
                    "scan": _scan(text),
                    "expected": text,
                    "source": source,
                }
                for i, (text, source) in enumerate(_LINES)
            ]
        elif kind == "captioning":
            bank = [
                {
                    "external_id": f"cap-{i}",
                    "scene": scene,
                    "keywords": keywords,
                    "source": "Synthetic course clip",
                }
                for i, (scene, keywords) in enumerate(_SCENES)
            ]
        else:
            bank = [
                {
                    "external_id": f"lab-{i}",
                    "item": sentence,
                    "options": _OPTIONS,
                    "expected": label,
                    "source": "Synthetic sentence",
                }
                for i, (sentence, label) in enumerate(_SENTENCES)
            ]
        return bank[offset : offset + count]

    def review(self, kind: str, spec: dict, answer: str, min_similarity: float) -> Review:
        return review_answer(kind, spec, answer, min_similarity)

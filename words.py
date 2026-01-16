from wordfreq import top_n_list
from pathlib import Path

WORDS_DIR = Path("words")
WORDS_DIR.mkdir(exist_ok=True)
SOLUTIONS_FILE = WORDS_DIR / "solutions.txt"

# Get many English words from wordfreq [web:128][web:138]
words = top_n_list("en", n_top=50000)

five_letter = []
for w in words:
    w = w.strip()
    # keep only pure alphabetic 5-letter words
    if len(w) == 5 and w.isalpha():
        five_letter.append(w.upper())   # convert to UPPERCASE here

# Deduplicate while preserving order
seen = set()
unique_five = []
for w in five_letter:
    if w not in seen:
        seen.add(w)
        unique_five.append(w)

print(f"Total 5-letter words: {len(unique_five)}")

# Each word is written on its own line, already UPPERCASE
with open(SOLUTIONS_FILE, "w", encoding="utf-8") as f:
    for w in unique_five:
        f.write(w + "\n")

print(f"Wrote {len(unique_five)} words to {SOLUTIONS_FILE}")

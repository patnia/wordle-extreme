import streamlit as st
from datetime import date
from pathlib import Path
import random

# ---------------------------
# Word loading
# ---------------------------

<<<<<<< HEAD
#WORDS_DIR = Path("words")
SOLUTIONS_FILE = Path("solutions.txt")
ALLOWED_FILE = Path("words.txt")
=======

#WORDS_DIR = Path("words")
SOLUTIONS_FILE = Path("solutions.txt")
ALLOWED_FILE = Path("words.txt")

>>>>>>> 9f98f74 (Submit guesses on Enter and remove button)

@st.cache_data
def load_words():
    with open(SOLUTIONS_FILE) as f:
        solutions = [w.strip().upper() for w in f if w.strip()]
    
    with open(ALLOWED_FILE) as f:
        allowed = [w.strip().upper() for w in f if w.strip()]

    allowed_set = set(allowed)
    missing = [w for w in solutions if w not in allowed_set]
    allowed.extend(missing)
    
    return solutions, allowed

SOLUTIONS, ALLOWED = load_words()

# ---------------------------
# Core scoring logic
# ---------------------------

def score_guess(target: str, guess: str):
    """
    Wordle-style scoring.
    Returns list of "correct" | "present" | "absent" per position.
    """
    target = target.upper()
    guess = guess.upper()
    result = ["absent"] * len(guess)

    target_chars = list(target)

    # first pass: exact matches
    for i, ch in enumerate(guess):
        if ch == target_chars[i]:
            result[i] = "correct"
            target_chars[i] = None

    # second pass: present but misplaced
    for i, ch in enumerate(guess):
        if result[i] == "correct":
            continue
        if ch in target_chars:
            result[i] = "present"
            target_chars[target_chars.index(ch)] = None

    return result

def get_daily_target(today: date, solutions):
    seed = today.toordinal()
    idx = seed % len(solutions)
    return solutions[idx]

def get_random_target(solutions):
    return random.choice(solutions)

# ---------------------------
# Streamlit app
# ---------------------------

st.set_page_config(page_title="Classic Wordle Extreme", page_icon="🧩", layout="centered")

MAX_GUESSES = 6
WORD_LENGTH = 5

def init_game(play_type: str):
    if play_type == "Daily":
        target = get_daily_target(date.today(), SOLUTIONS)
    else:
        target = get_random_target(SOLUTIONS)

    st.session_state.target = target
    st.session_state.play_type = play_type
    st.session_state.guesses = []
    st.session_state.evaluations = []
    st.session_state.game_over = False
    st.session_state.win = False
    st.session_state.message = ""

def ensure_initialized():
    if "target" not in st.session_state:
        init_game("Daily")

COLOR_MAP = {
    "correct": "#6aaa64",
    "present": "#c9b458",
    "absent": "#787c7e",
}

def render_cell(letter, status):
    bg = COLOR_MAP[status]
    st.markdown(
        f"<div style='text-align:center; font-weight:bold; "
        f"font-size:1.2rem; color:white; background:{bg}; "
        f"border-radius:4px; padding:4px; margin:2px; width:3rem; height:3rem;"
        f"display:flex; align-items:center; justify-content:center;'>"
        f"{letter}</div>",
        unsafe_allow_html=True,
    )

def render_board():
    total_rows = MAX_GUESSES
    for row_idx in range(total_rows):
        if row_idx < len(st.session_state.guesses):
            guess = st.session_state.guesses[row_idx]
            statuses = st.session_state.evaluations[row_idx]
        else:
            guess = " " * WORD_LENGTH
            statuses = ["absent"] * WORD_LENGTH

        cols = st.columns(WORD_LENGTH)
        for j, col in enumerate(cols):
            with col:
                letter = guess[j] if j < len(guess) else " "
                status = statuses[j]
                render_cell(letter, status)

def apply_guess(guess: str):
    if st.session_state.game_over:
        return

    guess = guess.upper()

    if len(guess) != WORD_LENGTH or not guess.isalpha():
        st.session_state.message = "Please enter a valid 5-letter word."
        return

    if guess not in ALLOWED:
        st.session_state.message = "Not in word list."
        return

    st.session_state.guesses.append(guess)
    eval_row = score_guess(st.session_state.target, guess)
    st.session_state.evaluations.append(eval_row)

    if all(x == "correct" for x in eval_row):
        st.session_state.game_over = True
        st.session_state.win = True
        st.session_state.message = "You solved it! 🎉"
    elif len(st.session_state.guesses) >= MAX_GUESSES:
        st.session_state.game_over = True
        st.session_state.win = False
        st.session_state.message = f"Out of guesses. Answer: {st.session_state.target}"

# ---------------------------
# UI
# ---------------------------

ensure_initialized()

st.title("Classic Wordle Extreme")
st.caption(f"{st.session_state.play_type} · {date.today().isoformat()}")

col_left, col_right = st.columns(2)
with col_left:
    play_type = st.radio(
        "Play type",
        ["Daily", "Practice"],
        index=0 if st.session_state.play_type == "Daily" else 1,
    )
with col_right:
    if st.button("New game"):
        init_game(play_type)

st.markdown("### Board")
render_board()

remaining = MAX_GUESSES - len(st.session_state.guesses)
st.markdown(f"**Guesses left:** {remaining}")

'''
guess_input = st.text_input("Enter a 5-letter guess", max_chars=WORD_LENGTH)
if st.button("Submit guess"):
    if guess_input:
        apply_guess(guess_input)
'''
def handle_guess_change():
    guess = st.session_state.current_guess
    if guess:
        apply_guess(guess)
        st.session_state.current_guess = ""

st.text_input("Enter a 5-letter guess", max_chars=WORD_LENGTH, key="current_guess", on_change=handle_guess_change)

if st.session_state.message:
    st.markdown(st.session_state.message)

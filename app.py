import streamlit as st
from datetime import date
from pathlib import Path
import random
import requests

# ---------------------------
# Word loading
# ---------------------------

SOLUTIONS_FILE = Path("solutions.txt")   # ~5k answer words
ALLOWED_FILE = Path("words.txt")        # ~10k allowed guesses

@st.cache_data
def load_words():
    with open(SOLUTIONS_FILE, encoding="utf-8") as f:
        solutions = [w.strip().upper() for w in f if w.strip()]

    if ALLOWED_FILE.exists():
        with open(ALLOWED_FILE, encoding="utf-8") as f:
            allowed = [w.strip().upper() for w in f if w.strip()]
    else:
        allowed = solutions

    # ensure all solutions are guessable
    allowed_set = set(allowed)
    missing = [w for w in solutions if w not in allowed_set]
    allowed.extend(missing)

    return solutions, allowed

SOLUTIONS, ALLOWED = load_words()

# ---------------------------
# Dictionary lookup
# ---------------------------

def get_definition(word: str) -> str:
    """
    Fetch a short English definition using a free dictionary API.
    Falls back gracefully if lookup fails.
    """
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word.lower()}"
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            return "No definition available."
        data = r.json()
        meaning = data[0]["meanings"][0]["definitions"][0]["definition"]
        return meaning.capitalize()
    except Exception:
        return "No definition available."

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

# ---------------------------
# Modes and targets
# ---------------------------

MODE_CONFIG = {
    "Classic": {"key": "classic", "boards": 1, "max_guesses": 6},
    "Quad":    {"key": "quad",    "boards": 4, "max_guesses": 9},
    "Octo":    {"key": "octo",    "boards": 8, "max_guesses": 13},
}

def get_daily_targets(mode_key: str, today: date, solutions):
    boards = MODE_CONFIG[mode_key_title(mode_key)]["boards"]

    # deterministic but simple: seed with mode+date and sample
    seed = hash((mode_key, today.toordinal()))
    rng = random.Random(seed)
    idxs = rng.sample(range(len(solutions)), boards)
    return [solutions[i] for i in idxs]

def get_random_targets(mode_key: str, solutions):
    boards = MODE_CONFIG[mode_key_title(mode_key)]["boards"]
    rng = random.Random()
    return rng.sample(solutions, boards)

def mode_key_title(mode_key: str) -> str:
    # helper to go from "classic" to "Classic" etc.
    for label, cfg in MODE_CONFIG.items():
        if cfg["key"] == mode_key:
            return label
    return "Classic"

# ---------------------------
# Streamlit app
# ---------------------------

st.set_page_config(
    page_title="Wordle Extreme",
    page_icon="🧩",
    layout="centered",
)

WORD_LENGTH = 5  # fixed 5-letter words


def init_game(mode_label: str, play_type: str):
    cfg = MODE_CONFIG[mode_label]
    mode_key = cfg["key"]
    n_boards = cfg["boards"]

    if play_type == "Daily":
        targets = get_daily_targets(mode_key, date.today(), SOLUTIONS)
    else:
        targets = get_random_targets(mode_key, SOLUTIONS)

    st.session_state.mode_label = mode_label
    st.session_state.mode_key = mode_key
    st.session_state.play_type = play_type
    st.session_state.targets = targets                # list[str]
    st.session_state.max_guesses = cfg["max_guesses"]
    st.session_state.guesses = []                     # shared list of guesses
    st.session_state.evaluations = {i: [] for i in range(n_boards)}
    st.session_state.solved = set()
    st.session_state.game_over = False
    st.session_state.win = False
    st.session_state.message = ""
    st.session_state.answer_definition = ""
    st.session_state.guess_buffer = ""


def ensure_initialized():
    if "mode_label" not in st.session_state:
        init_game("Classic", "Daily")
    if "answer_definition" not in st.session_state:
        st.session_state.answer_definition = ""
    if "guess_buffer" not in st.session_state:
        st.session_state.guess_buffer = ""


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

def render_board(board_index: int):
    evals = st.session_state.evaluations[board_index]
    total_rows = st.session_state.max_guesses

    for row_idx in range(total_rows):
        if row_idx < len(evals):
            guess = st.session_state.guesses[row_idx]
            statuses = evals[row_idx]
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

    # evaluate across all boards
    for i, target in enumerate(st.session_state.targets):
        evals_i = st.session_state.evaluations[i]

        if i in st.session_state.solved:
            # board already solved; keep row alignment
            evals_i.append(["correct"] * WORD_LENGTH)
            continue

        eval_row = score_guess(target, guess)
        evals_i.append(eval_row)

        if all(x == "correct" for x in eval_row):
            st.session_state.solved.add(i)

    # game over logic
    if len(st.session_state.solved) == len(st.session_state.targets):
        st.session_state.game_over = True
        st.session_state.win = True
        st.session_state.message = "You solved all boards! 🎉"
    elif len(st.session_state.guesses) >= st.session_state.max_guesses:
        st.session_state.game_over = True
        st.session_state.win = False
        answers = ", ".join(st.session_state.targets)
        st.session_state.message = f"Out of guesses. Answers: {answers}"

    if st.session_state.game_over:
        # definition for first board's answer
        st.session_state.answer_definition = get_definition(st.session_state.targets[0])

# ---------------------------
# Enter-to-submit handler
# ---------------------------

def handle_guess_change():
    guess = st.session_state.get("guess_buffer", "")
    if guess:
        apply_guess(guess)
        st.session_state["guess_buffer"] = ""  # clear after submit

# ---------------------------
# UI
# ---------------------------

ensure_initialized()

st.title("Wordle Extreme")

# Sidebar controls for mode and play type
mode_label = st.sidebar.selectbox("Mode", list(MODE_CONFIG.keys()))
play_type = st.sidebar.radio("Play type", ["Daily", "Practice"])

if st.sidebar.button("New game"):
    init_game(mode_label, play_type)

st.caption(
    f"{st.session_state.mode_label} · {st.session_state.play_type} · {date.today().isoformat()}"
)

n_boards = len(st.session_state.targets)

if n_boards == 1:
    st.subheader("Classic")
    render_board(0)
elif n_boards == 4:
    st.subheader("Quad")
    rows = [st.columns(2), st.columns(2)]
    idx = 0
    for row in rows:
        for col in row:
            with col:
                with st.container():
                    st.markdown(f"---\n**Board {idx+1}**")
                    render_board(idx)
                st.write("")  # small vertical spacer
                idx += 1
elif n_boards == 8:
    st.subheader("Octo")
    rows = [st.columns(4), st.columns(4)]
    idx = 0
    for row in rows:
        for col in row:
            with col:
                with st.container():
                    st.markdown(f"---\n**Board {idx+1}**")
                    render_board(idx)
                st.write("")  # small vertical spacer
                idx += 1

remaining = st.session_state.max_guesses - len(st.session_state.guesses)
st.markdown(f"**Guesses left:** {remaining}")

st.text_input(
    "Enter a 5-letter guess",
    max_chars=WORD_LENGTH,
    key="guess_buffer",
    on_change=handle_guess_change,
)

if st.session_state.message:
    st.markdown(st.session_state.message)

if st.session_state.game_over and st.session_state.answer_definition:
    st.markdown("### Today’s word")
    st.markdown(
        f"**{st.session_state.targets[0].title()}** – {st.session_state.answer_definition}"
    )

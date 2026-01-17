import streamlit as st
from datetime import date
from pathlib import Path
import random
import requests
import pandas as pd

USERS_FILE = Path("users.csv")

def load_users():
    if not USERS_FILE.exists():
        df = pd.DataFrame(columns=["username", "password"])
        df.to_csv(USERS_FILE, index=False)
        return df
    return pd.read_csv(USERS_FILE, dtype=str)

def save_users(df):
    df.to_csv(USERS_FILE, index=False)

def register_view():
    st.subheader("Create account")
    df = load_users()

    new_user = st.text_input("New username")
    new_pass = st.text_input("New password", type="password")

    if st.button("Sign up"):
        if not new_user or not new_pass:
            st.error("Username and password are required.")
            return

        if (df["username"] == new_user).any():
            st.error("Username already taken. Please choose another.")
            return

        df = pd.concat(
            [df, pd.DataFrame([{"username": new_user, "password": new_pass}])],
            ignore_index=True,
        )
        save_users(df)
        st.success("Account created. You can log in now.")

def login_view():
    st.title("Wordle Extreme")
    tab_login, tab_register = st.tabs(["Log in", "Sign up"])

    with tab_login:
        df = load_users()
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")

        if st.button("Log in"):
            if df.empty:
                st.error("No users exist yet. Please sign up first.")
            else:
                row = df[(df["username"] == username) & (df["password"] == password)]
                if not row.empty:
                    st.session_state.user = username
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("Invalid username or password.")

    with tab_register:
        register_view()

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    login_view()
    st.stop()

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

def get_daily_target(today: date, solutions):
    seed = today.toordinal()
    idx = seed % len(solutions)
    return solutions[idx]

def get_random_target(solutions):
    return random.choice(solutions)

# ---------------------------
# Streamlit app
# ---------------------------

st.set_page_config(
    page_title="Classic Wordle Extreme",
    page_icon="🧩",
    layout="centered"
)

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
    st.session_state.answer_definition = ""
    st.session_state.guess_buffer = ""

def ensure_initialized():
    if "target" not in st.session_state:
        init_game("Daily")
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

    if st.session_state.game_over:
        st.session_state.answer_definition = get_definition(st.session_state.target)

# ---------------------------
# Enter-to-submit handler
# ---------------------------

def handle_guess_change():
    # Called when user presses Enter in the text input
    guess = st.session_state.get("guess_buffer", "")
    if guess:
        apply_guess(guess)
        st.session_state["guess_buffer"] = ""  # clear after submit

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
        f"**{st.session_state.target.title()}** – {st.session_state.answer_definition}"
    )

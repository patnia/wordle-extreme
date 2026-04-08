import streamlit as st
from datetime import date
from pathlib import Path
import random
import requests
import concurrent.futures

# ---------------------------
# Word loading
# ---------------------------

SOLUTIONS_FILE = Path("solutions.txt")
ALLOWED_FILE = Path("words.txt")

@st.cache_data
def load_words():
    with open(SOLUTIONS_FILE, encoding="utf-8") as f:
        solutions = [w.strip().upper() for w in f if w.strip()]

    if ALLOWED_FILE.exists():
        with open(ALLOWED_FILE, encoding="utf-8") as f:
            allowed = [w.strip().upper() for w in f if w.strip()]
    else:
        allowed = solutions

    allowed_set = set(allowed)
    missing = [w for w in solutions if w not in allowed_set]
    allowed.extend(missing)
    allowed_set.update(missing)

    return solutions, allowed_set   # return a set for O(1) lookup

SOLUTIONS, ALLOWED = load_words()

# ---------------------------
# Dictionary lookup
# ---------------------------

def _fetch_one(word: str) -> str:
    """Fetch definition for a single word. Runs in a thread."""
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

def fetch_definitions_parallel(words: list[str]) -> list[str]:
    """
    Fetch definitions for multiple words in parallel using a thread pool.
    Replaces the sequential approach that blocked the UI for ~8 requests.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(words)) as executor:
        futures = [executor.submit(_fetch_one, w) for w in words]
        return [f.result() for f in futures]

# ---------------------------
# Core scoring logic
# ---------------------------

def score_guess(target: str, guess: str):
    """
    Wordle-style scoring.
    Returns list of 'correct' | 'present' | 'absent' per position.
    """
    target = target.upper()
    guess = guess.upper()
    result = ["absent"] * len(guess)
    target_chars = list(target)

    # First pass: exact matches
    for i, ch in enumerate(guess):
        if ch == target_chars[i]:
            result[i] = "correct"
            target_chars[i] = None

    # Second pass: present but misplaced
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

def mode_key_title(mode_key: str) -> str:
    for label, cfg in MODE_CONFIG.items():
        if cfg["key"] == mode_key:
            return label
    return "Classic"

def get_daily_targets(mode_key: str, today: date, solutions):
    boards = MODE_CONFIG[mode_key_title(mode_key)]["boards"]
    seed = hash((mode_key, today.toordinal()))
    rng = random.Random(seed)
    idxs = rng.sample(range(len(solutions)), boards)
    return [solutions[i] for i in idxs]

def get_random_targets(mode_key: str, solutions):
    boards = MODE_CONFIG[mode_key_title(mode_key)]["boards"]
    return random.sample(solutions, boards)

# ---------------------------
# Keyboard configuration
# ---------------------------

KEYBOARD_ROWS = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]

KEY_COLOR_PRIORITY = {
    "correct": 3,
    "present": 2,
    "absent":  1,
    "unused":  0,
}
KEYBOARD_COLORS = {
    "correct": "#6aaa64",
    "present": "#c9b458",
    "absent":  "#3a3a3c",
    "unused":  "#818384",
}

COLOR_MAP = {
    "correct": "#6aaa64",
    "present": "#c9b458",
    "absent":  "#787c7e",
    "empty":   "#121213",  # unfilled tile
}

# ---------------------------
# Game state initialisation
# ---------------------------

def init_game(mode_label: str, play_type: str):
    """
    Single source of truth for all session state.
    Called on new game; never patched piecemeal afterwards.
    Replaces the fragile ensure_initialized() pattern.
    """
    cfg = MODE_CONFIG[mode_label]
    mode_key = cfg["key"]
    n_boards = cfg["boards"]

    if play_type == "Daily":
        targets = get_daily_targets(mode_key, date.today(), SOLUTIONS)
    else:
        targets = get_random_targets(mode_key, SOLUTIONS)

    # Core game state
    st.session_state.mode_label   = mode_label
    st.session_state.mode_key     = mode_key
    st.session_state.play_type    = play_type
    st.session_state.targets      = targets
    st.session_state.max_guesses  = cfg["max_guesses"]
    st.session_state.guesses      = []          # list of actual guess strings
    st.session_state.evaluations  = {i: [] for i in range(n_boards)}
    st.session_state.solved       = set()
    st.session_state.game_over    = False
    st.session_state.win          = False
    st.session_state.message      = ""
    st.session_state.definitions  = [""] * n_boards

    # FIX 1: separate display rows from guess rows.
    # Solved boards stop receiving real evals but still show their own
    # correct tiles for every remaining row — not fake gray tiles.
    # display_rows[board_idx][row_idx] = list of (letter, status) tuples
    st.session_state.display_rows = {i: [] for i in range(n_boards)}

    # FIX 2: use a submit button instead of on_change to prevent
    # double-submission and stale buffer issues.
    st.session_state.pending_guess = ""

    # Keyboard state
    st.session_state.keyboard_state = {
        ch: "unused" for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    }
    st.session_state.keyboard_board_state = {
        ch: ["unused"] * n_boards for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    }

    st.session_state.screen = "game"

# ---------------------------
# Keyboard helpers
# ---------------------------

def update_keyboard(board_idx: int, guess: str, eval_row):
    for ch, status in zip(guess, eval_row):
        board_list = st.session_state.keyboard_board_state[ch]
        if KEY_COLOR_PRIORITY[status] > KEY_COLOR_PRIORITY[board_list[board_idx]]:
            board_list[board_idx] = status

        best = max(board_list, key=lambda s: KEY_COLOR_PRIORITY[s])
        st.session_state.keyboard_state[ch] = best

# ---------------------------
# Guess handling
# ---------------------------

def apply_guess(guess: str):
    if st.session_state.game_over:
        return

    guess = guess.upper().strip()

    if len(guess) != 5 or not guess.isalpha():
        st.session_state.message = "Please enter a valid 5-letter word."
        return

    if guess not in ALLOWED:
        st.session_state.message = "Not in word list."
        return

    st.session_state.message = ""
    st.session_state.guesses.append(guess)
    n_boards = len(st.session_state.targets)

    for i, target in enumerate(st.session_state.targets):
        if i in st.session_state.solved:
            # FIX 1: solved board — repeat its winning row visually
            # so the board stays full and green, not filled with gray.
            winning_row = st.session_state.display_rows[i][-1]  # last real row
            st.session_state.display_rows[i].append(winning_row)
            # evaluations entry still needed for row-count alignment
            st.session_state.evaluations[i].append(["correct"] * 5)
            continue

        eval_row = score_guess(target, guess)
        st.session_state.evaluations[i].append(eval_row)
        st.session_state.display_rows[i].append(
            list(zip(guess, eval_row))
        )
        update_keyboard(i, guess, eval_row)

        if all(s == "correct" for s in eval_row):
            st.session_state.solved.add(i)

    # Game-over checks
    if len(st.session_state.solved) == n_boards:
        st.session_state.game_over = True
        st.session_state.win = True
        st.session_state.message = "🎉 You solved all boards!"
    elif len(st.session_state.guesses) >= st.session_state.max_guesses:
        st.session_state.game_over = True
        st.session_state.win = False
        unrevealed = [
            st.session_state.targets[i]
            for i in range(n_boards)
            if i not in st.session_state.solved
        ]
        if unrevealed:
            st.session_state.message = (
                f"Out of guesses. Unsolved: {', '.join(unrevealed)}"
            )
        else:
            st.session_state.message = "Out of guesses."

    # FIX 3: fetch all definitions in parallel, not sequentially
    if st.session_state.game_over:
        st.session_state.definitions = fetch_definitions_parallel(
            st.session_state.targets
        )

# ---------------------------
# Rendering helpers
# ---------------------------

def render_cell(letter: str, status: str):
    bg = COLOR_MAP.get(status, COLOR_MAP["empty"])
    st.markdown(
        f"""
        <div style='
            text-align:center;
            font-weight:bold;
            font-size:1.2rem;
            color:white;
            background:{bg};
            border: 2px solid {"#538d4e" if status == "correct"
                               else "#b59f3b" if status == "present"
                               else "#565758" if status == "absent"
                               else "#3a3a3c"};
            border-radius:4px;
            width:3rem;
            height:3rem;
            display:flex;
            align-items:center;
            justify-content:center;
            margin:2px auto;
        '>{letter}</div>
        """,
        unsafe_allow_html=True,
    )

def render_board(board_index: int):
    """
    Renders a board using display_rows, which correctly handles
    solved boards (repeating green row) vs unsolved boards (empty rows).
    """
    display = st.session_state.display_rows[board_index]
    total_rows = st.session_state.max_guesses

    for row_idx in range(total_rows):
        cols = st.columns(5)
        if row_idx < len(display):
            row = display[row_idx]   # list of (letter, status) tuples
            for j, col in enumerate(cols):
                with col:
                    letter, status = row[j]
                    render_cell(letter, status)
        else:
            # Empty future row
            for col in cols:
                with col:
                    render_cell(" ", "empty")

def render_keyboard():
    st.markdown("---")
    n_boards = len(st.session_state.targets)

    for row in KEYBOARD_ROWS:
        cols = st.columns(len(row))
        for i, ch in enumerate(row):
            with cols[i]:
                segments_html = ""
                for b in range(n_boards):
                    status = st.session_state.keyboard_board_state[ch][b]
                    bg = KEYBOARD_COLORS[status]
                    segments_html += (
                        f"<div style='flex:1;height:100%;background:{bg};"
                        f"border-right:1px solid #111;'></div>"
                    )
                overall = KEYBOARD_COLORS[
                    st.session_state.keyboard_state.get(ch, "unused")
                ]
                st.markdown(
                    f"<div style='display:flex;flex-direction:column;"
                    f"align-items:center;'>"
                    f"<div style='font-weight:bold;color:#ccc;"
                    f"font-size:0.9rem;margin-bottom:2px;'>{ch}</div>"
                    f"<div style='display:flex;width:2.4rem;height:0.6rem;"
                    f"border:2px solid {overall};border-radius:4px;"
                    f"overflow:hidden;'>{segments_html}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

# ---------------------------
# Screens
# ---------------------------

def show_menu():
    st.title("Wordle Extreme")
    st.markdown("Choose a game mode to begin.")

    mode_label = st.radio("Mode", list(MODE_CONFIG.keys()), index=0)
    play_type  = st.radio("Play type", ["Daily", "Practice"], index=0)

    if st.button("Start game", type="primary"):
        init_game(mode_label, play_type)
        st.rerun()

def show_game():
    # Guard: if somehow we land here without state, go back to menu
    if "targets" not in st.session_state:
        st.session_state.screen = "menu"
        st.rerun()
        return

    st.title("Wordle Extreme")
    st.caption(
        f"{st.session_state.mode_label} · "
        f"{st.session_state.play_type} · "
        f"{date.today().isoformat()}"
    )

    col_back, col_new = st.columns([1, 1])
    with col_back:
        if st.button("← Menu"):
            st.session_state.screen = "menu"
            st.rerun()
    with col_new:
        if st.button("New game (Practice)"):
            init_game(st.session_state.mode_label, "Practice")
            st.rerun()

    n_boards = len(st.session_state.targets)

    # ---------------------------
    # FIX 4: Board layout — use equal columns, no spacer hack.
    # Classic: 1 centred column. Quad: 2 cols. Octo: 2 cols (4 rows).
    # ---------------------------

    if n_boards == 1:
        _, center, _ = st.columns([1, 2, 1])
        with center:
            render_board(0)

    elif n_boards == 4:
        for row_start in range(0, 4, 2):   # rows: (0,1), (2,3)
            c1, c2 = st.columns(2)
            for col_widget, board_idx in zip([c1, c2], [row_start, row_start + 1]):
                with col_widget:
                    solved_tag = " ✅" if board_idx in st.session_state.solved else ""
                    st.markdown(f"**Board {board_idx + 1}{solved_tag}**")
                    render_board(board_idx)

    elif n_boards == 8:
        for row_start in range(0, 8, 2):
            c1, c2 = st.columns(2)
            for col_widget, board_idx in zip([c1, c2], [row_start, row_start + 1]):
                with col_widget:
                    solved_tag = " ✅" if board_idx in st.session_state.solved else ""
                    st.markdown(f"**Board {board_idx + 1}{solved_tag}**")
                    render_board(board_idx)

    # ---------------------------
    # Guess input
    # FIX 2: use a form with a submit button instead of on_change.
    # This prevents double-submission and stale buffer issues entirely.
    # ---------------------------

    remaining = st.session_state.max_guesses - len(st.session_state.guesses)
    st.markdown(f"**Guesses remaining:** {remaining}")

    if not st.session_state.game_over:
        with st.form(key="guess_form", clear_on_submit=True):
            guess_input = st.text_input(
                "Enter a 5-letter word",
                max_chars=5,
                key="guess_input_field",
                label_visibility="collapsed",
                placeholder="Type your guess…",
            )
            submitted = st.form_submit_button("Guess", type="primary")

        if submitted and guess_input:
            apply_guess(guess_input)
            st.rerun()

    # Status message
    if st.session_state.message:
        if st.session_state.win:
            st.success(st.session_state.message)
        elif st.session_state.game_over:
            st.error(st.session_state.message)
        else:
            st.warning(st.session_state.message)

    # Post-game word definitions
    if st.session_state.game_over:
        st.markdown("---")
        if n_boards == 1:
            st.markdown("### Today's word")
            status = "✅ Solved" if 0 in st.session_state.solved else "❌ Unsolved"
            st.markdown(
                f"**{st.session_state.targets[0].title()}** {status}  \n"
                f"*{st.session_state.definitions[0]}*"
            )
        else:
            st.markdown("### Today's words")
            for i in range(n_boards):
                word   = st.session_state.targets[i].title()
                defn   = st.session_state.definitions[i]
                status = "✅ Solved" if i in st.session_state.solved else "❌ Unsolved"
                st.markdown(f"**Board {i+1} — {word}** {status}  \n*{defn}*")

    render_keyboard()

# ---------------------------
# Router
# ---------------------------

st.set_page_config(
    page_title="Wordle Extreme",
    page_icon="🧩",
    layout="centered",
)

if "screen" not in st.session_state:
    st.session_state.screen = "menu"

if st.session_state.screen == "menu":
    show_menu()
else:
    show_game()

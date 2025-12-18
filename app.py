from flask import Flask, request, jsonify, render_template, session
import numpy as np
from collections import Counter
from datetime import date
import os

# --- Game Logic Constants ---
COLORS = ["#FF0000", "#FFA500", "#FFFF00", "#00EE00", "#0000FF", "#EE00EE"]
CORRECT_COLORS = ["#000000", "#FFFFFF", "#FF0000"]
MAX_INPUTS = 12
CODE_LENGTH = 4


# --- Flask Setup ---
app = Flask(__name__)
# WARNING: CHANGE THIS KEY IN PRODUCTION!
app.secret_key = os.environ.get('DAILY_PATTERN_OFFSET', "DEFAULT_SECRET")

# REMOVE: Global current_pattern is no longer needed
# current_pattern = None 

# Define a fallback if the environment variable isn't set
DEFAULT_SECRET = 98765 

try:
    SECRET_OFFSET = int(os.environ.get('DAILY_PATTERN_OFFSET', DEFAULT_SECRET))
except ValueError:
    print("Warning: DAILY_PATTERN_OFFSET in environment is invalid. Using default.")
    SECRET_OFFSET = DEFAULT_SECRET

# -------- GAME LOGIC --------
def create_pattern():
    """Generates a daily-seeded 4-peg pattern (0-5 index)."""
    today = date.today()
    seed_string = today.strftime("%Y%m%d")
    seed_value = int(seed_string) + SECRET_OFFSET
    np.random.seed(seed_value)
    pattern = np.random.choice(6, 4).tolist() 
    np.random.seed(None)
    return pattern

def get_current_daily_pattern():
    """
    Retrieves the pattern from the session. If it's a new day, resets the game state.
    """
    current_date = date.today().isoformat() 
    
    # 1. Check if we need to reset/start a new daily game
    if session.get('date') != current_date:
        new_pattern = create_pattern() 
        
        # Reset and save all new state to the session
        session['daily_pattern'] = new_pattern
        session['date'] = current_date
        session['game_history'] = []
        session['num_guesses'] = 0
        session.modified = True
        
        return new_pattern
    
    # 2. Returning user, same day: Pattern is guaranteed to be in the session
    # If the pattern is somehow missing (e.g., first run after a server crash),
    # this will raise an error, but the index route should prevent that.
    return session['daily_pattern']

def check_correct(guess, original_pattern):
    """
    Compares the guess to the pattern and returns feedback (reds, whites).
    """
    guess_arr = np.array(guess)
    pattern_arr = np.array(original_pattern)
    
    reds = np.sum(guess_arr == pattern_arr)
    s = Counter(original_pattern) & Counter(guess)
    total_matches = sum(s.values())
    whites = total_matches - reds
    
    return int(reds), int(whites)


# --- API Routes ---

@app.route('/')
def index():
    """Serves the main HTML page and ensures the daily game state is loaded."""
    
    # CRUCIAL: Call this first to load the existing pattern/history OR reset for a new day.
    get_current_daily_pattern()

    history = session.get('game_history', [])
    num_guesses = session.get('num_guesses', 0)

    return render_template('index.html',
        COLORS=COLORS,
        CORRECT_COLORS=CORRECT_COLORS,
        MAX_SLOTS=CODE_LENGTH,
        MAX_GUESSES=MAX_INPUTS,
        initial_history=history,
        initial_num_guesses=num_guesses
    )

@app.route('/start_game', methods=['POST'])
def start_game():
    """
    This route is called by the frontend on load. It should NOT reset the progress,
    but simply return the current daily game state.
    """
    
    # CRITICAL FIX: Do NOT reset the history here. index() handles the new day reset.
    current_pattern = get_current_daily_pattern()
    history = session.get('game_history', [])
    num_guesses = session.get('num_guesses', 0)
    
    # Determine if the game is already over (in case the client wants the final pattern)
    game_over = (num_guesses >= MAX_INPUTS) or (history and history[-1]['reds'] == CODE_LENGTH)

    return jsonify({
        'message': 'Daily challenge loaded',
        'max_guesses': MAX_INPUTS,
        'colors': COLORS, 
        'history': history,
        'num_guesses': num_guesses,
        'pattern': current_pattern if game_over else None
    })

@app.route('/make_guess', methods=['POST'])
def make_guess():
    """Receives a guess and returns feedback."""

    # 1. Retrieve state from session (ALWAYS do this first)
    current_pattern = session.get('daily_pattern')
    num_guesses = session.get('num_guesses', 0)
    history = session.get('game_history', [])
    
    if current_pattern is None:
        return jsonify({'error': 'Game not started/State missing. Reload page.'}), 400

    # 2. Check for game over (prevents phantom guesses on refresh)
    if num_guesses >= MAX_INPUTS or (history and history[-1]['reds'] == CODE_LENGTH):
        return jsonify({'error': 'Game already over.'}), 400
        
    data = request.get_json()
    guess = data.get('guess') 
    
    if not isinstance(guess, list) or len(guess) != CODE_LENGTH:
        return jsonify({'error': 'Invalid guess format. Must be a list of 4 integers.'}), 400

    # 3. Run core game logic and update state
    reds, whites = check_correct(guess, current_pattern)
    num_guesses += 1
    
    history_entry = {
        'guess': guess,
        "reds": reds,
        'whites': whites
    }

    history.append(history_entry)
    
    # 4. Check game over conditions
    win = (reds == CODE_LENGTH)
    game_over = win or (num_guesses >= MAX_INPUTS)

    # 5. Save state back to session (CRUCIAL FOR PERSISTENCE)
    session['num_guesses'] = num_guesses
    session['game_history'] = history
    session.modified = True 

    # 6. Prepare response
    response = {
        'reds': reds,
        'whites': whites,
        'game_over': game_over,
        'win': win,
        'pattern': current_pattern if game_over else None 
    }
    return jsonify(response)


if __name__ == '__main__':
    # Running in debug mode can sometimes interfere with session cookies.
    # If the issue persists, try running with debug=False in a production environment.
    app.run(debug=True)
import os
import hashlib
import json
import requests
import stripe
import mysql.connector
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# --- Initialization & Configuration ---
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')

# Stripe Configuration
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
stripe_webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')

# Database Configuration
db_config = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}

# Hugging Face API Configuration
HF_API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"
HF_HEADERS = {"Authorization": f"Bearer {os.getenv('HF_API_TOKEN')}"}

# Flask-Login Configuration
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- User Model & Database Functions ---

class User(UserMixin):
    def __init__(self, id, username, credits=0):
        self.id = id
        self.username = username
        self.credits = credits

def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        return None

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    if not conn: return None
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, username, credits FROM users WHERE id = %s", (user_id,))
    user_data = cursor.fetchone()
    cursor.close()
    conn.close()
    if user_data:
        return User(id=user_data['id'], username=user_data['username'], credits=user_data['credits'])
    return None

# --- Helper Functions (Hash & AI Query) ---

def generate_text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def query_ai_model(context):
    # This function remains the same as before...
    # (For brevity, it's omitted here, but should be included from the previous version)
    prompt = f"""
    Based on the following text, generate exactly 5 distinct questions and their corresponding answers.
    Format your response as a valid JSON array of objects, where each object has a "question" key and an "answer" key.
    Do not include any other text or explanation outside of the JSON array.

    Here is the text:
    ---
    {context}
    ---
    """
    payload = {"inputs": prompt, "parameters": {"max_new_tokens": 500, "temperature": 0.7, "return_full_text": False}}
    try:
        response = requests.post(HF_API_URL, headers=HF_HEADERS, json=payload, timeout=30)
        response.raise_for_status()
        generated_text = response.json()[0]['generated_text']
        json_start_index = generated_text.find('[')
        json_end_index = generated_text.rfind(']') + 1
        if json_start_index == -1 or json_end_index == 0: return []
        json_string = generated_text[json_start_index:json_end_index]
        return json.loads(json_string)
    except (requests.exceptions.RequestException, json.JSONDecodeError, IndexError) as e:
        print(f"Error in AI query: {e}")
        return []

# --- Authentication Routes ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        if not conn:
            flash('Database connection failed.', 'danger')
            return render_template('register.html')
        
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            flash('Username already exists.', 'warning')
            return redirect(url_for('register'))
        
        hashed_password = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, hashed_password))
        conn.commit()
        cursor.close()
        conn.close()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        if not conn:
            flash('Database connection failed.', 'danger')
            return render_template('login.html')

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user_data and check_password_hash(user_data['password_hash'], password):
            user_obj = User(id=user_data['id'], username=user_data['username'], credits=user_data['credits'])
            login_user(user_obj)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# --- Core Application Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate-flashcards', methods=['POST'])
@login_required
def generate_flashcards():
    if current_user.credits < 1:
        return jsonify({'error': 'Insufficient credits. Please purchase more.'}), 403

    data = request.get_json()
    user_text = data.get('text', '').strip()
    if not user_text:
        return jsonify({'error': 'Text cannot be empty'}), 400

    context_hash = generate_text_hash(user_text)
    conn = get_db_connection()
    if not conn: return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = conn.cursor(dictionary=True)
    # Check for cards created by ANY user to leverage caching, but only linked to current user if created new
    cursor.execute("SELECT question, answer FROM flashcards WHERE context_hash = %s", (context_hash,))
    existing_flashcards = cursor.fetchall()

    if existing_flashcards:
        cursor.close()
        conn.close()
        return jsonify(existing_flashcards)
    
    generated_cards = query_ai_model(user_text)
    if not generated_cards:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Failed to generate flashcards from AI model'}), 500

    try:
        # Decrement user credits
        cursor.execute("UPDATE users SET credits = credits - 1 WHERE id = %s", (current_user.id,))
        
        # Save new cards linked to the user
        insert_query = "INSERT INTO flashcards (question, answer, context_hash, user_id) VALUES (%s, %s, %s, %s)"
        for card in generated_cards:
            if 'question' in card and 'answer' in card:
                cursor.execute(insert_query, (card['question'], card['answer'], context_hash, current_user.id))
        
        conn.commit()
        # The user object in session is not automatically updated, so we subtract it manually for the UI
        current_user.credits -= 1
        return jsonify(generated_cards)
    except mysql.connector.Error as err:
        conn.rollback()
        print(f"Transaction error: {err}")
        return jsonify({'error': 'A database error occurred during transaction.'}), 500
    finally:
        cursor.close()
        conn.close()

# --- Stripe Payment Routes ---

@app.route('/config')
@login_required
def get_config():
    return jsonify({'publishableKey': os.getenv('STRIPE_PUBLISHABLE_KEY')})

@app.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {'name': '10 AI Study Buddy Credits'},
                    'unit_amount': 500, # $5.00
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('index', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('index', _external=True),
            # Pass user id to associate payment with user
            client_reference_id=current_user.id
        )
        return jsonify({'sessionId': checkout_session.id})
    except Exception as e:
        return jsonify(error=str(e)), 403

@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, stripe_webhook_secret
        )
    except ValueError as e:
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        return 'Invalid signature', 400

    # Handle the checkout.session.completed event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session.get('client_reference_id')
        
        if user_id:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                # Add 10 credits for a successful purchase
                cursor.execute("UPDATE users SET credits = credits + 10 WHERE id = %s", (user_id,))
                conn.commit()
                cursor.close()
                conn.close()
                print(f"Successfully added 10 credits to user {user_id}")

    return 'Success', 200


if __name__ == '__main__':
    app.run(debug=True, port=5000)
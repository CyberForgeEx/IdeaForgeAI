from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import requests
import json
import sqlite3
import os
import re
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'fallback-secret-for-dev')  # Use a strong random value in production

# Database Configuration
DATABASE = os.path.join(os.path.dirname(__file__), 'idea_evaluator.db')

def get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Initialize the database with required tables."""
    conn = get_db_connection()
    
    # Users table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    ''')
    
    # Ideas table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            overall_score REAL NOT NULL,
            evaluation_data TEXT NOT NULL,  -- JSON string
            poml_data TEXT,  -- JSON string
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')
    
    # Evaluation factors table (normalized approach)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS evaluation_factors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idea_id INTEGER NOT NULL,
            factor_name TEXT NOT NULL,
            score INTEGER NOT NULL,
            analysis TEXT NOT NULL,
            FOREIGN KEY (idea_id) REFERENCES ideas (id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database on module load
init_database()

# API Configuration
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "x-ai/grok-4-fast:free"

HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json"
}

# Idea Validation
def validate_idea_content(title, description):
    """
    Comprehensive validation to check if the idea is a legitimate software project idea.
    Returns (is_valid: bool, error_message: str, suggestions: list)
    """
    # Basic validation
    if len(title.strip()) < 10:
        return False, "Title must be at least 10 characters long.", []
    
    if len(description.strip()) < 50:
        return False, "Description must be at least 50 characters long to provide adequate detail.", []
    
    if len(description.strip()) > 3000:
        return False, "Description is too long. Please keep it under 3000 characters.", []
    
    # Check for excessive repetition (gibberish detection)
    words = description.lower().split()
    if len(words) > 0:
        word_count = {}
        for word in words:
            word_count[word] = word_count.get(word, 0) + 1
        
        # Check if any word appears too frequently (more than 30% of total words)
        max_repetition = max(word_count.values())
        if max_repetition > len(words) * 0.3 and len(words) > 10:
            return False, "Your description contains excessive repetition. Please provide a more detailed and varied description.", []
    
    # Check for minimal word count and variety
    unique_words = set(word.lower().strip('.,!?;:"()[]{}') for word in words if len(word) > 3)
    if len(unique_words) < 5:
        return False, "Your description lacks sufficient detail and variety. Please elaborate more on your idea.", []
    
    # Technology/Software keywords validation
    tech_keywords = [
        'app', 'application', 'software', 'program', 'platform', 'system', 'tool', 'website', 'web',
        'mobile', 'desktop', 'api', 'database', 'backend', 'frontend', 'fullstack', 'framework',
        'library', 'sdk', 'ide', 'code', 'programming', 'development', 'developer',
        'ai', 'artificial intelligence', 'machine learning', 'ml', 'deep learning', 'neural network',
        'blockchain', 'cryptocurrency', 'crypto', 'nft', 'smart contract', 'defi', 'web3',
        'cloud', 'saas', 'paas', 'iaas', 'microservices', 'serverless', 'docker', 'kubernetes',
        'react', 'angular', 'vue', 'node', 'python', 'java', 'javascript', 'typescript',
        'flutter', 'swift', 'kotlin', 'react native', 'ionic',
        'users', 'customers', 'business', 'startup', 'product', 'service', 'solution',
        'automation', 'efficiency', 'productivity', 'workflow', 'process', 'management',
        'analytics', 'data', 'insights', 'dashboard', 'reporting', 'metrics',
        'social', 'network', 'community', 'marketplace', 'ecommerce', 'e-commerce',
        'fintech', 'healthtech', 'edtech', 'proptech', 'regtech', 'insurtech',
        'authentication', 'authorization', 'login', 'signup', 'user management',
        'notification', 'messaging', 'chat', 'video', 'audio', 'streaming',
        'search', 'filter', 'sort', 'recommendation', 'personalization',
        'integration', 'sync', 'backup', 'security', 'encryption', 'privacy',
        'responsive', 'mobile-friendly', 'cross-platform', 'scalable', 'performance'
    ]
    
    # Check if description contains technology-related keywords
    description_lower = description.lower()
    title_lower = title.lower()
    combined_text = f"{title_lower} {description_lower}"
    
    keyword_matches = sum(1 for keyword in tech_keywords if keyword in combined_text)
    
    # If no tech keywords found, it's likely not a software idea
    if keyword_matches == 0:
        suggestions = [
            "Include specific technology or programming concepts",
            "Mention the type of application or software you want to build",
            "Describe the technical features or functionality",
            "Explain what programming languages or frameworks you might use",
            "Detail how users would interact with your software"
        ]
        return False, "This doesn't appear to be a software or technology project idea. Please ensure your idea relates to software development, applications, or technology solutions.", suggestions
    
    # Check for common non-software ideas
    non_software_patterns = [
        r'\b(restaurant|food truck|cafe|bakery|catering)\b',
        r'\b(clothing|fashion|boutique|apparel)\b',
        r'\b(physical store|retail shop|brick and mortar)\b',
        r'\b(construction|building|real estate)\b',
        r'\b(farming|agriculture|gardening)\b',
        r'\b(handmade|crafts|artwork)\b',
        r'\b(consulting|coaching|training)\b(?!.*\b(app|software|platform|tool)\b)',
        r'\b(event planning|wedding|party)\b(?!.*\b(app|software|platform|management)\b)',
    ]
    
    for pattern in non_software_patterns:
        if re.search(pattern, combined_text, re.IGNORECASE):
            # Check if it also mentions software/tech aspects
            if keyword_matches < 2:
                suggestions = [
                    "If this is a software idea, please emphasize the technology aspects",
                    "Describe any mobile apps, websites, or software tools involved",
                    "Explain the digital or technological components of your idea",
                    "Focus on the software features and functionality you want to build"
                ]
                return False, "This appears to be a traditional business idea rather than a software project. Please focus on the technology or software aspects of your concept.", suggestions
    
    # Check for meaningless or test content
    meaningless_patterns = [
        r'^(test|testing|hello|hi|hey|example).*$',
        r'^[a-z\s]{1,10}$',
        r'^\d+$',
        r'^[^\w\s]+$'
    ]
    
    for pattern in meaningless_patterns:
        if re.match(pattern, combined_text.strip(), re.IGNORECASE):
            return False, "Please provide a meaningful software project idea with proper description.", []
    
    # Advanced AI-based validation
    validation_result = validate_idea_with_ai(title, description)
    if not validation_result['is_valid']:
        return False, validation_result['reason'], validation_result.get('suggestions', [])
    
    return True, "", []

def validate_idea_with_ai(title, description):
    """
    Use AI to validate if the idea is a legitimate software project.
    Returns dict with is_valid, reason, and suggestions.
    """
    if not OPENROUTER_API_KEY:
        # If no API key, skip AI validation and rely on keyword-based validation
        return {'is_valid': True, 'reason': '', 'suggestions': []}
    
    validation_prompt = """
You are a software project validator. Analyze the given title and description to determine if this is a legitimate software/technology project idea.

Rules for validation:
1. Must be related to software, apps, websites, platforms, or technology solutions
2. Should not be just physical products, traditional businesses, or services without tech components
3. Should not be gibberish, test content, or meaningless text
4. Should have enough detail to be evaluated as a software project
5. Should be feasible as a software development project

Respond ONLY with a JSON object in this exact format:
{{
  "is_valid": boolean,
  "reason": "explanation if invalid",
  "suggestions": ["suggestion1", "suggestion2"]
}}

Title: {title}
Description: {description}
"""

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": validation_prompt.format(title=title, description=description)}
        ],
        "max_tokens": 300,
        "temperature": 0.1
    }
    
    try:
        response = requests.post(API_URL, headers=HEADERS, json=payload, timeout=10)
        response.raise_for_status()
        response_data = response.json()
        ai_message = response_data['choices'][0]['message']['content'].strip()
        
        # Extract JSON from response
        if ai_message.startswith('```json```'):
            ai_message = ai_message.strip('```json```')
        elif ai_message.startswith('```'):
            ai_message = ai_message.strip('```').strip()
        
        validation_result = json.loads(ai_message)
        
        # Ensure required fields exist
        if 'is_valid' not in validation_result:
            return {'is_valid': True, 'reason': '', 'suggestions': []}
        
        return validation_result
        
    except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as e:
        # AI validation fails, default to allowing the idea
        print(f"AI validation error: {e}")
        return {'is_valid': True, 'reason': '', 'suggestions': []}

# Authentication 
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """Get current user from session."""
    if 'user_id' not in session:
        return None
    
    conn = get_db_connection()
    user = conn.execute(
        'SELECT * FROM users WHERE id = ?', (session['user_id'],)
    ).fetchone() # Retrieve the single user records that match the id.
    conn.close()
    return user

# Database Operations
def create_user(username, email, password):
    """Create a new user."""
    conn = get_db_connection()
    try:
        password_hash = generate_password_hash(password)
        cursor = conn.execute(
            'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
            (username, email, password_hash)
        )
        user_id = cursor.lastrowid
        conn.commit() # persist the changes.
        return user_id
    except sqlite3.IntegrityError as e:
        return None
    finally:
        conn.close()

def authenticate_user(username, password):
    """Authenticate a user."""
    conn = get_db_connection()
    user = conn.execute(
        'SELECT * FROM users WHERE username = ? OR email = ?',
        (username, username)
    ).fetchone()
    
    if user and check_password_hash(user['password_hash'], password):
        # Update last login
        conn.execute(
            'UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?',
            (user['id'],)
        )
        conn.commit()
        conn.close()
        return user
    
    conn.close()
    return None

def save_idea_evaluation(user_id, title, description, evaluation_data, poml_data=None):
    """Save an idea evaluation to the database."""
    conn = get_db_connection()
    
    # Calculate overall score
    if isinstance(evaluation_data, dict) and 'error' not in evaluation_data:
        scores = [data['score'] for data in evaluation_data.values() 
                 if isinstance(data, dict) and 'score' in data]
        overall_score = sum(scores) / len(scores) if scores else 0 # to prevent divide by zero error
    else:
        overall_score = 0
    
    # Insert idea
    cursor = conn.execute('''
        INSERT INTO ideas (user_id, title, description, overall_score, evaluation_data, poml_data)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, title, description, overall_score, 
          json.dumps(evaluation_data), json.dumps(poml_data) if poml_data else None))
    
    idea_id = cursor.lastrowid
    
    # Insert evaluation factors
    if isinstance(evaluation_data, dict) and 'error' not in evaluation_data:
        for factor_name, factor_data in evaluation_data.items():
            if isinstance(factor_data, dict) and 'score' in factor_data:
                conn.execute('''
                    INSERT INTO evaluation_factors (idea_id, factor_name, score, analysis)
                    VALUES (?, ?, ?, ?)
                ''', (idea_id, factor_name, factor_data['score'], factor_data['analysis']))
    
    conn.commit()
    conn.close()
    return idea_id

def get_user_ideas(user_id, limit=None):
    """Get all ideas for a specific user."""
    conn = get_db_connection()
    query = '''
        SELECT * FROM ideas 
        WHERE user_id = ? 
        ORDER BY created_at DESC
    '''
    if limit:
        query += f' LIMIT {limit}'
    
    ideas = conn.execute(query, (user_id,)).fetchall()
    
    # Convert to list of dictionaries and parse JSON fields
    ideas_list = []
    for idea in ideas:
        idea_dict = dict(idea)
        idea_dict['evaluation_data'] = json.loads(idea_dict['evaluation_data'])
        if idea_dict['poml_data']:
            idea_dict['poml_data'] = json.loads(idea_dict['poml_data'])
        ideas_list.append(idea_dict)
    
    conn.close()
    return ideas_list

def get_idea_by_id(idea_id, user_id):
    """Get a specific idea by ID (with user ownership check)."""
    conn = get_db_connection()
    idea = conn.execute(
        'SELECT * FROM ideas WHERE id = ? AND user_id = ?',
        (idea_id, user_id)
    ).fetchone()
    
    if idea:
        idea_dict = dict(idea)
        idea_dict['evaluation_data'] = json.loads(idea_dict['evaluation_data'])
        if idea_dict['poml_data']:
            idea_dict['poml_data'] = json.loads(idea_dict['poml_data'])
        conn.close()
        return idea_dict
    
    conn.close()
    return None

def delete_idea(idea_id, user_id):
    """Delete an idea (with user ownership check)."""
    conn = get_db_connection()
    cursor = conn.execute(
        'DELETE FROM ideas WHERE id = ? AND user_id = ?',
        (idea_id, user_id)
    )
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

# AI Evaluation Functions
def evaluate_idea_with_ai(idea_description):
    """Evaluate idea with AI."""
    # output setting for AI generated data.
    system_prompt = (
        "You are a seasoned venture capitalist and technical advisor. Your task is to "
        "evaluate a software project idea based on a set of criteria. Provide a score "
        "from 0 to 10 for each factor and a brief analysis. The output MUST be a single, "
        "valid JSON object with the following structure:\n\n"
        "{{\n"
        '  "innovation": {{"score": int, "analysis": "string"}},\n'
        '  "market_demand": {{"score": int, "analysis": "string"}},\n'
        '  "feasibility": {{"score": int, "analysis": "string"}},\n'
        '  "scalability": {{"score": int, "analysis": "string"}},\n'
        '  "monetization_potential": {{"score": int, "analysis": "string"}},\n'
        '  "team_resource_availability": {{"score": int, "analysis": "string"}},\n'
        '  "time_to_market": {{"score": int, "analysis": "string"}},\n'
        '  "future_trends": {{"score": int, "analysis": "string"}}\n'
        "}}"
    )

    # Fetching the data from the AI.
    user_prompt = (
        "Please evaluate the following software project idea:\n\n"
        f"Project Idea: {idea_description}\n\n"
        "Please provide a score from 0-10 and a brief analysis for each of the following factors:\n"
        "- **Innovation**: How unique or novel is the idea?\n"
        "- **Market Demand**: Is there an existing market for the idea?\n"
        "- **Feasibility**: Is the idea technically feasible with current technology?\n"
        "- **Scalability**: Can the project grow and scale over time?\n"
        "- **Monetization Potential**: How easy is it to monetize the project?\n"
        "- **Team/Resource Availability**: Does the project require a rare skill set?\n"
        "- **Time to Market**: How long will it take to build a working prototype?\n"
        "- **Future Trends**: Is the idea aligned with future tech trends like AI, Web 3.0, Blockchain etc.?"
    )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    }

    try:
        response = requests.post(API_URL, headers=HEADERS, json=payload)
        response.raise_for_status()
        response_data = response.json()
        ai_message = response_data['choices'][0]['message']['content'].strip()
        
        # Extract JSON from response
        if ai_message.startswith('```json```'):
            ai_message = ai_message.strip('```json```')
        elif ai_message.startswith('```'):
            ai_message = ai_message.strip('```').strip()
        
        try:
            evaluation_data = json.loads(ai_message)
            return evaluation_data
        except json.JSONDecodeError:
            return {"error": "Invalid JSON response from AI", "raw_response": ai_message}

    except requests.exceptions.RequestException as e:
        return {"error": f"API request failed: {str(e)}"}

def generate_poml_with_ai(idea_description):
    """Generate POML with AI."""
    poml_prompt = (
        "Generate a complete POML (Prompt Orchestration Markup Language) document "
        "for the following software project idea. The POML should define a logical "
        "flow for building the application with suitable tech stacks, including a few example prompts for key "
        "tasks. The output MUST be a valid, single JSON object representing the entire POML, and in the POML metadata name the author as IDEAFORGE and remove date."
    )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": poml_prompt + f"\n\nProject Idea: {idea_description}\n\n"}
        ]
    }
    
    try:
        response = requests.post(API_URL, headers=HEADERS, json=payload)
        response.raise_for_status()
        
        if not response.content:
            return {"error": "Empty response from API"}

        poml_message = response.json().get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        
        if poml_message.startswith('```json```'):
            poml_message = poml_message.strip('```json```')
        elif poml_message.startswith('```'):
            poml_message = poml_message.strip('```').strip()
            
        return json.loads(poml_message)
    except requests.exceptions.RequestException as e:
        return {"error": f"API request failed: {str(e)}"}
    except (json.JSONDecodeError, KeyError) as e:
        return {"error": "Invalid POML response from AI"}

# Routes
@app.route('/')
def index():
    """Home page - redirects based on login status."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        if not username or not email or not password:
            flash('All fields are required.', 'error')
        elif password != confirm_password:
            flash('Passwords do not match.', 'error')
        elif len(password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
        else:
            # Try to create user
            user_id = create_user(username, email, password)
            if user_id:
                session['user_id'] = user_id
                session['username'] = username
                flash('Registration successful! Welcome!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Username or email already exists.', 'error')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Username and password are required.', 'error')
        else:
            user = authenticate_user(username, password)
            if user:
                session['user_id'] = user['id']
                session['username'] = user['username']
                flash(f'Welcome back, {user["username"]}!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid username or password.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """User logout."""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard."""
    user = get_current_user()
    recent_ideas = get_user_ideas(user['id'])
    
    # Statistics
    conn = get_db_connection()
    stats = conn.execute('''
        SELECT 
            COUNT(*) as total_ideas,
            AVG(overall_score) as avg_score,
            MAX(overall_score) as best_score
        FROM ideas WHERE user_id = ?
    ''', (user['id'],)).fetchone()
    conn.close()
    
    # Convert stats to dict and handle None values
    stats_dict = dict(stats) if stats else {}
    stats_dict['total_ideas'] = stats_dict.get('total_ideas', 0)
    stats_dict['avg_score'] = stats_dict.get('avg_score', 0.0)
    stats_dict['best_score'] = stats_dict.get('best_score', 0.0)
    
    return render_template('dashboard.html', 
                         user=user, 
                         recent_ideas=recent_ideas,
                         stats=stats_dict)

@app.route('/evaluate', methods=['GET', 'POST'])
@login_required
def evaluate():
    """Evaluate a new idea with comprehensive validation."""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        idea_description = request.form.get('idea_description', '').strip()
        
        if not title or not idea_description:
            flash('Both title and description are required.', 'error')
            return render_template('evaluate.html', 
                                 title=title, 
                                 description=idea_description)
        
        # Comprehensive validation
        is_valid, error_message, suggestions = validate_idea_content(title, idea_description)
        
        if not is_valid:
            flash(error_message, 'error')
            
            # If there are suggestions, show them
            if suggestions:
                suggestion_text = "Suggestions to improve your idea:\n" + "\n".join(f"• {s}" for s in suggestions)
                flash(suggestion_text, 'info')
            
            return render_template('evaluate.html', 
                                 title=title, 
                                 description=idea_description,
                                 suggestions=suggestions)
        
        # Check API configuration
        if not OPENROUTER_API_KEY:
            flash('API key not configured. Please contact administrator.', 'error')
            return render_template('evaluate.html')
        
        # Get evaluation from AI
        evaluation_data = evaluate_idea_with_ai(idea_description)
        
        if "error" in evaluation_data:
            flash(f'Error during evaluation: {evaluation_data["error"]}', 'error')
            return render_template('evaluate.html', 
                                 title=title, 
                                 description=idea_description)
        
        # Generate POML
        poml_data = generate_poml_with_ai(idea_description)
        
        # Save to database
        idea_id = save_idea_evaluation(
            session['user_id'], title, idea_description, 
            evaluation_data, poml_data
        )
        
        flash('Idea evaluated and saved successfully!', 'success')
        return redirect(url_for('view_idea', idea_id=idea_id))
    
    return render_template('evaluate.html')

@app.route('/ideas')
@login_required
def my_ideas():
    """View all user ideas."""
    ideas = get_user_ideas(session['user_id'])
    return render_template('my_ideas.html', ideas=ideas)

@app.route('/idea/<int:idea_id>') # Specifing the ideas according to the idea_id which ever created previously.
@login_required
def view_idea(idea_id):
    """View a specific idea."""
    idea = get_idea_by_id(idea_id, session['user_id'])
    if not idea:
        flash('Idea not found.', 'error')
        return redirect(url_for('my_ideas'))
    
    return render_template('view_idea.html', idea=idea)

@app.route('/idea/<int:idea_id>/delete', methods=['POST'])
@login_required
def delete_idea_route(idea_id):
    """Delete an idea."""
    if delete_idea(idea_id, session['user_id']):
        flash('Idea deleted successfully.', 'success')
    else:
        flash('Idea not found or unable to delete.', 'error')
    
    return redirect(url_for('my_ideas'))

@app.route('/poml/<int:idea_id>')
@login_required
def view_poml(idea_id):
    """View POML for a specific idea."""
    idea = get_idea_by_id(idea_id, session['user_id'])
    if not idea:
        flash('Idea not found.', 'error')
        return redirect(url_for('my_ideas'))
    
    if not idea['poml_data']:
        flash('POML not available for this idea.', 'error')
        return redirect(url_for('view_idea', idea_id=idea_id))
    
    # Pretty-print POML data
    pretty_poml = json.dumps(idea['poml_data'], indent=2)
    
    return render_template('view_poml.html', idea=idea, pretty_poml=pretty_poml)
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import requests
import json
import sqlite3
import os
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'fallback-secret-for-dev')

# Timezone Configuration (UTC+4)
TIMEZONE_OFFSET = 4  # Hours offset from UTC

# Database Configuration
DATABASE = os.path.join(os.path.dirname(__file__), 'idea_evaluator.db')


def get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def convert_to_local_time(utc_time_str):
    """Convert UTC timestamp string to local time (UTC+4)."""
    if not utc_time_str:
        return ""
    try:
        # Parse the UTC timestamp
        utc_time = datetime.strptime(utc_time_str, '%Y-%m-%d %H:%M:%S')
        # Add timezone offset
        local_time = utc_time + timedelta(hours=TIMEZONE_OFFSET)
        # Return formatted string
        return local_time.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return utc_time_str


def format_datetime(utc_time_str, format_type='full'):
    """Format datetime for display with timezone conversion."""
    if not utc_time_str:
        return ""
    try:
        # Convert to local time first
        local_str = convert_to_local_time(utc_time_str)
        local_time = datetime.strptime(local_str, '%Y-%m-%d %H:%M:%S')
        
        if format_type == 'date':
            return local_time.strftime('%Y-%m-%d')
        elif format_type == 'time':
            return local_time.strftime('%H:%M:%S')
        elif format_type == 'short':
            return local_time.strftime('%b %d, %Y %H:%M')
        else:  # full
            return local_time.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return utc_time_str


# Register Jinja2 filters
app.jinja_env.filters['local_time'] = convert_to_local_time
app.jinja_env.filters['format_datetime'] = format_datetime


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
            evaluation_data TEXT NOT NULL,
            poml_data TEXT,
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
    
    # Favorites table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            idea_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (idea_id) REFERENCES ideas (id) ON DELETE CASCADE,
            UNIQUE(user_id, idea_id)
        )
    ''')
    
    conn.commit()
    conn.close()


# Initialize database on module load
init_database()

# Groq API Configuration
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_HEADERS = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json"
}


# Helper function to extract JSON
def extract_json_from_response(text):
    """Extract JSON from response with improved case handling."""
    text = text.strip()
    
    # Handle markdown code blocks
    if text.startswith('```json'):
        text = text[7:]
    elif text.startswith('```'):
        text = text[3:]
    
    if text.endswith('```'):
        text = text[:-3]
    
    return text.strip()


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
    if not GROQ_API_KEY:
        # If no API key, skip AI validation and rely on keyword-based validation
        return {'is_valid': True, 'reason': '', 'suggestions': []}
    
    validation_prompt = f"""You are a software project validator. Analyze the given title and description to determine if this is a legitimate software/technology project idea.

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
        "model": GROQ_MODEL,
        "messages": [
            {"role": "user", "content": validation_prompt}
        ],
        "max_tokens": 300,
        "temperature": 0.1
    }
    
    try:
        response = requests.post(GROQ_API_URL, headers=GROQ_HEADERS, json=payload, timeout=15)
        response.raise_for_status()
        response_data = response.json()
        ai_message = response_data['choices'][0]['message']['content'].strip()
        
        # Extract JSON from response
        ai_message = extract_json_from_response(ai_message)
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
    ).fetchone()
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
        conn.commit()
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
        overall_score = sum(scores) / len(scores) if scores else 0
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
    """Get a specific idea by ID (with user ownership check) - INCLUDES NOTES."""
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
       
        # Check if favorited
        idea_dict['is_favorited'] = is_idea_favorited(user_id, idea_id)
       
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


# Favorites Management
def toggle_favorite(user_id, idea_id):
    """Toggle favorite status for an idea."""
    conn = get_db_connection()
    
    # Check if already favorited
    existing = conn.execute(
        'SELECT id FROM favorites WHERE user_id = ? AND idea_id = ?',
        (user_id, idea_id)
    ).fetchone()
    
    if existing:
        # Remove from favorites
        conn.execute('DELETE FROM favorites WHERE user_id = ? AND idea_id = ?',
                    (user_id, idea_id))
        is_favorited = False
    else:
        # Add to favorites
        conn.execute('INSERT INTO favorites (user_id, idea_id) VALUES (?, ?)',
                    (user_id, idea_id))
        is_favorited = True
    
    conn.commit()
    conn.close()
    return is_favorited


def get_favorite_ideas(user_id):
    """Get all favorited ideas for a user."""
    conn = get_db_connection()
    ideas = conn.execute('''
        SELECT i.* FROM ideas i
        INNER JOIN favorites f ON i.id = f.idea_id
        WHERE f.user_id = ?
        ORDER BY f.created_at DESC
    ''', (user_id,)).fetchall()
    
    ideas_list = []
    for idea in ideas:
        idea_dict = dict(idea)
        idea_dict['evaluation_data'] = json.loads(idea_dict['evaluation_data'])
        if idea_dict['poml_data']:
            idea_dict['poml_data'] = json.loads(idea_dict['poml_data'])
        ideas_list.append(idea_dict)
    
    conn.close()
    return ideas_list


def is_idea_favorited(user_id, idea_id):
    """Check if an idea is favorited by user."""
    conn = get_db_connection()
    result = conn.execute(
        'SELECT id FROM favorites WHERE user_id = ? AND idea_id = ?',
        (user_id, idea_id)
    ).fetchone()
    conn.close()
    return result is not None


# Idea Comparison
def compare_ideas(user_id, idea_ids):
    """Get multiple ideas for comparison."""
    if not idea_ids:
        return []
    
    conn = get_db_connection()
    placeholders = ','.join('?' * len(idea_ids))
    query = f'''
        SELECT * FROM ideas
        WHERE user_id = ? AND id IN ({placeholders})
        ORDER BY overall_score DESC
    '''
    ideas = conn.execute(query, (user_id, *idea_ids)).fetchall()
    
    ideas_list = []
    for idea in ideas:
        idea_dict = dict(idea)
        idea_dict['evaluation_data'] = json.loads(idea_dict['evaluation_data'])
        if idea_dict['poml_data']:
            idea_dict['poml_data'] = json.loads(idea_dict['poml_data'])
        ideas_list.append(idea_dict)
    
    conn.close()
    return ideas_list


# AI Evaluation Functions with Groq
def evaluate_idea_with_ai(idea_description):
    """Evaluate idea with Groq AI."""
    system_prompt = """You are a seasoned venture capitalist and technical advisor. Your task is to evaluate a software project idea based on a set of criteria. Provide a score from 0 to 10 for each factor and a brief analysis.

The output MUST be a single, valid JSON object with the following structure:
{
  "innovation": {"score": int, "analysis": "string"},
  "market_demand": {"score": int, "analysis": "string"},
  "feasibility": {"score": int, "analysis": "string"},
  "scalability": {"score": int, "analysis": "string"},
  "monetization_potential": {"score": int, "analysis": "string"},
  "team_resource_availability": {"score": int, "analysis": "string"},
  "time_to_market": {"score": int, "analysis": "string"},
  "future_trends": {"score": int, "analysis": "string"}
}

Respond ONLY with the JSON object, no additional text."""
    
    user_prompt = f"""Please evaluate the following software project idea:

Project Idea: {idea_description}

Please provide a score from 0-10 and a brief analysis for each of the following factors:
- **Innovation**: How unique or novel is the idea?
- **Market Demand**: Is there an existing market for the idea?
- **Feasibility**: Is the idea technically feasible with current technology?
- **Scalability**: Can the project grow and scale over time?
- **Monetization Potential**: How easy is it to monetize the project?
- **Team/Resource Availability**: Does the project require a rare skill set?
- **Time to Market**: How long will it take to build a working prototype?
- **Future Trends**: Is the idea aligned with future tech trends like AI, Web 3.0, Blockchain etc.?"""
    
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 2500
    }
    
    try:
        response = requests.post(GROQ_API_URL, headers=GROQ_HEADERS, json=payload, timeout=30)
        response.raise_for_status()
        response_data = response.json()
        ai_message = response_data['choices'][0]['message']['content'].strip()
        
        # Extract JSON from response
        ai_message = extract_json_from_response(ai_message)
        
        try:
            evaluation_data = json.loads(ai_message)
            return evaluation_data
        except json.JSONDecodeError:
            return {"error": "Invalid JSON response from AI", "raw_response": ai_message}
    
    except requests.exceptions.RequestException as e:
        return {"error": f"API request failed: {str(e)}"}


def generate_poml_with_ai(idea_description):
    """Generate POML with Groq AI."""
    poml_prompt = f"""Generate a complete POML (Prompt Orchestration Markup Language) document for the following software project idea. The POML should define a logical flow for building the application with suitable tech stacks, including a few example prompts for key tasks.

Project Idea: {idea_description}

The output MUST be a valid, single JSON object representing the entire POML. In the POML metadata, name the author as IDEAFORGE and remove the date field.

Respond ONLY with the JSON object, no additional text or markdown."""
    
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "user", "content": poml_prompt}
        ],
        "temperature": 0.5,
        "max_tokens": 4500
    }
    
    try:
        response = requests.post(GROQ_API_URL, headers=GROQ_HEADERS, json=payload, timeout=30)
        response.raise_for_status()
        
        if not response.content:
            return {"error": "Empty response from API"}
        
        poml_message = response.json().get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        
        # Extract JSON from response
        poml_message = extract_json_from_response(poml_message)
        
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
    recent_ideas = get_user_ideas(user['id'], limit=5)
    
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
        if not GROQ_API_KEY:
            flash('Groq API key not configured. Please contact administrator.', 'error')
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


@app.route('/idea/<int:idea_id>')
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


# Favorite Routes
@app.route('/idea/<int:idea_id>/favorite', methods=['POST'])
@login_required
def toggle_favorite_route(idea_id):
    """Toggle favorite status for an idea."""
    # Verify idea exists and belongs to user
    idea = get_idea_by_id(idea_id, session['user_id'])
    if not idea:
        return jsonify({'success': False, 'message': 'Idea not found'}), 404
    
    is_favorited = toggle_favorite(session['user_id'], idea_id)
    
    return jsonify({
        'success': True,
        'is_favorited': is_favorited,
        'message': 'Added to favorites' if is_favorited else 'Removed from favorites'
    })


@app.route('/favorites')
@login_required
def favorites():
    """View all favorited ideas."""
    favorite_ideas = get_favorite_ideas(session['user_id'])
    return render_template('favorites.html', ideas=favorite_ideas)


# Comparison Route
@app.route('/compare')
@login_required
def compare():
    """Compare multiple ideas side-by-side."""
    idea_ids = request.args.getlist('ids', type=int)
    
    if not idea_ids or len(idea_ids) < 2:
        flash('Please select at least 2 ideas to compare.', 'warning')
        return redirect(url_for('my_ideas'))
    
    if len(idea_ids) > 4:
        flash('You can compare up to 4 ideas at once.', 'warning')
        idea_ids = idea_ids[:4]
    
    ideas = compare_ideas(session['user_id'], idea_ids)
    
    if len(ideas) < 2:
        flash('Not enough ideas found for comparison.', 'error')
        return redirect(url_for('my_ideas'))
    
    return render_template('compare.html', ideas=ideas)


# Statistics Route
@app.route('/statistics')
@login_required
def statistics():
    """View detailed statistics and analytics."""
    user = get_current_user()
    
    # Handle case where user doesn't exist (session is invalid)
    if not user:
        session.clear()
        flash('Your session has expired. Please log in again.', 'warning')
        return redirect(url_for('login'))
    
    ideas = get_user_ideas(user['id'])
    
    # Calculate statistics
    if not ideas:
        stats = {
            'total_ideas': 0,
            'avg_score': 0,
            'highest_score': 0,
            'lowest_score': 0,
            'factor_averages': {}
        }
    else:
        scores = [idea['overall_score'] for idea in ideas]
        
        # Calculate factor averages
        factor_scores = {}
        for idea in ideas:
            if 'error' not in idea['evaluation_data']:
                for factor, data in idea['evaluation_data'].items():
                    if factor not in factor_scores:
                        factor_scores[factor] = []
                    factor_scores[factor].append(data['score'])
        
        factor_averages = {
            factor: sum(scores) / len(scores)
            for factor, scores in factor_scores.items()
        }
        
        stats = {
            'total_ideas': len(ideas),
            'avg_score': sum(scores) / len(scores),
            'highest_score': max(scores),
            'lowest_score': min(scores),
            'factor_averages': factor_averages,
            'best_idea': max(ideas, key=lambda x: x['overall_score']),
            'worst_idea': min(ideas, key=lambda x: x['overall_score'])
        }
    
    return render_template('statistics.html', stats=stats, ideas=ideas)


# Error Handlers
@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors."""
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    return render_template('500.html'), 500


if __name__ == '__main__':
    app.run(debug=True)

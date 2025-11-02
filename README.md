<h2 align="center">
  IdeaForge: AI-Powered Software Idea Evaluator
  <img src="./assets/logo.png" alt="project logo">
</h2>

## Table of Contents
- [Project Overview](#project-overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
  - [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Running the Application](#running-the-application)
  - [User Workflow](#user-workflow)
- [Database Management](#database-management)
- [AI Integration](#ai-integration)
- [Acknowledgements](#acknowledgements)

## Project Overview
IdeaForge is a web-based application designed to help entrepreneurs, developers, and innovators evaluate software project ideas using AI-driven analysis. Users can submit ideas, which are validated for legitimacy as software projects, evaluated across key metrics (e.g., innovation, market demand, feasibility), and optionally generate a Prompt Orchestration Markup Language (POML) document for further development guidance.

The  web app includes user authentication, a dashboard with advanced analytics, and integration with AI models via the Groq API. It ensures ideas are focused on software/technology by employing both keyword-based and AI-powered validation to filter out non-relevant submissions. The updated UI features a professional, mobile-responsive design with claymorphic styling and a modern color scheme.

This project is built with security, usability, and scalability in mind, using SQLite for persistent storage and Flask as the web framework. It is suitable for personal use, startups, or educational purposes.

## Features
- **User Authentication**: Secure registration, login, and session management using hashed passwords.
- **Idea Submission & Validation**: Comprehensive checks with length validation, keyword matching, repetition detection, AI-based analysis, and truncated suggestions for improved user feedback.
- **AI-Powered Evaluation**: Scores ideas on factors like innovation, scalability, monetization potential, and alignment with future trends.
- **POML Generation**: Automatically generates a POML document outlining a logical flow for building the idea, including tech stacks and example prompts.
- **Dashboard & Idea Management**: View, edit, delete, and browse saved ideas with a statistics dashboard (total ideas, average/high/low scores, factor averages, best/worst ideas, ranked list).
- **Favorites System**: Mark ideas as favorites, view a dedicated favorites page, and toggle favorite status via AJAX.
- **Comments System**: Add, view, and delete comments on ideas for enhanced collaboration.
- **Idea Comparison**: Select up to 4 ideas for side-by-side comparison of scores and factors.
- **Timezone Support**: Configured for UTC+4 with conversion functions and Jinja2 filters for displaying local times in templates.
- **Enhanced UI**: Professional sidebar navigation, mobile responsiveness, claymorphic styling, and updated color scheme for an enterprise-like appearance.
- **Error Handling & Feedback**: User-friendly flashes, empty states, and suggestions for improving invalid ideas.
- **Deployment-Ready**: Configured for production with environment variables and support for platforms like PythonAnywhere.

## Tech Stack
- **Backend**: Flask (Python web framework)
- **Database**: SQLite (lightweight, file-based RDBMS)
- **Security**: Werkzeug (for password hashing)
- **AI Integration**: Groq API (for validation, evaluation, and POML generation)
- **HTTP Requests**: Requests library
- **Environment Management**: python-dotenv (for loading `.env` files)
- **Frontend**: Jinja2 templates (HTML/CSS/JS with claymorphic styling and mobile responsiveness)
- **Other**: JSON for data handling, re for regex validations

### Prerequisites
- Python 3.10 or higher
- pip (Python package installer)
- Virtual environment tool (e.g., venv)
- Groq API account (for AI features) – sign up at [console.groq.com](https://console.groq.com)

## Configuration
- **API Key**: Required for AI features. Obtain Free API-key from [console.groq.com](https://console.groq.com).
- **Database**: Path is absolute (`os.path.join(os.path.dirname(__file__), 'idea_evaluator.db')`) for reliability. For production scaling, consider migrating to PostgreSQL.
- **Model**: Defaults to "llama-3.3-70b-versatile" customizable in `app.py` by modifying the `GROQ_MODEL` variable.
- **Timezone**: Configured for UTC+4 with Jinja2 filters for local time display.

Update `app.py` for custom configurations, such as changing the AI model, timezone, or adding logging for debugging.

## Usage

### Running the Application
For development (not for production):
```
python app.py
```
Access at `http://127.0.0.1:5000/`.

### User Workflow
1. **Register/Login**: Create an account at `/register` or log in at `/login` to access features.
2. **Evaluate Idea**: Navigate to `/evaluate`, submit a title (min 10 chars) and description (min 50 chars). The app validates for software relevance and evaluates using AI.
3. **View Dashboard**: At `/dashboard`, see recent ideas, advanced statistics (total ideas, average/high/low scores, factor averages, best/worst ideas, ranked list), and manage submissions.
4. **View/Delete Ideas**: Access individual ideas at `/idea/<id>` with favorite status and comments, delete via POST at `/idea/<id>/delete`.
5. **Manage Favorites**: Mark/unmark ideas as favorites via AJAX and view them on the favorites page.
6. **Add/View Comments**: Add, view, or delete comments on ideas for collaboration.
7. **Compare Ideas**: Select up to 4 ideas for side-by-side comparison of scores and factors.
8. **View POML**: If generated, view the POML document at `/poml/<id>`.

## Database Management
- **Schema**:
  - `users`: Stores user details (id, username, email, password_hash, created_at, last_login).
  - `ideas`: Stores idea details (id, user_id, title, description, overall_score, evaluation_data, poml_data, timestamps).
  - `evaluation_factors`: Normalized table for evaluation scores and analyses (linked to ideas via idea_id).
  - `favorites`: Stores favorite ideas (user_id, idea_id, timestamp).
  - `comments`: Stores comments on ideas (id, user_id, idea_id, content, timestamp).
  - Foreign key constraints and cascading deletes ensure data integrity.

## AI Integration
- **Validation**: Combines rule-based checks (keywords, regex patterns for non-software ideas) and AI validation via Groq to ensure ideas are software-related.
- **Evaluation**: Scores ideas on eight factors (0-10): innovation, market demand, feasibility, scalability, monetization potential, team/resource availability, time to market, and future trends.
- **POML Generation**: Produces a JSON-based POML document with tech stacks and development prompts, authored as "IDEAFORGE".
- **Error Handling**: Gracefully handles API failures by falling back to keyword validation or returning user-friendly error messages.

Ensure your Groq API key has sufficient credits for continuous usage.

## Acknowledgements
- [Flask](https://flask.palletsprojects.com/) for the lightweight web framework.
- [Groq](https://groq.com/) for AI API integration.
- [Python](https://www.python.org/) community for robust libraries.

Thank you for using IdeaForge! 🚀

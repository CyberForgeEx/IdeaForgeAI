# IdeaForge: AI-Powered Software Idea Evaluator

![IdeaForge Logo](https://via.placeholder.com/150x50?text=IdeaForge) <!-- Replace with actual logo if available -->

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![Flask Version](https://img.shields.io/badge/Flask-3.0%2B-green)](https://flask.palletsprojects.com/)
[![Build Status](https://img.shields.io/badge/Build-Passing-brightgreen)](https://example.com/build) <!-- Update with actual CI/CD badge if set up -->

## Table of Contents

- [Project Overview](#project-overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
  - [Prerequisites](#prerequisites)
  - [Local Setup](#local-setup)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Running the Application](#running-the-application)
  - [User Workflow](#user-workflow)
- [Database Management](#database-management)
- [AI Integration](#ai-integration)
- [Acknowledgements](#acknowledgements)

## Project Overview

IdeaForge is a web-based application designed to help entrepreneurs, developers, and innovators evaluate software project ideas using AI-driven analysis. Users can submit ideas, which are validated for legitimacy as software projects, evaluated across key metrics (e.g., innovation, market demand, feasibility), and optionally generate a Prompt Orchestration Markup Language (POML) document for further development guidance.

The app includes user authentication, a dashboard for managing ideas, and integration with AI models via the OpenRouter API. It ensures ideas are focused on software/technology by employing both keyword-based and AI-powered validation to filter out non-relevant submissions.

This project is built with security and usability in mind, using SQLite for persistent storage and Flask as the web framework. It is suitable for personal use, startups, or educational purposes.

## Features

- **User Authentication**: Secure registration, login, and session management using hashed passwords.
- **Idea Submission & Validation**: Comprehensive checks to ensure ideas are legitimate software projects, including length validation, keyword matching, repetition detection, and AI-based analysis.
- **AI-Powered Evaluation**: Scores ideas on factors like innovation, scalability, monetization potential, and alignment with future trends.
- **POML Generation**: Automatically generates a POML document outlining a logical flow for building the idea, including tech stacks and example prompts.
- **Dashboard & Idea Management**: View, edit, delete, and browse saved ideas with statistics (e.g., average score, total ideas).
- **Database Persistence**: Stores users, ideas, and evaluations in a SQLite database with normalized tables for efficiency.
- **Error Handling & Feedback**: User-friendly flashes for errors, suggestions for improving invalid ideas.
- **Deployment-Ready**: Configured for production with environment variables and support for platforms like PythonAnywhere.

## Tech Stack

- **Backend**: Flask (Python web framework)
- **Database**: SQLite (lightweight, file-based RDBMS)
- **Security**: Werkzeug (for password hashing)
- **AI Integration**: OpenRouter API (for validation, evaluation, and POML generation)
- **HTTP Requests**: Requests library
- **Environment Management**: python-dotenv (for loading `.env` files)
- **Frontend**: Jinja2 templates (HTML/CSS/JS – assumes basic Bootstrap or similar in templates)
- **Other**: JSON for data handling, re for regex validations

### Prerequisites

- Python 3.10 or higher
- pip (Python package installer)
- Virtual environment tool (e.g., venv)
- OpenRouter API account (for AI features) – sign up at [openrouter.ai](https://openrouter.ai)

## Configuration

- **API Key**: Required for AI features. Obtain from [openrouter.ai](https://openrouter.ai). If missing, AI validation falls back to keyword-based checks.
- **Database**: Path is absolute (`os.path.join(os.path.dirname(__file__), 'idea_evaluator.db')`) for reliability. For production scaling, consider migrating to PostgreSQL.
- **Model**: Defaults to "x-ai/grok-4-fast:free" – customizable in `app.py` by modifying the `MODEL` variable.

Update `app.py` for custom configurations, such as changing the AI model or adding logging for debugging.

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
3. **View Dashboard**: At `/dashboard`, see recent ideas, statistics (total ideas, average score, best score), and manage submissions.
4. **View/Delete Ideas**: Access individual ideas at `/idea/<id>`, delete via POST at `/idea/<id>/delete`.
5. **View POML**: If generated, view the POML document at `/poml/<id>`.

## Database Management

- **Schema**:
  - `users`: Stores user details (id, username, email, password_hash, created_at, last_login).
  - `ideas`: Stores idea details (id, user_id, title, description, overall_score, evaluation_data, poml_data, timestamps).
  - `evaluation_factors`: Normalized table for evaluation scores and analyses (linked to ideas via idea_id).

## AI Integration

- **Validation**: Combines rule-based checks (keywords, regex patterns for non-software ideas) and AI validation via OpenRouter to ensure ideas are software-related.
- **Evaluation**: Scores ideas on eight factors (0-10): innovation, market demand, feasibility, scalability, monetization potential, team/resource availability, time to market, and future trends.
- **POML Generation**: Produces a JSON-based POML document with tech stacks and development prompts, authored as "IDEAFORGE".
- **Error Handling**: Gracefully handles API failures by falling back to keyword validation or returning error messages.

Ensure your OpenRouter API key has sufficient credits for continuous usage.

## Acknowledgements

- [Flask](https://flask.palletsprojects.com/) for the lightweight web framework.
- [OpenRouter](https://openrouter.ai/) for AI API integration.
- [Python](https://www.python.org/) community for robust libraries.

Thank you for using IdeaForge! 🚀

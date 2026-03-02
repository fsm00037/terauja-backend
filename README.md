# Terauja Backend - Psychology Project

This is the backend service for the **Terauja** project, a specialized psychological management system. Built with **FastAPI** and **SQLModel**, it provides a robust API for psychologists and patients, integrating AI-driven assessment tools and real-time monitoring.

## 🚀 Overview

Terauja is designed to facilitate the interaction between psychologists and patients through digital tools. It features a multi-agent AI system for depression assessment, ecological momentary assessment (EMA) questionnaires, and a comprehensive management dashboard.

### Key Features
- **Authentication & Authorization**: Secure JWT-based authentication for psychologists, patients, and superadmins.
- **Patient Management**: Tools for psychologists to manage patient records, sessions, and clinical notes.
- **EMA Questionnaires**: Daily "Ecological Momentary Assessment" (EMA) for real-time mood and behavior tracking.
- **AI Assessment System**: Multi-agent LLM infrastructure (integration with OpenAI/Helmholtz) for analyzing clinical conversations and providing symptom evidence.
- **Real-time Chat**: Secure messaging between patients and therapists.
- **Superadmin Dashboard**: Advanced analytics, user management, and system logs.
- **Firebase Integration**: Leverages Firebase for cloud-based services and notifications.

## 🛠️ Technology Stack
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/)
- **Database/ORM**: [SQLModel](https://sqlmodel.tiangolo.com/) (SQLAlchemy + Pydantic)
- **Security**: OAuth2, JWT (python-jose), Bcrypt
- **AI/LLM**: OpenAI API, custom LLM services
- **Validation**: Pydantic v2
- **Utilities**: Firebase Admin SDK, APScheduler, Python-dotenv

## ⚙️ Installation & Setup

For detailed instructions on how to set up your local development environment, please refer to the [INSTALL.md](file:///c:/Users/UJA/Desktop/psicoluja/terauja-backend/INSTALL.md) file.

### Quick Start
1. Create a virtual environment: `python -m venv venv`
2. Install dependencies: `pip install -r requirements.txt`
3. Configure your `.env` file.
4. Run the application: `python main.py`

## 📖 API Documentation

Once the server is running, you can access the interactive API documentation at:
- **Swagger UI**: [http://localhost:8001/docs](http://localhost:8001/docs)
- **ReDoc**: [http://localhost:8001/redoc](http://localhost:8001/redoc)

## 📁 Project Structure
- `routers/`: API endpoints organized by domain (auth, patients, chat, etc.).
- `models/`: SQLModel database schemas and Pydantic models.
- `services/`: Business logic, including AI assessment, Firebase, and scheduling.
- `utils/`: Common helpers for logging, authentication, and error handling.
- `main.py`: Application entry point and lifespan configuration.

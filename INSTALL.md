# Installation Guide

Follow these steps to set up and run the Terauja Backend project locally.

## 📋 Prerequisites
- **Python 3.8** or higher
- **pip** (Python package installer)
- (Recommended) **SQLite** for development or **PostgreSQL** for production.

## 🛠️ Step-by-Step Setup

### 1. Create a Virtual Environment
It is highly recommended to use a virtual environment to manage dependencies and avoid conflicts.

```powershell
# On Windows
python -m venv venv

# Activate it
.\venv\Scripts\activate
```

```bash
# On macOS/Linux
python3 -m venv venv

# Activate it
source venv/bin/activate
```

### 2. Install Dependencies
Install all required packages listed in the `requirements.txt` file.

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Create a `.env` file in the root directory and add the necessary configuration. You can use the existing `.env` structure as a reference.

Important variables include:
- `OPENAI_API_KEY_PSICOUJA`: For AI features.
- `BASE_URL_MODELS_PSICOUJA`: API URL for the AI models.
- Database connection strings (if applicable).

### 4. Database Initialization
The application uses **SQLModel** and automatically initializes the database schema (and default superadmin users) on startup via the `lifespan` event in `main.py`.

### 5. Running the Application

There are two ways to start the server:

**Option A: Directly with Python**
```bash
python main.py
```

**Option B: Using Uvicorn (Recommended for Development)**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

The API will be available at [http://localhost:8001](http://localhost:8001).

## ✅ Verification
Check the health of the application by visiting:
- [http://localhost:8001/docs](http://localhost:8001/docs) to see the API documentation.
- The root endpoint [http://localhost:8001/](http://localhost:8001/) should return a "running" message.

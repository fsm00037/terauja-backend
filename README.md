# Psychology Project Backend

This is the backend service for the Psychology Project, built with FastAPI and SQLModel.

## Prerequisites
- Python 3.8 or higher

## Setup

1. **Create a Virtual Environment** (optional but recommended):
   ```bash
   python -m venv venv
   ```

2. **Activate the Virtual Environment**:
   - On Windows:
     ```powershell
     .\venv\Scripts\activate
     ```
   - On macOS/Linux:
     ```bash
     source venv/bin/activate
     ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Application

You can start the server using Python directly:

```bash
python main.py
```

Or run it using Uvicorn:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

The server will run on **http://localhost:8001**.

## API Documentation

Once the server is running, you can access the interactive API documentation at:

- **Swagger UI**: [http://localhost:8001/docs](http://localhost:8001/docs)
- **ReDoc**: [http://localhost:8001/redoc](http://localhost:8001/redoc)

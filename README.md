# AI Booking Agent - Python Service

Python-based AI agent for coordinating band bookings.

## Setup

### 1. Create Virtual Environment
```bash
python -m venv venv
.\venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
```bash
# Copy example env file
cp .env.example .env

# Edit .env and add your actual credentials:
# - Supabase URL and service key (from your Next.js project)
# - Anthropic or OpenAI API key
# - Email service API key
```

### 4. Set Up Database
Run the database migrations in Supabase (see `database/schema.sql`)

### 5. Run Locally
```bash
# Start FastAPI server
uvicorn app.main:app --reload --port 8000

# In another terminal, start Celery worker (for background jobs)
celery -A app.tasks.celery_app worker --loglevel=info
```

## Running the FastAPI Agent Locally

To start the FastAPI server for local development/testing:

1. Open a terminal and navigate to the agent directory:
   ```sh
   cd agent
   ```
2. Activate the Python virtual environment (Windows PowerShell):
   ```sh
   .\venv\Scripts\Activate.ps1
   ```
3. Start the FastAPI server:
   ```sh
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

- The API will be available at http://localhost:8000
- The interactive docs (if enabled) are at http://localhost:8000/docs

> **Note:** Always run uvicorn from inside the `agent` directory so the `app` module is found.

## Project Structure
```
agent/
├── app/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration
│   ├── api/                 # API routes
│   ├── agent/               # LangGraph agent
│   ├── services/            # External services
│   ├── models/              # Pydantic models
│   ├── tasks/               # Celery tasks
│   └── utils/               # Utilities
├── tests/                   # Test files
├── database/                # SQL migrations
├── .env                     # Environment variables (not in git)
└── requirements.txt         # Python dependencies
```


## API Endpoints & Email Triggers

- `GET /health` - Health check
- `POST /api/v1/chat` - Start conversation
   - **Email Trigger:**
      - If a user sends a message like "ask John what his availability is for July 4th", the agent will extract the band member and date, then send an availability request email to the band member using the configured agent name (e.g., "SickDay Agent").
      - The email is sent via Resend and includes a friendly, LLM-generated message.
- `POST /api/v1/bookings/inquiry` - Submit booking inquiry
- `POST /api/v1/webhooks/email` - Email webhook (for inbound email processing)

**Email Triggers:**
- Outbound: When the chat intent is to check a band member's availability for a specific date, the agent sends an email to the member.
- Inbound: (Planned) Incoming emails to agent@sickdaywithferris.band will be processed and matched to conversations.

See [API documentation](http://localhost:8000/docs) when running locally.

cd agent; .\venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8000

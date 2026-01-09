# Resend Webhook Signature Verification

**Important:** When verifying Resend (Svix) webhook signatures, use the webhook "Signing Secret" exactly as shown in the Resend dashboard. Do **not** base64-decode this value. The secret should be used as a UTF-8 string when computing the HMAC signature.

**Troubleshooting Signature Validation:**
- The secret should look like `whsec_...` and must match exactly (no extra spaces or characters).
- In your backend, the signature verification function should use `secret.encode('utf-8')` as the HMAC key.
- If you see errors like `Invalid base64-encoded string`, you are likely trying to base64-decode the secret—**this is incorrect** for Resend.
- After updating the secret in your Render environment, always redeploy your service.
- The signature header (`Svix-Signature`) may contain multiple signatures separated by spaces or semicolons; your code should check all `v1,` signatures.

For more details, see the [Resend webhook docs](https://resend.com/docs/webhooks#verifying-webhooks).


This Python agent is deployed on [Render](https://render.com/):

1. Push your code to GitHub.
2. Create a new Web Service on Render and connect your repository.
3. Set the build and start commands:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port 10000` (or your chosen port)
4. Add required environment variables in the Render dashboard (see `.env.example`).
5. Render will automatically build and deploy your service.

**Notes:**

For more details, see [Render's documentation](https://render.com/docs/deploy-python).
# Automated Email Replies

**New:** The agent now automatically replies to inbound emails received via the Resend webhook. When an email is sent to your band address, the backend will process it, generate a response using the AI agent, and send a reply via Resend.

**To enable this feature:**
- Make sure your deployment on Render is up to date with the latest code.
- Confirm your Resend webhook is pointed at your Render deployment's `/api/v1/webhooks/email` endpoint.
- All required environment variables for Resend and webhook secrets must be set in Render.

After deployment, test by sending an email to your band address and confirming you receive an automated reply.
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


**Email Triggers & Conversation Logic:**
- Outbound: When the chat intent is to check a band member's availability for a specific date, the agent sends an email to the member.
- Inbound: Incoming emails to agent@sickdaywithferris.band are processed and matched to conversations. The agent uses the following logic:
   - If the sender is not a band member, the **first message** in a conversation is always treated as a venue inquiry ("venue_inquiry").
   - For all **follow-up messages** in the same conversation, the agent uses AI intent classification to determine if the message is a negotiation, proposal, follow-up, or other type. This allows the agent to respond contextually to ongoing venue discussions (e.g., event details, negotiation, confirmation, etc.).
   - Only actual band members (recognized by their email) can trigger the band member availability request flow.
   - The agent always fills in the correct agent name ("Ferris") and attempts to extract and acknowledge dates from the initial inquiry.

See [API documentation](http://localhost:8000/docs) when running locally.

cd agent; .\venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8000

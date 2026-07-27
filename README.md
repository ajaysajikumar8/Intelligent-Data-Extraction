# Intelligent Data Extraction Pipeline

An automated multi-tenant AI ingestion engine that processes unstructured corporate data (emails, PDFs, images, chat logs, REST API calls) and extracts validated, structured JSON using Google Gemini.

→ [Architecture & Data Flow](docs/architecture.md) · [Deployment Guide](docs/deployment.md)

---

## Quick Start

### Prerequisites
- Python 3.10+, Node.js 18+, PostgreSQL 14+
- Gemini API Key — [Google AI Studio](https://aistudio.google.com/)

### 1. Environment

```bash
# Backend environment setup
cp backend/.env.example backend/.env

# Frontend environment setup
cp frontend/.env.example frontend/.env.local
```

### 2. Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. Database

```bash
npx prisma db push
```

### 4. Frontend

```bash
cd frontend
npm install && npm run dev
```

---

See [backend/.env.example](backend/.env.example) and [frontend/.env.example](frontend/.env.example) for environment variable templates.

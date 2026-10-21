# Digital Me

An AI twin with two modes:

- **Presentation mode** (public): talks about me, my work and how I think. Reads only the `public` corpus.
- **Companion mode** (private): me talking to myself when I'm low. Requires an API key, reads only the `private` corpus, and is never logged.

## 100% free stack (no Docker, no admin rights, no credit card)

| Piece | Service | Cost |
|---|---|---|
| Database + vectors | Neon Postgres with pgvector (neon.tech) | free tier |
| LLM | Groq (console.groq.com), OpenAI-compatible | free tier, rate-limited |
| Embeddings | fastembed, runs locally on CPU | free |
| Backend | FastAPI on your machine | free |

Free tiers have limits and can change. If Groq changes its models, set `LLM_MODEL` in `.env`
to any chat model listed at console.groq.com/docs/models. Any OpenAI-compatible provider works
by changing `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL`.

## Run it

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # then fill in DATABASE_URL, LLM_API_KEY, COMPANION_API_KEY
python -m scripts.seed      # loads data/ into the vector database
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs and try `POST /chat`.

Generate a value for COMPANION_API_KEY:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Layout

```
backend/app/
  main.py        routes, auth, rate limit
  rag.py         chunking, ingest, scoped retrieval (pgvector)
  guardrails.py  injection heuristics, output scrubbing, context fencing
  persona.py     system prompts for both modes (edit PERSONA to sound like you)
  llm.py         OpenAI-compatible chat call
  db.py / embeddings.py / config.py
backend/data/public/   safe to share, feeds Presentation mode
backend/data/private/  git-ignored, feeds Companion mode
docker-compose.yml     optional local Postgres if you ever have Docker
```

## How the privacy split works

Presentation and Companion mode never share rows. The `scope` filter is applied in the SQL
query (`rag.retrieve`), and the scope is chosen by the server from the mode, never from request
input. A visitor cannot ask their way into private data.

## Known limits (next steps)

- Auth is a single shared key. Replace with JWT/OAuth (step 2).
- Rate limiting is in-memory, so it only works for a single instance.
- Injection checks are regex heuristics; prompt fencing and scoped retrieval do the real work.
- Companion mode has a crisis instruction in the prompt but no dedicated detection yet.
- Companion notes live in your Neon database in the cloud. Fine for development; decide before
  storing very personal text.

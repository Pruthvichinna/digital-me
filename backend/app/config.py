from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = ""

    # Any OpenAI-compatible provider works (Groq, Gemini, OpenRouter, Ollama...).
    llm_api_key: str = ""
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "openai/gpt-oss-120b"

    # Local embeddings, free, runs on CPU. 384 dimensions.
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384

    companion_api_key: str = ""
    public_rate_limit_per_min: int = 20

    # Public-hosting controls
    app_env: str = "development"          # "production" hides /docs
    companion_enabled: bool = True        # set false on a public deployment
    public_daily_limit: int = 80          # total public chats per UTC day (protects free LLM quota)
    auth_fail_limit: int = 8              # wrong keys per IP per 10 minutes
    fastembed_cache: str = ""             # folder to cache the embedding model in

    # RAG tuning
    chunk_size: int = 800
    chunk_overlap: int = 120
    top_k: int = 5
    max_history_turns: int = 8
    max_message_chars: int = 2000


settings = Settings()

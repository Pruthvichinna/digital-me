"""Runs once at build time so the embedding model is already downloaded when the server starts."""
from app.embeddings import _model

_model()
print("Embedding model ready.")

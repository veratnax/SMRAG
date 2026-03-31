"""
Configuration file for the Text Matching Tool
"""
import os

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")  # Set via environment variable or Streamlit secrets

# Embedding Model
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSION = 3072  # text-embedding-3-large dimension

# LLM Model for Re-ranking
LLM_MODEL = "gpt-4.1-mini"

# Chunking Configuration (for PDF)
CHUNK_SIZE = 500  # tokens
CHUNK_OVERLAP = 50  # tokens

# Matching Configuration
DEFAULT_TOP_N = 3
MAX_TOP_N = 10
SEMANTIC_WEIGHT = 0.7
KEYWORD_WEIGHT = 0.3

# Query + Guidance optimization: embed guidance once per session, combine with each query embedding
# Weight of guidance in combined vector (rest is query). 0.3 = 30% guidance, 70% query.
GUIDANCE_EMBEDDING_WEIGHT = 0.3

# QA Configuration
QA_SAMPLE_SIZE = 50  # First N queries for QA

# Vector Store Configuration
VECTOR_STORE_PATH = "./data/chroma_db"
COLLECTION_NAME = "knowledge_base"

# File Upload Configuration
MAX_FILE_SIZE_MB = 100
ALLOWED_PDF_EXTENSIONS = [".pdf"]
ALLOWED_EXCEL_EXTENSIONS = [".xlsx", ".xls", ".csv"]

# Export Configuration
EXPORT_FOLDER = "./data/exports"

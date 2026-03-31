# System Architecture Documentation

## Overview

The Text Matching Tool is designed for two specific use cases:
1. Matching queries from Excel against PDF knowledge bases
2. Matching queries from Excel against Excel knowledge bases

## High-Level Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    User Interface Layer                     │
│                   (Streamlit Web App)                       │
│  - File Upload                                              │
│  - Configuration                                            │
│  - Results Display                                          │
│  - QA Interface                                             │
└──────────────────────┬─────────────────────────────────────┘
                       │
┌──────────────────────▼─────────────────────────────────────┐
│                  Application Layer                          │
│               (Matching Pipeline)                           │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐      │
│  │  PDF         │  │  Excel       │  │  Embedder   │      │
│  │  Processor   │  │  Processor   │  │  (OpenAI)   │      │
│  └──────────────┘  └──────────────┘  └─────────────┘      │
│                                                             │
└──────────────────────┬─────────────────────────────────────┘
                       │
┌──────────────────────▼─────────────────────────────────────┐
│                   Matching Layer                            │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐       │
│  │  Semantic   │  │  Keyword    │  │  Hybrid      │       │
│  │  Search     │  │  Search     │  │  Matcher     │       │
│  │  (Vector)   │  │  (BM25)     │  │              │       │
│  └─────────────┘  └─────────────┘  └──────────────┘       │
│                                                             │
│                   ┌──────────────┐                         │
│                   │  LLM         │                         │
│                   │  Reranker    │                         │
│                   │  (GPT-4)     │                         │
│                   └──────────────┘                         │
└──────────────────────┬─────────────────────────────────────┘
                       │
┌──────────────────────▼─────────────────────────────────────┐
│                   Storage Layer                             │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐       │
│  │  Vector DB  │  │  SQLite     │  │  File        │       │
│  │  (Chroma)   │  │  (QA Data)  │  │  Storage     │       │
│  └─────────────┘  └─────────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. User Interface Layer

**Technology**: Streamlit

**Components**:
- **Main App** (`app.py`): Orchestrates UI flow
- **File Uploaders**: Handle PDF and Excel uploads
- **Configuration Panel**: Sidebar for settings
- **Results Display**: Show matching results
- **QA Interface**: Interactive review system

**Key Features**:
- Real-time feedback during processing
- Progress indicators
- Export functionality
- Session state management

---

### 2. Processing Layer

#### 2.1 PDF Processor (`processors/pdf_processor.py`)

**Purpose**: Extract and chunk text from PDF files

**Key Methods**:
- `process_pdf()`: Main processing function
- `_clean_text()`: Text normalization
- `_chunk_text()`: Create overlapping chunks

**Chunking Strategy**:
```
Original Text: [Page 1 Text..................][Page 2 Text................]
                        ↓
Chunks:        [Chunk1: 500 words]
                    [Chunk2: 500 words (50 word overlap)]
                         [Chunk3: 500 words (50 word overlap)]
```

**Output Format**:
```python
{
    'text': "chunk text...",
    'page_number': 42,
    'chunk_id': "page_42_chunk_0"
}
```

#### 2.2 Excel Processor (`processors/excel_processor.py`)

**Purpose**: Parse Excel/CSV files for KB and queries

**Key Methods**:
- `load_excel()`: Load file
- `process_knowledge_base()`: Extract KB entries
- `process_queries()`: Extract queries
- `get_columns()`: List available columns

**KB Output Format**:
```python
{
    'key': "ENG-003",
    'definition': "Starter motor failure...",
    'row_number': 45,
    'entry_id': "row_44",
    'text': "ENG-003: Starter motor failure..."
}
```

#### 2.3 Embedder (`processors/embedder.py`)

**Purpose**: Generate embeddings via OpenAI API

**Model**: `text-embedding-3-large` (3072 dimensions)

**Key Methods**:
- `embed_text()`: Single text embedding
- `embed_batch()`: Batch processing (100 texts/batch)
- `cosine_similarity()`: Calculate similarity

**Batch Processing**:
```python
Texts: [text1, text2, ..., text1000]
         ↓
Batches: [batch1(100)] → API → embeddings1
         [batch2(100)] → API → embeddings2
         ...
         [batch10(100)] → API → embeddings10
         ↓
Output: [emb1, emb2, ..., emb1000]
```

---

### 3. Matching Layer

#### 3.1 Vector Store (`utils/vector_store.py`)

**Technology**: ChromaDB

**Purpose**: Store and retrieve embeddings

**Key Operations**:
- `create_collection()`: Initialize vector DB
- `add_documents()`: Store embeddings
- `search()`: Semantic similarity search

**Search Algorithm**:
```
Query Embedding: [0.12, -0.34, 0.56, ...]
                        ↓
Vector Database: [doc1_emb, doc2_emb, ..., docN_emb]
                        ↓
Cosine Similarity Calculation
                        ↓
Top-K Results: [(doc_id, similarity_score), ...]
```

#### 3.2 Keyword Searcher (`matching/keyword_search.py`)

**Algorithm**: BM25 (Best Match 25)

**Purpose**: Exact/fuzzy keyword matching

**How BM25 Works**:
1. Tokenize query and documents
2. Calculate term frequency (TF)
3. Calculate inverse document frequency (IDF)
4. Compute BM25 score:
   ```
   BM25(q,d) = Σ IDF(qi) * (f(qi,d) * (k1 + 1)) / (f(qi,d) + k1 * (1 - b + b * |d|/avgdl))
   ```

**Output**:
```python
{
    'document': {...},
    'bm25_score': 2.45,
    'index': 12
}
```

#### 3.3 Hybrid Matcher (`matching/hybrid_matcher.py`)

**Purpose**: Combine semantic and keyword results

**Algorithm**:
```
Semantic Results: [doc1: 0.92, doc2: 0.85, doc3: 0.78]
Keyword Results:  [doc2: 3.2, doc4: 2.1, doc1: 1.8]
                        ↓
Normalize Scores to [0, 1]
                        ↓
Semantic: [doc1: 1.0, doc2: 0.85, doc3: 0.65]
Keyword:  [doc2: 1.0, doc4: 0.66, doc1: 0.56]
                        ↓
Weighted Combination (0.7 semantic + 0.3 keyword)
                        ↓
Combined: [doc1: 0.87, doc2: 0.89, doc3: 0.46, doc4: 0.20]
                        ↓
Ranked Results: [doc2, doc1, doc3, doc4]
```

**Default Weights**:
- Semantic: 70%
- Keyword: 30%

#### 3.4 LLM Reranker (`matching/llm_reranker.py`)

**Model**: GPT-4

**Purpose**: Final relevance assessment

**Process**:
```
Input: Query + Top 10 Hybrid Results
         ↓
Prompt Engineering:
  "Given query: '...'
   Rank these candidates by relevance:
   1. [text snippet]
   2. [text snippet]
   ..."
         ↓
GPT-4 Analysis
         ↓
Output: {
  "rankings": [3, 1, 7, 2, ...],
  "relevance_scores": [95, 88, 82, ...],
  "reasoning": "Candidate 3 directly answers..."
}
         ↓
Final Ranked Results
```

**Benefits**:
- Understands context and nuance
- Can reason about relevance
- Improves accuracy by ~15-20%

---

### 4. QA System

#### 4.1 Feedback Store (`qa/feedback_store.py`)

**Technology**: SQLite

**Database Schema**:
```sql
CREATE TABLE qa_feedback (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    query_id TEXT,
    query TEXT,
    match_rank INTEGER,
    match_id TEXT,
    match_text TEXT,
    status TEXT,  -- 'accepted', 'rejected', 'edited', 'skipped'
    notes TEXT,
    timestamp TEXT
);

CREATE TABLE qa_sessions (
    session_id TEXT PRIMARY KEY,
    use_case TEXT,
    total_queries INTEGER,
    completed_queries INTEGER,
    created_at TEXT,
    updated_at TEXT
);
```

**Workflow**:
```
User Reviews Match → Accept/Reject → Store in SQLite
                                           ↓
                                    Update Progress
                                           ↓
                                    Calculate Stats
                                           ↓
                                    Export Feedback
```

---

## Data Flow

### Use Case 1: PDF KB → Excel Queries

```
1. Upload PDF
      ↓
2. Extract Text by Page (PyMuPDF)
      ↓
3. Chunk Text (500 tokens, 50 overlap)
      ↓
4. Generate Embeddings (OpenAI API)
      ↓
5. Store in Vector DB (ChromaDB)
      ↓
6. Index for Keywords (BM25)
      ↓
7. Upload Query Excel
      ↓
8. For Each Query:
      ├─ Generate Query Embedding
      ├─ Semantic Search (Vector DB) → Top 20
      ├─ Keyword Search (BM25) → Top 20
      ├─ Hybrid Matching → Combined Top 10
      ├─ LLM Reranking (Optional) → Final Top N
      └─ Format Results with Page Numbers
      ↓
9. Export to Excel / QA Review
```

### Use Case 2: Excel KB → Excel Queries

```
1. Upload KB Excel
      ↓
2. Extract Key-Value Pairs
      ↓
3. Generate Embeddings for Each Entry
      ↓
4. Store in Vector DB
      ↓
5. Index for Keywords
      ↓
6. Upload Query Excel
      ↓
7. For Each Query:
      ├─ Generate Query Embedding
      ├─ Semantic Search → Top 20
      ├─ Keyword Search → Top 20
      ├─ Hybrid Matching → Combined Top 10
      ├─ LLM Reranking (Optional) → Final Top N
      └─ Format Results with Keys & Definitions
      ↓
8. Export to Excel / QA Review
```

---

## Performance Characteristics

### Processing Times

**PDF Processing**:
- 100 pages: ~30 seconds
- 1000 pages: ~3-5 minutes
- 2000 pages: ~8-10 minutes

**Excel KB Processing**:
- 100 rows: ~15 seconds
- 1000 rows: ~1-2 minutes
- 5000 rows: ~5-8 minutes

**Query Processing**:
- 10 queries: ~10 seconds
- 100 queries: ~1-2 minutes (without LLM)
- 100 queries: ~3-5 minutes (with LLM)

### Scalability

**Limitations**:
- PDF size: Tested up to 5000 pages
- Excel rows: Tested up to 10,000 rows
- Concurrent queries: Sequential processing
- Memory: ~2GB for 2000-page PDF

**Optimizations**:
- Batch embedding generation (100 texts/batch)
- Vector DB indexing for fast retrieval
- Caching of embeddings
- Rate limiting for API calls

---

## Security & Privacy

**API Keys**:
- Stored in session state (not persisted)
- Never logged or saved to disk
- User responsible for key security

**Data Storage**:
- Local SQLite database
- Local ChromaDB vector store
- Temporary file storage in ./data/
- No cloud storage by default

**Data Privacy**:
- All processing happens locally
- Only API calls go to OpenAI
- No data retention on OpenAI's end (zero data retention policy)

---

## Extension Points

### Adding New Search Algorithms

```python
# In matching/custom_search.py
class CustomSearcher:
    def search(self, query, top_k):
        # Your algorithm
        return results

# In matching_pipeline.py
from matching.custom_search import CustomSearcher
self.custom_searcher = CustomSearcher()
```

### Custom Weighting

```python
# In config.py
SEMANTIC_WEIGHT = 0.6
KEYWORD_WEIGHT = 0.3
CUSTOM_WEIGHT = 0.1

# In matching/hybrid_matcher.py
# Add custom score to combination
```

### Alternative Embeddings

```python
# In processors/embedder.py
class SentenceBERTEmbedder:
    def __init__(self):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
    
    def embed_text(self, text):
        return self.model.encode(text)
```

---

## Error Handling

**PDF Processing**:
- Corrupted PDFs: Try-catch with error message
- OCR needed: User notification
- Memory errors: Batch processing suggestion

**API Errors**:
- Rate limits: Exponential backoff
- Invalid key: Clear error message
- Timeouts: Retry logic (3 attempts)

**Data Errors**:
- Empty columns: Skip with warning
- Missing values: Filter out
- Invalid file formats: Pre-upload validation

---

## Testing Strategy

**Unit Tests**: Test individual components
- PDF chunking accuracy
- Embedding generation
- BM25 scoring
- Hybrid combination math

**Integration Tests**: Test pipeline end-to-end
- Sample PDF → Queries → Results
- Sample Excel KB → Queries → Results

**Performance Tests**: Measure processing times
- Various PDF sizes
- Different query volumes
- Memory usage profiling

**Accuracy Tests**: Evaluate match quality
- Manual ground truth labeling
- Precision/Recall metrics
- A/B testing with/without LLM

---

## Monitoring & Logging

**Current Logging**:
- Print statements for progress
- Error messages to stderr
- Processing statistics

**Recommended Additions**:
- Structured logging (JSON)
- Performance metrics
- API usage tracking
- Error rate monitoring

---

## Future Enhancements

1. **Batch Query Processing**: Parallel processing for faster results
2. **Fine-tuning**: Custom embedding models trained on user data
3. **Active Learning**: Use QA feedback to improve matching
4. **Multi-modal**: Support for images in PDFs
5. **Cloud Deployment**: Deploy on AWS/GCP/Azure
6. **API Mode**: REST API for integration
7. **Advanced QA**: Machine learning for auto-QA
8. **Collaborative**: Multi-user QA sessions

---

## References

- ChromaDB: https://docs.trychroma.com/
- OpenAI Embeddings: https://platform.openai.com/docs/guides/embeddings
- BM25 Algorithm: https://en.wikipedia.org/wiki/Okapi_BM25
- Streamlit: https://docs.streamlit.io/

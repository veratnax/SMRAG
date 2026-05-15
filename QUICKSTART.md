# Quick Start Guide

## Setup (5 minutes)

### 1. Install dependencies

**Python** (virtual environment recommended):

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Frontend** (Node.js 18+):

```bash
cd frontend && npm install && cd ..
```

See `requirements.txt` for Python packages (pandas, openpyxl, PyMuPDF, ChromaDB, OpenAI client, FastAPI, Uvicorn, etc.).

### 2. Get an OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Copy and save it securely

Optional: enter Anthropic / Google keys on login if you use Claude / Gemini for the query LLM.

### 3. Run the application

From the project root:

```bash
./start.sh
```

- **Web UI:** http://localhost:5173  
- **API:** http://localhost:8000  

Alternatively, run backend and frontend separately:

```bash
# Terminal 1 — backend
source .venv/bin/activate
uvicorn api:app --host 0.0.0.0 --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev
```

During development the React app proxies `/api/*` to the backend (`frontend/vite.config.js`).

---

## First Run - Excel to Excel Example

### Step 1: Prepare Your Files

**Knowledge Base Excel** (e.g., `failure_modes.xlsx`):
```
| Failure_Code | Description                     |
|--------------|---------------------------------|
| ENG-001      | Engine overheating issue        |
| ENG-002      | Starter motor failure           |
| FUEL-001     | Fuel pump malfunction           |
```

**Query Excel** (e.g., `complaints.xlsx`):
```
| Complaint                          |
|------------------------------------|
| Engine running too hot             |
| Car won't start, clicking noise    |
| Engine sputtering, loss of power   |
```

### Step 2: In the application

1. Open **http://localhost:5173**
2. Enter your **OpenAI API key** (and optional keys) → **Start Session**
3. Choose **Excel KB → Excel Queries** (sidebar)
4. Upload the knowledge-base file → select Key / Definition columns → **Process Knowledge Base**
5. Upload the query file → select **Query** column (and PK / tag columns if needed)
6. Run **Process First N & Start QA**, complete QA / learnings as needed, then use **estimate & process remaining** or full-file flow when prompted
7. **Export** results to Excel from the results view

---

## First Run - PDF to Excel Example

### Step 1: Prepare Your Files

**PDF Knowledge Base:** any text-extractable PDF (e.g., maintenance manual)

**Query Excel** (e.g., `questions.xlsx`):
```
| Question                                      |
|-----------------------------------------------|
| What is the torque specification for bolts?   |
| How often should oil be changed?              |
| What are the safety procedures?               |
```

### Step 2: In the application

1. **Start Session** with your API key(s)
2. Choose **PDF KB → Excel Queries**
3. Upload PDF → optional chunking options → **Process Knowledge Base**
4. Upload queries, select columns, run sample QA / full processing, then export

---

## Tips for Best Results

### Excel knowledge base

- Keep definitions concise but descriptive  
- Include relevant keywords  
- Use consistent terminology  

### PDF knowledge base

- OCR scanned PDFs first if needed  
- Large PDFs can take several minutes  

### Matching parameters

- Adjust **matches per query** and **match count mode** in the sidebar  
- **LLM re-ranking** and **query expansion** improve quality (cost estimates before large runs)  

### QA review

- Use the sample batch to validate before processing the whole file  
- Apply learnings, then optionally re-score the sample or process remaining rows  

---

## Cost expectations

Costs depend on embeddings, expansion, rerank model, and file size—use **estimate cost** in the UI before large runs when offered.

---

## Troubleshooting

### Cannot reach backend / stuck loading

- Ensure Uvicorn is on **port 8000** (`./start.sh` or `uvicorn api:app --port 8000`)
- Inspect `logs/backend.log`

### Session not found / upload failures after restart

- The API keeps sessions **in memory**; restarting the server clears them → **Start Session** again and re-upload  

### Module not found

```bash
pip install -r requirements.txt
```

### Frontend issues

```bash
cd frontend && rm -rf node_modules && npm install && npm run dev
```

---

## Next steps

1. Run `python test.py` for a pipeline sanity check  
2. Process your own data through the UI  
3. Read **ARCHITECTURE.md** for components and APIs  

**Happy matching!** 🚀

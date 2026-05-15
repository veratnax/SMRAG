# Text Matching Tool v2.0 🚀

AI-powered text matching with intelligent chunking, QA learning, and adaptive matching.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
./start.sh
```

- **Frontend:** http://localhost:5173 — React (Vite)
- **Backend API:** http://localhost:8000 — FastAPI (Uvicorn)

The backend is also started with `nohup`, so it keeps running if you close the terminal; see `logs/backend.log`.

See **QUICKSTART.md** for a detailed walkthrough.

## New in v2.0

✨ **Intelligent PDF Chunking** - LLM analyzes structure automatically  
✨ **QA Learning** - System improves from your feedback (15-25% accuracy boost)  
✨ **QA-First Workflow** - Review 50 queries before processing all  

## Documentation

- README_FULL.md - Complete documentation
- QUICKSTART.md - 5-minute guide  
- QA_LEARNING_IMPLEMENTATION.md - Learning system details
- ARCHITECTURE.md - Technical deep-dive

**Ready to match!** 🚀

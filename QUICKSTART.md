# Quick Start Guide

## Setup (5 minutes)

### 1. Install Dependencies

```bash
pip install streamlit pandas openpyxl pymupdf chromadb openai rank-bm25 numpy sentence-transformers
```

Or use the requirements file:
```bash
pip install -r requirements.txt
```

### 2. Get OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Copy and save it securely

### 3. Run the Application

```bash
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`

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

### Step 2: In the Application

1. **Enter API Key** in the sidebar
2. **Select**: "Excel Knowledge Base → Excel Queries"
3. **Upload Knowledge Base**: Upload `failure_modes.xlsx`
   - Select "Failure_Code" as Key Column
   - Select "Description" as Definition Column
4. **Click**: "Process Knowledge Base"
5. **Upload Queries**: Upload `complaints.xlsx`
   - Select "Complaint" as Query Column
6. **Click**: "Start Matching"
7. **View Results** and **Export to Excel**

---

## First Run - PDF to Excel Example

### Step 1: Prepare Your Files

**PDF Knowledge Base**: Any PDF document (e.g., maintenance manual)

**Query Excel** (e.g., `questions.xlsx`):
```
| Question                                      |
|-----------------------------------------------|
| What is the torque specification for bolts?   |
| How often should oil be changed?              |
| What are the safety procedures?               |
```

### Step 2: In the Application

1. **Enter API Key** in the sidebar
2. **Select**: "PDF Knowledge Base → Excel Queries"
3. **Upload PDF**: Upload your PDF file (may take 1-2 minutes for large files)
4. **Upload Queries**: Upload `questions.xlsx`
   - Select "Question" as Query Column
5. **Click**: "Start Matching"
6. **View Results** with page numbers
7. **Export to Excel**

---

## Tips for Best Results

### For Excel Knowledge Base
- Keep definitions concise but descriptive
- Include relevant keywords in definitions
- Use consistent terminology

### For PDF Knowledge Base
- OCR scanned PDFs first if needed
- Works best with well-formatted PDFs
- Large PDFs (1000+ pages) may take 5-10 minutes to process

### Matching Parameters
- **Start with 3 matches per query** (default)
- **Enable LLM Re-ranking** for best accuracy (costs ~$0.001 per query)
- **Increase matches to 5-10** if you need more options

### QA Review
- Use QA mode to validate accuracy on first 50 queries
- Accept/reject matches to build ground truth
- Export QA feedback for analysis

---

## Cost Expectations

**For 100 queries:**
- Against 2000-page PDF: ~$0.20
- Against 500-row Excel: ~$0.05

**Cost breakdown:**
- Embeddings: ~$0.07 per 2000-page PDF
- LLM re-ranking: ~$0.001 per query (optional)

---

## Troubleshooting

### "Module not found"
```bash
pip install -r requirements.txt
```

### "API key invalid"
- Check you copied the full key
- Ensure key has sufficient credits
- Try creating a new key

### "Out of memory" (large PDFs)
- Process in batches
- Close other applications
- Use a machine with more RAM (8GB+ recommended)

### Results not accurate
- Enable LLM re-ranking
- Increase number of matches
- Try rephrasing queries to be more specific

---

## Next Steps

1. ✅ Try the test script: `python test.py`
2. ✅ Process your first real dataset
3. ✅ Use QA mode to validate accuracy
4. ✅ Export and analyze results
5. ✅ Adjust weights in `config.py` if needed

---

## Support

- Read the full README.md for detailed documentation
- Check config.py for advanced settings
- Review code comments for implementation details

**Happy matching!** 🚀

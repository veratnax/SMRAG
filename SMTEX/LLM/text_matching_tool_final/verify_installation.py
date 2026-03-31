#!/usr/bin/env python3
"""
Installation Verification Script
Run this after installation to verify everything is set up correctly
"""

print("=" * 60)
print("Text Matching Tool v2.0 - Installation Verification")
print("=" * 60)

# Check Python version
import sys
print(f"\n1. Python Version: {sys.version}")
if sys.version_info < (3, 8):
    print("   ❌ ERROR: Python 3.8+ required")
    sys.exit(1)
else:
    print("   ✅ Python version OK")

# Check dependencies
print("\n2. Checking Dependencies...")

dependencies = {
    'streamlit': 'streamlit',
    'pandas': 'pandas',
    'openpyxl': 'openpyxl',
    'fitz': 'pymupdf',
    'chromadb': 'chromadb',
    'openai': 'openai',
    'rank_bm25': 'rank-bm25',
    'numpy': 'numpy'
}

missing = []
for module, package in dependencies.items():
    try:
        __import__(module)
        print(f"   ✅ {package}")
    except ImportError:
        print(f"   ❌ {package} - MISSING")
        missing.append(package)

if missing:
    print(f"\n   Missing packages: {', '.join(missing)}")
    print(f"   Install with: pip install {' '.join(missing)}")
    sys.exit(1)

# Check project structure
print("\n3. Checking Project Structure...")

import os
from pathlib import Path

required_files = [
    'app.py',
    'matching_pipeline.py',
    'config.py',
    'requirements.txt',
    'processors/pdf_processor.py',
    'processors/excel_processor.py',
    'processors/embedder.py',
    'processors/intelligent_chunker.py',
    'matching/keyword_search.py',
    'matching/hybrid_matcher.py',
    'matching/llm_reranker.py',
    'qa/feedback_store.py',
    'qa/qa_learner.py',
    'utils/vector_store.py',
    'utils/export.py'
]

missing_files = []
for file_path in required_files:
    if Path(file_path).exists():
        print(f"   ✅ {file_path}")
    else:
        print(f"   ❌ {file_path} - MISSING")
        missing_files.append(file_path)

if missing_files:
    print(f"\n   Missing files: {', '.join(missing_files)}")
    print("   Please ensure all files are extracted correctly")
    sys.exit(1)

# Check directories
print("\n4. Checking Directories...")
required_dirs = ['data', 'processors', 'matching', 'qa', 'utils']
for dir_name in required_dirs:
    dir_path = Path(dir_name)
    if not dir_path.exists():
        print(f"   Creating {dir_name}/")
        dir_path.mkdir(parents=True, exist_ok=True)
    print(f"   ✅ {dir_name}/")

# Test imports
print("\n5. Testing Module Imports...")
try:
    from processors import PDFProcessor, ExcelProcessor, Embedder, IntelligentChunker
    print("   ✅ Processors")
    
    from matching import KeywordSearcher, HybridMatcher, LLMReranker
    print("   ✅ Matching")
    
    from qa import QAFeedbackStore, QALearner
    print("   ✅ QA")
    
    from utils import VectorStore, ResultExporter
    print("   ✅ Utils")
    
    from matching_pipeline import MatchingPipeline
    print("   ✅ MatchingPipeline")
    
except Exception as e:
    print(f"   ❌ Import error: {str(e)}")
    sys.exit(1)

# Final check
print("\n" + "=" * 60)
print("✅ Installation Verified Successfully!")
print("=" * 60)
print("\nNext Steps:")
print("1. Get your OpenAI API key from https://platform.openai.com/api-keys")
print("2. Run: streamlit run app.py")
print("3. Enter your API key in the sidebar")
print("4. Upload your files and start matching!")
print("\nSee QUICKSTART.md for a detailed walkthrough.")
print("\nHappy matching! 🚀")

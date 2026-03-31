"""
Quick Test Script
Tests basic functionality of the matching pipeline
"""
import os
from matching_pipeline import MatchingPipeline
from processors import ExcelProcessor


def test_excel_kb():
    """Test Excel KB use case with sample data"""
    
    print("=" * 50)
    print("Testing Excel Knowledge Base Use Case")
    print("=" * 50)
    
    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY environment variable not set")
        print("Please set it with: export OPENAI_API_KEY='your-key-here'")
        return
    
    print("\n1. Creating sample knowledge base Excel...")
    
    # Create sample KB
    import pandas as pd
    kb_data = {
        'Code': ['ERR-001', 'ERR-002', 'ERR-003'],
        'Description': [
            'System fails to start due to power supply issue',
            'Network connection timeout error',
            'Database connection refused'
        ]
    }
    kb_df = pd.DataFrame(kb_data)
    kb_path = './data/test_kb.xlsx'
    kb_df.to_excel(kb_path, index=False)
    print(f"   Created: {kb_path}")
    
    print("\n2. Creating sample query Excel...")
    
    # Create sample queries
    query_data = {
        'Query': [
            'System won\'t boot up, no power',
            'Cannot connect to network',
            'Database error when starting'
        ]
    }
    query_df = pd.DataFrame(query_data)
    query_path = './data/test_queries.xlsx'
    query_df.to_excel(query_path, index=False)
    print(f"   Created: {query_path}")
    
    print("\n3. Initializing pipeline...")
    pipeline = MatchingPipeline(api_key)
    
    print("\n4. Setting up knowledge base...")
    stats = pipeline.setup_excel_knowledge_base(
        kb_path,
        key_column='Code',
        value_column='Description'
    )
    print(f"   Processed {stats['entries_processed']} entries")
    print(f"   Created {stats['embeddings_created']} embeddings")
    
    print("\n5. Processing queries...")
    results = pipeline.process_queries(
        query_path,
        query_column='Query',
        top_n=2,
        use_llm_reranking=False  # Disable to save costs in test
    )
    
    print(f"\n6. Results for {len(results)} queries:")
    print("-" * 50)
    
    for i, result in enumerate(results, 1):
        print(f"\nQuery {i}: {result['query']}")
        print(f"Matches found: {result['num_matches']}")
        
        for match in result['matches']:
            print(f"  - Rank {match['rank']}: {match['key']}")
            print(f"    Score: {match['combined_score']:.3f}")
            print(f"    Definition: {match['definition'][:100]}...")
    
    print("\n" + "=" * 50)
    print("Test completed successfully!")
    print("=" * 50)


def check_dependencies():
    """Check if all dependencies are installed"""
    
    print("Checking dependencies...")
    
    required = [
        'streamlit',
        'pandas',
        'openpyxl',
        'fitz',  # pymupdf
        'chromadb',
        'openai',
        'rank_bm25',
        'numpy'
    ]
    
    missing = []
    
    for package in required:
        try:
            __import__(package)
            print(f"  ✓ {package}")
        except ImportError:
            print(f"  ✗ {package} - MISSING")
            missing.append(package)
    
    if missing:
        print(f"\nMissing packages: {', '.join(missing)}")
        print("Install with: pip install -r requirements.txt")
        return False
    
    print("\nAll dependencies installed!")
    return True


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("Text Matching Tool - Quick Test")
    print("=" * 50 + "\n")
    
    if check_dependencies():
        print("\n")
        test_excel_kb()
    else:
        print("\nPlease install missing dependencies first.")

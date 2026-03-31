"""
Text Matching Tool - Streamlit Application
Main UI for the matching system
"""
import streamlit as st
import os
from datetime import datetime
import pandas as pd
from matching_pipeline import MatchingPipeline
from processors import ExcelProcessor
from utils.export import ResultExporter
from qa.feedback_store import QAFeedbackStore
from config import QA_SAMPLE_SIZE, MAX_TOP_N, DEFAULT_TOP_N
import uuid
import json


# Page configuration
st.set_page_config(
    page_title="Text Matching Tool",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'pipeline' not in st.session_state:
    st.session_state.pipeline = None
if 'results' not in st.session_state:
    st.session_state.results = None
if 'qa_mode' not in st.session_state:
    st.session_state.qa_mode = False
if 'qa_index' not in st.session_state:
    st.session_state.qa_index = 0
if 'qa_session_id' not in st.session_state:
    st.session_state.qa_session_id = None
if 'kb_processed' not in st.session_state:
    st.session_state.kb_processed = False
if 'matching_stage' not in st.session_state:
    # idle -> sample_done -> all_done
    st.session_state.matching_stage = 'idle'
if 'total_queries' not in st.session_state:
    st.session_state.total_queries = 0
if 'remaining_offset' not in st.session_state:
    st.session_state.remaining_offset = 0
if 'pending_query_path' not in st.session_state:
    st.session_state.pending_query_path = None
if 'pending_query_column' not in st.session_state:
    st.session_state.pending_query_column = None
if 'pending_top_n' not in st.session_state:
    st.session_state.pending_top_n = None
if 'pending_use_llm_reranking' not in st.session_state:
    st.session_state.pending_use_llm_reranking = None
if 'pending_matching_guidance' not in st.session_state:
    st.session_state.pending_matching_guidance = None


def reset_session_state():
    """Reset all session state variables for a fresh start"""
    keys_to_reset = [
        'pipeline', 'results', 'qa_mode', 'qa_index', 'qa_session_id', 
        'kb_processed', 'matching_stage', 'total_queries', 'remaining_offset',
        'pending_query_path', 'pending_query_column', 'pending_top_n', 
        'pending_use_llm_reranking', 'pending_matching_guidance'
    ]
    for key in keys_to_reset:
        if key in st.session_state:
            del st.session_state[key]


def main():
    st.title("🔍 Text Matching Tool")
    st.markdown("Match queries against knowledge bases using AI-powered semantic and keyword search")
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # API Key input
        api_key = st.text_input(
            "OpenAI API Key",
            type="password",
            help="Enter your OpenAI API key"
        )
        
        if not api_key:
            st.warning("⚠️ Please enter your OpenAI API key to continue")
            st.stop()
        
        st.markdown("---")
        
        # Use case selection
        use_case = st.radio(
            "Select Use Case",
            options=["PDF Knowledge Base → Excel Queries", 
                    "Excel Knowledge Base → Excel Queries"],
            help="Choose your matching scenario"
        )
        
        st.markdown("---")
        
        # Matching parameters
        st.subheader("Matching Parameters")
        top_n = st.slider(
            "Number of matches per query",
            min_value=1,
            max_value=MAX_TOP_N,
            value=DEFAULT_TOP_N,
            help="How many matches to return for each query"
        )
        
        use_llm_reranking = st.checkbox(
            "Use LLM Re-ranking",
            value=True,
            help="Use GPT-4 to re-rank results for better relevance"
        )
        
        matching_guidance = st.text_area(
            "Matching Guidance (Optional)",
            placeholder="e.g., Prefer exact ATA chapter alignment over general semantic similarity.",
            help="Small prompt describing how matches should be judged."
        )
    
    # Main content area
    if use_case == "PDF Knowledge Base → Excel Queries":
        handle_pdf_use_case(api_key, top_n, use_llm_reranking, matching_guidance)
    else:
        handle_excel_use_case(api_key, top_n, use_llm_reranking, matching_guidance)


def handle_pdf_use_case(api_key: str, top_n: int, use_llm_reranking: bool, matching_guidance: str):
    """Handle PDF KB + Excel Queries use case"""
    
    st.header("📄 PDF Knowledge Base → Excel Queries")
    
    # Step 1: Upload PDF
    st.subheader("Step 1: Upload Knowledge Base (PDF)")
    pdf_file = st.file_uploader(
        "Upload PDF file (e.g., maintenance manual)",
        type=['pdf'],
        key="pdf_upload"
    )
    
    if pdf_file and not st.session_state.kb_processed:
        # Chunking options
        with st.expander("⚙️ Chunking Options", expanded=True):
            use_intelligent = st.checkbox(
                "🧠 Use Intelligent Chunking (Recommended)",
                value=True,
                help="Let AI analyze your PDF structure and chunk intelligently"
            )
            
            if use_intelligent:
                user_context = st.text_area(
                    "Knowledge Base Context Prompt (Optional)",
                    placeholder="e.g., Aircraft maintenance manual with ATA codes and procedures",
                    help="Describe the domain so chunking and embeddings focus on the right context",
                    height=80
                )
            else:
                user_context = None
                st.info("Using fixed-size chunking (500 tokens with 50 token overlap)")
        
        # Save uploaded file
        pdf_path = f"./data/{pdf_file.name}"
        with open(pdf_path, "wb") as f:
            f.write(pdf_file.getbuffer())
        
        if st.button("🚀 Process PDF", type="primary", use_container_width=True):
            with st.spinner("Processing PDF... This may take a few minutes."):
                try:
                    # Initialize pipeline
                    st.session_state.pipeline = MatchingPipeline(api_key)
                    
                    # Process PDF with selected chunking strategy
                    stats = st.session_state.pipeline.setup_pdf_knowledge_base(
                        pdf_path,
                        use_intelligent_chunking=use_intelligent,
                        user_context=user_context if use_intelligent else None,
                        kb_context_prompt=user_context if user_context else None
                    )
                    
                    st.success("✅ PDF processed successfully!")
                    
                    # Show chunking strategy if intelligent
                    if use_intelligent and 'chunking_strategy' in stats:
                        strategy = stats['chunking_strategy']
                        with st.expander("📊 Detected Document Structure"):
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write(f"**Document Type:** {strategy.get('document_type', 'Unknown')}")
                                st.write(f"**Chunking Strategy:** {strategy.get('recommended_strategy', 'Unknown')}")
                                st.write(f"**Has Sections:** {'Yes' if strategy.get('has_clear_sections') else 'No'}")
                            with col2:
                                st.write(f"**Chunk Size:** {strategy.get('recommended_chunk_size', 'N/A')} tokens")
                                st.write(f"**Overlap:** {strategy.get('recommended_overlap', 'N/A')} tokens")
                            
                            if strategy.get('reasoning'):
                                st.info(f"💡 {strategy['reasoning']}")
                    
                    # Show statistics
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Chunks", stats.get('total_chunks', 'N/A'))
                    with col2:
                        st.metric("Avg Chunk Size", f"{stats.get('avg_chunk_size_words', 0):.0f} words")
                    with col3:
                        st.metric("Embeddings Created", stats['embeddings_created'])
                    
                    if stats.get('embeddings_failed', 0) > 0:
                        st.warning(
                            f"⚠️ {stats['embeddings_failed']} chunks could not be embedded and were skipped. "
                            "Semantic matching quality may be reduced."
                        )
                    
                    st.session_state.kb_processed = True
                    
                except Exception as e:
                    st.error(f"Error processing PDF: {str(e)}")
                    return
    
    # Step 2: Upload Queries
    if st.session_state.kb_processed:
        st.subheader("Step 2: Upload Queries (Excel)")
        
        query_file = st.file_uploader(
            "Upload Excel file with queries",
            type=['xlsx', 'xls', 'csv'],
            key="query_upload"
        )
        
        if query_file:
            # Save uploaded file
            query_path = f"./data/{query_file.name}"
            with open(query_path, "wb") as f:
                f.write(query_file.getbuffer())
            
            # Load and preview
            excel_proc = ExcelProcessor()
            excel_proc.load_excel(query_path)
            
            st.write("**Query File Preview:**")
            st.dataframe(excel_proc.preview_data(), use_container_width=True)
            
            # Column selection
            columns = excel_proc.get_columns()
            query_column = st.selectbox(
                "Select query column",
                options=columns,
                help="Column containing the queries"
            )
            
            # Process button
            # Process button (QA-first: run first 50, then gate the rest)
            if st.button("🚀 Process First 50 & Start QA Review", type="primary", use_container_width=True):
                # Figure out total query count first (avoid double processing)
                all_queries = excel_proc.process_queries(query_column)
                st.session_state.total_queries = len(all_queries)
                
                with st.spinner(f"Processing first {min(QA_SAMPLE_SIZE, st.session_state.total_queries)} queries..."):
                    try:

                        # Run only the first QA_SAMPLE_SIZE queries
                        results = st.session_state.pipeline.process_queries(
                            query_path,
                            query_column,
                            top_n=top_n,
                            use_llm_reranking=use_llm_reranking,
                            query_offset=0,
                            query_limit=QA_SAMPLE_SIZE,
                            matching_guidance=matching_guidance
                        )

                        st.session_state.results = results
                        st.session_state.matching_stage = 'sample_done'
                        st.session_state.remaining_offset = len(results)
                        st.session_state.pending_query_path = query_path
                        st.session_state.pending_query_column = query_column
                        st.session_state.pending_top_n = top_n
                        st.session_state.pending_use_llm_reranking = use_llm_reranking
                        st.session_state.pending_matching_guidance = matching_guidance

                        # Initialize QA session
                        st.session_state.qa_session_id = str(uuid.uuid4())
                        qa_store = QAFeedbackStore()
                        qa_store.create_session(
                            st.session_state.qa_session_id,
                            "pdf_kb",
                            len(results)
                        )

                        # Auto-enter QA
                        st.session_state.qa_mode = True
                        st.session_state.qa_index = 0

                        st.success(f"✅ Processed first {len(results)} of {st.session_state.total_queries} queries. Starting QA...")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error processing queries: {str(e)}")

    
    # Step 3: View Results
    if st.session_state.results:
        display_results(st.session_state.results, "pdf_kb", top_n)


def handle_excel_use_case(api_key: str, top_n: int, use_llm_reranking: bool, matching_guidance: str):
    """Handle Excel KB + Excel Queries use case"""
    
    st.header("📊 Excel Knowledge Base → Excel Queries")
    
    # Step 1: Upload KB Excel
    st.subheader("Step 1: Upload Knowledge Base (Excel)")
    kb_file = st.file_uploader(
        "Upload Excel file (e.g., failure modes dictionary)",
        type=['xlsx', 'xls', 'csv'],
        key="kb_upload"
    )
    
    if kb_file and not st.session_state.kb_processed:
        # Save uploaded file
        kb_path = f"./data/{kb_file.name}"
        with open(kb_path, "wb") as f:
            f.write(kb_file.getbuffer())
        
        # Load and preview
        excel_proc = ExcelProcessor()
        excel_proc.load_excel(kb_path)
        
        st.write("**Knowledge Base Preview:**")
        st.dataframe(excel_proc.preview_data(), use_container_width=True)
        
        # Column selection
        columns = excel_proc.get_columns()
        
        col1, col2 = st.columns(2)
        with col1:
            key_column = st.selectbox(
                "Key Column",
                options=columns,
                help="Column with keys (e.g., failure codes)"
            )
        with col2:
            value_column = st.selectbox(
                "Definition Column",
                options=columns,
                help="Column with definitions/descriptions"
            )
        
        # Additional context columns (optional)
        additional_cols = st.multiselect(
            "Additional Context Columns (optional)",
            options=[col for col in columns if col not in [key_column, value_column]],
            help="Extra columns to include in matching"
        )
        
        kb_context_prompt = st.text_area(
            "Knowledge Base Context Prompt (Optional)",
            placeholder="e.g., This KB contains aviation maintenance failure modes and ATA terminology.",
            help="Small prompt that provides domain context for KB embeddings"
        )
        
        # Process KB button
        if st.button("Process Knowledge Base", type="primary"):
            with st.spinner("Processing knowledge base..."):
                try:
                    # Initialize pipeline
                    st.session_state.pipeline = MatchingPipeline(api_key)
                    
                    # Process Excel KB
                    stats = st.session_state.pipeline.setup_excel_knowledge_base(
                        kb_path,
                        key_column,
                        value_column,
                        additional_cols if additional_cols else None,
                        kb_context_prompt=kb_context_prompt if kb_context_prompt else None
                    )
                    
                    st.success("✅ Knowledge base processed successfully!")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Entries Processed", stats['entries_processed'])
                    with col2:
                        st.metric("Embeddings Created", stats['embeddings_created'])
                    
                    if stats.get('embeddings_failed', 0) > 0:
                        st.warning(
                            f"⚠️ {stats['embeddings_failed']} KB rows could not be embedded and were skipped. "
                            "Semantic matching quality may be reduced."
                        )
                    
                    st.session_state.kb_processed = True
                    
                except Exception as e:
                    st.error(f"Error processing knowledge base: {str(e)}")
                    return
    
    # Step 2: Upload Queries
    if st.session_state.kb_processed:
        st.subheader("Step 2: Upload Queries (Excel)")
        
        query_file = st.file_uploader(
            "Upload Excel file with queries",
            type=['xlsx', 'xls', 'csv'],
            key="query_upload_excel"
        )
        
        if query_file:
            # Save uploaded file
            query_path = f"./data/{query_file.name}"
            with open(query_path, "wb") as f:
                f.write(query_file.getbuffer())
            
            # Load and preview
            excel_proc = ExcelProcessor()
            excel_proc.load_excel(query_path)
            
            st.write("**Query File Preview:**")
            st.dataframe(excel_proc.preview_data(), use_container_width=True)
            
            # Column selection
            columns = excel_proc.get_columns()
            query_column = st.selectbox(
                "Select query column",
                options=columns,
                help="Column containing the queries/complaints"
            )
            
            # Process button
            # Process button (QA-first: run first 50, then gate the rest)
            if st.button("🚀 Process First 50 & Start QA Review", type="primary", use_container_width=True):
                # Figure out total query count first (avoid double processing)
                all_queries = excel_proc.process_queries(query_column)
                st.session_state.total_queries = len(all_queries)
                
                with st.spinner(f"Processing first {min(QA_SAMPLE_SIZE, st.session_state.total_queries)} queries..."):
                    try:
                        results = st.session_state.pipeline.process_queries(
                            query_path,
                            query_column,
                            top_n=top_n,
                            use_llm_reranking=use_llm_reranking,
                            query_offset=0,
                            query_limit=QA_SAMPLE_SIZE,
                            matching_guidance=matching_guidance
                        )

                        st.session_state.results = results
                        st.session_state.matching_stage = 'sample_done'
                        st.session_state.remaining_offset = len(results)
                        st.session_state.pending_query_path = query_path
                        st.session_state.pending_query_column = query_column
                        st.session_state.pending_top_n = top_n
                        st.session_state.pending_use_llm_reranking = use_llm_reranking
                        st.session_state.pending_matching_guidance = matching_guidance

                        # Initialize QA session
                        st.session_state.qa_session_id = str(uuid.uuid4())
                        qa_store = QAFeedbackStore()
                        qa_store.create_session(
                            st.session_state.qa_session_id,
                            "excel_kb",
                            len(results)
                        )

                        # Auto-enter QA
                        st.session_state.qa_mode = True
                        st.session_state.qa_index = 0

                        st.success(f"✅ Processed first {len(results)} of {st.session_state.total_queries} queries. Starting QA...")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error processing queries: {str(e)}")

    
    # Step 3: View Results
    if st.session_state.results:
        display_results(st.session_state.results, "excel_kb", top_n)


def display_results(results: list, use_case: str, top_n: int):
    """Display matching results"""
    
    st.subheader("📊 Results")
    
    # Action buttons
    col1, col2, col3 = st.columns([2, 2, 2])
    
    with col1:
        if st.button("📥 Export Results to Excel", use_container_width=True):
            exporter = ResultExporter()
            filepath = exporter.export_results(results, use_case)
            
            with open(filepath, 'rb') as f:
                st.download_button(
                    "⬇️ Download Excel File",
                    f,
                    file_name=os.path.basename(filepath),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
    
    with col2:
        if st.button("✅ Start QA Review (First 50)", use_container_width=True):
            st.session_state.qa_mode = True
            st.session_state.qa_index = 0
            st.session_state.qa_session_id = str(uuid.uuid4())
            
            # Initialize QA session
            qa_store = QAFeedbackStore()
            qa_store.create_session(
                st.session_state.qa_session_id,
                use_case,
                min(QA_SAMPLE_SIZE, len(results))
            )
            st.rerun()
    
    with col3:
        if st.button("🔄 Reset", use_container_width=True):
            reset_session_state()
            st.rerun()
    
    st.markdown("---")
    
    # QA Mode
    if st.session_state.qa_mode:
        display_qa_interface(results, use_case)
    else:
        # Results browser
        st.write(f"**Total Queries:** {len(results)}")
        
        # Display sample results
        for i, result in enumerate(results[:10]):  # Show first 10
            with st.expander(f"Query {i+1}: {result['query'][:100]}..."):
                st.write(f"**Full Query:** {result['query']}")
                st.write(f"**Matches Found:** {result['num_matches']}")
                
                if result.get('error'):
                    st.error(f"Error: {result['error']}")
                elif result['matches']:
                    for match in result['matches']:
                        display_match(match, use_case)
                else:
                    st.info("No matches found")


def display_match(match: dict, use_case: str):
    """Display a single match"""
    st.markdown(f"**Rank {match['rank']}** - Score: {match['combined_score']:.3f}")
    
    if use_case == "pdf_kb":
        st.write(f"📄 **Page:** {match['page_number']}")
        st.write(f"**Text:** {match['text'][:300]}...")
    else:
        st.write(f"🔑 **Key:** {match['key']}")
        st.write(f"**Definition:** {match['definition'][:300]}...")
        st.write(f"📊 **KB Row:** {match['row_number']}")
    
    if 'llm_relevance_score' in match:
        st.write(f"🤖 **LLM Relevance:** {match['llm_relevance_score']:.3f}")
    
    if 'llm_reasoning' in match:
        with st.expander("View LLM Reasoning"):
            st.write(match['llm_reasoning'])
    
    st.markdown("---")


def display_qa_interface(results: list, use_case: str):
    """Display QA review interface"""
    
    qa_results = results[:min(QA_SAMPLE_SIZE, len(results))]
    
    if st.session_state.qa_index >= len(qa_results):
        st.success("🎉 QA Review Complete!")
        
        # Show statistics
        qa_store = QAFeedbackStore()
        stats = qa_store.get_session_stats(st.session_state.qa_session_id)
        
        st.write("**QA Statistics:**")
        st.json(stats['feedback_counts'])
        
        # Show QA Learning Analysis
        from qa.qa_learner import QALearner
        qa_learner = QALearner()
        analysis = qa_learner.analyze_qa_session(st.session_state.qa_session_id)
        
        if analysis['total_reviews'] > 0:
            st.markdown("---")
            st.subheader("🎓 QA Learning Analysis")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Acceptance Rate", f"{analysis['acceptance_rate']:.1%}")
            with col2:
                st.metric("Good Examples", len(analysis['good_examples']))
            with col3:
                st.metric("Confidence", f"{analysis['confidence']:.1%}")
            
            # Show suggested weights if available
            if analysis['suggested_weights']:
                with st.expander("📊 View Suggested Weight Adjustments"):
                    weights = analysis['suggested_weights']
                    st.write(f"**Current → Suggested:**")
                    st.write(f"Semantic: 70% → {weights['semantic_weight']:.1%}")
                    st.write(f"Keyword: 30% → {weights['keyword_weight']:.1%}")
                    st.info(f"💡 {weights['reasoning']}")
            
            # Show good examples if available
            if analysis['good_examples']:
                with st.expander("✅ View Good Query-Match Examples"):
                    for i, ex in enumerate(analysis['good_examples'][:3], 1):
                        st.write(f"**Example {i}:**")
                        st.write(f"Query: {ex['query']}")
                        st.write(f"Match: {ex['match_text'][:200]}...")
                        st.markdown("---")
        
        # Export QA feedback
        if st.button("📥 Export QA Feedback"):
            exporter = ResultExporter()
            feedback_data = qa_store.get_session_feedback(st.session_state.qa_session_id)
            filepath = exporter.export_qa_results(feedback_data)
            
            with open(filepath, 'rb') as f:
                st.download_button(
                    "⬇️ Download QA Feedback",
                    f,
                    file_name=os.path.basename(filepath),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        
        # If we only processed the QA sample so far, allow the user to continue processing.
        if st.session_state.matching_stage == 'sample_done' and st.session_state.remaining_offset < st.session_state.total_queries:
            st.markdown("---")
            st.subheader("⏭️ Process Remaining Queries")
            
            # Option to apply learnings
            apply_learnings = st.checkbox(
                "🎯 Apply QA Learnings (Recommended)",
                value=True,
                help="Use insights from QA to improve matching on remaining queries"
            )
            
            if st.button("▶️ Process Remaining Queries", type="primary", use_container_width=True):
                with st.spinner(f"Processing remaining {st.session_state.total_queries - st.session_state.remaining_offset} queries..."):
                    try:
                        # Apply learnings if requested
                        if apply_learnings and analysis['total_reviews'] >= 10:
                            with st.spinner("Applying QA learnings..."):
                                changes = st.session_state.pipeline.apply_qa_learnings(
                                    st.session_state.qa_session_id
                                )
                                
                                if changes['weights_adjusted']:
                                    st.success(f"✅ Adjusted weights: Semantic {changes['new_weights']['semantic_weight']:.1%}, Keyword {changes['new_weights']['keyword_weight']:.1%}")
                                
                                if changes['few_shot_enabled']:
                                    st.success(f"✅ Enabled few-shot learning with {changes['num_examples']} examples")
                        
                        more_results = st.session_state.pipeline.process_queries(
                            st.session_state.pending_query_path,
                            st.session_state.pending_query_column,
                            top_n=st.session_state.pending_top_n,
                            use_llm_reranking=st.session_state.pending_use_llm_reranking,
                            query_offset=st.session_state.remaining_offset,
                            query_limit=None,
                            matching_guidance=st.session_state.pending_matching_guidance
                        )

                        st.session_state.results = (st.session_state.results or []) + more_results
                        st.session_state.remaining_offset += len(more_results)
                        st.session_state.matching_stage = 'all_done'
                        st.session_state.qa_mode = False
                        st.success("✅ Finished processing all remaining queries!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error processing remaining queries: {str(e)}")
        
        return
    
    # Current query
    current_result = qa_results[st.session_state.qa_index]
    
    st.subheader(f"QA Review: Query {st.session_state.qa_index + 1} of {len(qa_results)}")
    st.progress((st.session_state.qa_index + 1) / len(qa_results))
    
    st.write("**Query:**")
    st.info(current_result['query'])
    
    st.markdown("---")
    
    # Display matches for review
    qa_store = QAFeedbackStore()

    kb_keys = []
    if use_case == "excel_kb" and st.session_state.pipeline and st.session_state.pipeline.knowledge_base:
        kb_keys = sorted(list({
            entry.get('key', '').strip()
            for entry in st.session_state.pipeline.knowledge_base
            if entry.get('key', '').strip()
        }))

    with st.form(key=f"qa_form_{st.session_state.qa_index}"):
        st.caption("Set a label for each candidate. Multiple candidates can be marked Relevant.")

        match_labels = {}
        for match in current_result['matches']:
            st.write(f"### Match {match['rank']}")
            display_match(match, use_case)
            label = st.selectbox(
                f"QA Label for Match {match['rank']}",
                options=["Unsure", "Relevant", "Not Relevant"],
                index=0,
                key=f"qa_label_{st.session_state.qa_index}_{match['rank']}"
            )
            match_labels[match['rank']] = label

        st.markdown("---")
        st.write("**If any match is incorrect, suggest a better output (optional):**")

        suggested_key = ""
        if use_case == "excel_kb":
            key_options = [""] + kb_keys
            suggested_key = st.selectbox(
                "Suggested Better Match Key (optional)",
                options=key_options,
                format_func=lambda x: x if x else "-- None --",
                key=f"qa_suggested_key_{st.session_state.qa_index}"
            )

        suggested_text = st.text_area(
            "Suggested Better Match Text (optional)",
            placeholder="Provide corrected output text if none of the shown matches are right.",
            key=f"qa_suggested_text_{st.session_state.qa_index}"
        )

        analyst_note = st.text_input(
            "QA Note (optional)",
            placeholder="Any additional instruction for future matching",
            key=f"qa_note_{st.session_state.qa_index}"
        )

        save_and_next = st.form_submit_button("💾 Save QA and Next", use_container_width=True, type="primary")

    if save_and_next:
        label_to_status = {
            "Relevant": "accepted",
            "Not Relevant": "rejected",
            "Unsure": "skipped"
        }

        for match in current_result['matches']:
            label = match_labels.get(match['rank'], "Unsure")
            status = label_to_status[label]
            match_id = match.get('chunk_id') or match.get('key', '')
            match_text = match.get('text', '') or match.get('definition', '')

            note_payload = {
                'review_label': label,
                'suggested_key': suggested_key if status == "rejected" else "",
                'suggested_text': suggested_text if status == "rejected" else "",
                'analyst_note': analyst_note if status == "rejected" else ""
            }

            qa_store.add_feedback(
                st.session_state.qa_session_id,
                current_result['query_id'],
                current_result['query'],
                match['rank'],
                match_id,
                match_text,
                status,
                notes=json.dumps(note_payload)
            )

        st.session_state.qa_index += 1
        qa_store.update_session_progress(
            st.session_state.qa_session_id,
            st.session_state.qa_index
        )
        st.rerun()
    
    st.markdown("---")
    
    # Navigation
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        if st.session_state.qa_index > 0:
            if st.button("⬅️ Previous", use_container_width=True):
                st.session_state.qa_index -= 1
                st.rerun()
    
    with col2:
        if st.button("⏭️ Skip", use_container_width=True):
            st.session_state.qa_index += 1
            qa_store.update_session_progress(
                st.session_state.qa_session_id,
                st.session_state.qa_index
            )
            st.rerun()
    
    with col3:
        if st.button("➡️ Next (No Save)", use_container_width=True):
            st.session_state.qa_index += 1
            qa_store.update_session_progress(
                st.session_state.qa_session_id,
                st.session_state.qa_index
            )
            st.rerun()


if __name__ == "__main__":
    main()

"""
Intelligent PDF Chunker
Uses LLM to analyze PDF structure and determine optimal chunking strategy
"""
from openai import OpenAI
from typing import List, Dict, Optional
import json
import fitz  # PyMuPDF
import re


class IntelligentChunker:
    """LLM-powered adaptive PDF chunking"""
    
    def __init__(self, api_key: str):
        """
        Initialize intelligent chunker
        
        Args:
            api_key: OpenAI API key
        """
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"  # Cheaper model for analysis
    
    def analyze_pdf_structure(self, pdf_path: str, user_context: Optional[str] = None) -> Dict:
        """
        Analyze PDF structure using LLM to determine optimal chunking
        
        Args:
            pdf_path: Path to PDF file
            user_context: Optional user description of the document
            
        Returns:
            Dictionary with chunking strategy
        """
        # Extract sample pages
        sample_text = self._extract_sample_pages(pdf_path, num_pages=5)
        
        # Build analysis prompt
        context_section = f"\n\nUSER CONTEXT:\n{user_context}\n" if user_context else ""
        
        prompt = f"""You are a document structure expert. Analyze this PDF excerpt and identify the optimal chunking strategy.

DOCUMENT EXCERPT (First 5 pages):
{sample_text[:4000]}
{context_section}

Analyze and return a JSON with:
1. document_type: (manual, report, book, article, specification, guide, etc.)
2. has_clear_sections: true/false
3. section_indicators: list of patterns (e.g., "TASK", "Chapter", numbered headings)
4. has_hierarchical_numbering: true/false (1.1, 1.2, etc.)
5. has_tables: true/false
6. content_density: (high, medium, low) - how information-dense the text is
7. recommended_strategy: (section_based, semantic_based, or fixed_size)
8. recommended_chunk_size: int (tokens) - between 300-1000
9. recommended_overlap: int (tokens) - between 50-150
10. reasoning: brief explanation of why this strategy was chosen

Return ONLY valid JSON, no markdown formatting, no other text.
"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a document analysis expert. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            strategy = json.loads(response.choices[0].message.content)
            
            # Validate and set defaults
            strategy.setdefault('recommended_chunk_size', 500)
            strategy.setdefault('recommended_overlap', 50)
            strategy.setdefault('recommended_strategy', 'fixed_size')
            
            return strategy
            
        except Exception as e:
            print(f"Error analyzing PDF structure: {str(e)}")
            # Return safe defaults
            return {
                'document_type': 'unknown',
                'has_clear_sections': False,
                'recommended_strategy': 'fixed_size',
                'recommended_chunk_size': 500,
                'recommended_overlap': 50,
                'reasoning': f'Analysis failed, using defaults. Error: {str(e)[:100]}'
            }
    
    def chunk_with_strategy(self, pdf_path: str, strategy: Dict) -> List[Dict]:
        """
        Apply chunking strategy to entire PDF
        
        Args:
            pdf_path: Path to PDF file
            strategy: Chunking strategy from analyze_pdf_structure
            
        Returns:
            List of chunk dictionaries
        """
        strategy_type = strategy.get('recommended_strategy', 'fixed_size')
        
        if strategy_type == 'section_based' and strategy.get('section_indicators'):
            return self._chunk_by_sections(pdf_path, strategy)
        else:
            return self._chunk_fixed_size(pdf_path, strategy)
    
    def _extract_sample_pages(self, pdf_path: str, num_pages: int = 5) -> str:
        """Extract text from first N pages"""
        try:
            doc = fitz.open(pdf_path)
            sample_text = []
            
            for i in range(min(num_pages, len(doc))):
                page = doc.load_page(i)
                text = page.get_text("text")
                sample_text.append(f"--- Page {i+1} ---\n{text}\n")
            
            doc.close()
            return "\n".join(sample_text)
            
        except Exception as e:
            raise Exception(f"Error extracting sample pages: {str(e)}")
    
    def _chunk_by_sections(self, pdf_path: str, strategy: Dict) -> List[Dict]:
        """
        Chunk by detected sections
        
        Args:
            pdf_path: Path to PDF file
            strategy: Strategy containing section_indicators
            
        Returns:
            List of section-based chunks
        """
        doc = fitz.open(pdf_path)
        chunks = []
        
        section_patterns = strategy.get('section_indicators', [])
        if not section_patterns:
            # Fallback to fixed size if no patterns
            doc.close()
            return self._chunk_fixed_size(pdf_path, strategy)
        
        # Compile regex patterns
        compiled_patterns = []
        for pattern in section_patterns:
            try:
                # Handle both literal strings and regex patterns
                if isinstance(pattern, str):
                    # Try to detect if it's a regex or literal
                    if any(c in pattern for c in r'.*+?[]{}()^$|\\'):
                        compiled_patterns.append(re.compile(pattern, re.IGNORECASE))
                    else:
                        # Literal string - match at start of line
                        compiled_patterns.append(re.compile(f"^{re.escape(pattern)}", re.IGNORECASE | re.MULTILINE))
            except re.error:
                continue
        
        if not compiled_patterns:
            # If no valid patterns, fallback
            doc.close()
            return self._chunk_fixed_size(pdf_path, strategy)
        
        current_section = []
        current_page_start = 1
        chunk_id = 0
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text("text")
            lines = text.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check if line matches section boundary
                is_boundary = any(pattern.search(line) for pattern in compiled_patterns)
                
                if is_boundary and current_section:
                    # Save previous section
                    section_text = '\n'.join(current_section)
                    if len(section_text.split()) > 10:  # Only save if substantial
                        section_chunks, chunk_id = self._split_section_if_needed(
                            section_text,
                            current_page_start,
                            page_num + 1,
                            chunk_id,
                            strategy
                        )
                        chunks.extend(section_chunks)
                    
                    current_section = [line]
                    current_page_start = page_num + 1
                else:
                    current_section.append(line)
        
        # Add final section
        if current_section:
            section_text = '\n'.join(current_section)
            if len(section_text.split()) > 10:
                section_chunks, chunk_id = self._split_section_if_needed(
                    section_text,
                    current_page_start,
                    len(doc),
                    chunk_id,
                    strategy
                )
                chunks.extend(section_chunks)
        
        doc.close()
        
        # If too few chunks, fallback to fixed size
        if len(chunks) < 3:
            return self._chunk_fixed_size(pdf_path, strategy)
        
        return chunks

    def _split_section_if_needed(self, section_text: str, page_start: int, page_end: int,
                                 chunk_id: int, strategy: Dict):
        """
        Split oversized section chunks to keep downstream embedding requests manageable.
        """
        chunk_size_tokens = max(300, int(strategy.get('recommended_chunk_size', 500)))
        overlap_tokens = max(20, int(strategy.get('recommended_overlap', 50)))
        
        # For section-based chunking, allow slightly larger chunks but still bounded.
        max_section_tokens = min(1200, chunk_size_tokens * 2)
        word_chunk_size = max(200, int(max_section_tokens * 0.75))
        word_overlap = max(20, int(overlap_tokens * 0.75))
        
        words = section_text.split()
        if not words:
            return [], chunk_id
        
        if len(words) <= word_chunk_size:
            return [{
                'text': section_text,
                'page_number': page_start,
                'page_end': page_end,
                'chunk_id': f"section_{chunk_id}",
                'chunk_type': 'section'
            }], chunk_id + 1
        
        chunks = []
        part_idx = 0
        start = 0
        while start < len(words):
            end = start + word_chunk_size
            part_words = words[start:end]
            if not part_words:
                break
            
            chunks.append({
                'text': ' '.join(part_words),
                'page_number': page_start,
                'page_end': page_end,
                'chunk_id': f"section_{chunk_id}_part_{part_idx}",
                'chunk_type': 'section'
            })
            part_idx += 1
            
            if end >= len(words):
                break
            
            start = end - word_overlap
        
        return chunks, chunk_id + 1
    
    def _chunk_fixed_size(self, pdf_path: str, strategy: Dict) -> List[Dict]:
        """
        Fixed-size chunking with smart overlap
        
        Args:
            pdf_path: Path to PDF file
            strategy: Strategy containing chunk_size and overlap
            
        Returns:
            List of fixed-size chunks
        """
        doc = fitz.open(pdf_path)
        chunks = []
        
        chunk_size = strategy.get('recommended_chunk_size', 500)
        overlap = strategy.get('recommended_overlap', 50)
        
        # Convert token counts to approximate word counts (1 token ≈ 0.75 words)
        word_chunk_size = int(chunk_size * 0.75)
        word_overlap = int(overlap * 0.75)
        
        all_words = []
        page_boundaries = []  # Track which words belong to which pages
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text("text")
            # Clean and normalize
            text = re.sub(r'\s+', ' ', text).strip()
            words = text.split()
            
            page_boundaries.append((len(all_words), len(all_words) + len(words), page_num + 1))
            all_words.extend(words)
        
        doc.close()
        
        # Create chunks with overlap
        chunk_id = 0
        start = 0
        
        while start < len(all_words):
            end = start + word_chunk_size
            chunk_words = all_words[start:end]
            
            if chunk_words:
                chunk_text = ' '.join(chunk_words)
                
                # Determine page range for this chunk
                chunk_start_word = start
                chunk_end_word = min(end, len(all_words))
                
                page_start = None
                page_end = None
                
                for pb_start, pb_end, page_num in page_boundaries:
                    if page_start is None and chunk_start_word < pb_end:
                        page_start = page_num
                    if chunk_end_word <= pb_end:
                        page_end = page_num
                        break
                
                if page_end is None:
                    page_end = page_boundaries[-1][2]
                
                chunks.append({
                    'text': chunk_text,
                    'page_number': page_start or 1,
                    'page_end': page_end or page_start or 1,
                    'chunk_id': f"chunk_{chunk_id}",
                    'chunk_type': 'fixed'
                })
                chunk_id += 1
            
            # Move start position with overlap
            start = end - word_overlap
            
            # Break if we're at the end
            if end >= len(all_words):
                break
        
        return chunks
    
    def get_chunking_summary(self, chunks: List[Dict]) -> Dict:
        """Get statistics about the chunks created"""
        if not chunks:
            return {}
        
        chunk_types = {}
        for chunk in chunks:
            chunk_type = chunk.get('chunk_type', 'unknown')
            chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1
        
        chunk_sizes = [len(chunk['text'].split()) for chunk in chunks]
        
        return {
            'total_chunks': len(chunks),
            'chunk_types': chunk_types,
            'avg_chunk_size_words': sum(chunk_sizes) / len(chunk_sizes) if chunk_sizes else 0,
            'min_chunk_size_words': min(chunk_sizes) if chunk_sizes else 0,
            'max_chunk_size_words': max(chunk_sizes) if chunk_sizes else 0,
        }

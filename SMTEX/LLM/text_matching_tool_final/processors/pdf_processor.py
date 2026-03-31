"""
PDF Processing Module
Handles PDF parsing, text extraction, and chunking with page number tracking
"""
import fitz  # PyMuPDF
import re
from typing import List, Dict
from config import CHUNK_SIZE, CHUNK_OVERLAP


class PDFProcessor:
    """Process PDF files and extract text with page numbers"""
    
    def __init__(self):
        self.chunks = []
    
    def process_pdf(self, pdf_path: str) -> List[Dict]:
        """
        Process PDF and return chunks with metadata
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of dictionaries with chunk text, page number, and metadata
        """
        self.chunks = []
        
        try:
            doc = fitz.open(pdf_path)
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                
                # Clean text
                text = self._clean_text(text)
                
                # Create chunks for this page
                page_chunks = self._chunk_text(text, page_num + 1)
                self.chunks.extend(page_chunks)
            
            doc.close()
            
            return self.chunks
            
        except Exception as e:
            raise Exception(f"Error processing PDF: {str(e)}")
    
    def _clean_text(self, text: str) -> str:
        """Clean extracted text"""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove special characters that might interfere
        text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        return text.strip()
    
    def _chunk_text(self, text: str, page_num: int) -> List[Dict]:
        """
        Split text into overlapping chunks
        
        Args:
            text: Text to chunk
            page_num: Page number for metadata
            
        Returns:
            List of chunk dictionaries
        """
        # Simple word-based chunking (approximation of token-based)
        words = text.split()
        chunks = []
        
        # Approximate: 1 token ≈ 0.75 words
        word_chunk_size = int(CHUNK_SIZE * 0.75)
        word_overlap = int(CHUNK_OVERLAP * 0.75)
        
        if len(words) <= word_chunk_size:
            # Entire page fits in one chunk
            if words:  # Only add if there's content
                chunks.append({
                    'text': ' '.join(words),
                    'page_number': page_num,
                    'chunk_id': f"page_{page_num}_chunk_0"
                })
        else:
            # Create overlapping chunks
            start = 0
            chunk_idx = 0
            
            while start < len(words):
                end = start + word_chunk_size
                chunk_words = words[start:end]
                
                if chunk_words:  # Only add non-empty chunks
                    chunks.append({
                        'text': ' '.join(chunk_words),
                        'page_number': page_num,
                        'chunk_id': f"page_{page_num}_chunk_{chunk_idx}"
                    })
                    chunk_idx += 1
                
                # Move start position with overlap
                start = end - word_overlap
                
                # Break if we're at the end
                if end >= len(words):
                    break
        
        return chunks
    
    def get_statistics(self) -> Dict:
        """Get processing statistics"""
        if not self.chunks:
            return {}
        
        pages = set(chunk['page_number'] for chunk in self.chunks)
        
        return {
            'total_chunks': len(self.chunks),
            'total_pages': len(pages),
            'avg_chunks_per_page': len(self.chunks) / len(pages) if pages else 0
        }

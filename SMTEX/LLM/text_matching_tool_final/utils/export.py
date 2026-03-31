"""
Export Module
Export results to Excel format
"""
import pandas as pd
from typing import List, Dict, Optional
import os
from datetime import datetime
from config import EXPORT_FOLDER


class ResultExporter:
    """Export matching results to Excel"""
    
    def __init__(self):
        os.makedirs(EXPORT_FOLDER, exist_ok=True)
    
    def export_results(self, results: List[Dict], use_case: str, 
                      filename: Optional[str] = None) -> str:
        """
        Export results to Excel
        
        Args:
            results: List of query results
            use_case: Type of matching ("pdf_kb" or "excel_kb")
            filename: Optional custom filename
            
        Returns:
            Path to exported file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"matching_results_{use_case}_{timestamp}.xlsx"
        
        filepath = os.path.join(EXPORT_FOLDER, filename)
        
        # Flatten results for Excel
        rows = []
        
        for result in results:
            query = result['query']
            query_row = result.get('row_number', 'N/A')
            
            if result.get('error'):
                # Add error row
                rows.append({
                    'Query_Row': query_row,
                    'Query': query,
                    'Error': result['error']
                })
            elif result['matches']:
                # Add row for each match
                for match in result['matches']:
                    row = {
                        'Query_Row': query_row,
                        'Query': query,
                        'Match_Rank': match['rank'],
                        'Combined_Score': round(match['combined_score'], 4)
                    }
                    
                    if use_case == "pdf_kb":
                        row['Page_Number'] = match.get('page_number', 'N/A')
                        row['Matched_Text'] = match.get('text', '')
                    else:  # excel_kb
                        row['Key'] = match.get('key', '')
                        row['Definition'] = match.get('definition', '')
                        row['KB_Row'] = match.get('row_number', 'N/A')
                    
                    if 'llm_relevance_score' in match:
                        row['LLM_Relevance_Score'] = round(match['llm_relevance_score'], 4)
                    
                    if 'llm_reasoning' in match:
                        row['LLM_Reasoning'] = match['llm_reasoning']
                    
                    rows.append(row)
            else:
                # No matches found
                rows.append({
                    'Query_Row': query_row,
                    'Query': query,
                    'Match_Rank': 0,
                    'Note': 'No matches found'
                })
        
        # Create DataFrame and export
        df = pd.DataFrame(rows)
        df.to_excel(filepath, index=False, engine='openpyxl')
        
        return filepath
    
    def export_qa_results(self, qa_data: List[Dict], filename: Optional[str] = None) -> str:
        """
        Export QA feedback to Excel
        
        Args:
            qa_data: List of QA feedback entries
            filename: Optional custom filename
            
        Returns:
            Path to exported file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"qa_feedback_{timestamp}.xlsx"
        
        filepath = os.path.join(EXPORT_FOLDER, filename)
        
        # Format QA data
        rows = []
        for entry in qa_data:
            row = {
                'Query': entry['query'],
                'Match_Rank': entry['match_rank'],
                'Match_Text': entry['match_text'][:200],  # Truncate
                'QA_Status': entry['status'],  # 'accepted', 'rejected', 'edited'
                'QA_Notes': entry.get('notes', ''),
                'Timestamp': entry.get('timestamp', '')
            }
            rows.append(row)
        
        df = pd.DataFrame(rows)
        df.to_excel(filepath, index=False, engine='openpyxl')
        
        return filepath

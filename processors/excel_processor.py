"""
Excel Processing Module
Handles Excel/CSV parsing for both knowledge base and queries
"""
import pandas as pd
from typing import List, Dict, Optional

INVALID_TAG_VALUES = {
    "not mentioned",
    "not confirmed",
    "not available",
    "unknown",
    "none",
    "null",
    "na",
    "n/a",
    "-",
    "",
}


class ExcelProcessor:
    """Process Excel files for knowledge base and queries"""
    
    def __init__(self):
        self.data = None
    
    def load_excel(self, file_path: str, sheet_name: Optional[str] = None) -> pd.DataFrame:
        """
        Load Excel or CSV file
        
        Args:
            file_path: Path to Excel/CSV file
            sheet_name: Optional sheet name for Excel files
            
        Returns:
            pandas DataFrame
        """
        try:
            if file_path.endswith('.csv'):
                self.data = pd.read_csv(file_path)
            else:
                self.data = pd.read_excel(file_path, sheet_name=sheet_name or 0)
            
            return self.data
            
        except Exception as e:
            raise Exception(f"Error loading Excel file: {str(e)}")
    
    def get_columns(self) -> List[str]:
        """Get list of column names"""
        if self.data is None:
            return []
        return self.data.columns.tolist()
    
    def process_knowledge_base(self, key_column: str, value_column: str, 
                               additional_columns: Optional[List[str]] = None) -> List[Dict]:
        """
        Process Excel as knowledge base
        
        Args:
            key_column: Column containing keys (e.g., failure codes)
            value_column: Column containing definitions
            additional_columns: Optional additional context columns
            
        Returns:
            List of knowledge base entries
        """
        if self.data is None:
            raise Exception("No data loaded. Call load_excel first.")
        
        entries = []
        
        for idx, row in self.data.iterrows():
            # Skip rows with missing key or value
            if pd.isna(row[key_column]) or pd.isna(row[value_column]):
                continue
            
            entry = {
                'key': str(row[key_column]).strip(),
                'definition': str(row[value_column]).strip(),
                'row_number': idx + 2,  # +2 for Excel row numbering (1-indexed + header)
                'entry_id': f"row_{idx}"
            }
            
            # Add additional context if specified
            if additional_columns:
                context_parts = []
                for col in additional_columns:
                    if col in self.data.columns and not pd.isna(row[col]):
                        context_parts.append(f"{col}: {row[col]}")
                
                if context_parts:
                    entry['additional_context'] = ' | '.join(context_parts)
            
            # Create combined text for embedding
            text_parts = [entry['key'], entry['definition']]
            if 'additional_context' in entry:
                text_parts.append(entry['additional_context'])
            
            entry['text'] = ': '.join(text_parts)
            
            entries.append(entry)
        
        return entries
    
    def process_queries(
        self,
        query_column: str,
        primary_key_column: Optional[str] = None,
        tag_column: Optional[str] = None,
        tag_separator: Optional[str] = None,
    ) -> List[Dict]:
        """
        Process Excel as query list

        Args:
            query_column: Column containing queries
            primary_key_column: Optional column (e.g. complaint ID) to attach to each query row
            tag_column: Optional column containing row-specific tags
            tag_separator: Optional separator used to split tags in ``tag_column``

        Returns:
            List of queries with metadata
        """
        if self.data is None:
            raise Exception("No data loaded. Call load_excel first.")

        pk_col = (
            primary_key_column
            if primary_key_column and primary_key_column in self.data.columns
            else None
        )
        tag_col = (
            tag_column
            if tag_column and tag_separator and tag_column in self.data.columns
            else None
        )

        queries = []

        for idx, row in self.data.iterrows():
            # Skip rows with missing query
            if pd.isna(row[query_column]):
                continue

            query_text = str(row[query_column]).strip()

            if query_text:  # Only add non-empty queries
                item = {
                    "query": query_text,
                    "query_id": f"query_{idx}",
                    "row_number": idx + 2,  # +2 for Excel row numbering
                }
                if pk_col is not None and not pd.isna(row[pk_col]):
                    item["primary_key"] = str(row[pk_col]).strip()
                if tag_col is not None:
                    raw = "" if pd.isna(row[tag_col]) else str(row[tag_col]).strip()
                    raw_l = raw.lower()
                    if raw_l in INVALID_TAG_VALUES:
                        item["query_tags"] = []
                    else:
                        tags = [t.strip() for t in raw.split(tag_separator) if t.strip()]
                        item["query_tags"] = tags
                queries.append(item)

        return queries
    
    def get_statistics(self) -> Dict:
        """Get data statistics"""
        if self.data is None:
            return {}
        
        return {
            'total_rows': len(self.data),
            'total_columns': len(self.data.columns),
            'columns': self.data.columns.tolist(),
            'missing_values': self.data.isnull().sum().to_dict()
        }
    
    def preview_data(self, n_rows: int = 5) -> pd.DataFrame:
        """Get preview of first n rows"""
        if self.data is None:
            return pd.DataFrame()
        return self.data.head(n_rows)

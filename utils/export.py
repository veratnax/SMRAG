"""
Export Module
Export results to Excel format
"""
import json
import pandas as pd
from typing import List, Dict, Optional, Set, Any
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
            q_pk = result.get('primary_key', '') or ''

            if result.get('error'):
                # Add error row
                rows.append({
                    'Query_Row': query_row,
                    'Query_Primary_Key': q_pk,
                    'Query': query,
                    'Error': result['error']
                })
            elif result['matches']:
                # Add row for each match
                for match in result['matches']:
                    row = {
                        'Query_Row': query_row,
                        'Query_Primary_Key': q_pk,
                        'Query': query,
                        'Match_Rank': match['rank'],
                        'Tag_Index': match.get('tag_index', ''),
                        'Tag_Value': match.get('tag_value', ''),
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
                    'Query_Primary_Key': q_pk,
                    'Query': query,
                    'Match_Rank': 0,
                    'Note': 'No matches found'
                })
        
        # Create DataFrame and export
        df = pd.DataFrame(rows)
        df.to_excel(filepath, index=False, engine='openpyxl')
        
        return filepath

    @staticmethod
    def _parse_qa_notes(notes: Optional[str]) -> Dict[str, Any]:
        if not notes:
            return {}
        try:
            return json.loads(notes)
        except Exception:
            return {}

    def export_qa_reviewed_merge(
        self,
        results: List[Dict],
        reviewed_query_ids: List[str],
        feedback_rows: List[Dict],
        use_case: str,
        filename: Optional[str] = None,
    ) -> str:
        """
        Export only queries marked reviewed (Save & Next), with model output + QA columns.
        When a match was rejected and analyst suggested a key/text, include Exported_* columns.
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"qa_reviewed_results_{use_case}_{timestamp}.xlsx"

        filepath = os.path.join(EXPORT_FOLDER, filename)
        reviewed: Set[str] = set(reviewed_query_ids)
        fb_map: Dict[tuple, Dict] = {}
        for entry in feedback_rows:
            fb_map[(entry["query_id"], entry["match_rank"])] = entry

        rows_out: List[Dict] = []
        for result in results:
            qid = result.get("query_id")
            if qid not in reviewed:
                continue
            query = result.get("query", "")
            query_row = result.get("row_number", "N/A")
            q_pk = result.get("primary_key", "") or ""

            if result.get("error"):
                rows_out.append({
                    "Query_Row": query_row,
                    "Query_Primary_Key": q_pk,
                    "Query": query,
                    "Error": result["error"],
                })
                continue

            matches = result.get("matches") or []
            if not matches:
                rows_out.append({
                    "Query_Row": query_row,
                    "Query_Primary_Key": q_pk,
                    "Query": query,
                    "Match_Rank": 0,
                    "Note": "No matches found",
                })
                continue

            for match in matches:
                rank = match.get("rank", 0)
                fb = fb_map.get((qid, rank))
                notes_p = self._parse_qa_notes(fb.get("notes") if fb else None)
                sk = (notes_p.get("suggested_key") or "").strip() if isinstance(notes_p.get("suggested_key"), str) else ""
                st = (notes_p.get("suggested_text") or "").strip() if isinstance(notes_p.get("suggested_text"), str) else ""
                status = fb.get("status", "") if fb else ""

                row: Dict[str, Any] = {
                    "Query_Row": query_row,
                    "Query_Primary_Key": q_pk,
                    "Query": query,
                    "Match_Rank": rank,
                    "Tag_Index": match.get("tag_index", ""),
                    "Tag_Value": match.get("tag_value", ""),
                    "Combined_Score": round(match.get("combined_score", 0) or 0, 4),
                    "QA_Status": status,
                    "Analyst_Suggested_Key": sk,
                    "Analyst_Suggested_Text": st,
                }

                if use_case == "pdf_kb":
                    row["Page_Number"] = match.get("page_number", "N/A")
                    row["Model_Matched_Text"] = match.get("text", "")
                    if status == "rejected" and st:
                        row["Exported_Matched_Text"] = st
                    else:
                        row["Exported_Matched_Text"] = match.get("text", "")
                else:
                    row["Model_Key"] = match.get("key", "")
                    row["Model_Definition"] = match.get("definition", "")
                    row["KB_Row"] = match.get("row_number", "N/A")
                    if status == "rejected" and sk:
                        row["Exported_Key"] = sk
                    else:
                        row["Exported_Key"] = match.get("key", "")
                    if status == "rejected" and st:
                        row["Exported_Definition"] = st
                    else:
                        row["Exported_Definition"] = match.get("definition", "")

                if "llm_relevance_score" in match:
                    row["LLM_Relevance_Score"] = round(match["llm_relevance_score"], 4)
                if "llm_reasoning" in match:
                    row["LLM_Reasoning"] = match["llm_reasoning"]

                rows_out.append(row)

        if not rows_out:
            rows_out.append({"Note": "No matching result rows for reviewed query IDs."})

        df = pd.DataFrame(rows_out)
        df.to_excel(filepath, index=False, engine="openpyxl")
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
                'Query_Primary_Key': entry.get('primary_key_value') or '',
                'Query': entry['query'],
                'Match_Rank': entry['match_rank'],
                'Tag_Index': entry.get('tag_index', ''),
                'Tag_Value': entry.get('tag_value', ''),
                'Match_Text': entry['match_text'][:200],  # Truncate
                'QA_Status': entry['status'],  # 'accepted', 'rejected', 'edited'
                'QA_Notes': entry.get('notes', ''),
                'Timestamp': entry.get('timestamp', '')
            }
            rows.append(row)

        df = pd.DataFrame(rows)
        df.to_excel(filepath, index=False, engine='openpyxl')

        return filepath

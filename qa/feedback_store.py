"""
QA Feedback Store
Store and manage QA feedback using SQLite
"""
import sqlite3
from typing import List, Dict, Optional
from datetime import datetime
import os


class QAFeedbackStore:
    """Manage QA feedback in SQLite database"""
    
    def __init__(self, db_path: str = "./data/qa_feedback.db"):
        """
        Initialize QA feedback store
        
        Args:
            db_path: Path to SQLite database
        """
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._create_tables()
    
    def _create_tables(self):
        """Create database tables if they don't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS qa_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                query_id TEXT NOT NULL,
                query TEXT NOT NULL,
                match_rank INTEGER NOT NULL,
                match_id TEXT NOT NULL,
                match_text TEXT NOT NULL,
                status TEXT NOT NULL,
                notes TEXT,
                timestamp TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS qa_sessions (
                session_id TEXT PRIMARY KEY,
                use_case TEXT NOT NULL,
                total_queries INTEGER NOT NULL,
                completed_queries INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()
    
    def create_session(self, session_id: str, use_case: str, total_queries: int) -> None:
        """
        Create a new QA session
        
        Args:
            session_id: Unique session identifier
            use_case: Type of matching
            total_queries: Total number of queries in session
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT INTO qa_sessions (session_id, use_case, total_queries, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, use_case, total_queries, now, now))
        
        conn.commit()
        conn.close()
    
    def add_feedback(self, session_id: str, query_id: str, query: str,
                    match_rank: int, match_id: str, match_text: str,
                    status: str, notes: Optional[str] = None) -> None:
        """
        Add QA feedback for a match
        
        Args:
            session_id: Session identifier
            query_id: Query identifier
            query: Query text
            match_rank: Rank of the match
            match_id: Match identifier
            match_text: Match text/content
            status: Feedback status ('accepted', 'rejected', 'relevant', 'not_relevant', 'skipped')
            notes: Optional notes
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        timestamp = datetime.now().isoformat()
        
        # Check if feedback already exists for this match
        cursor.execute("""
            SELECT id FROM qa_feedback 
            WHERE session_id = ? AND query_id = ? AND match_rank = ?
        """, (session_id, query_id, match_rank))
        
        existing = cursor.fetchone()
        
        if existing:
            # Update existing feedback
            cursor.execute("""
                UPDATE qa_feedback 
                SET status = ?, notes = ?, timestamp = ?
                WHERE id = ?
            """, (status, notes, timestamp, existing[0]))
        else:
            # Insert new feedback
            cursor.execute("""
                INSERT INTO qa_feedback 
                (session_id, query_id, query, match_rank, match_id, match_text, status, notes, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (session_id, query_id, query, match_rank, match_id, match_text, status, notes, timestamp))
        
        conn.commit()
        conn.close()
    
    def get_session_feedback(self, session_id: str) -> List[Dict]:
        """
        Get all feedback for a session
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of feedback entries
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM qa_feedback
            WHERE session_id = ?
            ORDER BY query_id, match_rank
        """, (session_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_query_feedback(self, session_id: str, query_id: str) -> List[Dict]:
        """
        Get feedback for a specific query
        
        Args:
            session_id: Session identifier
            query_id: Query identifier
            
        Returns:
            List of feedback entries for the query
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM qa_feedback
            WHERE session_id = ? AND query_id = ?
            ORDER BY match_rank
        """, (session_id, query_id))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def update_session_progress(self, session_id: str, completed_queries: int) -> None:
        """
        Update session progress
        
        Args:
            session_id: Session identifier
            completed_queries: Number of completed queries
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute("""
            UPDATE qa_sessions
            SET completed_queries = ?, updated_at = ?
            WHERE session_id = ?
        """, (completed_queries, now, session_id))
        
        conn.commit()
        conn.close()
    
    def get_session_stats(self, session_id: str) -> Dict:
        """
        Get statistics for a QA session
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dictionary with session statistics
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get session info
        cursor.execute("""
            SELECT * FROM qa_sessions WHERE session_id = ?
        """, (session_id,))
        session = cursor.fetchone()
        
        if not session:
            conn.close()
            return {}
        
        # Get feedback stats
        cursor.execute("""
            SELECT 
                status,
                COUNT(*) as count
            FROM qa_feedback
            WHERE session_id = ?
            GROUP BY status
        """, (session_id,))
        
        status_counts = {row['status']: row['count'] for row in cursor.fetchall()}
        
        conn.close()
        
        return {
            'session_id': session['session_id'],
            'use_case': session['use_case'],
            'total_queries': session['total_queries'],
            'completed_queries': session['completed_queries'],
            'feedback_counts': status_counts,
            'created_at': session['created_at'],
            'updated_at': session['updated_at']
        }

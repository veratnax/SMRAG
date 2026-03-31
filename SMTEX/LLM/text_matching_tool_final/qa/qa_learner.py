"""
QA Learning Module
Analyzes QA feedback to improve matching performance
"""
from typing import Dict, List, Optional
from qa.feedback_store import QAFeedbackStore
import statistics
import json


class QALearner:
    """Learn from QA feedback to improve matching"""
    
    def __init__(self):
        self.qa_store = QAFeedbackStore()
    
    def _is_accepted(self, status: str) -> bool:
        """Normalize status values for acceptance logic."""
        return status in ("accepted", "relevant")

    def _is_rejected(self, status: str) -> bool:
        """Normalize status values for rejection logic."""
        return status in ("rejected", "not_relevant")

    def _parse_notes(self, notes_text: Optional[str]) -> Dict:
        """Safely parse notes JSON payload."""
        if not notes_text:
            return {}
        try:
            parsed = json.loads(notes_text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {"notes": notes_text}

    def analyze_qa_session(self, session_id: str) -> Dict:
        """
        Analyze QA feedback to extract learning insights
        
        Args:
            session_id: QA session identifier
            
        Returns:
            Dictionary with analysis results and recommendations
        """
        feedback = self.qa_store.get_session_feedback(session_id)
        
        if not feedback:
            return {
                'total_reviews': 0,
                'accepted': 0,
                'rejected': 0,
                'acceptance_rate': 0.0,
                'suggested_weights': None,
                'good_examples': [],
                'confidence': 0.0
            }
        
        # Count accepted/rejected
        accepted = [f for f in feedback if self._is_accepted(f['status'])]
        rejected = [f for f in feedback if self._is_rejected(f['status'])]
        
        total_reviews = len(accepted) + len(rejected)
        acceptance_rate = len(accepted) / total_reviews if total_reviews > 0 else 0.0
        
        # Analyze which matches performed well
        analysis = {
            'total_reviews': total_reviews,
            'accepted': len(accepted),
            'rejected': len(rejected),
            'acceptance_rate': acceptance_rate,
            'rank_distribution': self._analyze_rank_distribution(feedback),
            'suggested_weights': self._suggest_weights(feedback),
            'good_examples': self._extract_good_examples(accepted),
            'correction_examples': self._extract_correction_examples(rejected),
            'confidence': min(total_reviews / 50, 1.0)  # Based on sample size
        }
        
        return analysis
    
    def _analyze_rank_distribution(self, feedback: List[Dict]) -> Dict:
        """Analyze which ranks were accepted/rejected"""
        rank_stats = {}
        
        for entry in feedback:
            rank = entry['match_rank']
            status = entry['status']
            
            if rank not in rank_stats:
                rank_stats[rank] = {'accepted': 0, 'rejected': 0}
            
            if self._is_accepted(status):
                rank_stats[rank]['accepted'] += 1
            elif self._is_rejected(status):
                rank_stats[rank]['rejected'] += 1
        
        # Calculate acceptance rate per rank
        for rank, stats in rank_stats.items():
            total = stats['accepted'] + stats['rejected']
            stats['acceptance_rate'] = stats['accepted'] / total if total > 0 else 0.0
        
        return rank_stats
    
    def _suggest_weights(self, feedback: List[Dict]) -> Optional[Dict]:
        """
        Suggest new weights based on QA patterns
        
        Note: This is a heuristic approach. For production, you'd want to:
        - Track which search method (semantic vs keyword) contributed to each match
        - Store intermediate scores during matching
        - Use more sophisticated ML techniques
        
        Current approach: Use acceptance rate and rank position as proxies
        """
        if len(feedback) < 10:
            return None
        
        accepted = [f for f in feedback if self._is_accepted(f['status'])]
        rejected = [f for f in feedback if self._is_rejected(f['status'])]
        
        # Heuristic: If many top ranks are accepted, current approach is good
        # If lower ranks are accepted more, we might need to adjust
        
        avg_accepted_rank = statistics.mean([f['match_rank'] for f in accepted]) if accepted else 0
        avg_rejected_rank = statistics.mean([f['match_rank'] for f in rejected]) if rejected else 0
        
        acceptance_rate = len(accepted) / (len(accepted) + len(rejected))
        
        # Current weights as baseline
        current_semantic = 0.7
        current_keyword = 0.3
        
        # Adjust based on performance
        if acceptance_rate > 0.8:
            # High acceptance - current weights are good, minimal adjustment
            semantic_adjustment = 0.0
        elif acceptance_rate < 0.5:
            # Low acceptance - try different balance
            # If low ranks are being accepted, try boosting alternative method
            if avg_accepted_rank > 2:
                semantic_adjustment = -0.1  # Try more keyword
            else:
                semantic_adjustment = 0.1  # Try more semantic
        else:
            # Medium acceptance - slight adjustment
            semantic_adjustment = 0.05 if avg_accepted_rank < 2 else -0.05
        
        new_semantic = max(0.4, min(0.9, current_semantic + semantic_adjustment))
        new_keyword = 1.0 - new_semantic
        
        return {
            'semantic_weight': new_semantic,
            'keyword_weight': new_keyword,
            'reasoning': self._generate_weight_reasoning(
                acceptance_rate, 
                avg_accepted_rank, 
                avg_rejected_rank,
                semantic_adjustment
            )
        }
    
    def _generate_weight_reasoning(self, acceptance_rate: float, 
                                   avg_accepted_rank: float,
                                   avg_rejected_rank: float,
                                   adjustment: float) -> str:
        """Generate human-readable explanation for weight suggestion"""
        if acceptance_rate > 0.8:
            return f"High acceptance rate ({acceptance_rate:.1%}). Current weights are working well."
        elif acceptance_rate < 0.5:
            if avg_accepted_rank > 2:
                return f"Low acceptance rate ({acceptance_rate:.1%}) with accepted matches at lower ranks (avg: {avg_accepted_rank:.1f}). Suggesting more keyword weighting to surface different results."
            else:
                return f"Low acceptance rate ({acceptance_rate:.1%}). Suggesting more semantic weighting for better understanding."
        else:
            direction = "semantic" if adjustment > 0 else "keyword"
            return f"Moderate acceptance rate ({acceptance_rate:.1%}). Slightly increasing {direction} weighting for improvement."
    
    def _extract_good_examples(self, accepted_feedback: List[Dict], 
                               max_examples: int = 5) -> List[Dict]:
        """
        Extract good query-match pairs for few-shot learning
        
        Args:
            accepted_feedback: List of accepted feedback entries
            max_examples: Maximum number of examples to return
            
        Returns:
            List of example dictionaries
        """
        # Prioritize rank 1 matches as they're most confident
        rank1_accepted = [f for f in accepted_feedback if f['match_rank'] == 1]
        other_accepted = [f for f in accepted_feedback if f['match_rank'] > 1]
        
        # Take rank 1 first, then others
        examples_pool = rank1_accepted + other_accepted
        
        examples = []
        for entry in examples_pool[:max_examples]:
            examples.append({
                'query': entry['query'],
                'match_text': entry['match_text'][:300],  # Truncate for context
                'match_rank': entry['match_rank']
            })
        
        return examples

    def _extract_correction_examples(self, rejected_feedback: List[Dict], 
                                     max_examples: int = 5) -> List[Dict]:
        """Extract rejected matches that include analyst-provided corrections."""
        examples = []
        for entry in rejected_feedback:
            notes = self._parse_notes(entry.get('notes'))
            suggested_key = notes.get('suggested_key', '').strip() if isinstance(notes.get('suggested_key'), str) else ""
            suggested_text = notes.get('suggested_text', '').strip() if isinstance(notes.get('suggested_text'), str) else ""
            analyst_note = notes.get('analyst_note', '').strip() if isinstance(notes.get('analyst_note'), str) else ""

            if suggested_key or suggested_text or analyst_note:
                examples.append({
                    'query': entry.get('query', ''),
                    'bad_match_text': entry.get('match_text', '')[:300],
                    'suggested_key': suggested_key,
                    'suggested_text': suggested_text[:300],
                    'analyst_note': analyst_note[:200]
                })

            if len(examples) >= max_examples:
                break

        return examples
    
    def build_few_shot_context(self, session_id: str, max_examples: int = 3) -> str:
        """
        Build few-shot context string from QA feedback
        
        Args:
            session_id: QA session identifier
            max_examples: Maximum number of examples to include
            
        Returns:
            Formatted context string for LLM prompt
        """
        analysis = self.analyze_qa_session(session_id)
        examples = analysis['good_examples'][:max_examples]
        correction_examples = analysis.get('correction_examples', [])[:max_examples]
        
        if not examples and not correction_examples:
            return ""
        
        context = ""
        if examples:
            context += "Based on previous analyst reviews, here are examples of good query-match pairs:\n\n"
            
            for i, example in enumerate(examples, 1):
                context += f"Example {i}:\n"
                context += f"Query: \"{example['query']}\"\n"
                context += f"Good Match: \"{example['match_text']}\"\n\n"
            
            context += "Use these examples to guide your relevance assessment.\n\n"

        if correction_examples:
            context += "Avoid patterns from analyst-rejected matches:\n\n"
            for i, example in enumerate(correction_examples, 1):
                context += f"Correction {i}:\n"
                context += f"Query: \"{example['query']}\"\n"
                context += f"Rejected Match: \"{example['bad_match_text']}\"\n"
                if example.get('suggested_key'):
                    context += f"Suggested Key: \"{example['suggested_key']}\"\n"
                if example.get('suggested_text'):
                    context += f"Suggested Better Match: \"{example['suggested_text']}\"\n"
                if example.get('analyst_note'):
                    context += f"Analyst Note: \"{example['analyst_note']}\"\n"
                context += "\n"
        
        return context
    
    def get_learning_summary(self, session_id: str) -> str:
        """
        Generate a human-readable summary of learnings
        
        Args:
            session_id: QA session identifier
            
        Returns:
            Formatted summary string
        """
        analysis = self.analyze_qa_session(session_id)
        
        if analysis['total_reviews'] == 0:
            return "No QA feedback available yet."
        
        summary = f"""
QA Learning Summary
==================
Total Reviews: {analysis['total_reviews']}
Accepted: {analysis['accepted']} ({analysis['acceptance_rate']:.1%})
Rejected: {analysis['rejected']} ({(1-analysis['acceptance_rate']):.1%})

Rank Performance:
"""
        
        for rank, stats in sorted(analysis['rank_distribution'].items()):
            summary += f"  Rank {rank}: {stats['acceptance_rate']:.1%} accepted ({stats['accepted']}/{stats['accepted']+stats['rejected']})\n"
        
        if analysis['suggested_weights']:
            weights = analysis['suggested_weights']
            summary += f"\nSuggested Weights:\n"
            summary += f"  Semantic: {weights['semantic_weight']:.1%}\n"
            summary += f"  Keyword: {weights['keyword_weight']:.1%}\n"
            summary += f"  Reasoning: {weights['reasoning']}\n"
        
        summary += f"\nGood Examples Identified: {len(analysis['good_examples'])}\n"
        summary += f"Confidence: {analysis['confidence']:.1%}\n"
        
        return summary

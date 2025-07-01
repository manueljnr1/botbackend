import asyncio
import random
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class SimpleHumanDelaySimulator:
    """Optimized human-like response delays for modern chat expectations"""
    
    def __init__(self):
        # Optimized response delay ranges (in seconds)
        self.quick_response_range = (0.3, 0.8)      # FAQs and simple answers
        self.normal_response_range = (0.8, 2.0)     # Regular questions
        self.complex_response_range = (1.5, 3.5)    # Complex explanations
        self.very_complex_range = (2.5, 5.0)        # Maximum for any response
        
        # Reduced factors for better UX
        self.response_length_factor = 0.005  # Reduced from 0.02 to 0.005
        self.randomness_factor = 0.2         # Reduced from 0.3 to 0.2
        self.min_delay = 0.2                 # Absolute minimum
        self.max_delay = 5.0                 # Absolute maximum
        
    def calculate_response_delay(self, user_message: str, bot_response: str) -> float:
        """Calculate optimized delay for modern chat expectations"""
        
        # 1. Analyze question complexity
        complexity_score = self._analyze_complexity(user_message)
        
        # 2. Consider response length (reduced impact)
        response_length = len(bot_response)
        
        # 3. Select base delay range based on complexity
        if complexity_score < 0.3:
            base_range = self.quick_response_range
            delay_type = "quick"
        elif complexity_score < 0.6:
            base_range = self.normal_response_range
            delay_type = "normal"
        elif complexity_score < 0.8:
            base_range = self.complex_response_range
            delay_type = "complex"
        else:
            base_range = self.very_complex_range
            delay_type = "very_complex"
        
        # 4. Calculate base delay
        base_delay = random.uniform(*base_range)
        
        # 5. Add minimal response length factor
        length_delay = response_length * self.response_length_factor
        
        # 6. Add reduced randomness
        total_delay = base_delay + length_delay
        randomness = total_delay * self.randomness_factor * random.uniform(-1, 1)
        
        # 7. Apply strict bounds
        final_delay = max(self.min_delay, min(self.max_delay, total_delay + randomness))
        
        logger.info(f"Delay: complexity={complexity_score:.2f} ({delay_type}), "
                   f"length={response_length}, final={final_delay:.2f}s")
        
        return final_delay
    
    def _analyze_complexity(self, message: str) -> float:
        """Analyze message complexity (0.0 = simple, 1.0 = very complex)"""
        message_lower = message.lower()
        complexity = 0.1  # Reduced base complexity
        
        # Question indicators
        question_words = ['what', 'how', 'why', 'when', 'where', 'which', 'who']
        for word in question_words:
            if word in message_lower:
                complexity += 0.1
                break
        
        # Complexity indicators
        complex_indicators = [
            'explain', 'detail', 'compare', 'difference', 'how to', 'step by step',
            'comprehensive', 'thorough', 'complete', 'understand', 'clarify',
            'complicated', 'complex', 'advanced', 'technical'
        ]
        
        for indicator in complex_indicators:
            if indicator in message_lower:
                complexity += 0.15
        
        # Multiple questions or parts
        if message_lower.count('?') > 1:
            complexity += 0.15  # Reduced from 0.2
        
        if ' and ' in message_lower or ' or ' in message_lower:
            complexity += 0.1
        
        # Message length factor (reduced impact)
        if len(message) > 100:
            complexity += 0.1  # Reduced from 0.2
        elif len(message) > 200:
            complexity += 0.15  # Reduced from 0.3
        
        # FAQ-like patterns (reduce complexity for common questions)
        faq_patterns = [
            'what is your', 'what are your', 'how can i', 'do you have',
            'business hours', 'contact', 'website', 'phone', 'email',
            'price', 'cost', 'free', 'support', 'hello', 'hi', 'hey'
        ]
        
        for pattern in faq_patterns:
            if pattern in message_lower:
                complexity -= 0.3  # Increased reduction for instant FAQ responses
                break
        
        return max(0.0, min(1.0, complexity))
    
    
"""
Language detection and translation service for the chatbot
"""
import logging
from typing import Optional, Tuple
# import os # os was imported but not used, can be removed if not needed elsewhere

logger = logging.getLogger(__name__)

# --- Define TRANSLATION_AVAILABLE at the module level first ---
TRANSLATION_AVAILABLE = False
# These will store the actual imported modules/classes if successful
_langdetect_detect = None
_LangDetectException = None
_GoogleTranslator = None

# Try to import the language detection and translation libraries
try:
    from langdetect import detect as langdetect_detect_imported, LangDetectException as LangDetectException_imported
    from deep_translator import GoogleTranslator as GoogleTranslator_imported
    
    # If imports are successful, update the flags and assign the imported items
    _langdetect_detect = langdetect_detect_imported
    _LangDetectException = LangDetectException_imported
    _GoogleTranslator = GoogleTranslator_imported
    TRANSLATION_AVAILABLE = True
    logger.info("Successfully imported langdetect and deep-translator. Translation and detection features are available.")

except ImportError:
    # TRANSLATION_AVAILABLE remains False (its default value)
    logger.warning(
        "Language detection/translation libraries (langdetect, deep-translator) not installed. "
        "Translation and detection features will be disabled. To enable them, run: "
        "pip install langdetect deep-translator"
    )
    # _langdetect_detect, _LangDetectException, _GoogleTranslator remain None

# Define supported languages with their codes
SUPPORTED_LANGUAGES = {
    'en': 'English',
    'es': 'Spanish',
    'fr': 'French',
    'de': 'German',
    'it': 'Italian',
    'pt': 'Portuguese',
    'nl': 'Dutch',
    'ru': 'Russian',
    'zh-cn': 'Chinese (Simplified)',
    'ja': 'Japanese',
    'ko': 'Korean',
    'ar': 'Arabic',
    'hi': 'Hindi',
    'sw': 'Swahili',
    'yo': 'Yoruba',
    'ha': 'Hausa',
    'bn': 'Bengali',
    'ur': 'Urdu',
    'id': 'Indonesian',
    'tr': 'Turkish',
    'vi': 'Vietnamese',
    'fa': 'Persian (Farsi)',
    'pl': 'Polish',
    'th': 'Thai',
    'uk': 'Ukrainian',
    'el': 'Greek',
    'tl': 'Filipino',
    'ig': 'Igbo'
}

# LangDetect to Google Translate language code mapping
LANGDETECT_TO_GOOGLE = {
    'zh-cn': 'zh-CN', # GoogleTranslator uses 'zh-CN' for simplified chinese
    'zh-tw': 'zh-TW', # GoogleTranslator uses 'zh-TW' for traditional chinese
    # Add other mappings if langdetect returns codes different from what GoogleTranslator expects
}

class LanguageService:
    """Service for language detection and translation"""
    
    def __init__(self):
        """Initialize the language service"""
        self.translator_operational = TRANSLATION_AVAILABLE
        logger.info(f"Translation service initialized. Operational: {self.translator_operational}")
    
    def detect_language(self, text: str) -> Optional[str]:
        """
        Detect the language of the text.
        Returns language code (e.g., 'en', 'es', etc.) or None if detection fails or libraries are unavailable.
        """
        if not TRANSLATION_AVAILABLE or not _langdetect_detect or not text:
            # This check ensures that the 'detect' function from langdetect was actually imported
            if text: # Only log if text was provided but detection is unavailable
                 logger.debug("Language detection libraries not available or text is empty. Cannot detect language.")
            return None
        
        try:
            lang_code = _langdetect_detect(text) 
            # Map langdetect's output to what GoogleTranslator might expect, if necessary
            mapped_lang_code = LANGDETECT_TO_GOOGLE.get(lang_code, lang_code)
            
            # Check if it's a language your system explicitly supports (optional, but good for consistency)
            if mapped_lang_code in SUPPORTED_LANGUAGES:
                logger.debug(f"Detected language: {SUPPORTED_LANGUAGES.get(mapped_lang_code, mapped_lang_code)} ({mapped_lang_code})")
                return mapped_lang_code
            else:
                # If you want to allow any language detected by langdetect, even if not in your SUPPORTED_LANGUAGES list:
                logger.debug(f"Detected language (not in explicit support list): {mapped_lang_code}")
                return mapped_lang_code # Or return None if you only want to handle explicitly supported ones
        except _LangDetectException as e: # Use the imported LangDetectException
            logger.warning(f"Language detection failed for text \"{text[:30]}...\": {e}")
            return None
        except Exception as e: # Catch any other unexpected errors
            logger.error(f"Unexpected error during language detection for text \"{text[:30]}...\": {e}")
            return None
    
    def translate(self, text: str, target_lang: str = 'en', source_lang: Optional[str] = None) -> Tuple[str, bool]:
        """
        Translate text to the target language.
        Returns (translated_text, was_translated_boolean).
        """
        if not self.translator_operational or not _GoogleTranslator or not text:
            # If translation is not operational or no text, return original
            if text: # Only log if text was provided but translation is unavailable
                logger.debug("Translation not operational or text is empty. Cannot translate.")
            return text, False
        
        # Determine the source language
        actual_source_lang = source_lang if source_lang else 'auto'
        
        # If source and target are the same, no need to translate
        if actual_source_lang != 'auto' and actual_source_lang == target_lang:
            logger.debug(f"Source language ({actual_source_lang}) and target language ({target_lang}) are the same. No translation needed.")
            return text, False
        
        # If source is 'auto', we should attempt detection first to avoid unnecessary translation
        if actual_source_lang == 'auto':
            detected_lang = self.detect_language(text)
            if detected_lang and detected_lang == target_lang:
                logger.debug(f"Detected language ({detected_lang}) is the same as target language ({target_lang}). No translation needed.")
                return text, False
        
        try:
            # Create a translator instance for this specific translation
            # deep-translator requires a new instance for each source/target pair
            translator = _GoogleTranslator(source=actual_source_lang, target=target_lang)
            
            # Perform the translation
            translated_text = translator.translate(text)
            
            if translated_text:
                logger.info(f"Translated from {actual_source_lang} to {target_lang}: \"{text[:30]}...\" -> \"{translated_text[:30]}...\"")
                return translated_text, True
            else:
                logger.error(f"Translation attempt from {actual_source_lang} to {target_lang} did not return expected result.")
                return text, False
        except Exception as e:
            logger.error(f"Error during translation from {actual_source_lang} to {target_lang} for text \"{text[:30]}...\": {e}")
            return text, False # Fallback to original text on error
    
    def get_language_name(self, lang_code: str) -> str:
        """Get the full language name from a language code."""
        return SUPPORTED_LANGUAGES.get(lang_code, lang_code)

# Create a singleton instance of the service
# This will be created when the module is first imported.
language_service = LanguageService()
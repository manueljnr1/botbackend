# test_translation.py
from app.utils.language_service import language_service

def test_translation():
    # Test language detection
    text = "Hola, ¿cómo estás?"
    detected_lang = language_service.detect_language(text)
    print(f"Detected language: {detected_lang}")
    
    # Test translation
    translated_text, was_translated = language_service.translate(text, target_lang='en')
    print(f"Original: {text}")
    print(f"Translated: {translated_text}")
    print(f"Was translated: {was_translated}")
    
    # Test other language
    english_text = "Hello, how are you?"
    fr_translation, was_translated = language_service.translate(english_text, target_lang='fr')
    print(f"Original: {english_text}")
    print(f"French: {fr_translation}")
    print(f"Was translated: {was_translated}")

if __name__ == "__main__":
    test_translation()
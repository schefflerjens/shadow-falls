import re
from collections import Counter

# Set of common English stopwords for content word frequency analysis
STOPWORDS = {
    'the', 'a', 'an', 'and', 'but', 'or', 'for', 'nor', 'so', 'yet', 'of', 'to', 'in', 'on', 'at',
    'by', 'from', 'with', 'about', 'as', 'into', 'like', 'through', 'after', 'over', 'between',
    'out', 'against', 'during', 'without', 'before', 'under', 'around', 'among', 'i', 'you',
    'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his',
    'their', 'our', 'its', 'this', 'that', 'these', 'those', 'is', 'am', 'are', 'was', 'were',
    'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'shall',
    'should', 'can', 'could', 'may', 'might', 'must', 'who', 'whom', 'which', 'what', 'whose',
    'there', 'here', 'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more',
    'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very'
}

# Words ending in -ly that are NOT adverbs (e.g. family, friendly)
ADVERB_EXCEPTIONS = {
    'only', 'early', 'family', 'ally', 'holy', 'silly', 'friendly', 'ugly', 'lonely', 'lovely',
    'fly', 'rely', 'ply', 'monopoly', 'jelly', 'belly', 'holly', 'bully', 'rally', 'sally',
    'lily', 'chilly', 'billy', 'folly', 'wooly', 'daily', 'weekly', 'monthly', 'yearly'
}

# Verbs used in passive auxiliary forms
PASSIVE_AUXILIARIES = {'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being'}

# Standard irregular past participles in English
IRREGULAR_PAST_PARTICIPLES = {
    'seen', 'known', 'taken', 'written', 'done', 'gone', 'built', 'held', 'caught', 'broken',
    'kept', 'felt', 'left', 'meant', 'spoken', 'given', 'run', 'brought', 'bought', 'sold',
    'found', 'lost', 'shot', 'spent', 'sent', 'met', 'heard', 'learnt', 'chosen', 'cut', 'hit',
    'hurt', 'put', 'read', 'set', 'shut', 'worn', 'drawn', 'shown', 'thrown', 'grown', 'blown',
    'flown', 'driven', 'ridden', 'fallen', 'shaken', 'begun', 'drunk', 'sung', 'swum', 'hidden',
    'slept', 'drawn', 'told', 'understood', 'forgotten', 'stood', 'struck', 'swept', 'sworn'
}

# Common past participles and adjectives ending in -ed/irregular that function statively
ADJECTIVAL_PARTICIPLE_EXCLUSIONS = {
    'naked', 'sacred', 'wicked', 'crooked', 'beloved', 'blessed', 'ragged', 'rugged',
    'bored', 'tired', 'finished', 'scared', 'worried', 'excited', 'confused', 
    'interested', 'pleased', 'satisfied', 'surprised', 'disappointed', 'annoyed', 
    'frightened', 'hurried', 'detailed', 'complicated', 'limited', 'advanced',
    'determined', 'skilled', 'experienced', 'talented', 'gifted', 'isolated',
    'unexpected', 'unprecedented', 'sophisticated', 'qualified', 'civilized',
    'depressed', 'exhausted', 'relaxed', 'stressed', 'deserved', 'closed', 'lost'
}


# Common stylistic filler words
FILLER_WORDS = {
    'just', 'very', 'really', 'suddenly', 'then', 'actually', 'basically', 'literally',
    'somehow', 'somewhat', 'perhaps', 'maybe'
}

def count_syllables(word: str) -> int:
    """
    Syllable counter with vowel heuristics and standard English exceptions.
    """
    word = word.lower().strip(".:,;?!-\"()[]{}'*_")
    if not word:
        return 0
    if len(word) <= 3:
        return 1
        
    vowels = "aeiouy"
    count = 0
    is_prev_vowel = False
    
    # Count consecutive vowel blocks
    for char in word:
        is_vowel = char in vowels
        if is_vowel and not is_prev_vowel:
            count += 1
        is_prev_vowel = is_vowel
        
    # Subtract silent 'e' at the end, but keep consonant + 'le'
    if word.endswith('e'):
        if len(word) > 2 and word[-2] not in vowels and word[-2] == 'l':
            pass # Keep (e.g. "table", "bottle")
        else:
            count -= 1
            
    # Handle 'es' and 'ed' endings
    if word.endswith('es') or word.endswith('ed'):
        if word.endswith('ed') and len(word) > 2 and word[-3] in 'td':
            pass # Waited, ended (retains syllable)
        elif word.endswith('es') and len(word) > 2 and word[-3] in 'sczhg':
            pass # Classes, boxes (retains syllable)
        else:
            count -= 1
            
    if count <= 0:
        count = 1
    return count

def compute_readability_metrics(text: str) -> dict:
    """
    Tokenizes text into sentences and words, then calculates readability grades and style indices.
    """
    # Clean up standard RTF control chars or markdown formatting if any
    cleaned_text = re.sub(r'<[^>]*>', '', text)
    
    # Sentence tokenization (split on punctuation followed by space or end of string)
    sentence_matches = re.split(r'[.!?]+(?:\s+|$)', cleaned_text.strip())
    sentences = [s.strip() for s in sentence_matches if s.strip()]
    total_sentences = len(sentences)
    
    # Word tokenization
    words = re.findall(r"\b[a-zA-Z']+\b", cleaned_text)
    total_words = len(words)
    
    if total_words == 0 or total_sentences == 0:
        return {
            "total_words": 0,
            "total_sentences": 0,
            "flesch_reading_ease": 100.0,
            "flesch_kincaid_grade": 0.0,
            "average_sentence_length": 0.0,
            "average_syllables_per_word": 0.0,
            "adverb_density": 0.0,
            "passive_voice_density": 0.0,
            "filler_word_density": 0.0,
            "top_repeated_words": [],
            "repeated_phrases": {}
        }
        
    # Readability values
    total_syllables = sum(count_syllables(w) for w in words)
    avg_sentence_length = total_words / total_sentences
    avg_syllables_per_word = total_syllables / total_words
    
    # Flesch Reading Ease (FRE)
    fre = 206.835 - 1.015 * avg_sentence_length - 84.6 * avg_syllables_per_word
    # Flesch-Kincaid Grade Level (FKGL)
    fkgl = 0.39 * avg_sentence_length + 11.8 * avg_syllables_per_word - 15.59
    
    # Ensure readability scores are within reasonable bounds
    fre = max(0.0, min(100.0, fre))
    fkgl = max(0.0, fkgl)
    
    # Adverb Density (-ly adverbs, excluding common exceptions)
    adverb_count = 0
    for w in words:
        wl = w.lower()
        if wl.endswith('ly') and wl not in ADVERB_EXCEPTIONS:
            adverb_count += 1
    adverb_density = (adverb_count / total_words) * 100
    
    # Passive Voice Count
    # Identify auxiliary + past participle within the same sentence (handling possible middle adverbs/words up to 2 words, e.g. "was quickly taken")
    passive_count = 0
    
    for sentence in sentences:
        s_words = re.findall(r"\b[a-zA-Z']+(?:-[a-zA-Z']+)*\b", sentence)
        s_words_lower = [w.lower() for w in s_words]
        matched_indices = set()
        for i, w in enumerate(s_words_lower):
            if w in PASSIVE_AUXILIARIES:
                # Look ahead up to 3 words for a past participle within the same sentence
                for offset in range(1, 4):
                    idx = i + offset
                    if idx < len(s_words_lower):
                        target = s_words_lower[idx]
                        
                        # Check for "supposed to" (semi-auxiliary modal phrase)
                        is_supposed_to = (target == 'supposed' and idx + 1 < len(s_words_lower) and s_words_lower[idx + 1] == 'to')
                        
                        # Check if target is a past participle and not already matched in this sentence
                        is_past_participle = (
                            idx not in matched_indices
                            and ((target.endswith('ed') and not target.endswith('need')) or (target in IRREGULAR_PAST_PARTICIPLES))
                            and '-' not in target
                            and target not in ADJECTIVAL_PARTICIPLE_EXCLUSIONS
                            and not is_supposed_to
                        )
                        
                        # Check if there's an intervening -ing verb that makes it progressive/adjectival
                        has_intervening_ing = False
                        if offset > 1:
                            for j in range(1, offset):
                                intervening_word = s_words_lower[i + j]
                                if intervening_word.endswith('ing') and intervening_word != 'being':
                                    has_intervening_ing = True
                                    break
                                    
                        if is_past_participle and not has_intervening_ing:
                            passive_count += 1
                            matched_indices.add(idx)
                            break  # count once per auxiliary
                            
    passive_density = (passive_count / total_sentences) * 100
    
    # Filler Words Count
    filler_count = 0
    # Include contiguous matches for multi-word fillers like "began to" / "started to"
    text_lower = cleaned_text.lower()
    multi_word_fillers = re.findall(r"\b(began to|started to)\b", text_lower)
    filler_count += len(multi_word_fillers)
    
    for w in words:
        if w.lower() in FILLER_WORDS:
            filler_count += 1
            
    filler_word_density = (filler_count / total_words) * 100
    
    # Repetition: Top content words (excluding stopwords)
    content_words = [w.lower() for w in words if w.lower() not in STOPWORDS]
    word_freq = Counter(content_words)
    top_repeated_words = word_freq.most_common(15)
    
    # Phrase Repetitions (2-gram, 3-gram, and 4-gram contiguous phrases)
    repeated_phrases = {
        "2_grams": [],
        "3_grams": [],
        "4_grams": []
    }
    
    words_lc = [w.lower() for w in words]
    for n, key in [(2, "2_grams"), (3, "3_grams"), (4, "4_grams")]:
        n_grams = [" ".join(words_lc[i:i+n]) for i in range(len(words_lc) - n + 1)]
        phrase_freq = Counter(n_grams)
        # Filter to phrases appearing at least 2 times
        dupes = [(phrase, count) for phrase, count in phrase_freq.most_common(10) if count >= 2]
        repeated_phrases[key] = dupes
        
    return {
        "total_words": total_words,
        "total_sentences": total_sentences,
        "flesch_reading_ease": round(fre, 1),
        "flesch_kincaid_grade": round(fkgl, 1),
        "average_sentence_length": round(avg_sentence_length, 1),
        "average_syllables_per_word": round(avg_syllables_per_word, 2),
        "adverb_density": round(adverb_density, 2),
        "passive_voice_density": round(passive_density, 2),
        "filler_word_density": round(filler_word_density, 2),
        "top_repeated_words": top_repeated_words,
        "repeated_phrases": repeated_phrases
    }

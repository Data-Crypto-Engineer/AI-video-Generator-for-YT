import re
import html
from typing import List, Tuple, Dict, Any

class ScriptNormalizer:
    """
    Normalizes raw user scripts for production without altering intended meaning.
    Performs editorial cleanup (spacing, capitalization, punctuation, entities)
    and checks religious/Islamic quotations for required verification flags.
    """

    # Common honorifics and religious reference patterns that require source verification
    RELIGIOUS_PATTERNS = [
        re.compile(r'\b(the\s+prophet|prophet\s+muhammad|rasulullah|messenger\s+of\s+allah)\s+(said|stated|told|taught|commanded)\b', re.IGNORECASE),
        re.compile(r'\b(allah\s+(says|stated|revealed|commands)|the\s+qur\'?an\s+says)\b', re.IGNORECASE),
        re.compile(r'\b(hadith|hadeeth|sunnah|sahih|bukhari|muslim|tirmidhi|abu\s+dawud)\b', re.IGNORECASE),
        re.compile(r'\b(in\s+surah\s+[a-z\-]+|ayah|surat\s+[a-z\-]+)\b', re.IGNORECASE),
        re.compile(r'\b(im[a-z]*|scholar|sheikh|shaykh|ibn\s+taymiyyah|al-ghazali)\s+(said|wrote|quoted)\b', re.IGNORECASE),
    ]

    def normalize(self, script: str) -> Tuple[str, List[str]]:
        """
        Cleans and normalizes script text.
        Returns:
            normalized_script: Cleaned string
            warnings: List of editorial or religious source verification warnings
        """
        warnings: List[str] = []

        if not script or not script.strip():
            return "", ["Script is empty."]

        # 1. Unescape HTML entities (&quot;, &#39;, &amp;, &lt;, &gt;, etc.)
        cleaned = html.unescape(script)

        # 2. Normalize Windows and legacy line breaks to standard newlines
        cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")

        # 3. Collapse excessive newlines (max 2 consecutive newlines for paragraph breaks)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

        # 4. Collapse multiple spaces and tabs to a single space
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)

        # 5. Fix common punctuation spacing (e.g. "word ,word" -> "word, word")
        cleaned = re.sub(r'\s+([,\.!?;:])', r'\1', cleaned)
        cleaned = re.sub(r'([,\.!?;:])([^\s\d\'"”’\)])', r'\1 \2', cleaned)

        # 6. Normalize duplicated punctuation (e.g. ",," -> ",", "???" -> "?", "!!" -> "!")
        cleaned = re.sub(r',{2,}', ',', cleaned)
        cleaned = re.sub(r';{2,}', ';', cleaned)
        cleaned = re.sub(r':{2,}', ':', cleaned)
        cleaned = re.sub(r'\!{2,}', '!', cleaned)
        cleaned = re.sub(r'\?{2,}', '?', cleaned)
        # Preserve ellipsis (...)
        cleaned = re.sub(r'\.{4,}', '...', cleaned)

        # 7. Normalize sentence capitalization
        def capitalize_sentences(text: str) -> str:
            # Capitalize start of paragraphs and start of sentences after . ! ?
            paragraphs = text.split("\n")
            capitalized_paras = []
            for para in paragraphs:
                para = para.strip()
                if not para:
                    capitalized_paras.append("")
                    continue
                
                # Capitalize first character of paragraph
                if para:
                    para = para[0].upper() + para[1:]
                
                # Capitalize after sentence endings
                def cap_match(match):
                    return match.group(1) + match.group(2).upper()
                
                para = re.sub(r'([\.!\?]\s+)([a-z])', cap_match, para)
                capitalized_paras.append(para)

            return "\n".join(capitalized_paras)

        cleaned = capitalize_sentences(cleaned)

        # 8. Check for Islamic/religious quotations requiring authentic verification
        for pattern in self.RELIGIOUS_PATTERNS:
            matches = pattern.findall(cleaned)
            if matches:
                # Extract sample for warning context
                match_obj = pattern.search(cleaned)
                sample = match_obj.group(0) if match_obj else "religious reference"
                warn_msg = (
                    f"Religious citation/reference detected in script ('{sample}'): "
                    f"Verify authentic source (Surah/Ayah or Hadith collection) before broadcast. "
                    f"The system will never fabricate or alter religious citations."
                )
                if warn_msg not in warnings:
                    warnings.append(warn_msg)

        # Final cleanup
        cleaned = cleaned.strip()

        return cleaned, warnings

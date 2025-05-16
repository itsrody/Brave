# adblock_processor/syntax_db.py
import json
import os
import re
from .utils.exceptions import SyntaxDBError

class SyntaxDB:
    """
    Manages access to syntax patterns for validation and translation.
    Patterns are loaded from JSON files.
    """
    def __init__(self, patterns_dir='syntax_patterns/'):
        self.patterns_dir = patterns_dir
        self.brave_supported_syntax = {}
        self.translation_patterns = [] # For rules that need translation
        self.unsupported_patterns = [] # For rules known to be unsupported

        self._load_patterns()

    def _load_patterns(self):
        """Loads all .json files from the patterns directory."""
        if not os.path.isdir(self.patterns_dir):
            raise SyntaxDBError(f"Syntax patterns directory not found: {self.patterns_dir}")

        for filename in os.listdir(self.patterns_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.patterns_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if not isinstance(data, list):
                            raise SyntaxDBError(f"Expected a list of patterns in {filename}, got {type(data)}")
                        
                        for pattern_entry in data:
                            self._process_pattern_entry(pattern_entry, filename)
                                
                except json.JSONDecodeError as e:
                    raise SyntaxDBError(f"Error decoding JSON from {filepath}: {e}")
                except IOError as e:
                    raise SyntaxDBError(f"Error reading file {filepath}: {e}")
        
        # Compile regex patterns for efficiency
        for p_list in [self.translation_patterns, self.unsupported_patterns]:
            for p in p_list:
                if 'pattern_regex' in p:
                    try:
                        p['compiled_regex'] = re.compile(p['pattern_regex'])
                    except re.error as e:
                        raise SyntaxDBError(f"Invalid regex in pattern '{p.get('name', 'N/A')}': {p['pattern_regex']}. Error: {e}")
        
        # For brave_supported_syntax, regex might be used for matching rule types
        for category, patterns in self.brave_supported_syntax.items():
            for p in patterns:
                 if 'pattern_regex' in p:
                    try:
                        p['compiled_regex'] = re.compile(p['pattern_regex'])
                    except re.error as e:
                        raise SyntaxDBError(f"Invalid regex in Brave supported pattern '{p.get('name', 'N/A')}': {p['pattern_regex']}. Error: {e}")


    def _process_pattern_entry(self, pattern_entry, source_file):
        """Categorizes a loaded pattern entry."""
        if not isinstance(pattern_entry, dict) or 'name' not in pattern_entry or 'supported_in_brave' not in pattern_entry:
            raise SyntaxDBError(f"Invalid pattern entry in {source_file}: {pattern_entry}. Missing 'name' or 'supported_in_brave'.")

        support_status = pattern_entry['supported_in_brave']

        if support_status == "yes":
            category = pattern_entry.get('category', 'general') # e.g., 'network', 'cosmetic', 'modifier'
            if category not in self.brave_supported_syntax:
                self.brave_supported_syntax[category] = []
            self.brave_supported_syntax[category].append(pattern_entry)
        elif support_status == "partial_translation_available" or support_status == "needs_translation":
            if 'pattern_regex' not in pattern_entry or 'brave_equivalent_template' not in pattern_entry:
                raise SyntaxDBError(f"Translation pattern '{pattern_entry['name']}' in {source_file} missing 'pattern_regex' or 'brave_equivalent_template'.")
            self.translation_patterns.append(pattern_entry)
        elif support_status == "no":
            if 'pattern_regex' not in pattern_entry:
                 # For simple unsupported patterns, regex might not be needed if it's a direct string match of a feature
                pass # Allow patterns without regex if they are just informational
            self.unsupported_patterns.append(pattern_entry)
        else:
            raise SyntaxDBError(f"Unknown 'supported_in_brave' status '{support_status}' in pattern '{pattern_entry['name']}' from {source_file}.")


    def get_brave_supported_pattern(self, rule_text, category='general'):
        """
        Checks if a rule matches any Brave-supported syntax pattern in a given category.
        Returns the matching pattern description or None.
        This is a simplified example; real validation is more complex.
        """
        if category in self.brave_supported_syntax:
            for pattern_info in self.brave_supported_syntax[category]:
                if 'compiled_regex' in pattern_info:
                    if pattern_info['compiled_regex'].fullmatch(rule_text.strip()):
                        return pattern_info
                elif 'token' in pattern_info: # e.g. for simple modifier checks
                    if pattern_info['token'] in rule_text:
                         return pattern_info
        return None

    def find_translation_candidate(self, rule_text):
        """
        Checks if a rule matches any pattern that can be translated.
        Returns a tuple (matching_pattern_info, match_object) or (None, None).
        """
        for pattern_info in self.translation_patterns:
            if 'compiled_regex' in pattern_info:
                match = pattern_info['compiled_regex'].fullmatch(rule_text.strip())
                if match:
                    return pattern_info, match
        return None, None

    def find_unsupported_pattern(self, rule_text):
        """
        Checks if a rule matches any known unsupported pattern.
        Returns the matching pattern_info or None.
        """
        for pattern_info in self.unsupported_patterns:
            if 'compiled_regex' in pattern_info:
                 match = pattern_info['compiled_regex'].search(rule_text.strip()) # Use search for broader matching
                 if match:
                    return pattern_info
            elif 'token' in pattern_info: # If it's a simple token check
                if pattern_info['token'] in rule_text:
                    return pattern_info
        return None

# Example usage:
# syntax_db = SyntaxDB(patterns_dir='path/to/your/syntax_patterns')
# supported_info = syntax_db.get_brave_supported_pattern("||example.com^$script", category="network")
# translation_info, match = syntax_db.find_translation_candidate("example.com#?#div:contains(ad)")
# unsupported_info = syntax_db.find_unsupported_pattern("!#if env_firefox")

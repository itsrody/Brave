# adblock_processor/validator.py
from syntax_db import SyntaxDB
from utils.logger import setup_logger
from utils.exceptions import ValidationError

# logger = setup_logger('validator_module') # Assuming logger is set up in main

class RuleValidator:
    """
    Validates parsed rules against Brave-supported syntax using SyntaxDB.
    This is a simplified validator. Real-world validation would be much more complex,
    involving checking specific option combinations, regex validity for certain options, etc.
    """
    def __init__(self, logger, syntax_db: SyntaxDB):
        self.logger = logger
        self.syntax_db = syntax_db

    def validate_rule(self, parsed_rule):
        """
        Validates a single parsed rule.
        Adds 'validation_status' and 'validation_notes' to the rule object.
        Validation Status:
            - 'valid'
            - 'unsupported'
            - 'needs_translation'
            - 'error' (if rule structure is fundamentally broken for validation)
            - 'comment' / 'metadata' / 'empty' (passthrough)
        """
        rule_type = parsed_rule.get('type')

        if rule_type in ['comment', 'metadata', 'empty', 'error']:
            parsed_rule['validation_status'] = rule_type
            parsed_rule['validation_notes'] = "Not a filter rule, passed through."
            return parsed_rule

        if rule_type != 'rule':
            parsed_rule['validation_status'] = 'error'
            parsed_rule['validation_notes'] = f"Unknown rule type '{rule_type}' for validation."
            self.logger.warning(f"Validation: Unknown rule type in {parsed_rule.get('list_name')}:{parsed_rule.get('line_number')}")
            return parsed_rule

        raw_rule_text = parsed_rule.get('raw_rule', '').strip()
        if not raw_rule_text:
            parsed_rule['validation_status'] = 'empty' # Should have been caught by parser
            parsed_rule['validation_notes'] = "Empty rule string."
            return parsed_rule
            
        # Priority:
        # 1. Check if it's something known to be unsupported directly.
        # 2. Check if it's a candidate for translation.
        # 3. Check if it matches known Brave-supported syntax.
        # 4. If none of the above, mark as potentially unsupported or needing deeper analysis.

        # 1. Check for known unsupported patterns (e.g., !#if directives from uBO)
        unsupported_info = self.syntax_db.find_unsupported_pattern(raw_rule_text)
        if unsupported_info:
            parsed_rule['validation_status'] = 'unsupported'
            parsed_rule['validation_notes'] = f"Matches known unsupported pattern: {unsupported_info.get('name')}. Reason: {unsupported_info.get('notes', 'No specific reason provided.')}"
            self.logger.debug(f"Rule '{raw_rule_text}' flagged as unsupported: {unsupported_info.get('name')}")
            return parsed_rule

        # 2. Check for translation candidates (e.g., AdGuard specific syntax)
        translation_pattern_info, _ = self.syntax_db.find_translation_candidate(raw_rule_text)
        if translation_pattern_info:
            parsed_rule['validation_status'] = 'needs_translation'
            parsed_rule['validation_notes'] = f"Matches pattern '{translation_pattern_info.get('name')}' which may be translatable. {translation_pattern_info.get('notes','')}"
            self.logger.debug(f"Rule '{raw_rule_text}' flagged for translation: {translation_pattern_info.get('name')}")
            return parsed_rule

        # 3. Basic Brave/ABP/uBO syntax checks (simplified)
        # This part needs to be significantly more detailed based on adblock-rust capabilities.
        # The "Brave Adblocker Rule Comparison" document is key here.
        # For now, a placeholder for common valid structures.
        
        is_likely_valid = False
        validation_notes = []

        # Basic network rule: ||domain.com^ or /path/
        # Basic cosmetic rule: example.com##selector
        # Basic exception: @@||domain.com^ or example.com#@#selector
        
        # A very simplified check:
        # If it starts with ||, |, http, or is a path filter (e.g. /adserver.js)
        # Or if it's a cosmetic rule (contains ##, #@#)
        # Or if it's an exception (starts with @@)
        
        # Network rule patterns (simplified)
        if raw_rule_text.startswith('||') or \
           raw_rule_text.startswith('|http') or \
           (not '##' in raw_rule_text and not '#@#' in raw_rule_text and '/' in raw_rule_text and not raw_rule_text.startswith('!')) or \
           (parsed_rule.get('is_exception') and not parsed_rule.get('is_cosmetic')):
            is_likely_valid = True
            validation_notes.append("Likely a valid network rule or exception.")
            # Further check options if any
            if parsed_rule.get('options_str'):
                # Here you would iterate options_dict and check against syntax_db.brave_supported_syntax['modifiers']
                # For example: $script, $image, $third-party, $domain=...
                # This is a complex step.
                # Example:
                # for opt_key, opt_val in parsed_rule.get('options_dict', {}).items():
                #   supported_modifier = self.syntax_db.get_brave_supported_pattern(opt_key, category='modifier')
                #   if not supported_modifier:
                #       is_likely_valid = False
                #       validation_notes.append(f"Unsupported modifier option: ${opt_key}")
                #       break
                pass # Placeholder for detailed option validation

        # Cosmetic rule patterns (simplified)
        elif parsed_rule.get('is_cosmetic') or parsed_rule.get('is_html_filter') or parsed_rule.get('is_scriptlet'):
            # example.com##.ad, ##.ad, example.com#@#.ad, #@#.ad
            # example.com##^.ad (uBO HTML filter - check adblock-rust support from doc)
            # example.com##+js(script) (Brave/uBO scriptlet - check adblock-rust support)
            # The parser already identified these types.
            # The "Brave Adblocker Rule Comparison" states Brave aims for uBO compatibility for these.
            # Procedural cosmetic filters like :has-text() need specific checks based on syntax_db.
            selector = parsed_rule.get('selector', '')
            
            # Check if it's a known Brave-supported procedural operator (e.g. :has-text())
            # This requires patterns in syntax_db for procedural operators.
            # Example: if ':has-text(' in selector:
            #   if not self.syntax_db.get_brave_supported_pattern(':has-text(', category='procedural_cosmetic'):
            #       is_likely_valid = False; validation_notes.append("Unsupported procedural operator :has-text variant.")
            
            # For now, assume basic ## and #@# are fine if not caught by unsupported/translation.
            # And assume ##^ and ##+js are fine if Brave aims for uBO compatibility.
            is_likely_valid = True 
            validation_notes.append(f"Likely a valid {parsed_rule.get('sub_type','cosmetic/scriptlet/html')} rule or exception.")
            # Deeper validation of selector syntax (CSS, uBO procedural, scriptlet args) is needed.

        if is_likely_valid:
            # Final check against general supported patterns if not already confirmed
            # This is a fallback if the above simplified checks are too loose.
            # You might have a general "valid_abp_rule_regex" in syntax_db.
            # supported_generic = self.syntax_db.get_brave_supported_pattern(raw_rule_text, category='general_rule_structure')
            # if supported_generic:
            #    parsed_rule['validation_status'] = 'valid'
            #    parsed_rule['validation_notes'] = f"Matches general supported syntax. Notes: {', '.join(validation_notes)}"
            # else:
            #    parsed_rule['validation_status'] = 'unsupported' # Or 'needs_review'
            #    parsed_rule['validation_notes'] = f"Does not match known Brave syntax patterns. Notes: {', '.join(validation_notes)}"
            parsed_rule['validation_status'] = 'valid' # Assuming for now
            parsed_rule['validation_notes'] = f"Tentatively valid. Detailed syntax check for options/selectors needed. Notes: {', '.join(validation_notes)}"

        else:
            # If not caught by specific unsupported/translation checks, and not matching simple valid patterns
            parsed_rule['validation_status'] = 'unsupported' # Default to unsupported if no positive match
            parsed_rule['validation_notes'] = f"Rule structure does not match common Brave/ABP/uBO patterns or known translatable/unsupported syntax. Requires review. Notes: {', '.join(validation_notes)}"
            self.logger.debug(f"Rule '{raw_rule_text}' from {parsed_rule.get('list_name')} marked as unsupported (default).")

        return parsed_rule

# Example Usage:
# if __name__ == '__main__':
#     logger_instance = setup_logger('validator_test', log_level_str='DEBUG')
#     # Mock SyntaxDB - in real use, it loads from files
#     class MockSyntaxDB:
#         def __init__(self):
#             self.brave_supported_syntax = {
#                 "network": [{"name": "basic_network_domain", "pattern_regex": r"^\|\|([a-zA-Z0-9.-]+)\^\S*", "compiled_regex": re.compile(r"^\|\|([a-zA-Z0-9.-]+)\^\S*")}],
#                 "modifier": [{"name": "script_option", "token": "$script"}],
#                 "procedural_cosmetic": [{"name": "has_text", "token": ":has-text("}]
#             }
#             self.translation_patterns = [
#                 {"name": "AdGuard #?# :contains", "pattern_regex": r"^(.*)#\?#(.*):contains\((.*)\)$", "compiled_regex": re.compile(r"^(.*)#\?#(.*):contains\((.*)\)$"), "supported_in_brave": "needs_translation", "brave_equivalent_template": "{0}##{1}:has-text({2})", "notes": "Translate to :has-text"}
#             ]
#             self.unsupported_patterns = [
#                 {"name": "uBO !#if", "pattern_regex": r"^!#if.*", "compiled_regex": re.compile(r"^!#if.*"), "supported_in_brave": "no", "notes": "Preprocessor directive"}
#             ]
#         def get_brave_supported_pattern(self, text, category): return None # Simplified
#         def find_translation_candidate(self, text): 
#             for p in self.translation_patterns:
#                 m = p['compiled_regex'].match(text)
#                 if m: return p, m
#             return None, None
#         def find_unsupported_pattern(self, text):
#             for p in self.unsupported_patterns:
#                 if p['compiled_regex'].match(text): return p
#             return None

#     syntax_db_mock = MockSyntaxDB()
#     validator = RuleValidator(logger=logger_instance, syntax_db=syntax_db_mock)
#     parser = RuleParser(logger=logger_instance)

#     test_rules_text = [
#         "||example.com^$script", # valid
#         "example.com##.ad", # valid (simplified)
#         "example.com#?#div:contains(ad)", # needs_translation
#         "!#if env_firefox", # unsupported
#         "some_weird_rule_$$$_%%%%", # unsupported (default)
#         "! A comment" # comment
#     ]
    
#     for i, rule_text in enumerate(test_rules_text):
#         parsed = parser.parse_line(i+1, rule_text, "validator_test_list.txt")
#         if parsed and parsed['type'] == 'rule':
#             validated_rule = validator.validate_rule(parsed)
#             logger_instance.info(f"Original: '{rule_text}' -> Status: {validated_rule['validation_status']}, Notes: {validated_rule['validation_notes']}")
#         elif parsed:
#             logger_instance.info(f"Original: '{rule_text}' -> Type: {parsed['type']}")


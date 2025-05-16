# adblock_processor/translator.py
from syntax_db import SyntaxDB
from utils.logger import setup_logger
from utils.exceptions import TranslationError

# logger = setup_logger('translator_module') # Assuming logger is set up in main

class RuleTranslator:
    """
    Translates rules flagged as 'needs_translation' or 'unsupported' (if a translation path exists)
    into Brave-compatible equivalents using SyntaxDB.
    """
    def __init__(self, logger, syntax_db: SyntaxDB, strategy='comment_out_untranslatable'):
        self.logger = logger
        self.syntax_db = syntax_db
        self.strategy = strategy # 'comment_out_untranslatable' or 'drop_untranslatable'

    def translate_rule(self, validated_rule):
        """
        Attempts to translate a validated rule.
        Modifies the rule object with 'translated_rule' and updates 'translation_status'.
        Translation Status:
            - 'translated'
            - 'commented_out'
            - 'dropped'
            - 'not_needed' (if status wasn't 'needs_translation' or applicable 'unsupported')
            - 'failed'
        """
        status = validated_rule.get('validation_status')
        original_rule_text = validated_rule.get('raw_rule', '')

        if status not in ['needs_translation', 'unsupported']:
            validated_rule['translation_status'] = 'not_needed'
            return validated_rule

        # Attempt translation if status is 'needs_translation'
        if status == 'needs_translation':
            pattern_info, match_obj = self.syntax_db.find_translation_candidate(original_rule_text)
            if pattern_info and match_obj:
                template = pattern_info.get('brave_equivalent_template')
                try:
                    # Use named groups if available in regex, otherwise indexed groups
                    if match_obj.groupdict():
                        translated = template.format(**match_obj.groupdict())
                    else:
                        translated = template.format(*match_obj.groups())
                    
                    validated_rule['translated_rule'] = translated
                    validated_rule['translation_status'] = 'translated'
                    validated_rule['validation_status'] = 'valid' # Mark as valid after successful translation
                    validated_rule['validation_notes'] = f"Originally '{original_rule_text}'. Translated from '{pattern_info.get('name')}'. {pattern_info.get('notes','')}"
                    self.logger.info(f"Translated rule: '{original_rule_text}' -> '{translated}' from list {validated_rule.get('list_name')}")
                    return validated_rule
                except Exception as e:
                    self.logger.error(f"Error applying translation template for rule '{original_rule_text}' using pattern '{pattern_info.get('name')}': {e}", exc_info=True)
                    validated_rule['translation_status'] = 'failed'
                    # Fall through to untranslatable strategy
            else:
                # Should not happen if validator correctly identified 'needs_translation' with a pattern
                self.logger.warning(f"Rule '{original_rule_text}' was 'needs_translation' but no matching translation pattern found by translator.")
                validated_rule['translation_status'] = 'failed'
                # Fall through to untranslatable strategy

        # Handle rules that are 'unsupported' or 'failed' translation
        # Check if an unsupported rule *still* has a direct translation path (less common)
        if status == 'unsupported' or validated_rule.get('translation_status') == 'failed':
            # This block is for cases where an 'unsupported' rule might have a direct, simple translation
            # not caught by the 'needs_translation' category, or if primary translation failed.
            # For example, a very specific AdGuard modifier that has a direct uBO counterpart.
            # This logic might overlap with 'needs_translation' and depends on how syntax_db is structured.
            # For now, we assume 'unsupported' means no straightforward translation via find_translation_candidate.
            pass # Placeholder for this secondary translation attempt if needed.


        # If still untranslated (either 'unsupported' or 'failed' translation)
        if validated_rule.get('translation_status') not in ['translated', 'not_needed']:
            notes = validated_rule.get('validation_notes', 'No specific reason.')
            if self.strategy == 'comment_out_untranslatable':
                validated_rule['translated_rule'] = f"! UNTRANSLATED ({status}): {original_rule_text} # Reason: {notes}"
                validated_rule['translation_status'] = 'commented_out'
                self.logger.debug(f"Commented out untranslatable rule: '{original_rule_text}' from {validated_rule.get('list_name')}. Reason: {notes}")
            elif self.strategy == 'drop_untranslatable':
                validated_rule['translation_status'] = 'dropped'
                self.logger.debug(f"Dropped untranslatable rule: '{original_rule_text}' from {validated_rule.get('list_name')}. Reason: {notes}")
            else: # Default to comment out
                validated_rule['translated_rule'] = f"! UNTRANSLATED ({status}): {original_rule_text} # Reason: {notes}"
                validated_rule['translation_status'] = 'commented_out'

        return validated_rule

# Example Usage:
# if __name__ == '__main__':
#     logger_instance = setup_logger('translator_test', log_level_str='DEBUG')
#     # Mock SyntaxDB - same as in validator example
#     class MockSyntaxDB:
#         def __init__(self):
#             self.translation_patterns = [
#                 {"name": "AdGuard #?# :contains", "pattern_regex": r"^(?P<domains>.*)#\?#(?P<selector>.*):contains\((?P<argument>.*)\)$", "compiled_regex": re.compile(r"^(?P<domains>.*)#\?#(?P<selector>.*):contains\((?P<argument>.*)\)$"), "supported_in_brave": "needs_translation", "brave_equivalent_template": "{domains}##{selector}:has-text({argument})", "notes": "Translate to :has-text"}
#             ]
#         def find_translation_candidate(self, text): 
#             for p in self.translation_patterns:
#                 m = p['compiled_regex'].match(text)
#                 if m: return p, m
#             return None, None
#     syntax_db_mock = MockSyntaxDB()
#     translator = RuleTranslator(logger=logger_instance, syntax_db=syntax_db_mock, strategy='comment_out_untranslatable')

#     rule1 = {'type': 'rule', 'raw_rule': 'example.com#?#div:contains(ad)', 'validation_status': 'needs_translation', 'validation_notes': 'AdGuard syntax', 'list_name': 'test_list', 'line_number': 1}
#     rule2 = {'type': 'rule', 'raw_rule': '!#if env_firefox', 'validation_status': 'unsupported', 'validation_notes': 'uBO directive', 'list_name': 'test_list', 'line_number': 2}
#     rule3 = {'type': 'rule', 'raw_rule': '||example.com^', 'validation_status': 'valid', 'list_name': 'test_list', 'line_number': 3}


#     translated1 = translator.translate_rule(rule1)
#     logger_instance.info(f"Rule1 Translated: {translated1}")
    
#     translated2 = translator.translate_rule(rule2)
#     logger_instance.info(f"Rule2 Translated: {translated2}")

#     translated3 = translator.translate_rule(rule3) # Should be 'not_needed'
#     logger_instance.info(f"Rule3 Translated: {translated3}")


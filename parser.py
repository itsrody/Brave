# adblock_processor/parser.py
import re
from .utils.logger import setup_logger
from .utils.exceptions import ParsingError

# logger = setup_logger('parser_module') # Assuming logger is set up in main

class RuleParser:
    """
    Parses raw filter list content into structured rule objects or dictionaries.
    """
    def __init__(self, logger):
        self.logger = logger
        # Regex to identify comments and metadata.
        # ABP-style metadata: ! Title: EasyList
        self.comment_regex = re.compile(r"^\s*!.*|^\s*#.*|^\s*\[Adblock.*") # Basic comments and section headers
        self.metadata_regex = re.compile(r"^\s*!\s*([A-Za-z\s]+):\s*(.+)") # e.g., ! Title: EasyList

    def parse_line(self, line_number, line_text, list_name="unknown_list"):
        """
        Parses a single line from a filter list.
        Returns a dictionary representing the rule or metadata, or None for empty/comment lines.
        """
        stripped_line = line_text.strip()

        if not stripped_line:
            return {'type': 'empty', 'original_line': line_text, 'line_number': line_number, 'list_name': list_name}

        if self.comment_regex.fullmatch(stripped_line):
            metadata_match = self.metadata_regex.match(stripped_line)
            if metadata_match:
                key = metadata_match.group(1).strip().lower().replace(" ", "_")
                value = metadata_match.group(2).strip()
                return {'type': 'metadata', 'key': key, 'value': value, 'original_line': line_text, 'line_number': line_number, 'list_name': list_name}
            return {'type': 'comment', 'original_line': line_text, 'line_number': line_number, 'list_name': list_name}

        # At this point, it's likely a rule
        # Basic rule structure: <pattern>$<options>
        # Cosmetic rule: <domains>##<selector> or <domains>#?#<selector> (AdGuard)
        # HTML filtering: <domains>##^<selector> (uBO)
        
        rule_obj = {
            'type': 'rule',
            'raw_rule': stripped_line,
            'original_line': line_text,
            'line_number': line_number,
            'list_name': list_name,
            'pattern': stripped_line, # Default pattern is the whole rule
            'options_str': None,
            'options_dict': {}, # Parsed options
            'domains': None, # For cosmetic/element hiding
            'selector': None, # For cosmetic/element hiding
            'is_exception': False,
            'is_cosmetic': False,
            'is_html_filter': False,
            'is_scriptlet': False,
        }

        # Check for exception rules (network or cosmetic)
        if stripped_line.startswith('@@'):
            rule_obj['is_exception'] = True
            rule_obj['pattern'] = stripped_line[2:] # Remove @@
        elif '##@@' in stripped_line: # uBO specific cosmetic exception
            rule_obj['is_exception'] = True
            # This specific case needs careful parsing, as ##@@ is not standard ABP
            # For simplicity, we'll mark it and let validator/translator handle complex uBO syntax
            # rule_obj['pattern'] = stripped_line # Keep full for now
        elif '#@#' in stripped_line: # Standard cosmetic exception
            rule_obj['is_exception'] = True
            parts = stripped_line.split('#@#', 1)
            rule_obj['domains'] = parts[0] if parts[0] else None
            rule_obj['selector'] = parts[1]
            rule_obj['is_cosmetic'] = True
            rule_obj['pattern'] = stripped_line # Keep full for now

        # Check for cosmetic rules (##, #?#, #$#)
        # Order matters: ##^ before ##
        if '##^' in stripped_line: # uBO HTML Filtering
            rule_obj['is_html_filter'] = True
            parts = stripped_line.split('##^', 1)
            rule_obj['domains'] = parts[0] if parts[0] else None
            rule_obj['selector'] = parts[1]
        elif '##+' in stripped_line: # uBO/Brave Scriptlet Injection ##+js()
             rule_obj['is_scriptlet'] = True
             parts = stripped_line.split('##+', 1)
             rule_obj['domains'] = parts[0] if parts[0] else None
             rule_obj['selector'] = '+' + parts[1] # selector is like +js(script, args)
        elif '##' in stripped_line:
            rule_obj['is_cosmetic'] = True
            parts = stripped_line.split('##', 1)
            rule_obj['domains'] = parts[0] if parts[0] else None
            rule_obj['selector'] = parts[1]
        elif '#?#' in stripped_line: # AdGuard extended cosmetic
            rule_obj['is_cosmetic'] = True
            parts = stripped_line.split('#?#', 1)
            rule_obj['domains'] = parts[0] if parts[0] else None
            rule_obj['selector'] = parts[1]
        elif '#$#' in stripped_line: # AdGuard CSS injection
            rule_obj['is_cosmetic'] = True # Treat as cosmetic for now
            parts = stripped_line.split('#$#', 1)
            rule_obj['domains'] = parts[0] if parts[0] else None
            rule_obj['selector'] = parts[1] # Selector here includes the CSS style block
        elif '#%#' in stripped_line: # AdGuard scriptlet
            rule_obj['is_scriptlet'] = True
            parts = stripped_line.split('#%#', 1)
            rule_obj['domains'] = parts[0] if parts[0] else None
            rule_obj['selector'] = parts[1] # Selector is the scriptlet call

        # Network rule options
        if not rule_obj['is_cosmetic'] and not rule_obj['is_html_filter'] and not rule_obj['is_scriptlet'] and '$' in rule_obj['pattern']:
            pattern_parts = rule_obj['pattern'].split('$', 1)
            rule_obj['pattern'] = pattern_parts[0]
            rule_obj['options_str'] = pattern_parts[1]
            try:
                # Naive options parsing, can be improved
                # Handles options like: script,domain=example.com|~example.org,third-party
                # Does not handle options with values containing commas robustly without more complex parsing
                raw_options = rule_obj['options_str'].split(',')
                for opt in raw_options:
                    if '=' in opt:
                        key_val = opt.split('=', 1)
                        rule_obj['options_dict'][key_val[0].strip().lower()] = key_val[1].strip()
                    else:
                        rule_obj['options_dict'][opt.strip().lower()] = True # Flag options
            except Exception as e:
                self.logger.warning(f"Could not parse options string '{rule_obj['options_str']}' for rule '{stripped_line}' in {list_name}:{line_number}: {e}")
                # Keep raw options string for validator/translator to attempt
        
        # Update pattern if it was changed by exception handling
        if rule_obj['is_exception'] and not rule_obj['is_cosmetic']:
             rule_obj['pattern'] = stripped_line[2:] # Remove @@ from pattern for non-cosmetic exceptions

        return rule_obj

    def parse_raw_list_content(self, raw_content, list_name="unknown_list"):
        """
        Parses the entire raw content of a filter list.
        Yields parsed rule objects.
        """
        if not raw_content:
            self.logger.warning(f"Empty content for list: {list_name}")
            return

        lines = raw_content.splitlines()
        self.logger.info(f"Parsing {len(lines)} lines from list: {list_name}")
        
        for i, line in enumerate(lines):
            try:
                parsed_obj = self.parse_line(i + 1, line, list_name)
                if parsed_obj: # and parsed_obj['type'] != 'empty': # Decide if you want to yield empty lines
                    yield parsed_obj
            except Exception as e:
                self.logger.error(f"Failed to parse line {i+1} in {list_name}: '{line}'. Error: {e}", exc_info=True)
                yield {'type': 'error', 'original_line': line, 'line_number': i+1, 'list_name': list_name, 'error': str(e)}

# Example Usage:
# if __name__ == '__main__':
#     logger_instance = setup_logger('parser_test', log_level_str='DEBUG')
#     parser = RuleParser(logger=logger_instance)
#     test_lines = [
#         "! Title: Test List",
#         "||example.com^$script,third-party",
#         "@@||baddomain.com^",
#         "example.org##.ad-banner",
#         "example.net#@#.safe-banner",
#         "google.com##^.annoying-element", # uBO HTML filter
#         "adguard.com#?#div:contains(promo)", # AdGuard extended cosmetic
#         "example.com##+js(alert, hello)", # Brave/uBO scriptlet
#         "",
#         "# A comment",
#         "[Adblock Plus 2.0]"
#     ]
#     for i, line_text in enumerate(test_lines):
#         parsed = parser.parse_line(i+1, line_text, "test_list.txt")
#         logger_instance.debug(parsed)

#     raw_list_data = "\n".join(test_lines)
#     for p_obj in parser.parse_raw_list_content(raw_list_data, "MyTestList"):
#         logger_instance.info(p_obj)


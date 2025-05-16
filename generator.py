# adblock_processor/generator.py
import datetime
import os
from .utils.logger import setup_logger
from .utils.exceptions import GenerationError

# logger = setup_logger('generator_module') # Assuming logger is set up in main

class ListGenerator:
    """
    Generates the final, optimized filter list.
    """
    def __init__(self, logger, output_file):
        self.logger = logger
        self.output_file = output_file
        self.processed_rules = set() # To store unique rules and avoid duplicates
        self.header_comments = []
        self.footer_comments = []
        self.rule_count = 0
        self.metadata_comments = {} # Store list-specific metadata like titles

    def add_rule(self, rule_object):
        """
        Adds a processed rule to be included in the final list.
        Expects rule_object to have 'validation_status', 'translation_status',
        'raw_rule', 'translated_rule' (if applicable), 'type'.
        """
        rule_type = rule_object.get('type')
        
        # Handle metadata from original lists (e.g., ! Title: ...)
        if rule_type == 'metadata':
            key = rule_object.get('key')
            value = rule_object.get('value')
            list_name = rule_object.get('list_name', 'unknown')
            if key and value:
                # Store metadata, perhaps prefixing with list name to avoid clashes
                # Or, decide on a unified header later. For now, just log.
                self.logger.debug(f"Captured metadata from {list_name}: {key} = {value}")
                if key not in self.metadata_comments:
                    self.metadata_comments[key] = []
                self.metadata_comments[key].append(f"{value} (from {list_name})")
            return

        # Handle comments from original lists
        if rule_type == 'comment' and '! Homepage:' in rule_object.get('original_line',''): # Keep homepage comments
            self.add_comment_to_header(rule_object.get('original_line',''))
            return


        final_rule_text = None
        validation_status = rule_object.get('validation_status')
        translation_status = rule_object.get('translation_status')

        if validation_status == 'valid' and translation_status == 'not_needed':
            final_rule_text = rule_object.get('raw_rule')
        elif translation_status == 'translated':
            final_rule_text = rule_object.get('translated_rule')
        elif translation_status == 'commented_out':
            final_rule_text = rule_object.get('translated_rule') # This is the commented out version

        # Do not add if 'dropped', 'empty', 'error', or 'unsupported' without translation
        if final_rule_text and final_rule_text not in self.processed_rules:
            self.processed_rules.add(final_rule_text)
            self.rule_count +=1
        elif final_rule_text and final_rule_text in self.processed_rules:
            self.logger.debug(f"Duplicate rule skipped: {final_rule_text[:100]}")


    def add_comment_to_header(self, comment_line):
        """Adds a comment line to the list header."""
        if comment_line not in self.header_comments: # Avoid duplicate header comments
            self.header_comments.append(comment_line)

    def generate_list(self, list_title="Unified Brave Adblock List", version="1.0"):
        """
        Generates the final adblock list file with headers, sorted rules, and footers.
        """
        self.logger.info(f"Starting generation of the final list: {self.output_file}")
        
        output_dir = os.path.dirname(self.output_file)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
                self.logger.info(f"Created output directory: {output_dir}")
            except OSError as e:
                raise GenerationError(f"Could not create output directory {output_dir}: {e}")

        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                # Write Header
                f.write(f"! Title: {list_title}\n")
                f.write(f"! Version: {version}\n")
                f.write(f"! Last Updated: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}\n")
                f.write(f"! Expires: 7 days (update frequency recommended)\n") # Example
                f.write(f"! Homepage: [Your Project Homepage URL]\n")
                f.write(f"! Rule Count: {self.rule_count} unique rules\n")
                f.write("!\n")
                
                # Add any collected important metadata or custom header comments
                if self.metadata_comments.get('title'):
                    f.write("! Original List Titles:\n")
                    for title_info in self.metadata_comments['title']:
                        f.write(f"!  - {title_info}\n")
                    f.write("!\n")

                for comment in self.header_comments:
                    f.write(f"{comment}\n")
                f.write("!\n! --- BEGIN RULES --- \n!\n")

                # Write Rules (sorted for consistency, though adblock engines might re-order)
                # Separate comments/metadata from actual rules for sorting
                actual_rules_to_write = sorted([r for r in list(self.processed_rules) if not r.startswith('!')])
                commented_out_rules = sorted([r for r in list(self.processed_rules) if r.startswith('!')])
                
                for rule in actual_rules_to_write:
                    f.write(f"{rule}\n")
                
                if commented_out_rules:
                    f.write("\n!\n! --- UNTRANSLATED/COMMENTED RULES --- \n!\n")
                    for rule in commented_out_rules:
                        f.write(f"{rule}\n")

                # Write Footer
                f.write("\n!\n! --- END RULES --- \n")
                for comment in self.footer_comments:
                    f.write(f"{comment}\n")
                
            self.logger.info(f"Successfully generated adblock list with {self.rule_count} unique rules to {self.output_file}")

        except IOError as e:
            self.logger.error(f"Error writing to output file {self.output_file}: {e}", exc_info=True)
            raise GenerationError(f"Could not write to output file: {e}")
        except Exception as e:
            self.logger.error(f"An unexpected error occurred during list generation: {e}", exc_info=True)
            raise GenerationError(f"Unexpected error during generation: {e}")

# Example Usage:
# if __name__ == '__main__':
#     logger_instance = setup_logger('generator_test', log_level_str='DEBUG')
#     output_path = "output/test_generated_list.txt"
#     generator = ListGenerator(logger=logger_instance, output_file=output_path)

#     generator.add_comment_to_header("! This is a test list generated by AdblockProcessor.")
#     generator.add_rule({'type': 'rule', 'raw_rule': '||example.com^', 'validation_status': 'valid', 'translation_status': 'not_needed'})
#     generator.add_rule({'type': 'rule', 'raw_rule': '||another.com^$script', 'validation_status': 'valid', 'translation_status': 'not_needed'})
#     generator.add_rule({'type': 'rule', 'raw_rule': '||example.com^', 'validation_status': 'valid', 'translation_status': 'not_needed'}) # Duplicate
#     generator.add_rule({'type': 'rule', 'translated_rule': '! UNTRANSLATED: some_adguard_rule', 'validation_status': 'unsupported', 'translation_status': 'commented_out'})
#     generator.add_rule({'type': 'metadata', 'key': 'title', 'value': 'EasyList Subset', 'list_name': 'EasyList'})


#     generator.generate_list(list_title="Test Unified List", version="0.1-alpha")
#     logger_instance.info(f"Test list generated at {output_path}")


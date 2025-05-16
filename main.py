# adblock_processor/main.py
import asyncio
import time
import os
import concurrent.futures
from functools import partial

from .config import AppConfig
from .utils.logger import setup_logger
from .utils.exceptions import AdblockProcessorError
from .downloader import Downloader
from .parser import RuleParser
from .syntax_db import SyntaxDB
from .validator import RuleValidator
from .translator import RuleTranslator
from .generator import ListGenerator

# Global logger instance, configured after AppConfig is loaded
logger = None

def process_single_rule_task(rule_obj, validator_instance, translator_instance):
    """
    Worker function to validate and translate a single rule object.
    Designed to be run in a ProcessPoolExecutor.
    """
    # Note: logger instance here will be the default root logger if not careful with ProcessPool.
    # For simplicity, critical errors should be propagated via exceptions or return values.
    # Or, pass logger configuration details and re-initialize per process if needed.
    try:
        validated_rule = validator_instance.validate_rule(rule_obj)
        if validated_rule.get('validation_status') in ['needs_translation', 'unsupported']:
            # Only translate if validation suggests it or if it's unsupported (translator might have a path)
            translated_rule = translator_instance.translate_rule(validated_rule)
            return translated_rule
        return validated_rule
    except Exception as e:
        # Log this error appropriately if possible, or ensure it's caught by the main process
        # For now, return an error state within the rule object
        rule_obj['processing_error'] = str(e)
        rule_obj['validation_status'] = 'error'
        rule_obj['translation_status'] = 'error'
        # print(f"Error processing rule {rule_obj.get('raw_rule')}: {e}") # For debugging in process
        return rule_obj


async def main_async_workflow():
    global logger
    start_time = time.time()

    try:
        # 1. Configuration
        config = AppConfig(config_file_path='config.ini')
        logger = setup_logger(
            log_level_str=config.get('settings', 'log_level', 'INFO'),
            log_file=config.get('settings', 'log_file', None)
        )
        logger.info("Adblock List Processor started.")
        logger.info(f"Using configuration from: {os.path.abspath(config.config_file_path)}")

        # 2. Initialize Core Components
        syntax_db_patterns_dir = os.path.join(os.path.dirname(__file__), '..', 'syntax_patterns') # Adjust if needed
        syntax_db = SyntaxDB(patterns_dir=syntax_db_patterns_dir)
        logger.info(f"SyntaxDB initialized from {os.path.abspath(syntax_db_patterns_dir)}.")
        
        downloader = Downloader(
            logger=logger,
            max_parallel_downloads=config.getint('settings', 'max_parallel_downloads', 5)
        )
        parser = RuleParser(logger=logger)
        validator = RuleValidator(logger=logger, syntax_db=syntax_db) # Logger for validator is mainly for its own debug
        translator = RuleTranslator(
            logger=logger, # Logger for translator
            syntax_db=syntax_db,
            strategy=config.get('settings', 'translation_strategy', 'comment_out_untranslatable')
        )
        output_list_path = config.get('settings', 'output_file', 'output/unified_brave_list.txt')
        generator = ListGenerator(logger=logger, output_file=output_list_path)

        # 3. Download Lists
        filter_lists_to_download = config.get_filter_lists()
        if not filter_lists_to_download:
            logger.warning("No filter lists configured in config.ini. Exiting.")
            return
            
        logger.info(f"Starting download of {len(filter_lists_to_download)} filter lists...")
        downloaded_contents = await downloader.download_lists(filter_lists_to_download)
        
        successful_downloads = [item for item in downloaded_contents if item[1] is not None]
        if not successful_downloads:
            logger.error("No lists were successfully downloaded. Exiting.")
            return
        logger.info(f"Successfully downloaded {len(successful_downloads)} lists.")

        # 4. Parse, Validate, and Translate Rules (in parallel for rules)
        all_parsed_rules = []
        for list_name, content, source_url in successful_downloads:
            if content:
                logger.info(f"Parsing content from '{list_name}'...")
                for parsed_obj in parser.parse_raw_list_content(content, list_name):
                    all_parsed_rules.append(parsed_obj)
            else:
                logger.warning(f"Skipping parsing for '{list_name}' due to download failure from {source_url}.")
        
        logger.info(f"Total parsed objects (rules, comments, metadata): {len(all_parsed_rules)}")
        
        actual_rules_to_process = [r for r in all_parsed_rules if r.get('type') == 'rule']
        non_rules = [r for r in all_parsed_rules if r.get('type') != 'rule']

        logger.info(f"Processing {len(actual_rules_to_process)} actual filter rules...")

        processed_rules_collector = []
        max_workers = config.getint('settings', 'max_processing_workers', os.cpu_count() or 1)
        
        # For CPU-bound tasks like regex in validation/translation, ProcessPoolExecutor is better.
        # However, passing complex objects like logger or custom class instances to ProcessPool
        # can be tricky due to pickling. For simplicity in this example, if tasks are not
        # extremely CPU intensive or if state sharing is complex, ThreadPoolExecutor might be used,
        # keeping in mind the GIL for pure Python CPU tasks.
        # Given the potential for heavy regex, let's aim for ProcessPool if possible,
        # or simplify what's passed to the worker.
        
        # We'll use ProcessPoolExecutor. The worker function `process_single_rule_task`
        # will get instances of Validator and Translator. These instances should be picklable.
        # The logger inside the worker might not be the same instance, so logging from workers
        # needs care.
        
        # Create instances for the worker processes. These will be pickled.
        # Ensure SyntaxDB is efficient to pickle or re-initialize in worker.
        # For now, assume SyntaxDB is picklable if its loaded patterns are basic Python types.
        worker_validator = RuleValidator(logger=None, syntax_db=syntax_db) # Logger won't be effective across processes easily
        worker_translator = RuleTranslator(logger=None, syntax_db=syntax_db, strategy=config.get('settings', 'translation_strategy'))

        if actual_rules_to_process:
            with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
                # Use functools.partial to pass fixed arguments (validator, translator instances)
                task_fn = partial(process_single_rule_task, validator_instance=worker_validator, translator_instance=worker_translator)
                
                # map is simpler if order doesn't matter for processing, but submit gives futures for better progress tracking
                future_to_rule = {executor.submit(task_fn, rule_obj): rule_obj for rule_obj in actual_rules_to_process}
                
                processed_count = 0
                for future in concurrent.futures.as_completed(future_to_rule):
                    original_rule_obj = future_to_rule[future]
                    try:
                        processed_rule = future.result()
                        processed_rules_collector.append(processed_rule)
                    except Exception as exc:
                        logger.error(f"Rule '{original_rule_obj.get('raw_rule', 'N/A')}' generated an exception during processing: {exc}", exc_info=False) # exc_info=False in loop
                        original_rule_obj['processing_error'] = str(exc)
                        original_rule_obj['validation_status'] = 'error'
                        processed_rules_collector.append(original_rule_obj) # Add with error
                    
                    processed_count += 1
                    if processed_count % 1000 == 0: # Log progress
                        logger.info(f"Processed {processed_count}/{len(actual_rules_to_process)} rules...")
            logger.info(f"Finished parallel processing of {len(actual_rules_to_process)} rules.")
        else:
            logger.info("No actual rules found to process.")

        # Add back non-rules (comments, metadata) to the collector for the generator
        processed_rules_collector.extend(non_rules)

        # 5. Generate Final List
        logger.info("Generating final unified adblock list...")
        for final_obj in processed_rules_collector:
            if final_obj.get('processing_error'): # Log errors from parallel processing
                 logger.warning(f"Rule from {final_obj.get('list_name')}:{final_obj.get('line_number')} ('{final_obj.get('original_line','').strip()}') had processing error: {final_obj.get('processing_error')}")
            generator.add_rule(final_obj)
        
        generator.generate_list(
            list_title=config.get('output_settings', 'list_title', "Unified Brave Adblock List"),
            version=config.get('output_settings', 'list_version', "1.0.0")
        )

    except ConfigError as e:
        print(f"CRITICAL CONFIGURATION ERROR: {e}. Please check your config.ini. Exiting.")
        if logger: logger.critical(f"Configuration error: {e}", exc_info=True)
    except AdblockProcessorError as e:
        if logger: logger.error(f"An application error occurred: {e}", exc_info=True)
        else: print(f"ERROR: {e}")
    except Exception as e:
        if logger: logger.critical(f"An unexpected critical error occurred: {e}", exc_info=True)
        else: print(f"UNEXPECTED CRITICAL ERROR: {e}")
    finally:
        end_time = time.time()
        duration = end_time - start_time
        if logger:
            logger.info(f"Adblock List Processor finished in {duration:.2f} seconds.")
        else:
            print(f"Adblock List Processor finished in {duration:.2f} seconds.")

def run():
    # This is the entry point if you make this package installable
    # For direct script execution, the if __name__ == '__main__' block is used.
    asyncio.run(main_async_workflow())

if __name__ == '__main__':
    # This allows running the script directly, e.g., python -m adblock_processor.main
    # Ensure your PYTHONPATH is set up correctly if running from outside the package root.
    # Or, if adblock_processor is in the current directory: python main.py (adjust imports)
    
    # To run from the project root (e.g., where adblock_list_processor/ directory is):
    # Ensure adblock_list_processor is in PYTHONPATH or run as a module:
    # python -m adblock_processor.main
    
    # If running this file directly from within the adblock_processor directory,
    # relative imports like ".config" will work.
    asyncio.run(main_async_workflow())


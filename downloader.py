# adblock_processor/downloader.py
import asyncio
import aiohttp
import time
from .utils.logger import setup_logger
from .utils.exceptions import DownloadError

# Assuming logger is set up in main or passed around
# For standalone testing:
# logger = setup_logger('downloader_module')

class Downloader:
    """
    Downloads filter lists from multiple sources concurrently.
    """
    def __init__(self, logger, max_parallel_downloads=5, timeout_seconds=30, max_retries=2):
        self.logger = logger
        self.max_parallel_downloads = max_parallel_downloads
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.max_retries = max_retries

    async def _fetch_url(self, session, url_name, url, attempt=1):
        """Fetches a single URL with retry logic."""
        self.logger.info(f"Attempting to download '{url_name}' from {url} (Attempt {attempt}/{self.max_retries + 1})")
        try:
            async with session.get(url, timeout=self.timeout) as response:
                response.raise_for_status()  # Raises HTTPError for bad responses (4XX, 5XX)
                content = await response.text(encoding='utf-8', errors='replace')
                self.logger.info(f"Successfully downloaded '{url_name}' ({len(content)} bytes)")
                return url_name, content, url
        except aiohttp.ClientResponseError as e:
            self.logger.error(f"HTTP error downloading '{url_name}': {e.status} {e.message} from {url}")
            if e.status in [403, 404]: # Don't retry on 403, 404
                 return url_name, None, url # Indicate failure for this specific URL
        except aiohttp.ClientError as e: # Includes timeouts, connection errors
            self.logger.error(f"Client error downloading '{url_name}': {e} from {url}")
        except asyncio.TimeoutError:
            self.logger.error(f"Timeout error downloading '{url_name}' from {url}")
        except Exception as e:
            self.logger.error(f"Unexpected error downloading '{url_name}': {e} from {url}", exc_info=True)

        if attempt <= self.max_retries:
            self.logger.info(f"Retrying download for '{url_name}' in {2**attempt} seconds...")
            await asyncio.sleep(2**attempt) # Exponential backoff
            return await self._fetch_url(session, url_name, url, attempt + 1)
        
        self.logger.error(f"Failed to download '{url_name}' after {self.max_retries + 1} attempts.")
        return url_name, None, url # Indicate failure

    async def download_lists(self, filter_lists_map):
        """
        Downloads all filter lists specified in the filter_lists_map.
        filter_lists_map: A dictionary {'list_name': 'url', ...}
        Returns a list of tuples: (list_name, content, source_url) or (list_name, None, source_url) on failure.
        """
        if not filter_lists_map:
            self.logger.warning("No filter lists provided for download.")
            return []

        results = []
        # Using a semaphore to limit concurrent downloads
        semaphore = asyncio.Semaphore(self.max_parallel_downloads)

        async with aiohttp.ClientSession() as session:
            tasks = []
            for list_name, url in filter_lists_map.items():
                # Acquire semaphore before creating task
                await semaphore.acquire()
                task = asyncio.ensure_future(self._fetch_url_with_semaphore(session, list_name, url, semaphore))
                tasks.append(task)
            
            # Wait for all tasks to complete
            # Using asyncio.as_completed to process results as they come in (optional)
            for future in asyncio.as_completed(tasks):
                try:
                    result = await future
                    if result: # result is (list_name, content, url)
                        results.append(result)
                except Exception as e:
                    # This should ideally be caught within _fetch_url or _fetch_url_with_semaphore
                    self.logger.error(f"Unhandled exception during task execution: {e}", exc_info=True)
        
        self.logger.info(f"Download process completed. {len(results)} lists attempted.")
        return results

    async def _fetch_url_with_semaphore(self, session, list_name, url, semaphore):
        """Wrapper for _fetch_url to release semaphore in a finally block."""
        try:
            return await self._fetch_url(session, list_name, url)
        finally:
            semaphore.release()


# Example Usage (typically in main.py):
# async def main_async_downloader_example():
#     logger_instance = setup_logger('downloader_example', log_level_str='DEBUG')
#     downloader = Downloader(logger=logger_instance, max_parallel_downloads=3)
#     lists_to_download = {
#         "easylist": "https://easylist.to/easylist/easylist.txt",
#         "fanboy_annoyances": "https://easylist.to/easylist/fanboy-annoyance.txt",
#         "non_existent": "http://localhost/non_existent_list.txt" # Example of a failing URL
#     }
#     start_time = time.time()
#     downloaded_content = await downloader.download_lists(lists_to_download)
#     end_time = time.time()
    
#     for name, content, url in downloaded_content:
#         if content:
#             logger_instance.info(f"Content for '{name}' (first 100 chars): {content[:100].replace(os.linesep, ' ')}")
#         else:
#             logger_instance.warning(f"Failed to retrieve content for '{name}' from {url}.")
#     logger_instance.info(f"Total download time: {end_time - start_time:.2f} seconds")

# if __name__ == '__main__':
#     asyncio.run(main_async_downloader_example())

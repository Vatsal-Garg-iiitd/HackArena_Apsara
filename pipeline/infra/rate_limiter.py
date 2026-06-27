import asyncio
import os
import time
import random
from typing import Callable, Any

class RateLimiter:
    def __init__(self, max_concurrent: int = 2):
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def execute_with_backoff(self, func: Callable, *args, max_retries: int = 4, **kwargs) -> Any:
        retries = 0
        while retries < max_retries:
            async with self.semaphore:
                try:
                    # We await if the function is a coroutine, otherwise just call it
                    if asyncio.iscoroutinefunction(func):
                        return await func(*args, **kwargs)
                    else:
                        # For synchronous functions, we might block the event loop, 
                        # but keeping it simple for the prototype
                        return func(*args, **kwargs)
                except Exception as e:
                    # Generic catch for HTTP 429, 503, quota, or unavailable errors
                    error_msg = str(e).lower()
                    if any(kw in error_msg for kw in ["429", "503", "quota", "rate limit", "unavailable"]):
                        retries += 1
                        if retries >= max_retries:
                            raise e
                        
                        # Exponential backoff with jitter
                        sleep_time = (2 ** retries) + random.uniform(0, 1)
                        print(f"Transient error ({error_msg[:100]}). Retrying in {sleep_time:.2f} seconds... (Attempt {retries}/{max_retries})")
                        await asyncio.sleep(sleep_time)
                    else:
                        raise e
        return None

# Global limiter instance. Keep the old default, but allow production runs to tune
# this without changing code.
limiter = RateLimiter(max_concurrent=int(os.getenv("GEMINI_MAX_CONCURRENT", "2")))

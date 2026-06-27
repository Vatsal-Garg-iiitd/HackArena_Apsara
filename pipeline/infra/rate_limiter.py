import asyncio
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
                    # Generic catch for HTTP 429 or quota errors
                    error_msg = str(e).lower()
                    if "429" in error_msg or "quota" in error_msg or "rate limit" in error_msg:
                        retries += 1
                        if retries >= max_retries:
                            raise e
                        
                        # Exponential backoff with jitter
                        sleep_time = (2 ** retries) + random.uniform(0, 1)
                        print(f"Rate limited. Retrying in {sleep_time:.2f} seconds... (Attempt {retries}/{max_retries})")
                        await asyncio.sleep(sleep_time)
                    else:
                        raise e
        return None

# Global limiter instance
limiter = RateLimiter(max_concurrent=2)

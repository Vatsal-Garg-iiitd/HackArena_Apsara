import os
from google import genai
from google.genai import types
from dotenv import load_dotenv
from typing import Any
from pipeline.infra.rate_limiter import limiter

load_dotenv()

class GeminiClient:
    def __init__(self):
        # Explicit check for API key
        if not os.getenv("GEMINI_API_KEY"):
            print("WARNING: GEMINI_API_KEY not found in environment. API calls will fail.")
        self.client = genai.Client()
        
    async def _do_generate(self, model_name: str, config: Any, prompt: str) -> Any:
        return await self.client.aio.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config
        )
        
    async def generate_json(self, model_name: str, system_instruction: str, prompt: str, schema: type = None) -> Any:
        """
        Asynchronous call to Gemini enforcing JSON output, wrapped in a rate limiter.
        If a Pydantic schema is provided, returns the parsed object.
        """
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            system_instruction=system_instruction
        )
        
        if schema:
            config.response_schema = schema
            
        # Use the rate limiter to execute the async call
        response = await limiter.execute_with_backoff(
            self._do_generate,
            model_name=model_name,
            config=config,
            prompt=prompt
        )
        
        if not response:
            return None
            
        if schema and response.text:
            import json
            try:
                data = json.loads(response.text)
                return schema.model_validate(data)
            except Exception as e:
                print(f"Error validating schema: {e}\nRaw JSON: {response.text}")
                return None
            
        return response.text

# Global instance
gemini_client = GeminiClient()

import sys
import os
import logging
import json
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any
import traceback
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for more verbose logging
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the path to the mcp module dynamically
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'mcp')))

from mcp.server.fastmcp import FastMCP

# Create an MCP server
mcp = FastMCP("Demo")

# Configure retry strategy
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)

def get_session():
    """Create a requests session with retry strategy"""
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def query_ollama_sync(content: str, retries=3) -> str:
    """Query the local Ollama instance with the content synchronously"""
    last_error = None
    for attempt in range(retries):
        try:
            response = requests.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": "deepseek-r1",
                    "messages": [{ "role": "user", "content": content }],
                    "stream": False  # Added stream parameter
                },
                timeout=120  # Increased timeout
            )
            response.raise_for_status()
            result = response.json()
            logger.debug(f"Ollama response: {result}")
            
            if "error" in result:
                raise Exception(f"Ollama error: {result['error']}")
            
            # Extract the response from the message if available
            if isinstance(result, dict) and "message" in result:
                return result["message"].get("content", str(result))
            
            return result.get("response", str(result))
            
        except Exception as e:
            last_error = e
            logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt < retries - 1:
                continue
            logger.error(f"All attempts failed in query_ollama_sync: {str(e)}")
            logger.error(traceback.format_exc())
            raise last_error

@mcp.tool("process_url_with_llm")
def process_url_with_llm(url: str, query: str = None) -> Dict[str, Any]:
    """Process URL content with Ollama"""
    try:
        session = get_session()
        response = session.get(url, verify=False, timeout=60)  # Increased timeout
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        content = ' '.join([p.get_text(strip=True) for p in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'span'])])
        
        if not content:
            return {
                "status": "error",
                "url": url,
                "error": "No content extracted from URL"
            }
        
        prompt = f"Analyze this content about JWT bearer tokens and OAuth2:\n\n{content}\n\nFocus on: {query}" if query else f"Analyze this content:\n\n{content}"
        
        result = query_ollama_sync(prompt)
        
        return {
            "status": "success",
            "url": url,
            "analysis": result
        }
        
    except Exception as e:
        logger.error(f"Error processing URL: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "url": url,
            "error": str(e)
        }

if __name__ == "__main__":
    mcp.run()
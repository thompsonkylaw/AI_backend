from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import os
import requests
import logging
from dotenv import load_dotenv
from openai import OpenAI
import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel
from typing import List, Dict

load_dotenv()

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
class ChatRequest(BaseModel):
    messages: List[Dict]
    model: str
    
    
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
PERPLEXITY_API_KEY = "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"
if not PERPLEXITY_API_KEY:
    raise ValueError("Missing PERPLEXITY_API_KEY environment variable")

DEEPSEEK_API_KEY = "sk-a96c8196a00241ee9f587cf1d1f1b99d"  # Consider moving to environment variable
if not DEEPSEEK_API_KEY:
    raise ValueError("Missing DEEPSEEK_API_KEY environment variable")

GOOGLE_API_KEY = "AIzaSyCihsIc9SAbQApcGcZlhwcsobzNNoDtz-s"
GOOGLE_CX = "9280abb2866c5441d"


@app.post("/api/ppxty")
# async def chat_endpoint(request: Request, messages: list[dict]):
async def chat_endpoint(chat_request: ChatRequest):    
    try:
        messages = chat_request.messages
        model = chat_request.model
        logger.info(f"Received request with messages: {messages}")
        
        url = "https://api.perplexity.ai/chat/completions"
        
        payload = {
            # "model": "r1-1776",
            "model": model,
            "messages": messages,
            "max_tokens": 2000,
        }
        
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"API Response: {result}")
            
            original_content = result['choices'][0]['message']['content']
            modified_content = original_content.replace("<think>", "<AIM AI助手>").replace("</think>", "</AIM AI助手>")
            
            return {"message": modified_content}
            
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP Error: {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# DeepSeek endpoint with asynchronous OpenAI client
@app.post("/api/ds")
# async def deepseek_endpoint(request: Request, messages: list[dict]):
async def deepseek_endpoint(chat_request: ChatRequest):
    try:
        messages = chat_request.messages
        model = chat_request.model
        logger.info(f"Received DeepSeek request with messages: {messages}")
        
        client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        
        response = await client.chat.completions.create(
            # model="deepseek-reasoner",
            model=model,
            messages=messages,
            stream=False
        )
        
        result = response.choices[0].message.content
        logger.info(f"DeepSeek API Response: {result}")
        
        return {"message": result}
        
    except Exception as e:
        logger.error(f"Unexpected error in DeepSeek endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))    
    

@app.post("/api/dswithsearch")
# async def deepseek_endpoint(request: Request, messages: list[dict]):
async def deepseek_endpoint(chat_request: ChatRequest):
    try:
        # 验证环境变量
        messages = chat_request.messages
        model = chat_request.model
        if not all([DEEPSEEK_API_KEY, GOOGLE_API_KEY, GOOGLE_CX]):
            raise RuntimeError("Missing API credentials in environment variables")
        logger.info(f"Received DeepSeek request with messages: {messages}")
        # 提取搜索查询
        search_query = next(
            (msg["content"] for msg in reversed(messages) 
            if msg["role"] == "user"
        ), None)
        search_results = []
        if search_query:
            try:
                async with httpx.AsyncClient() as client:
                    # 先验证API连通性
                    # test_params = {
                    #     "key": GOOGLE_API_KEY,
                    #     "cx": GOOGLE_CX,
                    #     "q": "API connectivity test",
                    #     "num": 1
                    # }
                    # test_response = await client.get(
                    #     "https://www.googleapis.com/customsearch/v1",
                    #     params=test_params
                    # )
                    # test_response.raise_for_status()
                    # 执行实际搜索
                    search_params = {
                        "key": GOOGLE_API_KEY,
                        "cx": GOOGLE_CX,
                        "q": search_query,
                        "num": 10,
                        "hl": "zh-CN"  # 添加中文语言优化
                    }
                    response = await client.get(
                        "https://www.googleapis.com/customsearch/v1",
                        params=search_params
                    )
                    response.raise_for_status()
                    
                    data = response.json()
                    search_results = data.get("items", [])
                    logger.info(f"Google search returned {len(search_results)} results")
            except httpx.HTTPStatusError as e:
                logger.error(f"Google API error: {e.response.text}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Search service error: {e.response.text}"
                )
            except Exception as e:
                logger.warning(f"Google search failed: {str(e)}")
                search_results = []
        # Build search context if results found
        if search_results:
            search_context = "Latest web search results:\n"
            for idx, item in enumerate(search_results[:3], 1):  # Use top 3 results
                search_context += (
                    f"{idx}. [{item.get('title', 'No title')}]({item.get('link', '')})\n"
                    f"{item.get('snippet', 'No description available')}\n\n"
                )
            
            # Insert search context before the last user message
            for idx in reversed(range(len(messages))):
                if messages[idx]["role"] == "user":
                    messages.insert(idx, {"role": "system", "content": search_context})
                    break
        # Call DeepSeek API
        print("messages",messages)
        client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        
        response = await client.chat.completions.create(
            # model="deepseek-reasoner",
            model=model,
            messages=messages,
            stream=False
        )
        result = response.choices[0].message.content
        logger.info(f"DeepSeek API response generated")
        
        return {"message": result}
    except Exception as e:
        logger.error(f"Endpoint error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))  

    
    
# @app.post("/api/ppxty")
# async def chat_endpoint(request: Request, messages: list[dict]):
    
#     try:
#         logger.info(f"Received request with messages: {messages}")
        
#         url = "https://api.perplexity.ai/chat/completions"
        
#         # Add system message with instructions
#         # system_message = {
#         #     "role": "system",
#         #     "content": "用超級詳盡的方式比較, 例如要有基礎保單架構,核心保障差異,所有比較都是用表格形式顯示"
#         # }
        
#         # Create modified messages array with system message first
#         # modified_messages = [system_message] + messages
        
#         payload = {
#             # "model": "sonar-deep-research",
#             "model": "r1-1776",
#             "messages": messages,  # Use modified messages
#             "max_tokens": 2000,
#         }
        
#         headers = {
#             "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
#             "Content-Type": "application/json"
#         }
        
#         response = requests.post(url, json=payload, headers=headers)
#         response.raise_for_status()
        
#         result = response.json()
#         logger.info(f"API Response: {result}")
        
#         # Replace the tags in the response
#         original_content = result['choices'][0]['message']['content']
#         modified_content = original_content.replace("<think>", "<AIM AI助手>").replace("</think>", "</AIM AI助手>")
        
#         return {"message": modified_content}
        
#     except requests.exceptions.HTTPError as e:
#         logger.error(f"HTTP Error: {e.response.text}")
#         raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
#     except Exception as e:
#         logger.error(f"Unexpected error: {str(e)}")
#         raise HTTPException(status_code=500, detail=str(e))   
    
# @app.post("/api/ds")
# async def deepseek_endpoint(request: Request, messages: list[dict]):
    
#     try:
#         logger.info(f"Received DeepSeek request with messages: {messages}")
        
#         client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        
#         # Add system message if not already present
#         # if messages and messages[0]["role"] != "system":
#         #     system_message = {"role": "system", "content": "用超級詳盡的方式比較, 例如要有基礎保單架構,核心保障差異,所有比較都是用表格形式顯示"}
#         #     modified_messages = [system_message] + messages
#         # else:
#         #     modified_messages = messages
        
#         response = client.chat.completions.create(
#             model="deepseek-reasoner",
#             # model="deepseek-chat",
#             messages=messages,
#             stream=False
#         )
        
#         result = response.choices[0].message.content
#         logger.info(f"DeepSeek API Response: {result}")
        
#         return {"message": result}
        
#     except Exception as e:
#         logger.error(f"Unexpected error in DeepSeek endpoint: {str(e)}")
#         raise HTTPException(status_code=500, detail=str(e))
         
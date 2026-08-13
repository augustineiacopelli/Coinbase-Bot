import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from coinbase.rest import RESTClient
from openai import OpenAI

load_dotenv()  # load .env if present

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CB_API_KEY = os.getenv("COINBASE_API_KEY")
CB_API_SECRET = os.getenv("COINBASE_API_SECRET")

app = FastAPI(title="Coinbase Always-On Bot", version="0.1.0")

# Coinbase REST client (public endpoints do not require auth; we accept keys for future expansion)
def coinbase_client():
    if CB_API_KEY and CB_API_SECRET:
        return RESTClient(api_key=CB_API_KEY, api_secret=CB_API_SECRET)
    return RESTClient()  # unauthenticated for public market endpoints

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/price/{product_id}")
def get_price(product_id: str = "BTC-USD"):
    try:
        client = coinbase_client()
        data = client.get(f"/api/v3/brokerage/market/products/{product_id}")
        # Basic shape: includes 'price', 'product_id', etc.
        if "price" not in data:
            raise HTTPException(404, detail=f"No price for {product_id}")
        return {"product_id": product_id, "price": data["price"]}
    except Exception as e:
        raise HTTPException(500, detail=str(e))

class WatchlistIn(BaseModel):
    symbols: List[str]

@app.post("/watchlist")
def watchlist(in_body: WatchlistIn):
    out = []
    client = coinbase_client()
    for sym in in_body.symbols:
        try:
            data = client.get(f"/api/v3/brokerage/market/products/{sym}")
            out.append({"product_id": sym, "price": data.get("price")})
        except Exception as e:
            out.append({"product_id": sym, "error": str(e)})
    return {"results": out}

# ---- Minimal "agent" that can call the price tool via function calling ----
class ChatIn(BaseModel):
    message: str
    symbols: Optional[List[str]] = None  # optional default watchlist

def tool_get_price(product_id: str = "BTC-USD"):
    # helper used by the agent function call
    client = coinbase_client()
    data = client.get(f"/api/v3/brokerage/market/products/{product_id}")
    return {"product_id": product_id, "price": data.get("price")}

@app.post("/chat")
def chat(in_body: ChatIn):
    if not OPENAI_API_KEY:
        raise HTTPException(500, detail="OPENAI_API_KEY not configured")
    client = OpenAI(api_key=OPENAI_API_KEY)

    tools = [{
        "type": "function",
        "function": {
            "name": "tool_get_price",
            "description": "Get latest price for a Coinbase product_id like BTC-USD",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type":"string", "description":"Coinbase product id, e.g., BTC-USD"}
                },
                "required": []
            }
        }
    }]

    messages = [
        {"role":"system","content":"You are a helpful crypto price assistant. Use the price tool whenever asked about prices."},
        {"role":"user","content": in_body.message}
    ]

    # First turn: let the model decide if it wants to call the tool
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tools
    )
    msg = resp.choices[0].message

    # If tool call requested, execute and return result to the model
    if getattr(msg, "tool_calls", None):
        for call in msg.tool_calls:
            if call.function.name == "tool_get_price":
                args = call.function.arguments or "{}"
                import json as _json
                params = _json.loads(args)
                product_id = params.get("product_id", "BTC-USD")
                tool_result = tool_get_price(product_id)

                messages.append({"role":"assistant","tool_calls":[{"id":call.id,"type":"function","function":{"name":"tool_get_price","arguments":args}}]})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": str(tool_result)
                })

                # final answer after tool result
                final = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages
                )
                return {"reply": final.choices[0].message.content, "tool_result": tool_result}

    # no tool call: just return the model's message
    return {"reply": msg.content}

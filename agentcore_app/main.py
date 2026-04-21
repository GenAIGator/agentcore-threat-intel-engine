"""AgentCore Runtime — Threat Intelligence Analyst Agent with Memory."""
import json
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

import boto3
from botocore.config import Config
from bedrock_agentcore.memory import MemoryClient

# Configuration
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-6")
KNOWLEDGE_BASE_ID = os.environ.get("KNOWLEDGE_BASE_ID", "")
MEMORY_ID = os.environ.get("AGENTCORE_MEMORY_ID", "")

SYSTEM_PROMPT = """You are a Threat Intelligence Analyst specializing in threat actor research, purple team simulation design, and incident attribution. You have access to a knowledge base containing 142 detailed threat profiles covering:

- 107 named threat actor groups (nation-state APTs, ransomware gangs, hacktivists, cybercrime syndicates)
- 35 generic threat categories (attack patterns, techniques, and actor archetypes)

Your three primary use cases:
1. THREAT ACTOR RESEARCH: Detailed intelligence on specific groups or categories including TTPs, MITRE ATT&CK, cloud/AWS paths, detection, and AI usage.
2. TABLETOP / PURPLE TEAM SIMULATIONS: Design realistic exercise scenarios and injects based on real threat actor behaviors.
3. INCIDENT ATTRIBUTION: Given observed activity, identify matching threat actors or categories and provide investigation guidance.

When answering:
1. Cite specific threat actors by name and aliases
2. Include MITRE ATT&CK technique IDs
3. Highlight cloud and AWS-specific risks
4. Note AI usage by threat actors
5. Provide actionable defender guidance
6. Distinguish between named groups and generic threat categories
7. Reference earlier parts of the conversation when relevant

Be concise but thorough. Use markdown formatting."""

# Lazy-loaded clients
_bedrock_runtime = None
_bedrock_agent_runtime = None
_memory_client = None


def get_bedrock_runtime():
    global _bedrock_runtime
    if _bedrock_runtime is None:
        config = Config(read_timeout=120, connect_timeout=10, retries={'max_attempts': 3})
        _bedrock_runtime = boto3.client('bedrock-runtime', region_name=AWS_REGION, config=config)
    return _bedrock_runtime


def get_bedrock_agent_runtime():
    global _bedrock_agent_runtime
    if _bedrock_agent_runtime is None:
        config = Config(read_timeout=60, connect_timeout=10)
        _bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=AWS_REGION, config=config)
    return _bedrock_agent_runtime


def get_memory_client():
    global _memory_client
    if _memory_client is None:
        _memory_client = MemoryClient(region_name=AWS_REGION)
    return _memory_client


# === MEMORY FUNCTIONS ===

def get_conversation_history(session_id: str, actor_id: str) -> list:
    """Retrieve conversation history from AgentCore Memory."""
    if not MEMORY_ID or not session_id:
        return []

    try:
        client = get_memory_client()
        events = client.list_events(
            memory_id=MEMORY_ID,
            session_id=session_id,
            actor_id=actor_id,
        )

        messages = []
        for event in events:
            for payload_item in event.get('payload', []):
                conv = payload_item.get('conversational', {})
                if conv:
                    content = conv.get('content', {}).get('text', '')
                    role = conv.get('role', '').lower()
                    if content and role in ('user', 'assistant'):
                        messages.append({"role": role, "content": content})

        return messages[-10:]  # Last 10 messages

    except Exception as e:
        print(f"Memory retrieval error: {e}")
        return []


def store_conversation_event(session_id: str, actor_id: str, user_msg: str, assistant_msg: str):
    """Store a conversation turn in AgentCore Memory."""
    if not MEMORY_ID or not session_id:
        return

    try:
        client = get_memory_client()
        client.create_event(
            memory_id=MEMORY_ID,
            actor_id=actor_id,
            session_id=session_id,
            messages=[
                (user_msg, "USER"),
                (assistant_msg[:2000], "ASSISTANT"),
            ]
        )
    except Exception as e:
        print(f"Memory store error: {e}")


def retrieve_long_term_memories(actor_id: str, query: str) -> str:
    """Retrieve long-term memories (summaries, facts) relevant to the query."""
    if not MEMORY_ID:
        return ""

    try:
        client = get_memory_client()
        memories = client.retrieve_memories(
            memory_id=MEMORY_ID,
            namespace=f"/threat-intel/facts",
            query=query,
        )

        if memories:
            return "\n".join([m.get('content', '') for m in memories[:3] if m.get('content')])
        return ""

    except Exception as e:
        print(f"Long-term memory retrieval error: {e}")
        return ""


# === KB RETRIEVAL ===

def retrieve_from_kb(query: str) -> str:
    """Retrieve relevant context from the knowledge base."""
    try:
        client = get_bedrock_agent_runtime()
        response = client.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": 10}
            }
        )

        results = []
        for result in response.get("retrievalResults", []):
            content = result.get("content", {}).get("text", "")
            score = result.get("score", 0)
            if content and score > 0.3:
                results.append(content)

        if results:
            return "\n\n---\n\n".join(results[:6])
        return ""

    except Exception as e:
        print(f"KB retrieval error: {e}")
        return ""


# === MODEL INVOCATION ===

def invoke_claude(prompt: str, context: str = "", history: list = None, long_term_context: str = "") -> str:
    """Invoke Claude model with RAG context, conversation history, and long-term memory."""

    # Build messages array with history
    messages = []
    if history:
        for msg in history[-6:]:
            messages.append(msg)

    # Build current user message with KB context + long-term memory
    parts = []
    if context:
        parts.append(f"Threat intelligence from knowledge base:\n{context}")
    if long_term_context:
        parts.append(f"Relevant long-term memory:\n{long_term_context}")

    if parts:
        user_content = "\n\n---\n\n".join(parts) + f"\n\nUser question: {prompt}\n\nProvide a detailed, actionable response. Reference earlier conversation context if relevant."
    else:
        user_content = prompt

    messages.append({"role": "user", "content": user_content})

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "system": SYSTEM_PROMPT,
        "messages": messages
    })

    try:
        client = get_bedrock_runtime()
        response = client.invoke_model(
            modelId=MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json"
        )

        response_body = json.loads(response['body'].read())
        return response_body.get('content', [{}])[0].get('text', 'No response generated.')

    except Exception as e:
        return f"Error invoking model: {str(e)}"


# === REQUEST HANDLER ===

def handle_request(prompt: str, session_id: str = "", actor_id: str = "user") -> str:
    """Process a request with memory-aware conversation."""

    # 1. Retrieve conversation history from short-term memory
    history = get_conversation_history(session_id, actor_id)

    # 2. Retrieve long-term memories relevant to this query
    long_term_context = retrieve_long_term_memories(actor_id, prompt)

    # 3. Retrieve KB context
    context = retrieve_from_kb(prompt)

    # 4. Invoke Claude with history + context + long-term memory
    response = invoke_claude(prompt, context, history, long_term_context)

    # 5. Store this turn in memory
    store_conversation_event(session_id, actor_id, prompt, response)

    return response


class ThreatIntelHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ping":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/invocations":
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length)) if content_length else {}

            prompt = body.get("prompt", body.get("inputText", body.get("query", "")))
            session_id = body.get("sessionId", body.get("session_id", ""))
            actor_id = body.get("userId", body.get("actor_id", "user"))

            try:
                response_text = handle_request(prompt, session_id, actor_id)
                result = {"output": {"text": response_text}}
            except Exception as e:
                result = {"output": {"text": f"Error: {str(e)}"}}

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    print("Threat Intelligence Analyst Agent starting on :8080")
    print(f"Model: {MODEL_ID}")
    print(f"Knowledge Base: {KNOWLEDGE_BASE_ID}")
    print(f"Memory: {MEMORY_ID or 'DISABLED'}")
    server = HTTPServer(("0.0.0.0", 8080), ThreatIntelHandler)
    server.serve_forever()

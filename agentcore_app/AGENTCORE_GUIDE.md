# AgentCore Runtime - Quick Reference Guide

## What is AgentCore Runtime?

A serverless environment to run your Python agent code. You upload a zip file, it runs your code when invoked. It includes Memory for conversation persistence and integrates with Bedrock Knowledge Bases for RAG.

## Key Gotchas

1. **AgentCore does NOT have boto3 pre-installed.** Bundle ALL dependencies in your zip.
2. **Binary dependencies must be Linux ARM64.** Build with `--platform manylinux2014_aarch64`.
3. **Remove any macOS `.so` / `.dylib` files** before zipping — they cause CREATE_FAILED.
4. **Session IDs must be >= 33 characters.**
5. **CloudFormation doesn't update runtime code when only S3 content changes.** Bump a version parameter or delete/recreate the stack.
6. **S3 Vectors metadata limit is 2048 bytes** but Bedrock adds ~900 bytes of overhead, so keep files under ~1050 bytes.

## Required Zip Structure

```
agent-code.zip
├── main.py              # Your entrypoint
├── boto3/               # Bundled dependency
├── botocore/            # Bundled dependency
├── bedrock_agentcore/   # AgentCore SDK (for MemoryClient)
├── s3transfer/          # Bundled dependency
└── ... other deps (all Linux ARM64)
```

## How to Package (from macOS)

```bash
bash agentcore_app/package.sh
```

The script:
- Installs deps targeting `manylinux2014_aarch64` / Python 3.12
- Removes any macOS `darwin` binaries
- Deletes the old zip before creating a new one
- Copies `main.py` into the build directory

## Required Code Structure

Your `main.py` must:

1. **Listen on port 8080**
2. **Implement `/ping` GET** — health check
3. **Implement `/invocations` POST** — handles requests

```python
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ping":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy"}).encode())

    def do_POST(self):
        if self.path == "/invocations":
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            prompt = body.get("prompt", "")
            result = process_request(prompt)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"output": {"text": result}}).encode())

if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
```

## Memory Integration

Uses the `bedrock-agentcore-starter-toolkit` SDK (`MemoryClient`):

```python
from bedrock_agentcore.memory import MemoryClient

client = MemoryClient(region_name="us-east-1")

# Store a conversation turn
client.create_event(
    memory_id="your-memory-id",
    actor_id="user123",
    session_id="session_abc",
    messages=[
        ("What is APT29?", "USER"),
        ("APT29 is a Russian espionage group...", "ASSISTANT"),
    ]
)

# Retrieve conversation history
events = client.list_events(
    memory_id="your-memory-id",
    session_id="session_abc",
    actor_id="user123",
)

# Retrieve long-term memories (semantic search)
memories = client.retrieve_memories(
    memory_id="your-memory-id",
    namespace="/threat-intel/facts",
    query="APT29 cloud tactics",
)
```

The Memory resource is created via CloudFormation with strategies for:
- **Semantic memory** — extracts facts from conversations
- **Summary memory** — summarizes sessions
- **User preferences** — tracks user interests

## CloudFormation Resources

```yaml
# Runtime (runs your code)
ThreatIntelRuntime:
  Type: AWS::BedrockAgentCore::Runtime
  Properties:
    AgentRuntimeName: my_agent
    RoleArn: !GetAtt RuntimeRole.Arn
    AgentRuntimeArtifact:
      CodeConfiguration:
        Code:
          S3:
            Bucket: my-bucket
            Prefix: path/to/agent-code.zip
        EntryPoint:
          - main.py
        Runtime: PYTHON_3_12
    NetworkConfiguration:
      NetworkMode: PUBLIC
    ProtocolConfiguration: HTTP
    EnvironmentVariables:
      AGENTCORE_MEMORY_ID: !GetAtt Memory.MemoryId

# Endpoint (required to invoke the runtime)
ThreatIntelEndpoint:
  Type: AWS::BedrockAgentCore::RuntimeEndpoint
  Properties:
    AgentRuntimeId: !GetAtt ThreatIntelRuntime.AgentRuntimeId
    Name: my_agent_endpoint

# Memory (conversation persistence)
ThreatIntelMemory:
  Type: AWS::BedrockAgentCore::Memory
  Properties:
    Name: my_memory
    EventExpiryDuration: 30
    MemoryExecutionRoleArn: !GetAtt MemoryRole.Arn
    MemoryStrategies:
      - SemanticMemoryStrategy:
          Name: Facts
          Namespaces:
            - /threat-intel/facts
      - SummaryMemoryStrategy:
          Name: Summaries
          Namespaces:
            - /summaries/{sessionId}
```

## Invoking the Agent

```python
import boto3, json

client = boto3.client('bedrock-agentcore', region_name='us-east-1')

# Session ID must be >= 33 characters
session_id = "my_session_20260414T120000_abc123def456"

response = client.invoke_agent_runtime(
    runtimeSessionId=session_id,
    agentRuntimeArn="arn:aws:bedrock-agentcore:us-east-1:123456:runtime/my_agent-xxxxx",
    qualifier="my_agent_endpoint",
    payload=json.dumps({
        "prompt": "Tell me about APT29",
        "sessionId": session_id,
        "userId": "user1",
    }).encode()
)

result = json.loads(response['response'].read())
print(result['output']['text'])
```

## Deployment Commands

```bash
# 1. Package
bash agentcore_app/package.sh

# 2. Upload
aws s3 cp agent-code.zip s3://YOUR-BUCKET-NAME/agentcore/agent-code.zip

# 3. Deploy (bump CodeVersion in template first)
aws cloudformation update-stack \
  --stack-name threat-intel-agentcore \
  --template-body file://cloudformation/agentcore-stack.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# If stack is stuck, delete and recreate:
aws cloudformation delete-stack --stack-name threat-intel-agentcore --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name threat-intel-agentcore --region us-east-1
aws cloudformation create-stack \
  --stack-name threat-intel-agentcore \
  --template-body file://cloudformation/agentcore-stack.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

## Knowledge Base Sync

```bash
# Upload threat profiles
aws s3 sync threat-profiles/ s3://YOUR-BUCKET-NAME/threat-profiles/ --delete

# Re-index
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id YOUR_KB_ID \
  --data-source-id YOUR_DATASOURCE_ID \
  --region us-east-1

# Check status
aws bedrock-agent get-ingestion-job \
  --knowledge-base-id YOUR_KB_ID \
  --data-source-id YOUR_DATASOURCE_ID \
  --ingestion-job-id <JOB_ID> \
  --region us-east-1
```

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| Runtime initialization exceeded 30s | Missing dependencies in zip | Bundle boto3 and all deps |
| Incompatible with Linux ARM64 | macOS binaries in zip | Use `--platform manylinux2014_aarch64` and remove darwin `.so` files |
| Invalid length for runtimeSessionId | Session ID too short | Must be >= 33 characters |
| CloudFormation updates don't take effect | S3 content changed but template didn't | Bump CodeVersion parameter or delete/recreate stack |
| Filterable metadata > 2048 bytes | Threat profile JSON too large | Keep files under ~1050 bytes (Bedrock adds ~900B overhead) |
| Memory not found | Stack was recreated, memory ID changed | Config auto-discovers from CloudFormation stack outputs |
| UPDATE_ROLLBACK_FAILED | AWS internal error | Delete and recreate the stack |

## Architecture

```
User (Streamlit) --> AgentCore Runtime --> Bedrock KB (RAG)
                          |                    |
                          v                    v
                    AgentCore Memory     S3 Vectors
                    (conversation)    (threat profiles)
                          |
                          v
                    Claude Sonnet 4.6
```

The Streamlit app auto-discovers the Runtime ARN from CloudFormation stack outputs — no manual config updates needed after stack recreation.

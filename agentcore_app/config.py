# Threat Intelligence Analyst - AgentCore Configuration
# Pulls Runtime ARN and Memory ID from CloudFormation stack outputs automatically.

import os
import boto3

# AWS Configuration
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
STACK_NAME = os.environ.get("STACK_NAME", "threat-intel-agentcore")

# Model Configuration
MODEL_ID = "us.anthropic.claude-sonnet-4-6"

# AgentCore endpoint qualifier (matches CloudFormation template)
ENDPOINT_QUALIFIER = "apt_threat_intel_agent_endpoint"


def _get_stack_outputs():
    """Pull Runtime ARN and Memory ID from CloudFormation stack outputs."""
    try:
        cf = boto3.client('cloudformation', region_name=AWS_REGION)
        response = cf.describe_stacks(StackName=STACK_NAME)
        outputs = response['Stacks'][0].get('Outputs', [])
        return {o['OutputKey']: o['OutputValue'] for o in outputs}
    except Exception as e:
        print(f"Warning: Could not fetch stack outputs: {e}")
        return {}


_outputs = _get_stack_outputs()

# Knowledge Base Configuration
KNOWLEDGE_BASE_ID = os.environ.get(
    "KNOWLEDGE_BASE_ID",
    _outputs.get("KnowledgeBaseId", "")
)

RUNTIME_ARN = os.environ.get(
    "AGENTCORE_RUNTIME_ARN",
    _outputs.get("RuntimeArn", "")
)

MEMORY_ID = os.environ.get(
    "AGENTCORE_MEMORY_ID",
    _outputs.get("MemoryId", "")
)

if not KNOWLEDGE_BASE_ID:
    print("ERROR: KNOWLEDGE_BASE_ID not found. Set KNOWLEDGE_BASE_ID or ensure stack '%s' exists." % STACK_NAME)
if not RUNTIME_ARN:
    print("ERROR: RUNTIME_ARN not found. Set AGENTCORE_RUNTIME_ARN or ensure stack '%s' exists." % STACK_NAME)
if not MEMORY_ID:
    print("WARNING: MEMORY_ID not found. Memory features will be disabled.")

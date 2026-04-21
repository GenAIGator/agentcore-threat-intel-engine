# Threat Intelligence Analyst

AI-powered threat intelligence platform with 142 threat actor profiles, built on Amazon Bedrock AgentCore with RAG retrieval and conversation memory.

## What It Does

- **Threat Actor Research** — Query 107 named groups and 35 generic attack categories with MITRE ATT&CK mappings, cloud/AWS attack paths, and detection guidance
- **Tabletop / Purple Team Simulations** — Generate realistic exercise scenarios and injects based on real threat actor behaviors
- **Incident Attribution** — Describe observed activity and get matched to likely threat actors with investigation guidance

## Architecture

```
Streamlit App (local) --> AgentCore Runtime --> Bedrock Knowledge Base (RAG)
                               |                        |
                               v                        v
                         AgentCore Memory          S3 Vectors
                         (conversation)         (threat profiles)
                               |
                               v
                         Claude Sonnet 4.6
```

## Coverage

- **142 threat profiles** (107 named groups + 35 generic categories)
- **Nation-state:** China (24), Russia (29), North Korea (9), Iran (10), India (2), Belarus, Vietnam, Pakistan, Lebanon
- **Cybercrime:** Ransomware/RaaS, BEC, data extortion, financial fraud, infostealers, initial access brokers
- **Hacktivists:** Anonymous, Killnet, GhostSec, SiegedSec, NoName057(16), and others
- **Attack patterns:** Supply chain, cloud abuse, identity theft, OT/ICS, wipers, living-off-the-land, CI/CD compromise, and more

## Prerequisites

- AWS account with Bedrock model access (Claude Sonnet 4.6, Titan Embeddings v2)
- AWS CLI configured
- Python 3.10+ with `streamlit` and `boto3` installed
- An S3 bucket for threat profiles and agent code

## Deployment

### 1. Enable model access

If you haven't used Claude Sonnet 4.6 or Titan Embeddings v2 before, go to the [Amazon Bedrock console](https://console.aws.amazon.com/bedrock/), navigate to **Model access**, and submit a use case for both models. Approval can take up to 15 minutes. Once approved, subscribe to the models and wait up to 2 more minutes for access to activate.

### 2. Create the S3 bucket and upload threat profiles

```bash
aws s3 mb s3://YOUR-BUCKET-NAME --region us-east-1

aws s3 sync threat-profiles/ s3://YOUR-BUCKET-NAME/threat-profiles/
```

### 3. Deploy the Knowledge Base stack

Update `S3BucketName` in the template if your bucket name differs.

```bash
aws cloudformation create-stack \
  --stack-name threat-intel-kb \
  --template-body file://cloudformation/bedrock-knowledge-base.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

Wait for completion, then get the Knowledge Base ID:

```bash
aws cloudformation describe-stacks --stack-name threat-intel-kb \
  --query 'Stacks[0].Outputs[?OutputKey==`KnowledgeBaseId`].OutputValue' --output text
```

Trigger ingestion:

```bash
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id YOUR_KB_ID \
  --data-source-id YOUR_DATASOURCE_ID \
  --region us-east-1
```

### 4. Upload agent code and deploy AgentCore stack

```bash
aws s3 cp agentcore_app/agent-code.zip s3://YOUR-BUCKET-NAME/agentcore/agent-code.zip

aws cloudformation create-stack \
  --stack-name threat-intel-agentcore \
  --template-body file://cloudformation/agentcore-stack.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

### 5. Run the Streamlit app

```bash
pip install streamlit boto3
cd agentcore_app
streamlit run app.py
```

The app auto-discovers the Runtime ARN from CloudFormation stack outputs.

## File Structure

```
cloudformation/
  bedrock-knowledge-base.yaml   # KB + S3 Vectors + data source
  agentcore-stack.yaml          # Runtime + Memory + Endpoint + IAM

agentcore_app/
  main.py                       # Agent code (deployed to AgentCore Runtime)
  app.py                        # Streamlit UI (runs locally)
  config.py                     # Auto-discovers config from CloudFormation
  agent-code.zip                # Pre-built deployment package (Linux ARM64)
  AGENTCORE_GUIDE.md            # Detailed reference guide

threat-profiles/                # 1630 JSON files (142 profiles x ~11 files each)
LICENSE                         # Apache License 2.0
NOTICE                          # Copyright notice
```

## Updating Threat Profiles

1. Add/edit JSON files in `threat-profiles/` (keep each file under 1050 bytes)
2. Sync to S3: `aws s3 sync threat-profiles/ s3://YOUR-BUCKET-NAME/threat-profiles/ --delete`
3. Re-index: `aws bedrock-agent start-ingestion-job --knowledge-base-id YOUR_KB_ID --data-source-id YOUR_DS_ID --region us-east-1`

No agent redeployment needed — the KB is queried at runtime.

## Updating Agent Code

See [AGENTCORE_GUIDE.md](agentcore_app/AGENTCORE_GUIDE.md) for detailed packaging and deployment instructions.

## Cost

Costs are minimal for low-usage workloads. AgentCore Runtime, Memory, S3 Vectors, and Bedrock model invocations are all pay-per-use with no idle charges. Refer to [AWS pricing](https://aws.amazon.com/bedrock/pricing/) for current rates.


## Disclaimer

See [DISCLAIMER.md](DISCLAIMER.md) for additional details.

This project and its associated content are provided for **educational and research purposes only**.

The project utilizes open-source software and Amazon Web Services (AWS) cloud infrastructure. The threat actor profiles, attack scenarios, and intelligence content are largely generated using artificial intelligence systems and based on publicly available threat intelligence reporting. Some material describes real-world attack techniques, tactics, and procedures (TTPs) used by threat actors, and includes tabletop exercise scenarios and purple team simulations involving adversarial activity. This content is included solely to support defensive security research, incident response training, and educational objectives.

Any generated content, threat assessments, attribution analysis, or simulation scenarios do not reflect the personal views, opinions, or beliefs of the author.

This project is developed independently and is not affiliated with, endorsed by, or representative of any current or former employer. All scenarios, organizations, individuals, and systems referenced within the project are entirely hypothetical, fictional, or used solely for illustrative purposes. Any resemblance to real organizations, systems, or individuals, whether explicit or implied, is purely coincidental and unintentional.

Users are responsible for ensuring that any testing or research conducted using this project complies with applicable laws, regulations, and organizational policies. The materials in this project should only be used against systems for which you have explicit authorization.

The author assumes no responsibility or liability for misuse of this project or any consequences resulting from its use.

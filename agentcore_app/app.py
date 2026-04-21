"""
Threat Intelligence Analyst - Streamlit App using AgentCore Runtime
"""

import streamlit as st
import boto3
from botocore.config import Config
import uuid
import datetime
import json
from config import AWS_REGION, RUNTIME_ARN, ENDPOINT_QUALIFIER

# Page config
st.set_page_config(
    page_title="Threat Intelligence Analyst",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS: push main chat to the left, create a fixed right panel
st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: bold; color: #1f77b4; margin-bottom: 0.3rem; }
    .sub-header { font-size: 1rem; color: #666; margin-bottom: 1rem; }
    .stButton>button { width: 100%; }

    /* Constrain chat to left 65% */
    .stChatMessage, .stChatInput, .stSpinner {
        max-width: 65% !important;
    }

    /* Fixed right panel */
    .right-panel {
        position: fixed;
        top: 60px;
        right: 20px;
        width: 28%;
        max-height: calc(100vh - 80px);
        overflow-y: auto;
        padding: 1rem;
        background: #fafafa;
        border-left: 1px solid #e0e0e0;
        border-radius: 8px;
        font-size: 0.85rem;
        z-index: 100;
    }
    .right-panel h3 { font-size: 1rem; margin-top: 0.8rem; margin-bottom: 0.4rem; }
    .right-panel h4 { font-size: 0.9rem; margin-top: 0.6rem; margin-bottom: 0.3rem; color: #555; }
    .right-panel ul { padding-left: 1.2rem; margin: 0.2rem 0; }
    .right-panel li { margin-bottom: 0.2rem; }
    .right-panel .coverage { color: #888; font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)


def make_session_id() -> str:
    ts = datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    unique = uuid.uuid4().hex[:12]
    return f"threat_intel_{ts}_{unique}"


@st.cache_resource
def get_agentcore_client():
    config = Config(read_timeout=120, connect_timeout=10, retries={'max_attempts': 3, 'mode': 'adaptive'})
    return boto3.client('bedrock-agentcore', region_name=AWS_REGION, config=config)


def invoke_agent(prompt: str, session_id: str) -> str:
    client = get_agentcore_client()
    payload = json.dumps({
        "prompt": prompt,
        "sessionId": session_id,
        "userId": "streamlit_user",
    }).encode('utf-8')
    try:
        response = client.invoke_agent_runtime(
            runtimeSessionId=session_id,
            agentRuntimeArn=RUNTIME_ARN,
            qualifier=ENDPOINT_QUALIFIER,
            payload=payload,
        )
        body = response.get('response')
        if body:
            result = json.loads(body.read().decode('utf-8'))
            return result.get('output', {}).get('text', str(result))
        return "No response from agent"
    except Exception as e:
        return f"Error: {str(e)}"


def main():
    # === SIDEBAR (filters & scenarios) ===
    with st.sidebar:
        st.markdown("### 🛡️ Threat Intel Analyst")
        st.caption("142 profiles · Named groups & categories")
        st.caption(f"Session: {st.session_state.get('session_id', '')[:20]}...")

        if st.button("🔄 New Session"):
            st.session_state.session_id = make_session_id()
            st.session_state.messages = []
            st.rerun()

        st.divider()

        st.subheader("🎯 By Country")
        for label, query in {
            "🇨🇳 China (24)": "List all Chinese threat actors and their primary objectives",
            "🇷🇺 Russia (29)": "List all Russian threat actors including ransomware groups and hacktivists",
            "🇰🇵 North Korea (9)": "List all North Korean threat actors and their financial/espionage tactics",
            "🇮🇷 Iran (10)": "List all Iranian threat actors and their capabilities",
        }.items():
            if st.button(label, key=f"c_{label}"):
                st.session_state.pending_query = query

        st.divider()

        st.subheader("💀 By Threat Type")
        for label, query in {
            "💰 Ransomware/RaaS": "Which threat actors operate ransomware-as-a-service? Compare their tactics.",
            "🕵️ Espionage": "Which groups focus on long-term espionage and intelligence collection?",
            "🔗 Supply Chain": "Which actors target supply chains, MSPs, or trusted vendor relationships?",
            "☁️ Cloud/SaaS": "Which threat actors specifically target cloud infrastructure and SaaS platforms?",
            "🏭 OT/ICS": "Which actors target operational technology and industrial control systems?",
            "📱 Identity/Social Eng": "Which actors use MFA fatigue, SIM swapping, or help desk impersonation?",
            "🤖 AI-Enabled": "Which threat actors use AI in their operations? What AI tactics are confirmed?",
        }.items():
            if st.button(label, key=f"t_{label}"):
                st.session_state.pending_query = query

        st.divider()

        st.subheader("🟣 Purple Team / Tabletop")
        for label, query in {
            "🎲 Ransomware Scenario": "Design a tabletop exercise simulating a LockBit affiliate attack against a healthcare organization. Include injects and decision points.",
            "🎲 Cloud Compromise": "Create a purple team scenario based on Scattered Spider tactics targeting Okta and AWS.",
            "🎲 Supply Chain Attack": "Design a tabletop exercise based on a supply chain compromise similar to SolarWinds or MOVEit.",
            "🎲 Insider Threat": "Create a simulation scenario for a privileged insider threat with data exfiltration.",
        }.items():
            if st.button(label, key=f"p_{label}"):
                st.session_state.pending_query = query

        st.divider()

        st.subheader("🔎 Incident Attribution")
        if st.button("📋 Describe an Incident", key="incident"):
            st.session_state.pending_query = "I'm going to describe an incident. Please analyze it and tell me which threat actors or categories most closely match the observed behavior, and explain your reasoning."

    # === RIGHT PANEL (static HTML, doesn't interfere with chat_input) ===
    st.markdown("""
    <div class="right-panel">
        <h3>🔬 Research Queries</h3>
        <ul>
            <li>APT29 cloud attack paths & detection</li>
            <li>Compare Volt Typhoon vs Salt Typhoon</li>
            <li>Initial access broker techniques</li>
            <li>LockBit vs BlackCat vs Cl0p differences</li>
            <li>Living-off-the-land detection</li>
            <li>Cryptocurrency wallet drainer operations</li>
        </ul>
        <h3>🟣 Simulation Ideas</h3>
        <ul>
            <li>NK crypto theft tabletop for DeFi</li>
            <li>BEC to data extortion scenario</li>
            <li>CI/CD pipeline backdoor simulation</li>
            <li>Wiper vs critical infrastructure</li>
        </ul>
        <h3>🔎 Attribution Examples</h3>
        <ul>
            <li>Web shell + WMI + RAR staging</li>
            <li>MFA fatigue + Okta + Snowflake</li>
            <li>C2 via Cloudflare + ransomware GPO</li>
            <li>MFT zero-day mass data theft</li>
        </ul>
        <h3>ℹ️ Coverage</h3>
        <p class="coverage">107 named groups + 34 categories</p>
    </div>
    """, unsafe_allow_html=True)

    # === MAIN CHAT (root level, chat_input pins to bottom) ===
    if 'session_id' not in st.session_state:
        st.session_state.session_id = make_session_id()
    if 'messages' not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if 'pending_query' in st.session_state:
        query = st.session_state.pending_query
        del st.session_state.pending_query
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)
        with st.chat_message("assistant"):
            with st.spinner("Analyzing threat intelligence..."):
                response = invoke_agent(query, st.session_state.session_id)
            st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})

    if user_input := st.chat_input("Research threat actors, design exercises, or describe an incident..."):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
        with st.chat_message("assistant"):
            with st.spinner("Analyzing threat intelligence..."):
                response = invoke_agent(user_input, st.session_state.session_id)
            st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})


if __name__ == "__main__":
    main()

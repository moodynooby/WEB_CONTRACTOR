"""Pipeline Orchestration Page - Run All Pipeline Stages."""

import json
import time
import traceback
from pathlib import Path

import requests
import streamlit as st

from core import settings
from core.settings import LOCAL_PROVIDER, PERFORMANCE_MODE, LLM_MODE
from core.logging import get_logger
from core.streamlit_utils import get_app
from core.telegram import TelegramNotifier
from core.llm import get_all_modes, get_all_local_providers

logger = get_logger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "app_config.json"


def get_current_settings() -> dict:
    """Get current mode settings from configuration."""
    from core.llm import get_mode_profile

    perf_profile = get_mode_profile(PERFORMANCE_MODE)
    return {
        "llm_mode": LLM_MODE,
        "performance_mode": PERFORMANCE_MODE,
        "local_provider": LOCAL_PROVIDER if LLM_MODE == "local" else None,
        "profile": perf_profile,
        "is_local": LLM_MODE == "local",
    }


def save_mode_settings(llm_mode: str, perf_mode: str, local_provider: str | None = None) -> tuple[bool, str]:
    """Save mode settings to configuration file."""
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)

        config.setdefault("llm", {})["mode"] = llm_mode
        config["llm"]["performance_mode"] = perf_mode

        if llm_mode == "local" and local_provider:
            config["llm"].setdefault("local", {})["provider"] = local_provider

        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)

        return True, "Settings saved successfully"
    except Exception as e:
        return False, f"Failed to save settings: {e}"


def test_connection(llm_mode: str, local_provider: str | None = None) -> list[dict]:
    """Test connection for current mode. Returns list of test results."""
    results = []

    if llm_mode == "cloud":
        # Test Groq
        if settings.GROQ_API_KEY:
            try:
                response = requests.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                    timeout=5,
                )
                results.append({
                    "name": "Groq API",
                    "status": "success" if response.status_code == 200 else "error",
                    "message": f"Connected (status {response.status_code})" if response.status_code == 200 else f"Failed (status {response.status_code})"
                })
            except Exception as e:
                results.append({"name": "Groq API", "status": "error", "message": str(e)})
        else:
            results.append({"name": "Groq API", "status": "warning", "message": "API key not configured"})

        # Test OpenRouter
        if settings.OPENROUTER_API_KEY:
            try:
                response = requests.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
                    timeout=5,
                )
                results.append({
                    "name": "OpenRouter API",
                    "status": "success" if response.status_code == 200 else "error",
                    "message": f"Connected (status {response.status_code})" if response.status_code == 200 else f"Failed (status {response.status_code})"
                })
            except Exception as e:
                results.append({"name": "OpenRouter API", "status": "error", "message": str(e)})
        else:
            results.append({"name": "OpenRouter API", "status": "warning", "message": "API key not configured"})

    elif llm_mode == "local" and local_provider:
        # Test local provider
        if local_provider == "ollama":
            url = "http://localhost:11434"
            try:
                response = requests.get(f"{url}", timeout=5)
                results.append({
                    "name": "Ollama",
                    "status": "success" if response.status_code == 200 else "error",
                    "message": f"Running at {url}" if response.status_code == 200 else f"Failed (status {response.status_code})"
                })
            except Exception as e:
                results.append({"name": "Ollama", "status": "error", "message": f"Cannot connect to {url}: {e}"})
        elif local_provider == "vllm":
            url = "http://localhost:8000"
            try:
                response = requests.get(f"{url}/v1/models", timeout=5)
                results.append({
                    "name": "vLLM",
                    "status": "success" if response.status_code == 200 else "error",
                    "message": f"Running at {url}" if response.status_code == 200 else f"Failed (status {response.status_code})"
                })
            except Exception as e:
                results.append({"name": "vLLM", "status": "error", "message": f"Cannot connect to {url}: {e}"})
        elif local_provider == "llama_cpp":
            results.append({"name": "llama-cpp-python", "status": "success", "message": "Python library (no server needed)"})

    return results

st.set_page_config(
    page_title="Pipeline",
    page_icon="🏗️",
    layout="wide",
)

telegram = None
if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
    try:
        telegram = TelegramNotifier(
            bot_token=settings.TELEGRAM_BOT_TOKEN,
            chat_id=settings.TELEGRAM_CHAT_ID,
        )
    except Exception as e:
        logger.error(f"Failed to initialize Telegram notifier: {e}")

if "pipeline_running" not in st.session_state:
    st.session_state.pipeline_running = False
if "pipeline_cancelled" not in st.session_state:
    st.session_state.pipeline_cancelled = False
if "pipeline_results" not in st.session_state:
    st.session_state.pipeline_results = {}
if "pipeline_stage_status" not in st.session_state:
    st.session_state.pipeline_stage_status = {}

app = get_app()

st.title("🏗️ Pipeline Orchestration")
st.caption("Run all pipeline stages in sequence with parallel execution where possible")

with st.expander("⚙️ Pipeline Configuration", expanded=True):
    col1, col2, col3 = st.columns(3)

    with col1:
        max_queries = st.number_input(
            "Max Discovery Queries",
            min_value=5,
            max_value=100,
            value=20,
            step=5,
            help="Maximum number of search queries to execute in discovery",
        )

    with col2:
        audit_limit = st.number_input(
            "Max Leads to Audit",
            min_value=5,
            max_value=100,
            value=20,
            step=5,
            help="Maximum number of pending leads to audit",
        )

    with col3:
        email_limit = st.number_input(
            "Max Emails to Generate",
            min_value=5,
            max_value=100,
            value=20,
            step=5,
            help="Maximum number of emails to generate for qualified leads",
        )

    col1, col2 = st.columns(2)
    with col1:
        auto_approve = st.toggle(
            "Auto-approve & Send Emails",
            value=False,
            help="If enabled, generated emails will be automatically approved and sent without manual review",
        )

    with col2:
        continue_on_error = st.toggle(
            "Continue on Error",
            value=True,
            help="If enabled, pipeline will continue with remaining stages even if one fails",
        )

    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("**Telegram Notifications:**")
    with col2:
        if telegram and telegram.enabled:
            st.success("✅ Enabled")
        else:
            st.warning("⚠️ Disabled")

with st.expander("🔧 Feature Toggles", expanded=True):
    st.info(
        "💡 **Tip:** Toggle features on/off here. For advanced settings (timeout, weights, priority, etc.), edit `config/app_config.json`"
    )

    config_load_error = None
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        config_load_error = f"Config file not found at {CONFIG_PATH}"
        config = {}
    except json.JSONDecodeError as e:
        config_load_error = f"Invalid JSON in config: {e}"
        config = {}
    except Exception as e:
        config_load_error = f"Failed to load config: {e}"
        config = {}

    if config_load_error:
        st.error(f"⚠️ {config_load_error}")
        st.warning("Feature toggles are disabled. Please fix the config file.")

    with st.expander("🌐 Discovery Sources", expanded=True):
        st.caption(
            "💡 For priority, max_results, and other advanced settings → edit `config/app_config.json` → `discovery_sources`"
        )

        sources_enabled_master = st.toggle(
            "**Enable All Sources**",
            value=config.get("discovery_sources", {})
            .get("sources", {})
            .get("google_maps", {})
            .get("enabled", True),
            help="Master toggle for all discovery sources",
        )

        sources = config.get("discovery_sources", {}).get("sources", {})
        source_cols = st.columns(3)
        source_states = {}

        source_items = list(sources.items())
        for idx, (source_name, source_config) in enumerate(source_items):
            col = source_cols[idx % 3]
            with col:
                enabled = st.toggle(
                    f"**{source_name.replace('_', ' ').title()}**",
                    value=source_config.get("enabled", True)
                    if sources_enabled_master
                    else False,
                    help=f"{source_config.get('description', 'No description')}\n\nMax results: {source_config.get('max_results', 50)}",
                    key=f"source_{source_name}",
                )
                source_states[source_name] = enabled

    with st.expander("📊 Query Features", expanded=True):
        st.caption(
            "💡 For threshold, weights, and other advanced settings → edit `config/app_config.json` → `query_scoring` or `query_performance`"
        )

        col1, col2 = st.columns(2)
        with col1:
            query_scoring_enabled = st.toggle(
                "**Query Scoring**",
                value=config.get("query_scoring", {}).get("enabled", True),
                help="Uses LLM to score queries based on historical performance and specificity",
            )
        with col2:
            query_perf_enabled = st.toggle(
                "**Query Performance Tracking**",
                value=config.get("query_performance", {}).get("enabled", True),
                help="Tracks query success/failure rates and auto-disables stale queries",
            )

    with st.expander("🤖 Audit Agents", expanded=True):
        st.caption(
            "💡 For weights, timeout, system prompts, and other advanced settings → edit `config/app_config.json` → `agents`"
        )

        agents_enabled_master = st.toggle(
            "**Enable All Agents**",
            value=config.get("agents", {}).get("content", {}).get("enabled", True),
            help="Master toggle for all audit agents",
        )

        agent_cols = st.columns(2)
        agent_states = {}

        agent_names = ["content", "business", "technical", "performance"]
        agent_descriptions = {
            "content": "Evaluates website copy clarity, CTAs, value proposition, and trust signals",
            "business": "Evaluates service clarity, target audience, differentiation, and industry standards",
            "technical": "Checks SEO elements, meta tags, structured data, and basic technical issues",
            "performance": "Analyzes page size, load time, and resource efficiency",
        }

        for idx, agent_name in enumerate(agent_names):
            col = agent_cols[idx % 2]
            with col:
                agent_config = config.get("agents", {}).get(agent_name, {})
                enabled = st.toggle(
                    f"**{agent_name.title()} Agent**",
                    value=agent_config.get("enabled", True)
                    if agents_enabled_master
                    else False,
                    help=agent_descriptions.get(agent_name, "Audit agent"),
                    key=f"agent_{agent_name}",
                )
                agent_states[agent_name] = enabled

        if agent_states.get("business", True):
            with st.container():
                st.markdown("&nbsp;&nbsp;&nbsp;&nbsp;└─ **Sub-settings:**")
                llm_audit_enabled = st.toggle(
                    "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**LLM Business Audit**",
                    value=config.get("agents", {})
                    .get("business", {})
                    .get("llm_audit", {})
                    .get("enabled", True),
                    help="Uses LLM to perform deep business analysis. Disable for faster audits.",
                    key="llm_audit_toggle",
                )
        else:
            llm_audit_enabled = False

    with st.expander("📧 Email Generation", expanded=True):
        st.caption(
            "💡 For system prompts, templates, and other advanced settings → edit `config/app_config.json` → `email_generation`"
        )

        email_gen_enabled = st.toggle(
            "**Enable Email Generation**",
            value=config.get("email_generation", {}).get("enabled", True),
            help="Generate personalized cold emails for qualified leads",
        )

current_settings = get_current_settings()

with st.expander("🎛️ LLM Mode & Performance Settings", expanded=True):
    st.info(
        "💡 **Tip:** Switch between Cloud and Local LLM inference, and choose your performance mode"
    )

    mode_icon = "☁️" if not current_settings["is_local"] else "🖥️"
    mode_label = (
        "Cloud"
        if not current_settings["is_local"]
        else f"Local ({current_settings['local_provider']})"
    )
    perf_mode = current_settings["profile"]

    st.markdown(
        f"**Current:** {mode_icon} {mode_label} | {perf_mode['icon']} {perf_mode['label']}"
    )

    col_mode1, col_mode2 = st.columns(2)

    with col_mode1:
        st.markdown("**LLM Location:**")
        llm_mode_option = st.radio(
            "Select LLM Mode",
            options=["cloud", "local"],
            format_func=lambda x: "☁️ Cloud (Groq/OpenRouter)"
            if x == "cloud"
            else "🖥️ Local (On-device)",
            index=0 if current_settings["llm_mode"] == "cloud" else 1,
            horizontal=True,
            label_visibility="collapsed",
            key="llm_mode_radio",
        )

    with col_mode2:
        if llm_mode_option == "local":
            st.markdown("**Local Provider:**")
            local_providers = get_all_local_providers()
            provider_options = [p["key"] for p in local_providers]

            current_provider_idx = 0
            if LOCAL_PROVIDER in provider_options:
                current_provider_idx = provider_options.index(LOCAL_PROVIDER)

            selected_provider = st.selectbox(
                "Provider",
                options=provider_options,
                index=current_provider_idx,
                format_func=lambda x: next(
                    p["name"] for p in local_providers if p["key"] == x
                ),
                key="local_provider_select",
            )
        else:
            selected_provider = None

    st.markdown("**Performance Mode:**")
    modes = get_all_modes()
    
    # Filter modes based on LLM mode selection
    if llm_mode_option == "cloud":
        visible_modes = [m for m in modes if m.get("mode_type") == "cloud"]
    else:
        visible_modes = [m for m in modes if m.get("mode_type") == "local"]
    
    mode_options = [m["key"] for m in visible_modes]

    current_perf_idx = 0
    if PERFORMANCE_MODE in mode_options:
        current_perf_idx = mode_options.index(PERFORMANCE_MODE)

    mode_cols = st.columns(len(visible_modes))
    selected_perf_mode = None

    for idx, (col, mode_key) in enumerate(zip(mode_cols, mode_options)):
        mode_data = visible_modes[idx]
        with col:
            is_selected = idx == current_perf_idx
            if st.button(
                f"{mode_data['icon']} {mode_data['label'].split()[-1]}",
                key=f"perf_mode_{mode_key}",
                type="primary" if is_selected else "secondary",
                help=f"{mode_data['description']}\nModel: {mode_data['model_size']}",
                use_container_width=True,
            ):
                selected_perf_mode = mode_key

    if selected_perf_mode is None:
        # Fallback: use current config mode if it matches visible modes, otherwise first visible
        if PERFORMANCE_MODE in mode_options:
            selected_perf_mode = PERFORMANCE_MODE
        else:
            selected_perf_mode = mode_options[0]

    selected_mode_data = next((m for m in visible_modes if m["key"] == selected_perf_mode), visible_modes[0])
    with st.expander("ℹ️ Mode Details", expanded=False):
        st.markdown(f"""
        **{selected_mode_data["icon"]} {selected_mode_data["label"]}**
        - **Model Size:** {selected_mode_data["model_size"]}
        - **Quality Priority:** {selected_mode_data["quality_priority"]}
        - **Temperature:** {selected_mode_data["temperature"]}
        - **Max Tokens:** {selected_mode_data["max_tokens"]:,}
        - **Parallel Workers:** {selected_mode_data["parallel_workers"]}
        - **Context Size:** {selected_mode_data["context_size"]:,}
        - **Description:** {selected_mode_data["description"]}
        """)

    # Test Connection button - works for both cloud and local
    if st.button("🔌 Test Connection", use_container_width=True):
        with st.spinner("Testing connection(s)..."):
            local_prov = selected_provider if llm_mode_option == "local" else None
            results = test_connection(llm_mode_option, local_prov)
            
            for result in results:
                if result["status"] == "success":
                    st.success(f"✅ **{result['name']}:** {result['message']}")
                elif result["status"] == "warning":
                    st.warning(f"⚠️ **{result['name']}:** {result['message']}")
                else:
                    st.error(f"❌ **{result['name']}:** {result['message']}")

    st.divider()
    col_apply1, col_apply2, col_apply3 = st.columns([1, 2, 1])
    with col_apply2:
        if st.button(
            "💾 Apply Mode Settings", type="primary", use_container_width=True
        ):
            local_prov = selected_provider if llm_mode_option == "local" else None
            success, message = save_mode_settings(
                llm_mode=llm_mode_option,
                performance_mode=selected_perf_mode,
                local_provider=local_prov,
            )

            if success:
                st.success(message)
                st.info("⚠️ Settings saved. Refresh the page to apply changes.")
                if "mode_settings_changed" not in st.session_state:
                    st.session_state.mode_settings_changed = True
            else:
                st.error(message)

feature_settings = {
    "sources_enabled": sources_enabled_master,
    "source_states": source_states,
    "query_scoring_enabled": query_scoring_enabled,
    "query_perf_enabled": query_perf_enabled,
    "agents_enabled": agents_enabled_master,
    "agent_states": agent_states,
    "llm_audit_enabled": llm_audit_enabled,
    "email_gen_enabled": email_gen_enabled,
}


def save_feature_toggles(settings_dict: dict):
    """Save feature toggle settings back to config file."""
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)

        if "source_states" in settings_dict:
            for source_name, enabled in settings_dict["source_states"].items():
                if source_name in config.get("discovery_sources", {}).get(
                    "sources", {}
                ):
                    config["discovery_sources"]["sources"][source_name]["enabled"] = (
                        enabled
                    )

        if "query_scoring_enabled" in settings_dict:
            config.setdefault("query_scoring", {})["enabled"] = settings_dict[
                "query_scoring_enabled"
            ]
        if "query_perf_enabled" in settings_dict:
            config.setdefault("query_performance", {})["enabled"] = settings_dict[
                "query_perf_enabled"
            ]

        if "agent_states" in settings_dict:
            for agent_name, enabled in settings_dict["agent_states"].items():
                if agent_name in config.get("agents", {}):
                    config["agents"][agent_name]["enabled"] = enabled

        if "llm_audit_enabled" in settings_dict:
            config.setdefault("agents", {}).setdefault("business", {}).setdefault(
                "llm_audit", {}
            )["enabled"] = settings_dict["llm_audit_enabled"]

        if "email_gen_enabled" in settings_dict:
            config.setdefault("email_generation", {})["enabled"] = settings_dict[
                "email_gen_enabled"
            ]

        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)

        return True
    except Exception as e:
        logger.error(f"Failed to save feature toggles: {e}")
        return False


with st.sidebar:
    if st.session_state.pipeline_running:
        st.markdown(
            '<div class="big-red-button">',
            unsafe_allow_html=True,
        )
        if st.button(
            "⏹️ CANCEL PIPELINE",
            type="secondary",
            key="cancel_btn",
            help="Stop the pipeline execution",
        ):
            st.session_state.pipeline_cancelled = True
            st.warning("⚠️ Pipeline cancellation requested...")
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="big-red-button">',
            unsafe_allow_html=True,
        )
        if st.button(
            "🚀 RUN  PIPELINE",
            type="primary",
            key="run_all_btn",
            help="Execute all pipeline stages in sequence",
        ):
            st.session_state.pipeline_running = True
            st.session_state.pipeline_cancelled = False
            st.session_state.pipeline_results = {}
            st.session_state.pipeline_stage_status = {}
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

st.divider()

if st.session_state.pipeline_running:
    start_time = time.time()
    all_stats = {}
    pipeline_failed = False

    save_feature_toggles(feature_settings)
    st.cache_data.clear()

    if telegram:
        telegram.notify_pipeline_started()

    stages = [
        {
            "name": "Discovery",
            "emoji": "🔍",
            "key": "discovery",
            "function": "run_discovery",
            "kwargs": {"max_queries": max_queries},
            "enabled": feature_settings["sources_enabled"]
            and any(feature_settings["source_states"].values()),
        },
        {
            "name": "Audit",
            "emoji": "📋",
            "key": "audit",
            "function": "run_audit",
            "kwargs": {"limit": audit_limit},
            "enabled": feature_settings["agents_enabled"]
            and any(feature_settings["agent_states"].values()),
        },
        {
            "name": "Email Generation",
            "emoji": "📧",
            "key": "email_generation",
            "function": "generate_emails",
            "kwargs": {"limit": email_limit},
            "enabled": feature_settings["email_gen_enabled"],
        },
        {
            "name": "Email Send",
            "emoji": "📤",
            "key": "email_send",
            "function": "send_emails",
            "kwargs": {"auto_approve": auto_approve},
            "enabled": True,
        },
    ]

    enabled_stages = [s for s in stages if s.get("enabled", True)]
    disabled_stages = [s for s in stages if not s.get("enabled", True)]

    if disabled_stages:
        st.info(
            f"⏭️ Skipping disabled stages: {', '.join([s['name'] for s in disabled_stages])}"
        )

    progress_bar = st.progress(0)
    status_text = st.empty()

    for stage in disabled_stages:
        st.session_state.pipeline_stage_status[stage["key"]] = "skipped"

    status_container = st.container()
    with status_container:
        st.markdown("### Pipeline Progress")
        stage_cols = st.columns(len(stages))
        for idx, (col, stage) in enumerate(zip(stage_cols, stages)):
            with col:
                status = st.session_state.pipeline_stage_status.get(
                    stage["key"], "pending"
                )
                if status == "pending":
                    st.markdown(f"⚪ {stage['emoji']} {stage['name']}", help="Waiting")
                elif status == "running":
                    st.markdown(f"🔄 {stage['emoji']} {stage['name']}", help="Running")
                elif status == "completed":
                    st.markdown(
                        f"✅ {stage['emoji']} {stage['name']}", help="Completed"
                    )
                elif status == "failed":
                    st.markdown(f"❌ {stage['emoji']} {stage['name']}", help="Failed")
                elif status == "skipped":
                    st.markdown(f"⏭️ {stage['emoji']} {stage['name']}", help="Skipped")

    for stage_idx, stage in enumerate(enabled_stages):
        if st.session_state.pipeline_cancelled:
            status_text.warning("⚠️ Pipeline cancelled by user")
            for remaining_stage in enabled_stages[stage_idx:]:
                st.session_state.pipeline_stage_status[remaining_stage["key"]] = (
                    "skipped"
                )
            break

        progress = int(((stage_idx) / len(enabled_stages)) * 100)
        progress_bar.progress(progress)
        status_text.info(f"{stage['emoji']} Running stage: {stage['name']}...")
        st.session_state.pipeline_stage_status[stage["key"]] = "running"

        st.rerun()

        try:
            stage_start = time.time()

            if stage["function"] == "run_discovery":

                def progress_callback(current, total, message):
                    status_text.info(f"🔍 {message} ({current}/{total})")

                result = app.run_discovery(
                    max_queries=stage["kwargs"]["max_queries"],
                    progress_callback=progress_callback,
                )
                all_stats[stage["key"]] = {
                    "leads_found": result.get("leads_found", 0),
                    "leads_saved": result.get("leads_saved", 0),
                    "queries_executed": result.get("queries_executed", 0),
                    "duration": f"{time.time() - stage_start:.1f}s",
                }

            elif stage["function"] == "run_audit":

                def progress_callback(current, total, message):
                    status_text.info(f"📋 {message} ({current}/{total})")

                result = app.run_audit(
                    limit=stage["kwargs"]["limit"],
                    progress_callback=progress_callback,
                )
                qualified = result.get("qualified", 0)
                audited = result.get("audited", 0)
                qual_rate = (qualified / audited * 100) if audited > 0 else 0

                all_stats[stage["key"]] = {
                    "audited": audited,
                    "qualified": qualified,
                    "qualification_rate": f"{qual_rate:.1f}%",
                    "duration": f"{time.time() - stage_start:.1f}s",
                }

            elif stage["function"] == "generate_emails":

                def progress_callback(current, total, message):
                    status_text.info(f"📧 {message} ({current}/{total})")

                result = app.generate_emails(
                    limit=stage["kwargs"]["limit"],
                    progress_callback=progress_callback,
                )
                all_stats[stage["key"]] = {
                    "generated": result.get("generated", 0),
                    "duration": f"{time.time() - stage_start:.1f}s",
                }

            elif stage["function"] == "send_emails":
                from core.repository import get_emails_for_review, update_email_content

                emails = get_emails_for_review()
                emails_to_send = [
                    e for e in emails if e.get("status") == "needs_review"
                ]

                if stage["kwargs"].get("auto_approve", False):
                    sent_count = 0
                    failed_count = 0
                    total = len(emails_to_send)

                    for email_idx, email in enumerate(emails_to_send):
                        if st.session_state.pipeline_cancelled:
                            break

                        status_text.info(f"📤 Sending email {email_idx + 1}/{total}...")
                        try:
                            update_email_content(
                                email.get("id"),
                                email.get("subject", ""),
                                email.get("body", ""),
                            )
                            success = app.send_email(
                                to_email=email.get("to_email")
                                or email.get("email", ""),
                                subject=email.get("subject", ""),
                                body=email.get("body", ""),
                                campaign_id=email.get("id"),
                                lead_id=email.get("lead_id"),
                            )
                            if success:
                                sent_count += 1
                            else:
                                failed_count += 1
                        except Exception as e:
                            logger.error(f"Failed to send email: {e}")
                            failed_count += 1

                    all_stats[stage["key"]] = {
                        "sent": sent_count,
                        "failed": failed_count,
                        "total_attempted": total,
                        "duration": f"{time.time() - stage_start:.1f}s",
                    }
                else:
                    all_stats[stage["key"]] = {
                        "pending_review": len(emails_to_send),
                        "auto_approve": "Disabled",
                        "duration": f"{time.time() - stage_start:.1f}s",
                    }

            st.session_state.pipeline_stage_status[stage["key"]] = "completed"
            st.session_state.pipeline_results[stage["key"]] = all_stats[stage["key"]]

            if telegram:
                telegram.notify_stage_completed(stage["name"], all_stats[stage["key"]])

        except Exception as e:
            error_msg = str(e)
            tb = traceback.format_exc()
            logger.error(f"Stage {stage['name']} failed: {error_msg}")

            st.session_state.pipeline_stage_status[stage["key"]] = "failed"
            all_stats[stage["key"]] = {
                "error": error_msg,
                "duration": f"{time.time() - stage_start:.1f}s",
            }

            if telegram:
                telegram.notify_error(stage["name"], error_msg, tb)

            if not continue_on_error:
                status_text.error(
                    f"❌ Pipeline stopped due to error in {stage['name']}"
                )
                pipeline_failed = True
                for remaining_stage in enabled_stages[stage_idx + 1 :]:
                    st.session_state.pipeline_stage_status[remaining_stage["key"]] = (
                        "skipped"
                    )
                break
            else:
                status_text.warning(
                    f"⚠️ {stage['name']} failed, continuing with next stage..."
                )
                if telegram:
                    telegram.notify_stage_failed(stage["name"], error_msg)

        st.rerun()

    total_duration = time.time() - start_time
    progress_bar.progress(100)
    st.session_state.pipeline_running = False

    if not st.session_state.pipeline_cancelled and not pipeline_failed:
        status_text.success("✅ Pipeline completed successfully!")

        all_stats["total_duration"] = f"{total_duration:.1f}s"

        if telegram:
            telegram.notify_pipeline_completed(all_stats)

        st.divider()
        st.subheader("📊 Pipeline Results Summary")

        col1, col2, col3, col4 = st.columns(4)

        discovery_stats: dict = all_stats.get("discovery", {})
        audit_stats: dict = all_stats.get("audit", {})
        email_gen_stats: dict = all_stats.get("email_generation", {})
        email_send_stats: dict = all_stats.get("email_send", {})

        col1.metric(
            "🔍 Leads Discovered",
            f"{discovery_stats.get('leads_found', 0):,}",
            f"{discovery_stats.get('leads_saved', 0)} saved",
        )
        col2.metric(
            "📋 Leads Audited",
            f"{audit_stats.get('audited', 0):,}",
            f"{audit_stats.get('qualified', 0)} qualified",
        )
        col3.metric(
            "📧 Emails Generated",
            f"{email_gen_stats.get('generated', 0):,}",
        )
        col4.metric(
            "📤 Emails Sent",
            f"{email_send_stats.get('sent', email_send_stats.get('pending_review', 0)):,}",
        )

        st.divider()

        with st.expander("📋 Detailed Stage Results", expanded=True):
            for stage_name, stage_key in [
                ("Discovery", "discovery"),
                ("Audit", "audit"),
                ("Email Generation", "email_generation"),
                ("Email Send", "email_send"),
            ]:
                if stage_key in all_stats:
                    stats = all_stats[stage_key]
                    with st.expander(f"✅ {stage_name}", expanded=True):
                        for key, value in stats.items():
                            st.metric(key.replace("_", " ").title(), value)

            st.metric("⏱️ Total Duration", f"{total_duration:.1f}s")

    elif st.session_state.pipeline_cancelled:
        status_text.warning("⚠️ Pipeline was cancelled by user")
    else:
        status_text.error("❌ Pipeline failed - check error messages above")

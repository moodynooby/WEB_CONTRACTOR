"""Discovery Page - Lead Discovery Pipeline."""

import streamlit as st
from database.repository import get_all_buckets
from discovery.engine import BucketGenerator
from infra.logging import get_logger
from ui.utils import get_app

logger = get_logger(__name__)

st.title("🔍 Lead Discovery")
st.caption("Generate search queries and scrape leads from configured buckets")

app = get_app()

if "discovery_running" not in st.session_state:
    st.session_state.discovery_running = False
if "discovery_result" not in st.session_state:
    st.session_state.discovery_result = None

if "bucket_gen_step" not in st.session_state:
    st.session_state.bucket_gen_step = 0  
if "bucket_gen_data" not in st.session_state:
    st.session_state.bucket_gen_data = {}
if "bucket_gen_result" not in st.session_state:
    st.session_state.bucket_gen_result = None
if "bucket_gen_error" not in st.session_state:
    st.session_state.bucket_gen_error = None

buckets = get_all_buckets()
bucket_names = [b["name"] for b in buckets]

def render_bucket_generator():
    """Render the multi-step bucket generation wizard."""
    
    if "bucket_generator" not in st.session_state:
        st.session_state.bucket_generator = BucketGenerator()
    
    generator = st.session_state.bucket_generator
    
    st.markdown("---")
    
    if st.session_state.bucket_gen_step > 0:
        current = st.session_state.bucket_gen_step
        
        st.markdown("**Progress:** " + " → ".join([
            f"**{i+1}**" if i+1 == current else str(i+1) for i in range(4)
        ]))
        st.markdown("---")
    
    if st.session_state.bucket_gen_step == 1:
        st.subheader("✨ Step 1: What type of business?")
        st.caption("Enter the business type you want to target (e.g., 'dentists', 'yoga studios', 'restaurants')")
        
        business_type = st.text_input(
            "Business Type",
            value=st.session_state.bucket_gen_data.get("business_type", ""),
            key="step1_business",
            placeholder="e.g., dentists, yoga studios, photographers",
        )
        
        st.markdown("**Common examples:**")
        examples_cols = st.columns(3)
        examples = [
            ["Dentists", "Yoga Studios", "Restaurants"],
            ["Photographers", "Marketing Agencies", "Web Developers"],
            ["Interior Designers", "Fitness Trainers", "Accountants"],
        ]
        
        for i, col in enumerate(examples_cols):
            for example in examples[i]:
                if col.button(example, key=f"example_{example}", use_container_width=True):
                    st.session_state.bucket_gen_data["business_type"] = example
                    st.session_state.bucket_gen_data.setdefault("settings", {})
                    st.session_state.bucket_gen_step = 2
                    st.rerun()
        
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("Next →", type="primary", use_container_width=True):
                if business_type.strip():
                    st.session_state.bucket_gen_data["business_type"] = business_type.strip()
                    st.session_state.bucket_gen_data.setdefault("settings", {})
                    st.session_state.bucket_gen_step = 2
                    st.rerun()
                else:
                    st.error("Please enter a business type")
        with col2:
            if st.button("Cancel", use_container_width=True):
                st.session_state.bucket_gen_step = 0
                st.session_state.bucket_gen_data = {}
                st.session_state.bucket_gen_result = None
                st.session_state.bucket_gen_error = None
                st.rerun()
    
    elif st.session_state.bucket_gen_step == 2:
        st.subheader("📍 Step 2: Where to search?")
        st.caption("Select target cities and regions for this bucket")
        
        geographic_segments = {
            "Tier-1 Metros": ["Mumbai", "Delhi", "Bangalore", "Chennai", "Kolkata", "Hyderabad", "Pune"],
            "Tier-2 Cities": ["Ahmedabad", "Jaipur", "Lucknow", "Indore", "Surat", "Nagpur", "Bhopal"],
            "Gujarat State": ["Ahmedabad", "Surat", "Vadodara", "Rajkot", "Gandhinagar"],
            "Business Districts": ["Bandra-Mumbai", "Connaught Place-Delhi", "MG Road-Bangalore", "Banjara Hills-Hyderabad"],
        }
        
        st.markdown("**Quick Select:**")
        quick_cols = st.columns(2)
        
        selected_locations = st.session_state.bucket_gen_data.get("locations", [])
        
        for i, (segment, cities) in enumerate(geographic_segments.items()):
            with quick_cols[i % 2]:
                if st.button(f"Add all {segment}", key=f"quick_{segment}", use_container_width=True):
                    new_locs = [c for c in cities if c not in selected_locations]
                    selected_locations.extend(new_locs)
                    st.session_state.bucket_gen_data["locations"] = selected_locations
                    st.rerun()
        
        st.markdown("---")
        
        all_cities = list(set([city for cities in geographic_segments.values() for city in cities]))
        all_cities.sort()
        
        selected_from_multiselect = st.multiselect(
            "Or select individual cities:",
            options=all_cities,
            default=selected_locations,
            help="Select one or more cities to target",
        )
        
        st.markdown("**Custom Locations:**")
        custom_locations = st.text_area(
            "Add custom locations (one per line):",
            value="\n".join([loc for loc in selected_locations if loc not in all_cities]),
            placeholder="e.g.,\nChandigarh\nGoa\nNoida",
            height=100,
        )
        
        final_locations = list(set(selected_from_multiselect))
        if custom_locations.strip():
            custom_list = [loc.strip() for loc in custom_locations.strip().split("\n") if loc.strip()]
            final_locations.extend(custom_list)
            final_locations = list(set(final_locations))
        
        st.session_state.bucket_gen_data["locations"] = final_locations
        
        st.markdown("---")
        st.expander("⚙️ Advanced Settings", expanded=False)
        with st.expander("⚙️ Advanced Settings"):
            col1, col2 = st.columns(2)
            with col1:
                max_queries = st.number_input(
                    "Max Queries per Run",
                    min_value=1,
                    max_value=100,
                    value=st.session_state.bucket_gen_data.get("settings", {}).get("max_queries", 10),
                    step=5,
                    key="step2_max_queries",
                )
            with col2:
                max_results = st.number_input(
                    "Max Results per Query",
                    min_value=1,
                    max_value=200,
                    value=st.session_state.bucket_gen_data.get("settings", {}).get("max_results", 50),
                    step=10,
                    key="step2_max_results",
                )
            
            st.session_state.bucket_gen_data["settings"] = {
                "max_queries": max_queries,
                "max_results": max_results,
            }
        
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("← Back", use_container_width=True):
                st.session_state.bucket_gen_step = 1
                st.rerun()
        with col2:
            if st.button("Generate with AI ✨", type="primary", use_container_width=True):
                if not final_locations:
                    st.error("Please select at least one location")
                else:
                    with st.spinner("🤖 AI is generating bucket configuration..."):
                        try:
                            config = generator.generate(
                                business_type=st.session_state.bucket_gen_data["business_type"],
                                target_locations=final_locations,
                                max_queries=max_queries,
                                max_results=max_results,
                            )
                            st.session_state.bucket_gen_result = config
                            st.session_state.bucket_gen_error = None
                            st.session_state.bucket_gen_step = 3
                            st.rerun()
                        except Exception as e:
                            st.session_state.bucket_gen_error = str(e)
                            logger.error(f"Bucket generation error: {e}")
                            st.rerun()
    
    elif st.session_state.bucket_gen_step == 3:
        if st.session_state.bucket_gen_result:
            st.subheader("📝 Step 3: Review & Edit Generated Bucket")
            st.caption("The AI has generated a bucket configuration. You can edit any field before saving.")
            
            config = st.session_state.bucket_gen_result
            
            with st.form("bucket_review_form"):
                col1, col2 = st.columns(2)
                
                with col1:
                    new_name = st.text_input(
                        "Bucket Name",
                        value=config.get("name", ""),
                        help="Unique identifier for this bucket",
                    )
                    
                    categories_str = st.text_area(
                        "Categories (one per line)",
                        value="\n".join(config.get("categories", [])),
                        height=120,
                        help="Business categories to search for",
                    )
                    
                    priority = st.number_input(
                        "Priority (1-5)",
                        min_value=1,
                        max_value=5,
                        value=config.get("priority", 3),
                        help="Higher priority buckets are processed first",
                    )
                    
                    monthly_target = st.number_input(
                        "Monthly Lead Target",
                        min_value=10,
                        max_value=10000,
                        value=config.get("monthly_target", 100),
                        step=50,
                    )
                
                with col2:
                    search_patterns_str = st.text_area(
                        "Search Patterns (one per line)",
                        value="\n".join(config.get("search_patterns", [])),
                        height=150,
                        help="Search queries that will be used for discovery",
                    )
                    
                    locations_str = st.text_area(
                        "Geographic Segments (one per line)",
                        value="\n".join(config.get("geographic_segments", [])),
                        height=150,
                        help="Target locations for searches",
                    )
                    
                    col2a, col2b = st.columns(2)
                    with col2a:
                        max_queries_edit = st.number_input(
                            "Max Queries",
                            min_value=1,
                            max_value=100,
                            value=config.get("max_queries", 10),
                            step=5,
                        )
                    with col2b:
                        max_results_edit = st.number_input(
                            "Max Results",
                            min_value=1,
                            max_value=200,
                            value=config.get("max_results", 50),
                            step=10,
                        )
                    
                    daily_email_limit = st.number_input(
                        "Daily Email Limit",
                        min_value=10,
                        max_value=1000,
                        value=config.get("daily_email_limit", 50),
                        step=10,
                    )
                
                edited_categories = [c.strip() for c in categories_str.strip().split("\n") if c.strip()]
                edited_search_patterns = [p.strip() for p in search_patterns_str.strip().split("\n") if p.strip()]
                edited_locations = [loc.strip() for loc in locations_str.strip().split("\n") if loc.strip()]
                
                updated_config = config.copy()
                updated_config["name"] = new_name
                updated_config["categories"] = edited_categories
                updated_config["search_patterns"] = edited_search_patterns
                updated_config["geographic_segments"] = edited_locations
                updated_config["priority"] = priority
                updated_config["monthly_target"] = monthly_target
                updated_config["max_queries"] = max_queries_edit
                updated_config["max_results"] = max_results_edit
                updated_config["daily_email_limit"] = daily_email_limit
                
                st.session_state.bucket_gen_result = updated_config
                
                col_btn1, col_btn2 = st.columns([1, 2])
                
                with col_btn1:
                    save_clicked = st.form_submit_button("💾 Save Bucket", type="primary")
                    if save_clicked:
                        is_valid, errors = generator.validate_config(updated_config)
                        
                        if not is_valid:
                            st.error("Please fix the following errors:")
                            for error in errors:
                                st.error(f"• {error}")
                        else:
                            success, message = generator.save_config(updated_config)
                            
                            if success:
                                st.success(f"✅ {message}")
                                st.session_state.bucket_gen_step = 4
                                st.rerun()
                            else:
                                st.error(f"❌ {message}")
                
                with col_btn2:
                    regenerate_clicked = st.form_submit_button("🔄 Regenerate")
                    if regenerate_clicked:
                        with st.spinner("Regenerating..."):
                            try:
                                new_config = generator.generate(
                                    business_type=st.session_state.bucket_gen_data["business_type"],
                                    target_locations=st.session_state.bucket_gen_data["locations"],
                                    max_queries=st.session_state.bucket_gen_data.get("settings", {}).get("max_queries", 10),
                                    max_results=st.session_state.bucket_gen_data.get("settings", {}).get("max_results", 50),
                                )
                                st.session_state.bucket_gen_result = new_config
                                st.rerun()
                            except Exception as e:
                                st.session_state.bucket_gen_error = str(e)
                                st.rerun()
            
            if st.button("← Back", key="back_from_review"):
                st.session_state.bucket_gen_step = 2
                st.rerun()
    
    elif st.session_state.bucket_gen_step == 4:
        st.success("🎉 Bucket created successfully!")
        st.balloons()
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✨ Create Another Bucket"):
                st.session_state.bucket_gen_step = 1
                st.session_state.bucket_gen_data = {}
                st.session_state.bucket_gen_result = None
                st.rerun()
        with col2:
            if st.button("Close"):
                st.session_state.bucket_gen_step = 0
                st.session_state.bucket_gen_data = {}
                st.session_state.bucket_gen_result = None
                st.session_state.bucket_gen_error = None
                st.rerun()
    
    if st.session_state.bucket_gen_error:
        st.error(f"❌ {st.session_state.bucket_gen_error}")
        if st.button("Clear Error"):
            st.session_state.bucket_gen_error = None
            st.rerun()


buckets = get_all_buckets()
bucket_names = [b["name"] for b in buckets]

if st.button("✨ Generate New Bucket", type="secondary", use_container_width=True):
    if st.session_state.bucket_gen_step == 0:
        st.session_state.bucket_gen_step = 1
        st.rerun()

if st.session_state.bucket_gen_step > 0:
    with st.container(border=True):
        render_bucket_generator()

st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    selected_bucket = st.selectbox(
        "Select Bucket",
        ["All Buckets"] + bucket_names,
    )
    bucket_name = None if selected_bucket == "All Buckets" else selected_bucket

with col2:
    max_queries = st.number_input(
        "Max Queries",
        min_value=1,
        max_value=100,
        value=20,
        step=5,
    )

if st.session_state.discovery_running:
    st.warning("⏳ Discovery already in progress...")
    if st.button("Cancel", type="secondary"):
        st.session_state.discovery_running = False
        st.rerun()
elif st.button(
    "🚀 Run Discovery", type="primary", disabled=st.session_state.discovery_running
):
    st.session_state.discovery_running = True
    st.session_state.discovery_result = None

    with st.status("Running discovery...", expanded=True) as status:

        def progress_callback(current: int, total: int, message: str):
            status.update(label=f"Processing query {current}/{total}")

        try:
            result = app.scraper.run(
                bucket_name=bucket_name,
                max_queries=max_queries,
                progress_callback=progress_callback,
            )
            st.session_state.discovery_result = result
            status.update(
                label="✅ Discovery complete!",
                state="complete",
                expanded=False,
            )
        except Exception as e:
            st.session_state.discovery_result = {"error": str(e)}
            status.update(
                label=f"❌ Discovery failed: {e}",
                state="error",
                expanded=True,
            )
            logger.error(f"Discovery error: {e}")

    st.session_state.discovery_running = False

    if (
        st.session_state.discovery_result
        and "error" not in st.session_state.discovery_result
    ):
        result = st.session_state.discovery_result
        st.success(
            f"**{result['leads_saved']}** new leads saved "
            f"(from {result['leads_found']} found)"
        )
        col1, col2, col3 = st.columns(3)
        col1.metric("Queries Executed", result["queries_executed"])
        col2.metric("Leads Found", result["leads_found"])
        col3.metric("Leads Saved", result["leads_saved"])
    elif (
        st.session_state.discovery_result
        and "error" in st.session_state.discovery_result
    ):
        st.error(f"Discovery failed: {st.session_state.discovery_result['error']}")

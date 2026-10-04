import os
import json
import uuid
import streamlit as st
from utils.filesystem import WorkspaceManager
from crew.flow import VideoProductionFlow
from tools.ffmpeg_tool import FFmpegTool
from utils.gemini_client import GeminiReasoningClient

from datetime import datetime, timezone

def render_ai_quota_status_card():
    """Calculates hours until midnight UTC and displays status badges."""
    now_utc = datetime.now(timezone.utc)
    # Calculate midnight UTC tomorrow
    midnight_utc = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
    from datetime import timedelta
    next_reset = midnight_utc + timedelta(days=1)
    diff = next_reset - now_utc
    hours_left = diff.seconds // 3600
    mins_left = (diff.seconds % 3600) // 60

    st.sidebar.markdown("---")
    st.sidebar.subheader("⚡ AI Quota & Engine Status")

    # Cloudflare Quota info
    st.sidebar.markdown(f"""
    **Cloudflare Free Tier:** 10,000 Neurons/day  
    ⏳ **Reset countdown:** in **{hours_left}h {mins_left}m** *(00:00 UTC)*
    """)

    # Model selector to save neurons
    image_model_choice = st.sidebar.selectbox(
        "Visual AI Model",
        [
            "FLUX.1 Schnell (Highest Quality, ~8k neurons/img)",
            "SDXL-Lightning (Fast, ~600 neurons/img — 15+ imgs/day)"
        ],
        index=0,
        help="Switch to SDXL-Lightning if you want to generate more videos without running out of free neurons."
    )

    st.sidebar.caption("🛡️ **Active Fallback:** When quotas are full, Dynamic Context Search automatically finds topic-matching HD imagery so production never fails.")

# 1. Quota Alert Banner at the top of results
if any(getattr(s, "quota_exhausted", False) for s in (st.session_state.flow_state.plan.scenes if "flow_state" in st.session_state and st.session_state.flow_state and st.session_state.flow_state.plan else [])):
    now_utc = datetime.now(timezone.utc)
    hours_left = (86400 - (now_utc.hour * 3600 + now_utc.minute * 60 + now_utc.second)) // 3600
    st.warning(
        f"⚠️ **Cloudflare 10,000 Daily Neurons Limit Reached:** Visuals for this video were sourced via "
        f"**Dynamic Context Search** to match your script. Cloudflare free neurons will automatically refresh in approx **{hours_left} hours** *(at 00:00 UTC)*."
    )

# 2. Add Badges under each Scene in the Scene Breakdown
# (Inside your scene display loop in app.py):
for idx, scene in enumerate(scenes):
    col_img, col_txt = st.columns([1, 2])
    with col_img:
        if scene.visual_path and os.path.exists(scene.visual_path):
            st.image(scene.visual_path, width="stretch")
        
        # Display which engine created this visual
        v_source = getattr(scene, "visual_source", "Cloudflare FLUX")
        st.caption(f"🎨 **Visual:** `{v_source}`")
        
        # Display audio source
        a_source = "Gemini TTS (Kore)" if "gemini" in str(getattr(scene, "audio_path", "")).lower() else "Studio Narration"
        st.caption(f"🎙️ **Audio:** `{a_source}`")

    with col_txt:
        st.markdown(f"**Scene {scene.id}** ({scene.duration:.1f}s)")
        st.write(scene.narration)
        st.caption(f"**Visual Prompt:** {scene.visual_prompt}")



# Streamlit Page Setup
st.set_page_config(
    page_title="AI Video Production Agent",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #6366F1, #A855F7, #EC4899);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #94A3B8;
        margin-bottom: 1.5rem;
    }
    .agent-card {
        background-color: #1E293B;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 8px;
        border-left: 4px solid #6366F1;
    }
    .stButton>button {
        background: linear-gradient(90deg, #6366F1, #8B5CF6);
        color: white;
        font-weight: 600;
        border: none;
        border-radius: 8px;
        padding: 0.6rem 1.4rem;
        transition: all 0.2s ease-in-out;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
    }
</style>
""", unsafe_allow_html=True)

# Load secrets into environment safely if running inside Streamlit
if "CLOUDFLARE_ACCOUNT_ID" in st.secrets:
    os.environ["CLOUDFLARE_ACCOUNT_ID"] = st.secrets["CLOUDFLARE_ACCOUNT_ID"]
if "CLOUDFLARE_API_TOKEN" in st.secrets:
    os.environ["CLOUDFLARE_API_TOKEN"] = st.secrets["CLOUDFLARE_API_TOKEN"]
if "GEMINI_API_KEY" in st.secrets:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]
if "YOUTUBE_CLIENT_ID" in st.secrets:
    os.environ["YOUTUBE_CLIENT_ID"] = st.secrets["YOUTUBE_CLIENT_ID"]
if "YOUTUBE_CLIENT_SECRET" in st.secrets:
    os.environ["YOUTUBE_CLIENT_SECRET"] = st.secrets["YOUTUBE_CLIENT_SECRET"]
if "YOUTUBE_REFRESH_TOKEN" in st.secrets:
    os.environ["YOUTUBE_REFRESH_TOKEN"] = st.secrets["YOUTUBE_REFRESH_TOKEN"]

# Session State Initialization
if "project_id" not in st.session_state:
    st.session_state.project_id = str(uuid.uuid4())
if "flow_state" not in st.session_state:
    st.session_state.flow_state = None
if "logs" not in st.session_state:
    st.session_state.logs = []
if "v2_result" not in st.session_state:
    st.session_state.v2_result = None

# Sidebar Diagnostics
with st.sidebar:
    st.image("https://images.unsplash.com/photo-1574717024653-61fd2cf4d44d?auto=format&fit=crop&w=600&q=80", use_container_width=True)
    st.markdown("### 🛠️ System Diagnostics")
    
    # Check FFmpeg
    ffmpeg_tool = FFmpegTool()
    ff_ok, ff_info = ffmpeg_tool.check_availability()
    if ff_ok:
        st.success("✓ FFmpeg 4.4+ Ready")
    else:
        st.error("✗ FFmpeg Not Found")

    # Check Cloudflare
    cf_token = os.environ.get("CLOUDFLARE_API_TOKEN")
    cf_acc = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if cf_token and cf_acc:
        st.success("✓ Cloudflare FLUX Configured")
    else:
        st.warning("⚠️ Cloudflare credentials missing")

    # Check Gemini
    gem_key = os.environ.get("GEMINI_API_KEY")
    if gem_key:
        st.success("✓ Gemini TTS & Reasoning Configured")
    else:
        st.error("✗ GEMINI_API_KEY missing")

    # YouTube V2 Status
    yt_conf = bool(os.environ.get("YOUTUBE_CLIENT_ID") and os.environ.get("YOUTUBE_REFRESH_TOKEN"))
    if yt_conf:
        st.info("✓ YouTube V2 OAuth Configured")
    else:
        st.caption("ℹ️ YouTube V2: OAuth credentials not set (V1 MP4 production operates fully without credentials)")

    st.markdown("---")
    st.markdown("### 🤖 8 Production Agents")
    st.caption("1. **Director**: Screenplay & Scene Decomposition\n2. **Visual**: Cloudflare FLUX-1-Schnell\n3. **Voice**: Google Gemini 3.8 Flash-Lite TTS\n4. **Music/SFX**: Licensed Library & Ducking\n5. **Editor**: Deterministic FFmpeg Assembly\n6. **QA**: Forensic stream QC & ffprobe\n7. **Thumbnail**: High-CTR Art & Packaging\n8. **YouTube**: V2 OAuth2 Distribution")

# Main Header
st.markdown('<div class="main-header">AI VIDEO PRODUCTION STUDIO</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Autonomous multi-agent video studio: transforms raw text into broadcast-grade narrated documentaries with Ken Burns motion, ducked music, and subtitles.</div>', unsafe_allow_html=True)

# Sample Scripts
SAMPLE_SCRIPTS = {
    "The Soul Sanctuary (Peace & Contemplation)": "The heart can become heavy not from weakness, but from carrying what was meant to be surrendered. In quiet moments of contemplation, return to the breath and find peace. True healing begins when we soften our grip and trust the path before us.",
    "Deep Sea Bioluminescence": "Miles beneath the ocean surface lies an alien world where sunlight has never touched. In this perpetual abyss, creatures illuminate the dark with living fire—chemical lights called bioluminescence. Some flash to attract prey, others to blind predators in the ink-black depths. Life here thrives under pressures that would crush steel submarines.",
    "The Origin of Black Holes": "When a star twenty times more massive than our sun runs out of nuclear fuel, its core collapses under gravity in a fraction of a second. The resulting supernova tears the outer layers apart, leaving behind a gravitational singularity so dense that not even light can escape its event horizon. Here, physics as we understand it simply breaks down.",
    "Ancient Lost Cities": "Deep within the dense Amazon rainforest, modern LiDAR scans have pierced through centuries of dense canopy to reveal vast networks of forgotten civilization. Pyramids, canals, and ancient causeways tell the story of millions who lived here thousands of years before Columbus. History is being rewritten one laser pulse at a time."
}

col_sample, col_clear = st.columns([4, 1])
with col_sample:
    selected_sample = st.selectbox("Load sample script:", ["(Custom Script)"] + list(SAMPLE_SCRIPTS.keys()))
with col_clear:
    if st.button("New Project"):
        st.session_state.project_id = str(uuid.uuid4())
        st.session_state.flow_state = None
        st.session_state.logs = []
        st.session_state.v2_result = None
        st.rerun()

initial_text = SAMPLE_SCRIPTS[selected_sample] if selected_sample != "(Custom Script)" else ""

# Input Form
script_input = st.text_area(
    "Paste your script:",
    value=initial_text,
    height=160,
    placeholder="Enter the screenplay or script narration here..."
)

col1, col2, col3, col4 = st.columns(4)

with col1:
    style_option = st.selectbox(
        "Video style:",
        [
            "The Soul Sanctuary (Peaceful & Spiritual)",
            "Cinematic Documentary",
            "Warm Nature & Landscapes",
            "Deep Space Odyssey",
            "Historical Mystery",
            "Minimalist Ambient"
        ]
    )

with col2:
    voice_option = st.selectbox(
        "Narrator Voice (Gemini TTS):",
        ["Kore (Warm/Documentary)", "Puck (Engaging/Expressive)", "Fenrir (Authoritative/Deep)", "Aoede (Poetic/Reflective)"]
    )
    voice_name = voice_option.split()[0]

with col3:
    aspect_option = st.selectbox(
        "Aspect ratio:",
        ["16:9 (Landscape YouTube)", "9:16 (Shorts/Reels)"]
    )
    aspect_ratio = "16:9" if "16:9" in aspect_option else "9:16"

with col4:
    res_option = st.selectbox(
        "Output resolution:",
        ["1080p (Full HD)", "720p (HD)"]
    )
    resolution = "1080p" if "1080p" in res_option else "720p"

# Create Video Action Button
start_production = st.button("🚀 CREATE VIDEO", use_container_width=True)

if start_production:
    if not script_input.strip():
        st.error("Please enter a script before starting production.")
    else:
        st.session_state.logs = []
        progress_bar = st.progress(0.0)
        status_box = st.empty()

        def on_progress(stage: str, msg: str, pct: float):
            progress_bar.progress(min(1.0, max(0.0, pct)))
            status_box.markdown(f"**Stage [{stage}]**: {msg}")
            st.session_state.logs.append(f"[{stage}] {msg}")

        flow = VideoProductionFlow(st.session_state.project_id, progress_callback=on_progress)
        
        with st.spinner("AI agents collaborating on your video..."):
            flow_state = flow.run_v1_pipeline(
                script=script_input,
                style=style_option,
                voice_name=voice_name,
                aspect_ratio=aspect_ratio,
                resolution=resolution
            )
            st.session_state.flow_state = flow_state
            st.rerun()

# Display Production Results
state = st.session_state.flow_state
if state:
    if state.is_completed and state.video_path and os.path.exists(state.video_path):
        st.markdown("---")
        st.success("🎉 **VIDEO PRODUCTION READY** — Broadcast Assets Built Successfully!")

        # Script Normalization & Editorial Review
        if state.normalized_script:
            with st.expander("📝 Script Normalization & Verification", expanded=False):
                st.markdown("**Original Input:**")
                st.caption(state.original_script)
                st.markdown("**Normalized Production Script:**")
                st.write(state.normalized_script)
                if state.warnings:
                    for w in state.warnings:
                        st.warning(f"⚠️ {w}")

        col_vid, col_meta = st.columns([3, 2])

        with col_vid:
            st.markdown("### 🎬 Final Rendered MP4")
            with open(state.video_path, "rb") as vf:
                video_bytes = vf.read()
                st.video(video_bytes)

            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                st.download_button(
                    "⬇️ Download MP4",
                    data=video_bytes,
                    file_name=f"video_{state.project_id[:8]}.mp4",
                    mime="video/mp4",
                    use_container_width=True
                )
            with col_d2:
                if state.thumbnail_path and os.path.exists(state.thumbnail_path):
                    with open(state.thumbnail_path, "rb") as tf:
                        st.download_button(
                            "⬇️ Thumbnail JPG",
                            data=tf.read(),
                            file_name=f"thumbnail_{state.project_id[:8]}.jpg",
                            mime="image/jpeg",
                            use_container_width=True
                        )
            with col_d3:
                wm = WorkspaceManager(state.project_id)
                manifest_data = wm.load_manifest()
                if manifest_data:
                    st.download_button(
                        "⬇️ Manifest JSON",
                        data=json.dumps(manifest_data, indent=2),
                        file_name=f"manifest_{state.project_id[:8]}.json",
                        mime="application/json",
                        use_container_width=True
                    )

        with col_meta:
            if state.thumbnail_path and os.path.exists(state.thumbnail_path):
                st.markdown("### 🖼️ YouTube Thumbnail")
                st.image(state.thumbnail_path, use_container_width=True)

            if state.packaging and state.packaging.metadata:
                st.markdown("### 🏷️ YouTube Packaging")
                st.text_input("Title:", value=state.packaging.metadata.title, disabled=True)
                st.text_area("Description:", value=state.packaging.metadata.description, height=120, disabled=True)
                st.caption(f"**Tags:** {', '.join(state.packaging.metadata.tags[:8])}")

        # Authoritative Timeline & Scene Breakdown
        if state.plan and state.plan.scenes:
            with st.expander(f"⏱️ Authoritative Timeline & Scene Plan ({len(state.plan.scenes)} Scenes, {state.plan.total_duration:.1f}s)", expanded=False):
                timeline_rows = []
                for s in state.plan.scenes:
                    dur = s.audio_duration or s.duration
                    timeline_rows.append({
                        "Scene": s.id,
                        "Start": f"{s.start_time:.2f}s",
                        "End": f"{s.end_time:.2f}s",
                        "Duration": f"{dur:.2f}s",
                        "Motion": s.camera_motion.value if hasattr(s.camera_motion, "value") else str(s.camera_motion),
                        "Transition": s.transition.value if hasattr(s.transition, "value") else str(s.transition),
                        "Status": s.status.value if hasattr(s.status, "value") else str(s.status)
                    })
                st.table(timeline_rows)

                for s in state.plan.scenes:
                    sc1, sc2, sc3 = st.columns([1, 2, 1])
                    with sc1:
                        if s.visual_path and os.path.exists(s.visual_path):
                            st.image(s.visual_path, caption=f"Scene {s.id}")
                    with sc2:
                        st.markdown(f"**Scene {s.id}** ({s.start_time:.1f}s - {s.end_time:.1f}s)")
                        st.write(f"_{s.narration}_")
                        st.caption(f"**Visual Prompt:** {s.visual_prompt[:120]}...")
                    with sc3:
                        if s.audio_path and os.path.exists(s.audio_path):
                            with open(s.audio_path, "rb") as af:
                                st.audio(af.read(), format="audio/wav")

        # QA Report Accordion
        if state.qa_result:
            with st.expander("🔍 QA Forensic Audit Report", expanded=False):
                qa = state.qa_result
                st.metric("QA Score", f"{qa.score}%", delta=qa.status.value)
                for check in qa.checks:
                    icon = "✅" if check.passed else ("❌" if check.is_fatal else "⚠️")
                    st.write(f"{icon} **[{check.category.upper()}] {check.check_name}**: {check.details}")

        # VERSION 2: YouTube Publisher
        st.markdown("---")
        st.markdown("### 🚀 Version 2: YouTube Distribution")
        st.caption("Publish the finalized MP4, custom thumbnail, and SEO metadata directly to your YouTube channel using official OAuth 2.0.")

        c_priv, c_pub = st.columns([2, 3])
        with c_priv:
            privacy_choice = st.selectbox(
                "Release Privacy:",
                ["private (Recommended for review)", "unlisted", "public"]
            )
            privacy_val = privacy_choice.split()[0]
        with c_pub:
            st.markdown("<br>", unsafe_allow_html=True)
            publish_btn = st.button("📤 UPLOAD TO YOUTUBE", use_container_width=True)

        if publish_btn:
            with st.spinner("Contacting YouTube Data API v3..."):
                flow = VideoProductionFlow(state.project_id)
                yt_res = flow.run_v2_publish(privacy_status=privacy_val)
                st.session_state.v2_result = yt_res

        if st.session_state.v2_result:
            res = st.session_state.v2_result
            if res.get("success"):
                st.success(f"✅ {res.get('message')}")
                st.markdown(f"**YouTube URL:** [{res.get('url')}]({res.get('url')})")
                st.caption(f"Video ID: `{res.get('video_id')}` | Privacy: `{res.get('privacy_status')}`")
            elif res.get("status") == "not_authenticated":
                st.warning(f"⚠️ **Authentication Required:** {res.get('message')}")
            else:
                st.error(f"Upload failed: {res.get('message')}")

    elif state.stage == "failed":
        st.error(f"Production halted at stage: **{state.stage}**")
        for err in state.errors:
            st.code(err, language="text")

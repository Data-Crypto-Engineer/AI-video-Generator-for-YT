# AI Video Production Studio (CrewAI Multi-Agent Pipeline)

A broadcast-grade autonomous video production system orchestrated by **8 specialized agents** using **CrewAI**, **Python 3.12**, **Streamlit**, and **FFmpeg**.

The user supplies only a raw script. The system automatically turns that script into a fully narrated, edited, scored, and captioned YouTube-ready video.

---

## 🎬 Architecture & The 8 Specialized Agents

The application cleanly separates **agentic decision-making** from **deterministic multimedia processing**:
- **AI Agents**: Decide *WHAT* should happen (scene pacing, cinematography, voice tone, music theme, thumbnail visual hook, QA reasoning).
- **Python + FFmpeg**: Deterministically execute *HOW* it happens (HTTP requests, media validation, pan/zoom motion, audio mixing, subtitle burn-in, MP4 rendering).
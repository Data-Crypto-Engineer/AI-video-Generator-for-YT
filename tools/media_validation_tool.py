import os
from typing import Dict, Any, List, Optional
from models.qa import QAResult, QAStatus, QACheckItem
from models.production import ProductionPlan
from utils.validation import validate_video_file, validate_wav_audio, validate_file_exists_and_non_empty, get_audio_duration, probe_media_file
from utils.logging import get_logger

logger = get_logger("media_validation_tool")

class MediaValidationTool:
    """
    Forensic QA verification tool for inspecting production manifests, media streams,
    authoritative timelines, aspect ratios, and broadcast criteria.
    """
    def inspect_production(
        self,
        production_plan: ProductionPlan,
        video_path: str,
        thumbnail_path: Optional[str] = None,
        subtitles_path: Optional[str] = None
    ) -> QAResult:
        checks: List[QACheckItem] = []
        errors: List[str] = []
        warnings: List[str] = []

        cfg = production_plan.project
        req_aspect = cfg.aspect_ratio or "16:9"
        req_res = cfg.resolution or "1080p"
        is_portrait = "9:16" in req_aspect or req_aspect == "portrait"

        if req_res == "1080p":
            expected_w, expected_h = (1080, 1920) if is_portrait else (1920, 1080)
        else: # 720p
            expected_w, expected_h = (720, 1280) if is_portrait else (1280, 720)

        # -------------------------------------------------------------
        # 1. SCRIPT CHECKS
        # -------------------------------------------------------------
        norm_script = production_plan.normalized_script or production_plan.original_script
        has_script = bool(norm_script and norm_script.strip())
        checks.append(QACheckItem(
            category="script",
            check_name="normalized_script_present",
            passed=has_script,
            details="Normalized script verified and stored" if has_script else "Script is empty",
            is_fatal=True
        ))
        if not has_script:
            errors.append("Normalized script is missing or empty")

        scenes = production_plan.scenes or []
        checks.append(QACheckItem(
            category="script",
            check_name="scenes_not_empty",
            passed=len(scenes) > 0,
            details=f"Production plan contains {len(scenes)} scenes" if scenes else "No scenes in plan",
            is_fatal=True
        ))
        if not scenes:
            errors.append("Production plan contains 0 scenes")

        # Check continuous 1-based indexing
        ids_continuous = all(s.id == (idx + 1) for idx, s in enumerate(scenes))
        checks.append(QACheckItem(
            category="script",
            check_name="scene_ids_continuous",
            passed=ids_continuous,
            details="Scene IDs continuous from 1 to N" if ids_continuous else "Scene IDs are discontinuous",
            is_fatal=True
        ))
        if not ids_continuous:
            errors.append("Scene IDs are discontinuous or not 1-indexed")

        # Narration text non-empty
        empty_narr = [s.id for s in scenes if not s.narration or not s.narration.strip()]
        checks.append(QACheckItem(
            category="script",
            check_name="narration_non_empty",
            passed=len(empty_narr) == 0,
            details="All scenes have non-empty narration" if not empty_narr else f"Scenes with empty narration: {empty_narr}",
            is_fatal=True
        ))
        if empty_narr:
            errors.append(f"Scenes {empty_narr} have empty narration text")

        # -------------------------------------------------------------
        # 2. SCENE TIMELINE CHECKS
        # -------------------------------------------------------------
        all_durations_positive = True
        total_audio_duration = 0.0
        timeline_continuous = True
        prev_end = 0.0

        for idx, s in enumerate(scenes):
            dur = s.audio_duration or s.duration or 0.0
            if dur <= 0.05:
                all_durations_positive = False
            total_audio_duration += dur

            if idx > 0 and abs(s.start_time - prev_end) > 0.3:
                timeline_continuous = False
            prev_end = s.end_time or (s.start_time + dur)

        checks.append(QACheckItem(
            category="timeline",
            check_name="scene_durations_positive",
            passed=all_durations_positive,
            details=f"All {len(scenes)} scenes have positive measured audio durations" if all_durations_positive else "One or more scenes have non-positive duration",
            is_fatal=True
        ))
        if not all_durations_positive:
            errors.append("One or more scenes have invalid audio duration (<= 0.05s)")

        checks.append(QACheckItem(
            category="timeline",
            check_name="timeline_continuity",
            passed=timeline_continuous,
            details="Scene start and end times form a continuous timeline without gaps" if timeline_continuous else "Timeline has accidental gaps or overlaps between scenes",
            is_fatal=False
        ))
        if not timeline_continuous:
            warnings.append("Scene start/end times have slight discontinuity")

        # -------------------------------------------------------------
        # 3. VISUAL ASSET CHECKS
        # -------------------------------------------------------------
        all_visuals_exist = True
        for s in scenes:
            if not s.visual_path or not validate_file_exists_and_non_empty(s.visual_path, min_bytes=1000):
                all_visuals_exist = False
                errors.append(f"Scene {s.id:02d} visual file is missing or corrupted: {s.visual_path}")

        checks.append(QACheckItem(
            category="visuals",
            check_name="all_scene_images_valid",
            passed=all_visuals_exist,
            details="All scene visuals verified and non-empty (>1000 bytes)" if all_visuals_exist else "One or more scene visuals missing",
            is_fatal=True
        ))

        # -------------------------------------------------------------
        # 4. AUDIO INTEGRITY & DUCKING CHECKS
        # -------------------------------------------------------------
        all_audio_exist = True
        for s in scenes:
            if not s.audio_path:
                all_audio_exist = False
                errors.append(f"Scene {s.id:02d} audio path not set")
                continue
            valid, msg = validate_wav_audio(s.audio_path)
            if not valid:
                all_audio_exist = False
                errors.append(f"Scene {s.id:02d} audio invalid: {msg}")

        checks.append(QACheckItem(
            category="audio",
            check_name="all_scene_narration_valid",
            passed=all_audio_exist,
            details=f"Narration files verified (total duration: {total_audio_duration:.2f}s)" if all_audio_exist else "Narration files missing or corrupt",
            is_fatal=True
        ))

        # -------------------------------------------------------------
        # 5. SUBTITLE CHECKS
        # -------------------------------------------------------------
        if subtitles_path and validate_file_exists_and_non_empty(subtitles_path, min_bytes=10):
            checks.append(QACheckItem(
                category="subtitles",
                check_name="srt_file_valid",
                passed=True,
                details=f"SRT subtitles file present and non-empty ({subtitles_path})",
                is_fatal=False
            ))
        else:
            warnings.append("Subtitles file not generated or missing")
            checks.append(QACheckItem(
                category="subtitles",
                check_name="srt_file_valid",
                passed=False,
                details="Subtitles file missing",
                is_fatal=False
            ))

        # -------------------------------------------------------------
        # 6. THUMBNAIL CHECKS
        # -------------------------------------------------------------
        if thumbnail_path and validate_file_exists_and_non_empty(thumbnail_path, min_bytes=1000):
            checks.append(QACheckItem(
                category="packaging",
                check_name="thumbnail_valid",
                passed=True,
                details=f"Thumbnail generated and verified: {thumbnail_path}",
                is_fatal=False
            ))
        else:
            warnings.append("Thumbnail image missing or empty")
            checks.append(QACheckItem(
                category="packaging",
                check_name="thumbnail_valid",
                passed=False,
                details="Thumbnail missing",
                is_fatal=False
            ))

        # -------------------------------------------------------------
        # 7. FINAL VIDEO MP4 & STREAM FORENSICS
        # -------------------------------------------------------------
        is_video_valid, video_msg, metrics = validate_video_file(video_path)
        checks.append(QACheckItem(
            category="video",
            check_name="mp4_stream_integrity",
            passed=is_video_valid,
            details=video_msg,
            is_fatal=True
        ))
        if not is_video_valid:
            errors.append(f"Final MP4 validation failed: {video_msg}")

        # Check resolution & aspect ratio
        actual_w = metrics.get("width", 0)
        actual_h = metrics.get("height", 0)
        res_matches = (actual_w == expected_w and actual_h == expected_h)
        checks.append(QACheckItem(
            category="video",
            check_name="resolution_matches_request",
            passed=res_matches,
            details=f"Actual resolution ({actual_w}x{actual_h}) matches requested ({expected_w}x{expected_h})" if res_matches else f"Resolution mismatch: expected {expected_w}x{expected_h}, got {actual_w}x{actual_h}",
            is_fatal=True
        ))
        if not res_matches:
            errors.append(f"MP4 resolution mismatch: requested {expected_w}x{expected_h}, rendered {actual_w}x{actual_h}")

        # Check video codec
        v_codec = metrics.get("video_codec", "").lower()
        v_codec_ok = "h264" in v_codec or "avc" in v_codec
        checks.append(QACheckItem(
            category="video",
            check_name="video_codec_h264",
            passed=v_codec_ok,
            details=f"Video codec verified: {v_codec}" if v_codec_ok else f"Invalid video codec: {v_codec}",
            is_fatal=True
        ))
        if not v_codec_ok:
            errors.append(f"Video codec is not H.264: {v_codec}")

        # Check audio stream presence in video
        a_codec = metrics.get("audio_codec", "").lower()
        has_audio = (a_codec not in ("none", "", "null"))
        checks.append(QACheckItem(
            category="video",
            check_name="video_contains_audio_stream",
            passed=has_audio,
            details=f"Audio stream verified in MP4 ({a_codec})" if has_audio else "No audio stream found in final MP4",
            is_fatal=True
        ))
        if not has_audio:
            errors.append("Final MP4 has no audio stream")

        # Check video duration against total scene narration timeline
        actual_dur = metrics.get("duration", 0.0)
        dur_diff = abs(actual_dur - total_audio_duration)
        dur_matches = dur_diff <= 1.25  # Tolerance for crossfades/transitions
        checks.append(QACheckItem(
            category="timeline",
            check_name="duration_matches_timeline",
            passed=dur_matches,
            details=f"Video duration ({actual_dur:.2f}s) matches narration timeline ({total_audio_duration:.2f}s) within tolerance (diff: {dur_diff:.2f}s)" if dur_matches else f"Duration mismatch: Video ({actual_dur:.2f}s) vs Narration ({total_audio_duration:.2f}s), diff={dur_diff:.2f}s",
            is_fatal=True
        ))
        if not dur_matches:
            errors.append(f"Duration mismatch: Video is {actual_dur:.2f}s but planned narration is {total_audio_duration:.2f}s (exceeds tolerance of 1.25s)")

        # -------------------------------------------------------------
        # 8. SCORING & FINAL STATUS
        # -------------------------------------------------------------
        passed_count = sum(1 for c in checks if c.passed)
        score = (passed_count / max(1, len(checks))) * 100.0

        fatal_failures = [c.check_name for c in checks if not c.passed and c.is_fatal]
        if fatal_failures or errors:
            status = QAStatus.FAIL
        elif warnings:
            status = QAStatus.WARNING
        else:
            status = QAStatus.PASS

        logger.info(f"QA audit completed: status={status.value}, score={score:.1f}%, fatal_failures={len(fatal_failures)}, warnings={len(warnings)}")

        return QAResult(
            status=status,
            score=round(score, 1),
            checks=checks,
            errors=errors,
            warnings=warnings,
            video_metrics=metrics,
            recoverable=True if status != QAStatus.PASS else False,
            suggested_repair_step="Re-render video with corrected timeline parameters" if fatal_failures else None
        )

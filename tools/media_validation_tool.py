import os
from typing import Dict, Any, List, Optional
from models.qa import QAResult, QAStatus, QACheckItem
from models.production import ProductionPlan
from utils.validation import validate_video_file, validate_wav_audio, validate_file_exists_and_non_empty, get_audio_duration
from utils.logging import get_logger

logger = get_logger("media_validation_tool")

class MediaValidationTool:
    """
    Forensic QA verification tool for inspecting production manifests and media streams.
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

        # 1. Script & Scene Continuity Checks
        scenes = production_plan.scenes
        if not scenes:
            errors.append("Production plan contains 0 scenes")
            checks.append(QACheckItem(
                category="script",
                check_name="scenes_not_empty",
                passed=False,
                details="No scenes found in plan",
                is_fatal=True
            ))
        else:
            checks.append(QACheckItem(
                category="script",
                check_name="scenes_not_empty",
                passed=True,
                details=f"Production plan contains {len(scenes)} scenes",
                is_fatal=True
            ))

        # Check continuous 1-based indexing
        expected_id = 1
        ids_continuous = True
        for s in scenes:
            if s.id != expected_id:
                ids_continuous = False
                break
            expected_id += 1

        checks.append(QACheckItem(
            category="script",
            check_name="scene_ids_continuous",
            passed=ids_continuous,
            details=f"Scene IDs continuous from 1 to {len(scenes)}" if ids_continuous else "Scene IDs discontinuous",
            is_fatal=True
        ))
        if not ids_continuous:
            errors.append("Scene IDs are not continuous")

        # 2. Visual Checks
        all_visuals_exist = True
        for s in scenes:
            if not s.visual_path or not validate_file_exists_and_non_empty(s.visual_path, min_bytes=1000):
                all_visuals_exist = False
                errors.append(f"Scene {s.id:02d} visual file is missing or corrupted: {s.visual_path}")

        checks.append(QACheckItem(
            category="visuals",
            check_name="all_scene_images_valid",
            passed=all_visuals_exist,
            details="All scene images verified and non-empty" if all_visuals_exist else "One or more scene images missing",
            is_fatal=True
        ))

        # 3. Audio Narration Checks
        all_audio_exist = True
        total_audio_duration = 0.0
        for s in scenes:
            if not s.audio_path:
                all_audio_exist = False
                errors.append(f"Scene {s.id:02d} audio path not set")
                continue
            valid, msg = validate_wav_audio(s.audio_path)
            if not valid:
                all_audio_exist = False
                errors.append(f"Scene {s.id:02d} audio invalid: {msg}")
            else:
                dur = get_audio_duration(s.audio_path) or 0.0
                total_audio_duration += dur

        checks.append(QACheckItem(
            category="audio",
            check_name="all_scene_narration_valid",
            passed=all_audio_exist,
            details=f"Total narration duration: {total_audio_duration:.2f}s" if all_audio_exist else "Narration files missing/invalid",
            is_fatal=True
        ))

        # 4. Subtitle Checks
        if subtitles_path and os.path.exists(subtitles_path):
            checks.append(QACheckItem(
                category="subtitles",
                check_name="srt_file_exists",
                passed=True,
                details=f"Subtitles file present: {subtitles_path}",
                is_fatal=False
            ))
        else:
            warnings.append("Subtitles file not generated or missing")
            checks.append(QACheckItem(
                category="subtitles",
                check_name="srt_file_exists",
                passed=False,
                details="Subtitles file missing",
                is_fatal=False
            ))

        # 5. Thumbnail Checks
        if thumbnail_path and validate_file_exists_and_non_empty(thumbnail_path, min_bytes=1000):
            checks.append(QACheckItem(
                category="visuals",
                check_name="thumbnail_valid",
                passed=True,
                details=f"Thumbnail generated: {thumbnail_path}",
                is_fatal=False
            ))
        else:
            warnings.append("Thumbnail image missing or empty")
            checks.append(QACheckItem(
                category="visuals",
                check_name="thumbnail_valid",
                passed=False,
                details="Thumbnail missing",
                is_fatal=False
            ))

        # 6. Final Video MP4 Checks with ffprobe
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

        # Compute QA score
        passed_count = sum(1 for c in checks if c.passed)
        score = (passed_count / max(1, len(checks))) * 100.0

        status = QAStatus.PASS if len(errors) == 0 else QAStatus.FAIL

        logger.info(f"QA audit completed: status={status.value}, score={score:.1f}%, errors={len(errors)}, warnings={len(warnings)}")

        return QAResult(
            status=status,
            score=round(score, 1),
            checks=checks,
            errors=errors,
            warnings=warnings,
            video_metrics=metrics,
            recoverable=True,
            suggested_repair_step="Re-render video" if errors else None
        )

"""Merge rendered frames + audio into MP4 using ffmpeg."""
import os
import subprocess
import shutil

QUALITY_MAP = {
    "ultra": "18",
    "high": "23",
    "medium": "28",
    "low": "32",
}


def merge_video(
    frames_dir: str,
    audio_file: str | None,
    output_path: str,
    fps: int,
    quality: str,
) -> dict:
    """Merge image frames and optional audio into MP4.

    Args:
        frames_dir: Directory containing frame_000000.png, frame_000001.png, ...
        audio_file: Path to audio file, or None for silent video
        output_path: Output .mp4 path
        fps: Frames per second
        quality: CRF quality level key

    Returns:
        dict with output_path and file_size_bytes
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required: please install ffmpeg")

    crf = QUALITY_MAP.get(quality, "23")
    frames_pattern = os.path.join(frames_dir, "frame_%06d.png")

    if audio_file and os.path.exists(audio_file):
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", frames_pattern,
            "-i", audio_file,
            "-c:v", "libx264",
            "-crf", crf,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            output_path,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", frames_pattern,
            "-c:v", "libx264",
            "-crf", crf,
            "-pix_fmt", "yuv420p",
            output_path,
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr}")

    size = os.path.getsize(output_path)
    return {
        "output_path": output_path,
        "file_size_bytes": size,
        "quality": quality,
    }

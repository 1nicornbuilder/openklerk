"""
FFmpeg-based screen recording for OpenClerc demos.

Provides utility functions to:
1. Record demos via Playwright's built-in video capture
2. Post-process recordings into distribution clips using FFmpeg
"""
import subprocess
import shutil
from pathlib import Path


def check_ffmpeg() -> bool:
    """Check if FFmpeg is available."""
    return shutil.which("ffmpeg") is not None


def convert_to_mp4(input_path: str, output_dir: str = "./output", output_name: str = "full_demo.mp4") -> str:
    """Convert Playwright's WebM recording to MP4."""
    output_path = Path(output_dir) / output_name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-vf", "scale=1920:1080",
        "-c:a", "aac",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)
    return str(output_path)


def create_60s_clip(full_video: str, output_dir: str = "./output", output_name: str = "clip_60s.mp4") -> str:
    """Create a 60-second highlight reel from the full demo."""
    output_path = Path(output_dir) / output_name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", full_video,
        "-filter_complex",
        (
            "[0:v]select='between(t,0,5)+between(t,15,25)"
            "+between(t,45,55)+between(t,120,140)+between(t,170,180)',"
            "setpts=N/FRAME_RATE/TB[v]"
        ),
        "-map", "[v]",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)
    return str(output_path)


def create_30s_clip(full_video: str, output_dir: str = "./output", output_name: str = "clip_30s.mp4") -> str:
    """Create a 30-second teaser from the full demo."""
    output_path = Path(output_dir) / output_name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", full_video,
        "-filter_complex",
        (
            "[0:v]select='between(t,0,3)+between(t,20,25)"
            "+between(t,50,55)+between(t,130,140)+between(t,175,180)',"
            "setpts=N/FRAME_RATE/TB[v]"
        ),
        "-map", "[v]",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)
    return str(output_path)


def create_github_gif(full_video: str, output_dir: str = "./output", output_name: str = "demo_preview.gif") -> str:
    """Create a compressed GIF for GitHub README."""
    output_path = Path(output_dir) / output_name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", full_video,
        "-ss", "0",
        "-t", "15",
        "-vf", "fps=12,scale=640:-1:flags=lanczos",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)
    return str(output_path)

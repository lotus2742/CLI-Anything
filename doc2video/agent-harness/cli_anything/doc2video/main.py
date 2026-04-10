"""cli-anything-doc2video — entry point."""
import json
import sys
import click
from prompt_toolkit import PromptSession

from .core.parse import parse_document
from .core.tts import generate_tts
from .core.render import render_frames
from .core.merge import merge_video


def output(data: dict, json_mode: bool):
    if json_mode:
        click.echo(json.dumps(data))
    else:
        for k, v in data.items():
            click.echo(f"{k}: {v}")


@click.group(invoke_without_command=True)
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output JSON for agent consumption.")
@click.pass_context
def cli(ctx, json_mode):
    """cli-anything-doc2video: Convert documents to narrated MP4 videos."""
    ctx.ensure_object(dict)
    ctx.obj["json_mode"] = json_mode
    if ctx.invoked_subcommand is None:
        # REPL mode
        session = PromptSession()
        click.echo("doc2video REPL — type a command or 'exit' to quit.")
        while True:
            try:
                line = session.prompt("doc2video> ").strip()
                if line in ("exit", "quit"):
                    break
                if not line:
                    continue
                args = line.split()
                try:
                    cli.main(args, standalone_mode=False, obj={"json_mode": json_mode})
                except Exception as e:
                    click.echo(f"Error: {e}")
            except (EOFError, KeyboardInterrupt):
                break


@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("-o", "--output", "output_path", default=None, help="Output .txt file path.")
@click.option("--format", "fmt", type=click.Choice(["plain", "slides"]), default="slides",
              help="Output format: plain text or slide-separated sections.")
@click.pass_context
def parse(ctx, input_file, output_path, fmt):
    """Parse a document into structured text/slides.

    Supports .txt, .md, .pdf input formats.
    """
    json_mode = ctx.obj["json_mode"]
    result = parse_document(input_file, fmt)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result["content"])
    output({**result, "output_path": output_path or ""}, json_mode)


@cli.command()
@click.argument("text_file", type=click.Path(exists=True))
@click.option("-o", "--output", "output_path", required=True, help="Output audio file path (.mp3/.wav).")
@click.option("--voice", default="zh-CN-XiaoxiaoNeural", show_default=True,
              help="TTS voice name (edge-tts voices).")
@click.option("--rate", default="+0%", show_default=True, help="Speech rate, e.g. +10% or -5%.")
@click.pass_context
def tts(ctx, text_file, output_path, voice, rate):
    """Generate TTS audio from a text file using edge-tts."""
    json_mode = ctx.obj["json_mode"]
    result = generate_tts(text_file, output_path, voice, rate)
    output(result, json_mode)


@cli.command()
@click.argument("text_file", type=click.Path(exists=True))
@click.option("-o", "--output-dir", "output_dir", required=True, help="Directory to save rendered frame images.")
@click.option("--width", default=1280, show_default=True)
@click.option("--height", default=720, show_default=True)
@click.option("--fps", default=24, show_default=True)
@click.option("--style", type=click.Choice(["default", "dark", "minimal"]), default="default", show_default=True)
@click.pass_context
def render(ctx, text_file, output_dir, width, height, fps, style):
    """Render document slides into image frames."""
    json_mode = ctx.obj["json_mode"]
    result = render_frames(text_file, output_dir, width, height, fps, style)
    output(result, json_mode)


@cli.command()
@click.argument("frames_dir", type=click.Path(exists=True))
@click.argument("audio_file", type=click.Path(exists=True))
@click.option("-o", "--output", "output_path", required=True, help="Output MP4 file path.")
@click.option("--fps", default=24, show_default=True)
@click.option("--quality", type=click.Choice(["ultra", "high", "medium", "low"]), default="high", show_default=True)
@click.pass_context
def merge(ctx, frames_dir, audio_file, output_path, fps, quality):
    """Merge rendered frames and audio into a final MP4 video."""
    json_mode = ctx.obj["json_mode"]
    result = merge_video(frames_dir, audio_file, output_path, fps, quality)
    output(result, json_mode)


@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("-o", "--output", "output_path", required=True, help="Output MP4 file path.")
@click.option("--voice", default="zh-CN-XiaoxiaoNeural", show_default=True)
@click.option("--rate", default="+0%", show_default=True)
@click.option("--style", type=click.Choice(["default", "dark", "minimal"]), default="default", show_default=True)
@click.option("--fps", default=24, show_default=True)
@click.option("--quality", type=click.Choice(["ultra", "high", "medium", "low"]), default="high", show_default=True)
@click.option("--no-tts", is_flag=True, default=False, help="Skip TTS, produce silent video.")
@click.pass_context
def process(ctx, input_file, output_path, voice, rate, style, fps, quality, no_tts):
    """Full pipeline: parse → TTS → render → merge into MP4.

    This is the one-shot command for converting a document to a video.
    """
    import tempfile, os
    json_mode = ctx.obj["json_mode"]

    with tempfile.TemporaryDirectory() as tmpdir:
        # Step 1: parse
        click.echo("Step 1/4: Parsing document...")
        parsed = parse_document(input_file, "slides")
        slides_path = os.path.join(tmpdir, "slides.txt")
        with open(slides_path, "w", encoding="utf-8") as f:
            f.write(parsed["content"])

        # Step 2: TTS
        audio_path = os.path.join(tmpdir, "audio.mp3")
        if not no_tts:
            click.echo("Step 2/4: Generating TTS audio...")
            generate_tts(slides_path, audio_path, voice, rate)
        else:
            click.echo("Step 2/4: Skipping TTS (--no-tts).")
            audio_path = None

        # Step 3: render frames
        click.echo("Step 3/4: Rendering frames...")
        frames_dir = os.path.join(tmpdir, "frames")
        os.makedirs(frames_dir, exist_ok=True)
        render_frames(slides_path, frames_dir, 1280, 720, fps, style, audio_file=audio_path)

        # Step 4: merge
        click.echo("Step 4/4: Merging video...")
        result = merge_video(frames_dir, audio_path, output_path, fps, quality)

    output({**result, "output_path": output_path}, json_mode)

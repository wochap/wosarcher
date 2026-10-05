"""Report export with pandoc: DOCX directly, PDF through pandoc's Typst writer and the `typst` compiler."""

import asyncio
import shutil
import tempfile
from pathlib import Path

from wosarcher.models import ExportFormat
from wosarcher.ports import ExportError

TIMEOUT_SECONDS = 60.0
# Markdown without the extensions that let report text reach the output as code or metadata,
# or turn dollar amounts into math.
READER = "-".join(
    [
        "markdown",
        "raw_html",
        "raw_attribute",
        "raw_tex",
        "tex_math_dollars",
        "tex_math_single_backslash",
        "tex_math_double_backslash",
        "yaml_metadata_block",
        "citations",
    ]
)
# Images become their alt text, so neither pandoc nor Typst opens the file or URL they name.
IMAGES_AS_TEXT = "function Image(image) return image.caption end\n"
# A font bundled with Typst: pandoc 3.7's Typst template leaves the font list empty otherwise,
# which Typst 0.14 rejects. It covers Latin and Greek text.
PDF_FONT = "Libertinus Serif"
PROGRAMS: dict[ExportFormat, list[str]] = {"pdf": ["pandoc", "typst"], "docx": ["pandoc"]}


def last_line(stderr: bytes) -> str:
    lines = [line.strip() for line in stderr.decode("utf-8", "replace").splitlines() if line.strip()]
    return lines[-1] if lines else "no error output"


class PandocExporter:
    def __init__(self, timeout: float = TIMEOUT_SECONDS) -> None:
        self.timeout = timeout

    def missing(self, fmt: ExportFormat) -> list[str]:
        return [program for program in PROGRAMS[fmt] if shutil.which(program) is None]

    def arguments(self, pandoc: str, folder: Path, fmt: ExportFormat) -> list[str]:
        output = folder / f"out.{fmt}"
        args = [pandoc, "--sandbox", "--from", READER, "--lua-filter", str(folder / "images.lua")]
        if fmt == "pdf":
            args += ["--to", "typst", "--pdf-engine", shutil.which("typst") or "typst", "-V", "papersize=a4"]
            args += ["-V", f"mainfont={PDF_FONT}"]
        else:
            args += ["--to", "docx"]
        return [*args, "--output", str(output), str(folder / "in.md")]

    async def export(self, markdown: str, fmt: ExportFormat) -> bytes:
        missing = self.missing(fmt)
        if missing:
            raise ExportError(f"{fmt.upper()} export needs {' and '.join(missing)} on the server")
        pandoc = shutil.which("pandoc") or "pandoc"
        with tempfile.TemporaryDirectory(prefix="wosarcher-export-") as name:
            folder = Path(name)
            (folder / "in.md").write_text(markdown, encoding="utf-8")
            (folder / "images.lua").write_text(IMAGES_AS_TEXT, encoding="utf-8")
            process = await asyncio.create_subprocess_exec(
                *self.arguments(pandoc, folder, fmt),
                cwd=folder,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(process.communicate(), self.timeout)
            except TimeoutError:
                process.kill()
                await process.wait()
                raise ExportError(f"{fmt} export took longer than {self.timeout:.0f} seconds") from None
            output = folder / f"out.{fmt}"
            if process.returncode != 0 or not output.is_file():
                raise ExportError(last_line(stderr))
            return output.read_bytes()

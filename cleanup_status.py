from pathlib import Path
path = Path("collector/ui.py")
lines = path.read_text(encoding="utf-8").splitlines()
start = next(i for i, line in enumerate(lines) if line.strip().startswith("def _update_status"))
# find the end of the new block by locating the next blank line followed by def run
end = start
while end + 1 < len(lines) and not lines[end + 1].lstrip().startswith("def run"):
    end += 1
# ensure end points to line before def run
if end + 1 < len(lines) and lines[end + 1].lstrip().startswith("def run"):
    pass
else:
    raise SystemExit("Unable to locate def run after _update_status")
path.write_text("\n".join(lines[:end+1] + lines[end+1:]) + "\n", encoding="utf-8")

"""Render real command output into a self-contained terminal SVG for the README.

The image is generated from an actual run, so it cannot drift away from the
behaviour it claims to document.

    python habit.py plan ... > /tmp/run.txt
    python tools/render_screenshot.py /tmp/run.txt docs/terminal.svg
"""
from pathlib import Path
import html
import sys

WIDTH = 920
PADDING = 30
LINE = 24
BAR = 36
FONT = 15
TITLE = 'mai-habit — python habit.py plan'


def colour_for(line):
    stripped = line.strip()
    if stripped.startswith('## '):
        return '#79c0ff'
    if stripped.startswith('# '):
        return '#ffa657'
    if stripped.startswith('演示数据') or stripped.startswith('MCP 计价数据'):
        return '#f0883e'
    if stripped.startswith('- '):
        return '#8b949e'
    if '合计' in stripped:
        return '#7ee787'
    if stripped.startswith('当前没有') or stripped.startswith('按可用证据'):
        return '#8b949e'
    return '#c9d1d9'


def escape(text):
    return html.escape(text.replace('\t', '    '), quote=False)


def render(lines):
    height = BAR + PADDING * 2 + LINE * max(1, len(lines))
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
             f'viewBox="0 0 {WIDTH} {height}" role="img" '
             f'aria-label=" Terminal output of the mai-habit plan command" '
             f'font-family="ui-monospace, SFMono-Regular, Consolas, \'Microsoft YaHei\', monospace">',
             f'<rect width="{WIDTH}" height="{height}" rx="10" fill="#0d1117"/>',
             f'<path d="M0 {BAR}V10a10 10 0 0 1 10-10h{WIDTH - 20}a10 10 0 0 1 10 10v{BAR - 10}z" fill="#161b22"/>']
    for index, colour in enumerate(('#ff5f57', '#febc2e', '#28c840')):
        parts.append(f'<circle cx="{22 + index * 20}" cy="{BAR / 2:.0f}" r="6" fill="{colour}"/>')
    parts.append(f'<text x="{WIDTH / 2:.0f}" y="{BAR / 2 + 4:.0f}" fill="#8b949e" font-size="12" '
                 f'text-anchor="middle">{escape(TITLE)}</text>')
    y = BAR + PADDING + FONT
    for line in lines:
        if line.strip():
            parts.append(f'<text x="{PADDING}" y="{y}" fill="{colour_for(line)}" '
                         f'font-size="{FONT}" xml:space="preserve">{escape(line)}</text>')
        y += LINE
    parts.append('</svg>')
    return '\n'.join(parts) + '\n'


def main(argv):
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[4:], file=sys.stderr)
        return 2
    lines = Path(argv[1]).read_text(encoding='utf-8').splitlines()
    target = Path(argv[2])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(lines), encoding='utf-8')
    print(f'wrote {target} ({len(lines)} lines)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))

# Preview Markdown in Browser

## When to Use
When the user asks to preview a `.md` file with rendered formatting (bold, tables, code blocks, etc.).

## How

Convert markdown to HTML via Python and open in the default browser:

```bash
python3 -c "
import markdown
with open('PATH_TO_MD_FILE') as f:
    md = f.read()
html = markdown.markdown(md, extensions=['tables'])
with open('/tmp/preview.html', 'w') as f:
    f.write('<html><head><style>body{font-family:-apple-system,sans-serif;max-width:800px;margin:40px auto;padding:0 20px;line-height:1.6}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px}code{background:#f4f4f4;padding:2px 4px;border-radius:3px}</style></head><body>' + html + '</body></html>')
" && open /tmp/preview.html
```

## Notes
- Requires `python3` with the `markdown` package (`pip3 install markdown` if missing)
- Uses `extensions=['tables']` for GitHub-style table rendering
- Output goes to `/tmp/preview.html` — overwritten each time, no cleanup needed
- `open` on macOS opens in the default browser
- Do NOT use `grip` (requires GitHub API, unreliable behind corporate network)
- Do NOT use `qlmanage -p` (doesn't render markdown formatting)
- Do NOT use TextEdit (shows raw text, no markup rendering)

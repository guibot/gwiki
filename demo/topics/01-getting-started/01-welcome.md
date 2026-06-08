# Welcome to the Wiki

![alt text](demo/topics/01-getting-started/img2.png)

This is a demo topic. Replace this content with your own notes.

The wiki auto-detects the structure from the filesystem — no configuration needed.

## How it works

Each subfolder inside `topics/` becomes a **category** in the sidebar.
Each `.md` file inside a category becomes a **topic**.

Folder and file names become display labels automatically:
- `01-getting-started` → **Getting Started**
- `01-welcome.md` → **Welcome**

## Running

```bash
python3 server_wiki.py
```

Then open `http://localhost:8080` in your browser.

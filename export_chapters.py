"""Export OBS chapter markers (F9 marks) from hybrid-MP4 recordings to one CSV.
Usage: python export_chapters.py <folder-or-file> [...]  -> writes <recording>.marks.csv next to each recording.
Rows: file, mark_index, time_seconds, title. The first chapter (OBS writes a start chapter at 0) is skipped."""
import csv, json, os, subprocess, sys
def chapters(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_chapters", "-of", "json", path], capture_output=True, text=True, encoding="utf-8")
    return json.loads(out.stdout or "{}").get("chapters", [])
files = []
for a in sys.argv[1:]:
    if os.path.isdir(a):
        files += sorted(os.path.join(a, f) for f in os.listdir(a) if f.lower().endswith(".mp4"))
    else:
        files.append(a)
if not files:
    sys.exit("no mp4 given")
for f in files:
    ch = chapters(f)
    dest = os.path.splitext(f)[0] + ".marks.csv"
    with open(dest, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["file", "mark_index", "time_seconds", "title"])
        for i, c in enumerate(ch[1:], 1):
            w.writerow([os.path.basename(f), i, float(c["start_time"]), c.get("tags", {}).get("title", "")])
    print(f"{os.path.basename(f)}: {max(len(ch)-1,0)} marks -> {os.path.basename(dest)}")

#!/usr/bin/env python3
"""What was each forked session actually about?

Useful once, right after installing the hook: it only renames forks from the
next prompt on, so the ones already in your sidebar stay nameless. This prints
what each of them did, so you can retitle them (by hand, or by handing this
output to Claude).

A forked transcript opens with its parent's history copied in, and those copied
lines keep the *parent's* sessionId -- only the fork's own lines carry the
fork's. So the fork's own work is exactly the lines whose sessionId matches the
file name. (A transcript that merely starts with copied history is not proof of
a fork: resuming or compacting a session does the same. The default scope
therefore goes by the *name* still looking inherited, which is what you
actually want to fix.)

    fork-topics.py                   # forks whose name is still inherited
    fork-topics.py --scope forks     # anything whose history was copied in
    fork-topics.py --scope all       # every transcript
    fork-topics.py <uuid> [<uuid>]   # just these
    fork-topics.py --project ~/.claude/projects/-Users-me-code-thing

Reads only; writes nothing. Standard library only. Python 3.8+.
"""

import argparse
import glob
import json
import os
import re
import sys
import time

FORK_SUFFIX = re.compile(r"\s*\((?:fork|Fork|FORK)(?:\s*\d+)?\)\s*$")

NOISE_PREFIXES = (
    "<system-reminder", "Caveat:", "<command-name>", "<local-command",
    "[Request interrupted", "<user-prompt-submit-hook>", "<task-notification",
    "<side-sessions-event", "API Error", "<ide_", "<cross-session-message",
    "This session is being continued from a previous conversation",
)


def config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude"
    )


def text_of(message):
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                out.append(block.get("text") or "")
        return "\n".join(out)
    return ""


def first_session_id(path):
    """sessionId of the transcript's first record, or None."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    return json.loads(line).get("sessionId")
                except Exception:
                    continue
    except Exception:
        return None
    return None


def own_content(path, uuid, want=3):
    """(user prompts, assistant snippets, own line count, current title)."""
    users, asst, own, title = [], [], 0, None
    try:
        fh = open(path, "r", encoding="utf-8", errors="replace")
    except Exception:
        return users, asst, own, title
    with fh:
        for line in fh:
            if uuid not in line:      # cheap prefilter: parent's lines skipped
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("sessionId") != uuid:
                continue
            own += 1
            if rec.get("type") == "custom-title" and rec.get("customTitle"):
                title = rec["customTitle"]
                continue
            if rec.get("type") not in ("user", "assistant"):
                continue
            if rec.get("isMeta") or rec.get("isVirtual") or rec.get("isSidechain"):
                continue
            msg = rec.get("message") or {}
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue
            txt = (text_of(msg) or "").split("<system-reminder>")[0].strip()
            if not txt or txt.startswith(NOISE_PREFIXES):
                continue
            flat = " ".join(txt.split())[:220]
            if role == "user" and len(users) < want:
                users.append(flat)
            elif role == "assistant" and len(asst) < want:
                asst.append(flat)
    return users, asst, own, title


def transcripts(base, project=None):
    roots = [project] if project else sorted(
        glob.glob(os.path.join(base, "projects", "*"))
    )
    found = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        found.extend(glob.glob(os.path.join(root, "*.jsonl")))
    found.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return found


def session_names(base):
    """sessionId -> the name the app currently shows, from its own records."""
    names = {}
    for path in glob.glob(os.path.join(base, "sessions", "*.json")):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                rec = json.load(fh)
        except Exception:
            continue
        sid, name = rec.get("sessionId"), (rec.get("name") or "").strip()
        if sid and name:
            names[sid] = name
    return names


def main():
    ap = argparse.ArgumentParser(
        description="Show what each forked Claude Code session was about."
    )
    ap.add_argument("uuids", nargs="*", help="transcript ids; default: scan")
    ap.add_argument("--config-dir", default=config_dir(),
                    help="Claude config dir (default: $CLAUDE_CONFIG_DIR or ~/.claude)")
    ap.add_argument("--project", help="one projects/<dir> to look in")
    ap.add_argument("--limit", type=int, default=3, help="lines per side (default 3)")
    ap.add_argument("--scope", choices=["needs-name", "forks", "all"],
                    default="needs-name",
                    help="needs-name (default): name still ends in (fork); "
                         "forks: history was copied in; all: everything")
    ap.add_argument("--days", type=float, default=0,
                    help="only transcripts touched in the last N days "
                         "(default 0 = no limit; old and archived sessions "
                         "have transcripts on disk too)")
    args = ap.parse_args()

    base = args.config_dir
    paths = transcripts(base, args.project)
    if args.days > 0:
        cutoff = time.time() - args.days * 86400
        paths = [p for p in paths if os.path.getmtime(p) >= cutoff]
    if args.uuids:
        wanted = set(args.uuids)
        paths = [p for p in paths
                 if os.path.basename(p)[:-6] in wanted
                 or os.path.basename(p)[:8] in wanted]

    if not paths:
        print("找不到 transcript / no transcripts found under %s" % base, file=sys.stderr)
        return 1

    names = session_names(base)
    shown = 0
    for path in paths:
        uuid = os.path.basename(path)[:-6]
        scope = "all" if args.uuids else args.scope
        if scope == "forks":
            head = first_session_id(path)
            if head is None or head == uuid:
                continue  # nothing was copied in
        users, asst, own, title = own_content(path, uuid, args.limit)
        # The app's own record wins; the transcript's title is the fallback
        # (a fork that was never prompted only carries the parent's old title).
        name = names.get(uuid) or title
        if scope == "needs-name" and not FORK_SUFFIX.search(name or ""):
            continue
        shown += 1
        print("=" * 72)
        print("%s  %s" % (uuid[:8], name or "(无标题 / untitled)"))
        print("   %s" % path)
        if not users and not asst:
            print("   没发过 prompt，只有 %d 行元数据 / never prompted (%d meta lines)"
                  % (own, own))
            continue
        for i, line in enumerate(users, 1):
            print("   用户/user %d: %s" % (i, line))
        for i, line in enumerate(asst[:2], 1):
            print("   助手/asst %d: %s" % (i, line))
    print("=" * 72)
    print("共 %d 个 / %d shown" % (shown, shown))
    if args.scope == "needs-name" and not args.uuids and not shown:
        print("没有名字还是继承来的 fork —— 都已经有自己的名字了。"
              "想看全部：--scope forks / 或 --scope all")
    return 0


if __name__ == "__main__":
    sys.exit(main())

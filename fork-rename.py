#!/usr/bin/env python3
"""Give every forked Claude Code session a name of its own.

Claude Code's desktop app names a forked session after its parent, with a
"(fork)" / "(fork 2)" suffix. Fork a few times and the sidebar is a wall of
identical rows.

This is a UserPromptSubmit hook. On every prompt it checks the session's own
record under <config dir>/sessions/<pid>.json. If the name still looks
inherited -- it ends in "(fork)" or "(fork N)", which means nobody has renamed
it yet -- the hook injects a short instruction asking Claude to call
mcp__ccd_session_mgmt__set_session_title on itself with a name derived from
what the user just asked for.

Nothing is renamed behind Claude's back: the hook only supplies context, the
model does the renaming with the desktop app's own tool, and the app applies
its usual permission rules.

Silent no-ops (exit 0, no output): sessions that are not forks, names a human
has already edited, sessions outside the desktop app, slash commands, filler
prompts ("ok", "continue"), and anything unexpected.

Configuration (all optional): <config dir>/fork-rename.json
See README.md, or run with --print-config to dump the effective settings.

Requires nothing but the standard library. Python 3.8+.
"""

import json
import glob
import os
import re
import sys

CONFIG_FILENAME = "fork-rename.json"
MARK_DIRNAME = "fork-rename"

# An inherited fork name: "<parent> (fork)" or "<parent> (fork 2)".
# A name a human has edited ("Platform (fork) API") no longer ends this way,
# so it is left alone.
FORK_SUFFIX = re.compile(r"\s*\((?:fork|Fork|FORK)(?:\s*\d+)?\)\s*$")

# Prompts too thin to name a session after. They do not consume the session's
# one reminder -- the next real prompt still triggers it.
DEFAULT_FILLER = [
    "go", "go on", "continue", "ok", "okay", "k", "y", "yes", "n", "no",
    "next", "retry", "again", "stop", "wait", "thanks", "thx", "ty",
    "继续", "接着", "好", "好的", "嗯", "是", "对", "行", "可以", "再来",
    "重试", "下一个", "谢谢", "停", "算了",
]

DEFAULTS = {
    # "domain" -> "<area> · <what you did>"   (areas cluster when sorted by name)
    # "topic"  -> "<what you did>"            (shortest; no lineage)
    # "parent" -> "<parent name> · <topic>"   (keeps lineage up front)
    "style": "domain",
    # Example area words handed to the model. Yours, not the tool's -- put the
    # modules of whatever you actually work on here.
    "domains": [],
    # "zh", "en", or "auto" (follow the prompt's own script).
    "language": "auto",
    # Shorter prompts are skipped (an image-only paste lands here).
    "min_prompt_chars": 4,
    # Prompts starting with any of these are skipped.
    "skip_prefixes": ["/", "!"],
    # Added to the built-in filler list.
    "extra_filler": [],
    # Remind at most once per session. false = until the name stops looking
    # inherited (noisier, but survives a refused rename).
    "remind_once": True,
}


def config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude"
    )


def load_config(base):
    cfg = dict(DEFAULTS)
    path = os.path.join(base, CONFIG_FILENAME)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            user = json.load(fh)
        if isinstance(user, dict):
            for key in DEFAULTS:
                if key in user:
                    cfg[key] = user[key]
    except FileNotFoundError:
        pass
    except Exception:
        pass  # a broken config must never break prompt submission
    return cfg


def session_record(base, session_id):
    """The desktop app's record for this session, found by transcript id."""
    pattern = os.path.join(base, "sessions", "*.json")
    for path in glob.glob(pattern):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                rec = json.load(fh)
        except Exception:
            continue
        if rec.get("sessionId") == session_id:
            return rec
    return None


def looks_chinese(text):
    return any("一" <= ch <= "鿿" for ch in text)


def pick_language(cfg, prompt):
    lang = (cfg.get("language") or "auto").lower()
    if lang in ("zh", "en"):
        return lang
    return "zh" if looks_chinese(prompt) else "en"


def title_spec(cfg, lang, parent):
    """What to tell the model the title should look like."""
    style = (cfg.get("style") or "domain").lower()
    domains = [d for d in (cfg.get("domains") or []) if isinstance(d, str)]
    examples = " / ".join(domains[:14])

    if lang == "zh":
        if style == "topic":
            return (
                '  title: 这次请求的话题，像新建会话那样一个能独立看懂的短名字\n'
                "中文 4-12 字 / 英文 2-5 词，不要带父会话的名字，也不要 (fork) 字样。"
            )
        if style == "parent":
            return (
                '  title: "%s · <这次请求的话题>"\n'
                "话题 4-12 字，整个标题不超过 40 字。" % parent
            )
        spec = '  title: "<领域> · <这次的具体事>"\n领域是 2-4 个字的模块名'
        if examples:
            spec += "，按这次请求真正落在哪块写：%s 这类" % examples
        else:
            spec += "，用这个项目自己的模块名（页面、子系统、工具链那一级）"
        return (
            spec + "。后半是这次干的事，中文 4-10 字 / 英文 2-5 词。\n"
            "不要带父会话的名字，不要 (fork) 字样，也不要用 # 之类的符号标层级 —— "
            "领域排在最前面是为了在侧边栏里一眼扫到、同模块的会话挨在一起。"
        )

    if style == "topic":
        return (
            "  title: the topic of this request -- a short name that stands on "
            "its own, like a new session's\n"
            "2-5 words. No parent name, no \"(fork)\"."
        )
    if style == "parent":
        return (
            '  title: "%s · <topic of this request>"\n'
            "Keep the topic to 2-5 words." % parent
        )
    spec = '  title: "<area> · <what this request is about>"\nThe area is one or two words'
    if examples:
        spec += ", whichever this request actually lands in: %s" % examples
    else:
        spec += ", a module of the project at hand (a page, a subsystem, a toolchain)"
    return (
        spec + ". Then what you are doing, 2-5 words.\n"
        "No parent name, no \"(fork)\", no \"#\" depth marks -- the area comes "
        "first so the sidebar can be scanned at a glance and sessions in the "
        "same module sort together."
    )


def build_instruction(cfg, lang, current_name):
    parent = FORK_SUFFIX.sub("", current_name).strip(" ·-—:：") or current_name
    spec = title_spec(cfg, lang, parent)
    if lang == "zh":
        return (
            "[fork 会话改名]\n"
            "这个会话是 fork 出来的，标题还是继承父会话的「%s」，"
            "和其他 fork 出来的会话重名、分不出谁是谁。\n"
            "请在本轮**第一批**工具调用里（和别的调用并行发出，不要单独占一条消息）"
            "调用 mcp__ccd_session_mgmt__set_session_title：\n"
            '  session_id: "self"\n'
            "%s\n"
            "用用户自己的语言。改完不要在回复里提这件事，直接正常处理用户的请求。"
            "如果改名被拒绝或需要确认而没通过，就不要再试。"
        ) % (current_name, spec)
    return (
        "[fork session rename]\n"
        "This session is a fork and still carries its parent's name (\"%s\"), "
        "so it is indistinguishable from every other fork in the sidebar.\n"
        "In this turn's **first batch** of tool calls (alongside the others, "
        "not in a message of its own), call "
        "mcp__ccd_session_mgmt__set_session_title:\n"
        '  session_id: "self"\n'
        "%s\n"
        "Use the user's own language. Do not mention the rename in your reply; "
        "just carry on with the request. If the rename is refused or needs an "
        "approval that does not come, do not try again."
    ) % (current_name, spec)


def main():
    base = config_dir()
    cfg = load_config(base)

    if "--print-config" in sys.argv:
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
        return

    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    session_id = (data.get("session_id") or "").strip()
    prompt = (data.get("prompt") or "").strip()
    if not session_id:
        return

    mark = os.path.join(base, MARK_DIRNAME, session_id)
    if cfg.get("remind_once", True) and os.path.exists(mark):
        return

    for prefix in cfg.get("skip_prefixes") or []:
        if prefix and prompt.startswith(prefix):
            return

    filler = set(DEFAULT_FILLER) | {
        str(w).strip().lower() for w in (cfg.get("extra_filler") or [])
    }
    try:
        min_chars = int(cfg.get("min_prompt_chars", 4))
    except Exception:
        min_chars = 4
    if len(prompt) < min_chars or prompt.lower() in filler:
        return

    rec = session_record(base, session_id)
    if not rec or not rec.get("hostSessionId"):
        # Not a desktop-app session: set_session_title is the app's own tool
        # and does not exist anywhere else, so there is nothing to ask for.
        return

    name = (rec.get("name") or "").strip()
    if not name or not FORK_SUFFIX.search(name):
        return  # not a fork, or already named by hand

    try:
        os.makedirs(os.path.join(base, MARK_DIRNAME), exist_ok=True)
        with open(mark, "w", encoding="utf-8") as fh:
            fh.write(name + "\n")
    except Exception:
        pass  # worst case the reminder repeats

    lang = pick_language(cfg, prompt)
    print(json.dumps({
        "suppressOutput": True,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": build_instruction(cfg, lang, name),
        },
    }, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # never block a prompt

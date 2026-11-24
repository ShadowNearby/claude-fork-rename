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

In a terminal session there is no such tool (renaming there is your own
/rename), so the hook sets the title itself through its output's sessionTitle
field, built from the prompt's own words. By default it only does so when no
title is visible yet, which covers a fresh session and a --fork-session fork
(the fork's transcript, title included, is still unwritten when the hook runs)
while leaving a resumed session's title alone. See "terminal" in DEFAULTS.

Silent no-ops (exit 0, no output): sessions that are not forks, names a human
has already edited, slash commands, filler prompts ("ok", "continue"), and
anything unexpected.

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
    # Terminal (non-desktop) sessions, where no rename tool exists and the hook
    # has to set the title itself, from the prompt's own words:
    #   "untitled"  title a session with no title visible yet (default). That
    #               covers a fresh session and a --fork-session fork: the fork's
    #               transcript is still unwritten when this hook runs, so the
    #               title it inherited is not there to see.
    #   "always"    also retitle when a title IS already there -- i.e. a
    #               --resume of a session that was titled before. Opt in if you
    #               resume sessions and change the subject.
    #   "off"       leave terminal sessions alone
    "terminal": "untitled",
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
    path = os.environ.get("FORK_RENAME_CONFIG") or os.path.join(base, CONFIG_FILENAME)
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


def transcript_state(path, prompt):
    """(does it already carry a title, how many user turns predate this prompt).

    The prompt may or may not be in the file yet when this hook runs, so a user
    message identical to it is not counted.
    """
    titled, users = False, 0
    if not path or not os.path.exists(path):
        return titled, users
    needle = " ".join(prompt.split())
    try:
        fh = open(path, "r", encoding="utf-8", errors="replace")
    except Exception:
        return titled, users
    with fh:
        for line in fh:
            if '"custom-title"' in line or '"ai-title"' in line:
                titled = True
                continue
            if '"type":"user"' not in line and '"type": "user"' not in line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("type") != "user" or rec.get("isMeta") or rec.get("isVirtual"):
                continue
            msg = rec.get("message") or {}
            if msg.get("role") != "user":
                continue
            content = msg.get("content")
            if isinstance(content, list):
                content = " ".join(
                    b.get("text") or "" for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            text = " ".join(str(content or "").split())
            if not text or text.startswith("<"):
                continue
            if needle and needle in text:
                continue          # this very prompt, already written out
            users += 1
    return titled, users


# Openers that say nothing about the topic.
LEAD_IN = [
    "帮我", "请帮我", "请", "麻烦", "能不能", "可以帮我", "我想", "我要", "现在",
    "please ", "pls ", "can you ", "could you ", "i want to ", "i need to ",
    "let's ", "lets ", "help me ",
]
SENTENCE_END = "。！？；\n.!?;"


def title_from_prompt(prompt, lang):
    """A title the hook can build on its own, for terminals with no rename tool."""
    text = re.sub(r"```.*?```", " ", prompt, flags=re.S)       # code blocks
    text = re.sub(r"<[^>\n]{1,80}>", " ", text)                 # tags
    text = re.sub(r"https?://\S+", " ", text)                   # urls
    text = re.sub(r"(/[\w.-]+){2,}", " ", text)                 # long paths
    text = " ".join(text.split())
    for opener in LEAD_IN:
        if text.lower().startswith(opener):
            text = text[len(opener):].lstrip("，,：: ")
            break
    for i, ch in enumerate(text):
        if ch in SENTENCE_END and i >= 4:
            text = text[:i]
            break
    text = text.strip(" ，,。.、:：-—")
    if not text:
        return ""
    if lang == "zh":
        return text[:24].strip(" 的在和与")
    words = text.split()[:7]
    # a dangling preposition is usually where a path or url got stripped out
    while words and words[-1].lower() in (
        "in", "on", "at", "to", "for", "with", "from", "of", "and", "the", "a"
    ):
        words.pop()
    return " ".join(words)[:48]


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

    def remember(what):
        try:
            os.makedirs(os.path.join(base, MARK_DIRNAME), exist_ok=True)
            with open(mark, "w", encoding="utf-8") as fh:
                fh.write(what + "\n")
        except Exception:
            pass  # worst case the reminder repeats

    lang = pick_language(cfg, prompt)
    rec = session_record(base, session_id)

    if rec and rec.get("hostSessionId"):
        # Desktop app: ask the model to call the app's own rename tool, which
        # is the only thing that can retitle a session there.
        name = (rec.get("name") or "").strip()
        if not name or not FORK_SUFFIX.search(name):
            return  # not a fork, or already named by hand
        remember(name)
        print(json.dumps({
            "suppressOutput": True,
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": build_instruction(cfg, lang, name),
            },
        }, ensure_ascii=False))
        return

    # Terminal: no rename tool exists, so the hook sets the title itself from
    # the prompt's own words, through the hook output's sessionTitle field.
    mode = (cfg.get("terminal") or "untitled").lower()
    if mode == "off":
        return
    titled, _earlier = transcript_state(data.get("transcript_path"), prompt)
    if titled and mode != "always":
        return
    title = title_from_prompt(prompt, lang)
    if not title:
        return
    remember(title)
    print(json.dumps({
        "suppressOutput": True,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "sessionTitle": title,
        },
    }, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # never block a prompt

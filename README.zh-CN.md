# claude-fork-rename

[English](README.md) · 中文

给 Claude Code 桌面版 fork 出来的会话起个自己的名字。

Fork 一个会话，新会话直接继承父会话的名字，后面加个 `(fork)` / `(fork 2)`。
Fork 几次之后，侧边栏就是一排一模一样的行：

```
今天
  Checkout 重构 (fork)
  Checkout 重构 (fork)
  Checkout 重构 (fork 2)
  Checkout 重构 (fork)
  Checkout 重构 (fork)
```

装上之后，每个 fork 在**第一条有内容的 prompt** 上给自己换个名字：

```
今天
  前端 · 购物车空态
  前端 · 表单校验提示
  接口 · 退款回调超时
  部署 · 灰度开关读不到
  CI · 缓存命中率太低
```

## 怎么装

三条路，任选一条。

**当插件装** —— 在会话里一条命令（Claude Code 2.1.275 及以后）：

```
/plugin install fork-rename --marketplace ShadowNearby/claude-fork-rename
```

更早的版本分两步：

```
/plugin marketplace add ShadowNearby/claude-fork-rename
/plugin install fork-rename@claude-fork-rename
```

**一行命令**（在终端里）：

```bash
curl -fsSL https://raw.githubusercontent.com/ShadowNearby/claude-fork-rename/main/install.sh | bash
```

**克隆下来装**，顺带拿到 `fork-topics.py`：

```bash
git clone https://github.com/ShadowNearby/claude-fork-rename
cd claude-fork-rename && ./install.sh
```

插件那条路把 hook 留在插件自己里面并从那儿注册，你的 `settings.json` 除了多一个
「插件已启用」之外什么都不变。脚本那两条路是装进你的 Claude 配置目录
（`$CLAUDE_CONFIG_DIR`，默认 `~/.claude`）：

| 文件 | 作用 |
| --- | --- |
| `hooks/fork-rename.py` | hook 本体，只用标准库 |
| `settings.json` | 加一条 `UserPromptSubmit` 记录（改前自动备份） |
| `fork-rename.json` | 配置，已存在就不动 |

两种都是**新开的会话**才生效，也都读同一份 `~/.claude/fork-rename.json`。卸载：
`/plugin uninstall fork-rename`，或者 `./install.sh --uninstall`（只摘自己那条）。

## 配置

`~/.claude/fork-rename.json`，全部可选。看当前生效的值：

```bash
python3 ~/.claude/hooks/fork-rename.py --print-config
```

```jsonc
{
  // 标题长什么样，三种任选
  //   "domain"  →  "前端 · 购物车空态"      领域在前，同模块的会话挨在一起
  //   "topic"   →  "购物车空态"             最短，看不出来源
  //   "parent"  →  "Checkout 重构 · 购物车空态"   带父会话名字，血缘最清楚
  "style": "domain",

  // 终端（非桌面版）会话怎么处理，见下面「终端里怎么起名」一节
  //   "untitled" 还没有标题的才起名（默认，涵盖新会话和 --fork-session）
  //   "always"   连已经有标题的也改（--resume 回去换了话题的场景）
  //   "off"      不碰终端会话
  "terminal": "untitled",

  // "domain" 风格下给模型的领域例子。写你自己真正在做的模块，
  // 留空它就按手头项目自己判断。
  "domains": ["前端", "接口", "数据库", "部署", "CI", "文档"],

  // 指令和标题用什么语言："zh" / "en" / "auto"（跟着 prompt 走）
  "language": "auto",

  // 短于这个长度的 prompt 跳过（只贴一张图就属于这种）
  "min_prompt_chars": 4,

  // 以这些开头的 prompt 跳过
  "skip_prefixes": ["/", "!"],

  // 追加到内置的「继续 / ok / 好的」这类词表里
  "extra_filler": [],

  // 每个会话只提醒一次。false = 只要名字还像继承来的就一直提醒
  "remind_once": true
}
```

### 为什么默认是「领域 · 具体事」

这个默认值是试出来的，三版：

1. **`父名 · 话题`** —— 一屏的行开头全是同一个父会话名，区分度被挤到最右边，等于没有。
2. **只写话题** —— 短了，但同一个项目里的事挤在一起：三个「…页」摆在一块还是得点进去看。
3. **`领域 · 具体事`** —— 最有用的词排在最前面，侧边栏按名字排序时同模块自动连成一段。

还有人提过用 `#` / `##` 标 fork 层级。真用下来层级这一维信息量最小：绝大多数 fork 都是一级的，
标完还是一排 `#`。所以默认不带层级，血缘交给 app 自己记的 `startedBy`。

不喜欢就换 `style`，或者直接改脚本里 `title_spec()` 那几行。

## 终端里怎么起名

终端里的 `claude` 没有 `set_session_title` 这个工具（那边改名是你自己敲 `/rename`），
所以 hook 不去求模型，而是**自己写标题**：往 hook 输出里塞
`hookSpecificOutput.sessionTitle`，标题从 prompt 自己的话里截一句（去掉代码块、URL、
长路径和「帮我 / please」这类开场，切到第一个句读，中文 24 字 / 英文 7 词以内）。

```
$ claude            # 新会话，第一条 prompt
> 购物车空的时候那块白屏，加个空态
  → 标题变成「购物车空的时候那块白屏」
```

几个实测出来的行为，值得先知道：

- **`--fork-session` 出来的 fork 会被起名**，尽管它继承了父会话的标题。原因是 transcript
  延迟写入：第一条 prompt 提交时 fork 的新文件还没落盘，hook 看到的是「还没有标题」。
  （把 hook 关掉再 fork，就能看到它确实继承了父会话的名字。）
- **`--resume` 回去的会话不会被改名**：那个文件早就在，标题也在，默认档会跳过。想让它也
  跟着新话题改，把 `terminal` 设成 `always`。
- 和桌面版那条路不同，终端这条**分不出「继承来的名字」和「你手工起的名字」**（前者在那一刻
  看不见），所以 fork 一个你精心命名过的会话，终端这边也会按新 prompt 重起一个名字。
- `sessionTitle` 这个字段官方只在 `SessionStart` 下列过，在 `UserPromptSubmit` 下是
  实测可用、**没有文档保证**的行为。哪天失效了，终端这档就退化成什么都不做（桌面版不受影响）。

## 侧边栏里已经攒下的 fork

hook 只管新的。已经在列表里的那些，先看看它们各自干了什么：

```bash
python3 fork-topics.py               # 名字还是继承来的 fork
python3 fork-topics.py --days 14     # 只看最近两周动过的
python3 fork-topics.py --scope forks # 凡是把历史抄进来的会话都列
python3 fork-topics.py <uuid> ...    # 只看这几个
```

```
========================================================================
3c7f91a2  Checkout 重构 (fork)
   ~/.claude/projects/-Users-me-code-thing/3c7f91a2-….jsonl
   用户/user 1: 购物车空的时候那块白屏，加个空态
   助手/asst 1: The empty-cart branch renders nothing; adding the empty state…
========================================================================
共 1 个 / 1 shown
```

然后手工改，或者把这段输出丢给 Claude 让它批量调 `set_session_title`。

两点需要知道：

- fork 的第一条 prompt 常常只是一张截图、没有文字，这时候话题得从助手的回答里看 ——
  所以上面两种行都会打印。
- 老会话、归档过的会话，transcript 还留在磁盘上，名字也还是 `(fork)`，所以默认这档会把它们
  一起列出来。想只看最近的用 `--days`；想确认某个还在不在侧边栏里，让 Claude 查一下它的
  `isArchived` 就行。

## 原理

- **桌面版的** fork，transcript 开头是父会话历史的副本，**那些行保留父会话的 `sessionId`**，
  只有 fork 自己的行带自己的 id。所以「这个 fork 自己干了什么」= 过滤出
  `sessionId == 文件名` 的行。`fork-topics.py` 全靠这一条。
  （反过来不成立：首行 id 不是自己只说明历史是抄进来的，resume 和 compact 也会这样，
  所以默认按名字筛，而不是按这个判断。CLI 的 `--fork-session` 又不一样，它把抄过来的行
  全改成新会话的 id，所以这个办法只对桌面版的 fork 有效。）
- hook 判断「名字还是继承来的」= 会话在 `~/.claude/sessions/<pid>.json` 里的 `name`
  以 `(fork)` / `(fork N)` 结尾。你手工改过的名字不以此结尾，所以不会被碰。
- 改名**不是脚本偷偷干的**：hook 只往上下文里塞一段指令，由模型调用桌面 app 自己的
  `mcp__ccd_session_mgmt__set_session_title`，权限照 app 的规矩走。
- 触发过的会话在 `~/.claude/fork-rename/<session id>` 留个标记，所以每个会话最多提醒一次 ——
  万一改名被拒，它不会每条 prompt 都来烦你。

## 边界

- **桌面版和终端走两条路**：桌面版（Code tab）有 `set_session_title`，hook 让模型调它，
  名字由模型概括，只在「名字还是继承来的」时动手；终端里没这个工具，hook 自己用
  `sessionTitle` 字段写标题，名字从 prompt 截，判断条件是「还没有标题」。
- **新会话生效**；改设置前就开着的会话不保证热加载。
- 云端会话、SSH 会话读不到你本机的 `~/.claude`，跟着那台机器的配置走。
- 每条 prompt 都会跑一次这个脚本，大约 60 ms，不是 fork 就一声不响退出。
- 出任何意外都静默退出，不会卡住你的 prompt。

## License

MIT

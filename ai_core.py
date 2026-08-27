# -*- coding: utf-8 -*-
"""
tavern-android / ai_core.py —— 酒馆版（desktop-pet-tavern）纯 Python 内核，零第三方依赖。
供 Kivy 手机端复用：世界书 / BM25 记忆 / 分页摘要压缩 / 互动小说 / 角色卡导入 / OpenAI 兼容流式。

来源：desktop-pet-tavern/main.py 抽取改造（只保留纯逻辑，去掉全部 Qt/UI）。
桌面版改动不影响本文件；本文件改动也不影响桌面版。
"""
import os
import sys
import re
import json
import math
import ssl
import time
import threading
import urllib.request

try:
    import certifi
except Exception:
    # Desktop/minimal environments may not have certifi installed.  In that
    # case the request path below falls back to the platform SSL store.
    certifi = None

# --------------------------------------------------------------------------- #
# 路径：Android 使用 python-for-android 提供的 app 私有目录；桌面测试时指向用户目录
# --------------------------------------------------------------------------- #


def _default_app_dir():
    """Return a writable per-app directory on Android, with a desktop fallback.

    Android does not guarantee that ``expanduser("~")`` is writable.  On the
    MuMu device it resolves to ``/data``, which caused the first screen to
    crash when HistoryManager tried to create ``/data/.tavern_pet``.
    """
    try:
        from android.storage import app_storage_path

        base_dir = app_storage_path()
        if base_dir:
            return os.path.join(base_dir, ".tavern_pet")
    except Exception:
        # The android module is unavailable during desktop development/tests,
        # and older python-for-android versions may not expose this helper.
        pass

    # python-for-android exposes this path in the environment as a fallback.
    base_dir = os.environ.get("ANDROID_APP_PATH")
    if base_dir:
        return os.path.join(base_dir, ".tavern_pet")

    return os.path.join(os.path.expanduser("~"), ".tavern_pet")


APP_DIR = _default_app_dir()
HISTORY_DIR = os.path.join(APP_DIR, "history")
WORLDBOOK_DIR = os.path.join(APP_DIR, "worldbooks")
SUMMARY_FILE = os.path.join(HISTORY_DIR, "summaries.json")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #
PAGE_SIZE = 50          # 每页消息条数上限，达到即翻页并生成摘要
MERGE_EVERY = 10        # 每累计这么多条独立页摘要，合并成一条合并摘要
WORLDVIEW_MAX_CHARS = 2000
APPEARANCE_MAX_CHARS = 2000
BM25_TOP_K = 6
BM25_MAX_DOC_CHARS = 400
BM25_MIN_DOC_CHARS = 4
BM25_MAX_DF = 3         # 被动注入相关性门限：top 文档需命中至少一个「具体词」

# 人设 / 世界观 / 去 AI 味 / 小说 常量（与桌面版一致）
REASON_IN_CHARACTER = (
    "在思考链中，你必须以角色的第一人称内心独白进行思考，"
    "完全进入角色，用角色的口吻和视角去感受和反应，"
    "思考过程就是角色的心理活动，不要说教，不要脱离角色。"
)

REASON_ANALYTICAL = (
    "在思考链中，用第三人称分析当前对话，拆解用户意图与角色反应，"
    "给出简短分析，不做角色扮演。"
)

DELAI_RULES = (
    "写作要求（请严格遵守）："
    "1. 对白简短自然，像真人聊天，不要写长篇大论。"
    "2. 每行对白尽量不超过 20 字，必要时用短句分行。"
    "3. 避免生硬的书面语、套话和 AI 腔（如「作为」「总的来说」「希望你能」）。"
    "4. 用行动和细节代替形容词。"
    "5. 情绪通过动作和语气表现，不要直接说「我很开心」这类直白标签。"
    "6. 不要给对话加小标题、编号或 Markdown 符号。"
    "7. 不要每段都加总结句；一句话能说清就不展开。"
    "8. 不要重复对方的话，也不要复述自己的上一句。"
    "9. 对话要自然衔接，不要突然跳题或开始说教。"
    "10. 不要为显得自然硬塞网络用语，保持角色人设与口吻一致。"
)

TAVERN_SYSTEM = (
    "你是沉浸式互动小说的叙述引擎（Adventure Mode）。"
    "用第二人称叙述，兼扮演场景中所有角色与 NPC。"
    "用户输入以「>」开头，表示其行动或对话，你据此推演剧情。"
    "每次结尾给出 2~4 个带编号的选项（1. 2. 3. ...），"
    "再加一行「自由输入：> 自由行动」供玩家自拟行动。"
    "用环境、动作、对白推动剧情，保持世界观一致性，不要替用户做决定。"
)

PHI_CHAT = (
    "【核心规则提醒】保持你的人设、世界观与玩家身份一致；"
    "不要出戏、不要替用户做决定、不要重复已知信息。"
)

PHI_TAVERN = (
    "【核心规则提醒】你是叙述引擎：第二人称叙事、兼扮 NPC、"
    "结尾给 2~4 个编号选项 + 自由输入。"
)

PERSONA_EXAMPLE = (
    "【他是谁】\n一个温柔的邻家少女，说话轻声细语，偶尔害羞。\n\n"
    "【怎么说话】\n句尾爱加呀、嗯、~，用词口语化，情绪自然。\n\n"
    "【和你的关系】\n你是她从小一起长大的青梅竹马，她习惯依赖你。"
)

PERSONA_EXAMPLE_XML = (
    "<小橘>\n"
    "job: 小橘 is a cafe cat girl.\n"
    "appearance: 小橘 has orange hair, green eyes, wears a white apron.\n"
    "personalities: 温柔, 好奇, 爱笑\n"
    "skills: 泡咖啡, 讲冷笑话\n"
    "</小橘>\n\n"
    "Characters behave based on their personalities."
)

PERSONA_EXAMPLE_PLIST = (
    "[小橘的外貌: 头发（橙色，双马尾），眼睛（绿色），穿着（白色围裙）;\n"
    " 标签: 咖啡店, 治愈, 日常;\n"
    " 场景: 小橘在咖啡店吧台后与 {{user}} 相遇;\n"
    " 性格: 温柔，好奇，爱笑，爱好（泡咖啡，讲冷笑话）]"
)


def _strip_tavern_phrases(s):
    """去掉世界观里压制长叙事的「简洁口语化」等聊天专用指令。"""
    for p in ("用简洁口语化中文回应主人", "简洁口语化", "请始终以此世界观展开对话与行为"):
        s = s.replace(p, "")
    return s.strip("，。 ,.；;")


def assemble_player_prompt(fields):
    """把玩家身份表单字段拼成 prompt；全部为空时返回 ''。"""
    name = (fields.get("name") or "").strip()
    gender = (fields.get("gender") or "").strip()
    age = (fields.get("age") or "").strip()
    appearance = (fields.get("appearance") or "").strip()
    traits = [str(t).strip() for t in (fields.get("traits") or []) if str(t).strip()]
    relation = (fields.get("relation") or "").strip()
    extra = (fields.get("extra") or "").strip()
    lines = []
    if name:
        lines.append("姓名：" + name)
    if gender:
        lines.append("性别：" + gender)
    if age:
        lines.append("年龄：" + age)
    if appearance:
        lines.append("外貌：" + appearance)
    if traits:
        lines.append("性格：" + "、".join(traits))
    if relation:
        lines.append("与角色的关系：" + relation)
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def _apply_worldbook_budget(entries, budget_cap):
    """世界书 token 预算：budget_cap>0 时按 蓝灯>绿灯、order 大者优先 保留，超限丢弃。"""
    if not entries or not int(budget_cap or 0):
        return entries
    ranked = sorted(
        entries,
        key=lambda e: (0 if e.get("status") == "blue" else 1, -(int(e.get("order", 100) or 0))),
    )
    kept, used = [], 0
    for e in ranked:
        cost = len(e.get("content") or "")
        if used + cost > int(budget_cap):
            continue
        kept.append(e)
        used += cost
    return kept


def effect_panel_text(cfg):
    """参数生效面板：说明哪些采样参数真正传给了 API、哪些未支持。"""
    lines = [
        "✅ 已生效（会真正发给 API）：",
        " · temperature = %s" % cfg.get("temperature"),
        " · model = %s" % cfg.get("model"),
        " · stream = 流式开启",
        " · enable_thinking = %s" % ("开" if cfg.get("enable_thinking") else "关"),
    ]
    if cfg.get("enable_search_tool"):
        lines.append(" · enable_search_tool = 开（AI 可调 search_history 工具）")
    lines.append("")
    lines.append("⚠️ 未支持（本软件不提供、也不会发送）：")
    for k in ("top_p", "top_k", "frequency_penalty", "presence_penalty",
              "repetition_penalty", "min_p", "typical_p", "max_tokens"):
        lines.append(" · %s" % k)
    lines.append("")
    lines.append("提示：总上下文建议控制在 6 万 token 以内（留足注意力预算）。")
    lines.append("其余设置（人设 / 世界书 / 玩家身份 / 示例对话 / 去AI味 等）"
                 "用于构造上下文，属「提示词层」而非「采样参数」，均已生效。")
    return "\n".join(lines)


def parse_choices(text):
    """从 AI 输出末尾解析「编号选项 + 自由输入」块，返回 (叙事正文, 选项列表)。"""
    if not text:
        return text, []
    lines = text.split("\n")
    anchor = None
    for i in range(len(lines) - 1, -1, -1):
        if "自由输入" in lines[i]:
            anchor = i
            break
    if anchor is None:
        anchor = len(lines)
    choices = []
    first_choice = None
    j = anchor - 1
    while j >= 0:
        s = lines[j].strip()
        if not s:
            j -= 1
            continue
        m = re.match(r"^(\d+)[.、)）]\s*(.+)$", s)
        if m:
            choices.insert(0, m.group(2).strip())
            first_choice = j
            j -= 1
        else:
            break
    if first_choice is None or len(choices) < 2:
        return text, []
    narr_lines = lines[:first_choice]
    while narr_lines and re.match(r"^[\s\-—*=_]*$", narr_lines[-1]):
        narr_lines.pop()
    narrative = "\n".join(narr_lines).rstrip()
    return narrative, choices


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
DEFAULT_CFG = {
    "base_url": "https://api.deepseek.com",
    "api_key": "",
    "model": "deepseek-v4-flash",
    "temperature": 0.8,
    "persona_prompt": ("【PERSONA_LOAD】cat_LOLI MODE_long_cat_TAIL LANG_ZH_CN_ONLY "
                       "SELF_claim_cat_GIRL FOOD_LOVE PERSONALITY_LAZY_girl "
                       "PERSONALITY_TSUNDERE_SWEET OBEY_MASTER_ALWAYS "
                       "TRAIT_LOVE_MASTER_FOREVER_acknowledge TIMEOUT_SIGNAL"),
    "worldview_prompt": ("你是一只被主人收养的猫娘，生活在人类与猫娘共存的世界。"
                         "保留猫耳与猫尾，习性半猫半人：慵懒爱睡、怕水爱鱼、粘人又傲娇。"
                         "请始终以此世界观展开对话与行为，用简洁口语化中文回应主人。"),
    "player_identity": "",
    "appearance_prompt": "",
    "dialogue_examples": "",
    "opening_message": "",
    "raw_prefix": "",
    "enable_thinking": False,
    "thinking_style": "in_character",
    "enable_bm25": True,
    "bm25_top_k": 6,
    "enable_search_tool": True,
    "enable_delai": False,
    "tavern_mode": False,
    "pet_name": "🐾 小桌",
    "model_source": "cloud",
}


def load_config():
    cfg = dict(DEFAULT_CFG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    if "system_prompt" in cfg and not cfg.get("worldview_prompt"):
        cfg["worldview_prompt"] = cfg["system_prompt"]
    cfg.pop("system_prompt", None)
    return cfg


def save_config(cfg):
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("保存配置失败:", e)


# --------------------------------------------------------------------------- #
# 世界书（Lorebook）：数据模型 + JSON 存储 + 匹配引擎
# --------------------------------------------------------------------------- #
_VALID_LOGIC = ("AND", "OR", "NOT")
_VALID_STATUS = ("blue", "green", "red")
_VALID_POSITION = ("before_char", "after_char", "before_an", "after_an", "depth")


def default_entry():
    return {
        "title": "未命名条目", "content": "", "memo": "",
        "primary_keywords": [], "use_regex": False, "logic": "OR",
        "optional_keywords": [], "status": "green", "position": "before_char",
        "depth": 4, "order": 100,
    }


def default_worldbook(name="默认世界书", scope="character"):
    return {
        "name": name, "scope": scope, "active": True,
        "char_strategy": "global_first", "scan_depth": 2, "recursive": True,
        "case_sensitive": False, "match_whole_words": False,
        "content_percent": 25, "budget_cap": 0, "alert_overflow": False,
        "entries": [],
    }


def validate_entry(e):
    out = default_entry()
    if isinstance(e, dict):
        out.update(e)
    out["primary_keywords"] = [str(k).strip() for k in (out.get("primary_keywords") or [])
                               if str(k).strip()]
    out["optional_keywords"] = [str(k).strip() for k in (out.get("optional_keywords") or [])
                                if str(k).strip()]
    if out.get("logic") not in _VALID_LOGIC:
        out["logic"] = "OR"
    if out.get("status") not in _VALID_STATUS:
        out["status"] = "green"
    if out.get("position") not in _VALID_POSITION:
        out["position"] = "before_char"
    for k in ("depth", "order"):
        try:
            out[k] = int(out.get(k))
        except (TypeError, ValueError):
            out[k] = default_entry()[k]
    out["use_regex"] = bool(out.get("use_regex", False))
    out["title"] = str(out.get("title") or "未命名条目")
    out["content"] = str(out.get("content") or "")
    out["memo"] = str(out.get("memo") or "")
    return out


def validate_worldbook(wb):
    out = default_worldbook()
    if isinstance(wb, dict):
        out.update(wb)
    out["name"] = (str(out.get("name") or "").strip() or "默认世界书")
    if out.get("scope") not in ("global", "character"):
        out["scope"] = "character"
    out["active"] = bool(out.get("active", True))
    if out.get("char_strategy") not in ("char_first", "global_first"):
        out["char_strategy"] = "global_first"
    for k in ("scan_depth", "content_percent", "budget_cap"):
        try:
            out[k] = int(out.get(k))
        except (TypeError, ValueError):
            out[k] = 0
    for k in ("recursive", "case_sensitive", "match_whole_words", "alert_overflow"):
        out[k] = bool(out.get(k, False))
    entries = out.get("entries") or []
    if not isinstance(entries, list):
        entries = []
    out["entries"] = [validate_entry(e) for e in entries]
    return out


def _worldbook_path(name):
    safe = re.sub(r'[\\/:*?"<>|]', "_", str(name)).strip() or "worldbook"
    return os.path.join(WORLDBOOK_DIR, safe + ".json")


def save_worldbook(wb):
    wb = validate_worldbook(wb)
    os.makedirs(WORLDBOOK_DIR, exist_ok=True)
    with open(_worldbook_path(wb["name"]), "w", encoding="utf-8") as f:
        json.dump(wb, f, ensure_ascii=False, indent=2)
    return wb


def load_worldbooks():
    books = []
    if not os.path.isdir(WORLDBOOK_DIR):
        return books
    for fn in sorted(os.listdir(WORLDBOOK_DIR)):
        if not fn.lower().endswith(".json"):
            continue
        try:
            with open(os.path.join(WORLDBOOK_DIR, fn), "r", encoding="utf-8") as f:
                data = json.load(f)
            books.append(validate_worldbook(data))
        except Exception as e:
            print("加载世界书失败（已跳过 %s）: %s" % (fn, e))
    return books


def delete_worldbook(name):
    p = _worldbook_path(name)
    if os.path.exists(p):
        try:
            os.remove(p)
            return True
        except Exception:
            return False
    return False


def migrate_worldview_to_worldbook(cfg):
    """向后兼容：worldbooks/ 无任何世界书且旧 worldview_prompt 非空时，迁成一条蓝灯条目。"""
    if os.path.isdir(WORLDBOOK_DIR) and any(
            fn.lower().endswith(".json") for fn in os.listdir(WORLDBOOK_DIR)):
        return False
    wv = (cfg.get("worldview_prompt") or "").strip()
    if not wv:
        return False
    wb = default_worldbook("默认世界书", "character")
    wb["entries"] = [{
        "title": "默认世界观（迁移自旧 worldview）",
        "content": wv, "status": "blue", "position": "after_char", "order": 100,
    }]
    try:
        save_worldbook(wb)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# 分页历史 + 摘要
# --------------------------------------------------------------------------- #
def page_path(n):
    return os.path.join(HISTORY_DIR, "page_%04d.json" % n)


def load_page_file(n):
    p = page_path(n)
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def save_page_file(n, msgs):
    try:
        os.makedirs(HISTORY_DIR, exist_ok=True)
        with open(page_path(n), "w", encoding="utf-8") as f:
            json.dump(msgs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("保存分页失败:", e)


def load_summaries():
    if os.path.exists(SUMMARY_FILE):
        try:
            with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                if "blocks" in data and isinstance(data["blocks"], list):
                    return [b for b in data["blocks"] if isinstance(b, dict)]
                if "pages" in data and isinstance(data["pages"], dict):
                    blocks = []
                    for k, v in data["pages"].items():
                        try:
                            pn = int(k)
                        except Exception:
                            continue
                        if v:
                            blocks.append({"type": "page", "page": pn, "text": v})
                    blocks.sort(key=lambda b: b["page"])
                    return blocks
        except Exception:
            pass
    return []


def save_summaries(blocks):
    try:
        os.makedirs(HISTORY_DIR, exist_ok=True)
        with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
            json.dump({"blocks": blocks}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("保存摘要失败:", e)


# --------------------------------------------------------------------------- #
# 角色卡导入（SillyTavern v1/v2 JSON 或嵌 chara 的 PNG）
# --------------------------------------------------------------------------- #
def _extract_chara_png(raw):
    import base64
    try:
        if raw[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        i = 8
        while i + 8 <= len(raw):
            length = int.from_bytes(raw[i:i + 4], "big")
            ctype = raw[i + 4:i + 8].decode("ascii", errors="replace")
            data = raw[i + 8:i + 8 + length]
            if ctype == "tEXt":
                sep = data.find(b"\x00")
                if sep != -1:
                    key = data[:sep].decode("ascii", errors="replace")
                    val = data[sep + 1:]
                    if key == "chara":
                        try:
                            txt = base64.b64decode(val).decode("utf-8", errors="replace")
                            return json.loads(txt)
                        except Exception:
                            return None
            i += 8 + length + 4
        return None
    except Exception:
        return None


def load_character_card(path):
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except Exception:
        return None
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        js = _extract_chara_png(raw)
    else:
        try:
            js = json.loads(raw.decode("utf-8", errors="replace"))
        except Exception:
            return None
    if not isinstance(js, dict):
        return None
    data = js.get("data") if isinstance(js.get("data"), dict) else js
    name = (data.get("name") or js.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    personality = (data.get("personality") or "").strip()
    scenario = (data.get("scenario") or "").strip()
    description = re.sub(r"</?html>", "", description, flags=re.IGNORECASE).strip()
    persona = description
    if personality:
        persona = (persona + "\n\n" + personality).strip() if persona else personality
    persona = persona[:WORLDVIEW_MAX_CHARS]
    scenario = scenario[:WORLDVIEW_MAX_CHARS]
    return {"name": name, "persona": persona, "scenario": scenario}


# --------------------------------------------------------------------------- #
# BM25（零依赖中文友好分词 + Okapi BM25）
# --------------------------------------------------------------------------- #
def tokenize(text):
    if not text:
        return []
    t = text.lower()
    toks = [m.group(0) for m in re.finditer(r"[a-z0-9]+", t)]
    cjk = [c for c in t if "\u4e00" <= c <= "\u9fff"]
    toks.extend(cjk)
    for i in range(len(cjk) - 1):
        toks.append(cjk[i] + cjk[i + 1])
    return toks


class BM25Index:
    def __init__(self, docs_tokens, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.docs = docs_tokens
        self.N = len(docs_tokens)
        self.avgdl = (sum(len(d) for d in docs_tokens) / self.N) if self.N else 0.0
        df = {}
        for d in docs_tokens:
            for w in set(d):
                df[w] = df.get(w, 0) + 1
        self.idf = {w: math.log((self.N - f + 0.5) / (f + 0.5) + 1.0)
                    for w, f in df.items()}
        self.df = df
        self.tf = []
        for d in docs_tokens:
            c = {}
            for w in d:
                c[w] = c.get(w, 0) + 1
            self.tf.append(c)

    def search(self, query_tokens, top_k=BM25_TOP_K):
        results = []
        for i in range(self.N):
            score = 0.0
            dl = len(self.docs[i])
            tf = self.tf[i]
            for w in query_tokens:
                idf = self.idf.get(w)
                if idf is None:
                    continue
                f = tf.get(w, 0)
                if f == 0:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * (dl / self.avgdl if self.avgdl else 1))
                score += idf * (f * (self.k1 + 1)) / denom
            if score > 0:
                results.append((i, score))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]


SEARCH_HISTORY_TOOL = {
    "type": "function",
    "function": {
        "name": "search_history",
        "description": (
            "检索与问题相关的历史对话片段（跨所有过往聊天记录）。"
            "当需要回忆用户之前提过的人、事、设定、偏好、约定或任何旧话题时使用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索关键词或问题，尽量具体"},
                "top_k": {"type": "integer", "description": "返回条数，默认 5", "default": 5},
            },
            "required": ["query"],
        },
    },
}


def search_history(query, top_k=5):
    """扫描全部历史分页，用 BM25 召回与 query 最相关的消息，返回格式化文本。"""
    query = (query or "").strip()
    if not query:
        return "（检索词为空）"
    docs = []
    if os.path.exists(HISTORY_DIR):
        for fn in sorted(os.listdir(HISTORY_DIR)):
            if not (fn.startswith("page_") and fn.endswith(".json")):
                continue
            try:
                n = int(fn[5:-5])
            except Exception:
                continue
            for m in load_page_file(n):
                c = (m.get("content") or "").strip()
                if len(c) < BM25_MIN_DOC_CHARS:
                    continue
                docs.append({"page": n, "role": m.get("role"), "content": c})
    if not docs:
        return "（没有可检索的历史记录）"
    idx = BM25Index([tokenize(d["content"]) for d in docs])
    hits = idx.search(tokenize(query), top_k)
    lines = []
    for di, _ in hits:
        d = docs[di]
        role = ("用户" if d["role"] == "user"
                else "AI" if d["role"] == "assistant" else d["role"])
        content = d["content"]
        if len(content) > BM25_MAX_DOC_CHARS:
            content = content[:BM25_MAX_DOC_CHARS] + "…"
        lines.append("【第 %d 页 · %s】%s" % (d["page"], role, content))
    return "\n\n".join(lines) if lines else "（未检索到相关内容）"


# --------------------------------------------------------------------------- #
# API 流式调用（OpenAI 兼容，标准库 urllib）
# --------------------------------------------------------------------------- #
def _ssl_context():
    """Build a verifying context that works with Android's bundled Python.

    Android's system CA store is not consistently visible to the OpenSSL
    runtime shipped inside python-for-android.  certifi supplies a portable
    Mozilla CA bundle, while the default context remains the fallback for
    desktop and platform-managed environments.
    """
    if certifi is not None:
        try:
            cafile = certifi.where()
            if cafile and os.path.isfile(cafile):
                return ssl.create_default_context(cafile=cafile)
        except Exception as e:
            print('内置 CA 证书加载失败，回退到系统证书:', e)
    try:
        return ssl.create_default_context()
    except Exception as e:
        print('系统 CA 证书加载失败，使用 urllib 默认校验:', e)
        return None


def _stream_once(messages, cfg, tools, on_token=None, on_reasoning=None):
    base = (cfg.get("base_url") or "").rstrip("/")
    url = base + "/chat/completions"
    model_name = str(cfg.get("model") or "gpt-3.5-turbo").strip()
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": True,
        "temperature": float(cfg.get("temperature", 0.8)),
    }
    if cfg.get("enable_thinking"):
        payload["thinking"] = {"type": "enabled"}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
        if model_name.lower() == "gpt-5.6-luna":
            payload["reasoning_effort"] = "none"
    if cfg.get("model_source") != "local":
        payload["stream_options"] = {"include_usage": True}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    api_key = cfg.get("api_key") or ""
    if cfg.get("model_source") == "local" and not api_key:
        api_key = "ollama"
    req.add_header("Authorization", "Bearer " + api_key)
    tool_calls = []
    last_usage = None
    context = _ssl_context()
    if context is None:
        response = urllib.request.urlopen(req, timeout=120)
    else:
        response = urllib.request.urlopen(req, timeout=120, context=context)
    with response as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                obj = json.loads(chunk)
            except Exception:
                continue
            u = obj.get("usage")
            if isinstance(u, dict):
                last_usage = u
            try:
                delta = obj["choices"][0]["delta"]
            except Exception:
                continue
            reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
            token = delta.get("content") or ""
            if reasoning and on_reasoning:
                on_reasoning(reasoning)
            if token and on_token:
                on_token(token)
            for tc in (delta.get("tool_calls") or []):
                idx = tc.get("index", 0)
                while len(tool_calls) <= idx:
                    tool_calls.append({"id": "", "type": "function",
                                       "function": {"name": "", "arguments": ""}})
                if tc.get("id"):
                    tool_calls[idx]["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    tool_calls[idx]["function"]["name"] = fn["name"]
                if fn.get("arguments"):
                    tool_calls[idx]["function"]["arguments"] += fn["arguments"]
    return tool_calls, last_usage


def run_model_session(messages, cfg, on_token=None, on_reasoning=None, max_rounds=4):
    """执行一次完整模型会话（含工具往返），返回 (text, reasoning, usage)。"""
    tools = [SEARCH_HISTORY_TOOL] if cfg.get("enable_search_tool", True) else None
    full_text, full_reasoning = [], []
    acc_usage = {"prompt_tokens": 0, "completion_tokens": 0,
                 "total_tokens": 0, "turns": 0}
    msgs = [dict(m) for m in messages]

    def _on_token(t):
        if on_token:
            on_token(t)
        full_text.append(t)

    def _on_reasoning(r):
        if on_reasoning:
            on_reasoning(r)
        full_reasoning.append(r)

    for _ in range(max_rounds):
        tool_calls, usage = _stream_once(msgs, cfg, tools, _on_token, _on_reasoning)
        if usage:
            acc_usage["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
            acc_usage["completion_tokens"] += int(usage.get("completion_tokens") or 0)
            acc_usage["total_tokens"] += int(usage.get("total_tokens") or 0)
            acc_usage["turns"] += 1
        if not tool_calls:
            break
        msgs.append({
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls,
        })
        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            args_str = fn.get("arguments") or "{}"
            try:
                args = json.loads(args_str) if args_str.strip() else {}
            except Exception:
                args = {}
            if name == "search_history":
                q = (args.get("query") or "").strip()
                try:
                    k = int(args.get("top_k", 5) or 5)
                except Exception:
                    k = 5
                result = search_history(q, k)
            else:
                result = "（未知工具：%s）" % name
            msgs.append({
                "role": "tool",
                "tool_call_id": tc.get("id"),
                "content": result,
            })
    return "".join(full_text), "".join(full_reasoning), acc_usage


# --------------------------------------------------------------------------- #
# 世界书匹配引擎（模块函数）
# --------------------------------------------------------------------------- #
def _worldbook_scan_text(messages, scan_depth):
    msgs = [m for m in (messages or []) if m.get("role") in ("user", "assistant")]
    n = max(int(scan_depth or 0), 1) * 2
    recent = msgs[-n:]
    return "\n".join((m.get("content") or "") for m in recent)


def _match_entry(e, text):
    keys = e.get("primary_keywords") or []
    opt = e.get("optional_keywords") or []
    logic = e.get("logic") or "OR"
    use_regex = e.get("use_regex", False)

    def hit(word):
        if use_regex:
            try:
                return re.search(word, text) is not None
            except re.error:
                return word in text
        return word in text

    if not keys:
        return False
    hits = [hit(k) for k in keys]
    if logic == "AND":
        return all(hits)
    if logic == "NOT":
        return any(hits) and not any(hit(o) for o in opt)
    return any(hits)


def collect_worldbook_entries(cfg, messages):
    """加载并匹配世界书，返回 {bucket: [...]}；bucket ∈ before_char/after_char/after_an/depth。"""
    buckets = {"before_char": [], "after_char": [], "after_an": [], "depth": []}
    tavern = bool(cfg.get("tavern_mode", False))
    for wb in load_worldbooks():
        if not wb.get("active", True):
            continue
        scan_depth = int(wb.get("scan_depth", 2) or 0)
        scan_text = None
        matched = []
        for e in wb.get("entries", []):
            status = e.get("status", "green")
            if status == "red":
                continue
            if status == "green":
                if scan_text is None:
                    scan_text = _worldbook_scan_text(messages, scan_depth)
                if not _match_entry(e, scan_text):
                    continue
            content = (e.get("content") or "").strip()
            if tavern:
                content = _strip_tavern_phrases(content)
                if content == _strip_tavern_phrases(DEFAULT_CFG.get("worldview_prompt") or ""):
                    content = ""
            if not content:
                continue
            e2 = dict(e)
            e2["content"] = content
            matched.append(e2)
        matched = _apply_worldbook_budget(matched, wb.get("budget_cap", 0))
        for e in matched:
            pos = e.get("position", "before_char")
            if pos == "depth":
                buckets["depth"].append((int(e.get("depth", 4) or 0), e["content"]))
            elif pos == "before_char":
                buckets["before_char"].append((int(e.get("order", 100) or 0), e["content"]))
            elif pos in ("after_char", "before_an"):
                buckets["after_char"].append((int(e.get("order", 100) or 0), e["content"]))
            else:
                buckets["after_an"].append((int(e.get("order", 100) or 0), e["content"]))
    for k in ("before_char", "after_char", "after_an"):
        buckets[k] = [c for _, c in sorted(buckets[k], key=lambda x: x[0])]
    buckets["depth"] = [(d, c) for d, c in sorted(buckets["depth"], key=lambda x: x[0])]
    return buckets


# --------------------------------------------------------------------------- #
# 上下文构建（模块函数，从桌面 PetWindow.build_context 改造）
# --------------------------------------------------------------------------- #
def build_context(cfg, messages, summaries, max_page, bm25_result=None):
    """构建发给模型的上下文。bm25_result 为可选的 (idx, docs) 缓存，由 HistoryManager 提供。"""
    msgs = []
    tavern = bool(cfg.get("tavern_mode", False))
    worldbook_buckets = collect_worldbook_entries(cfg, messages)
    if tavern:
        msgs.append({"role": "system", "content": TAVERN_SYSTEM})
    raw = (cfg.get("raw_prefix") or "").strip()
    if raw:
        msgs.append({"role": "system", "content": raw})
    if cfg.get("enable_thinking"):
        ts = cfg.get("thinking_style", "in_character")
        if ts == "in_character":
            msgs.append({"role": "system", "content": REASON_IN_CHARACTER})
        elif ts == "analytical":
            msgs.append({"role": "system", "content": REASON_ANALYTICAL})
    for c in worldbook_buckets["before_char"]:
        msgs.append({"role": "system", "content": c})
    if not tavern:
        persona = (cfg.get("persona_prompt") or "").strip()
        if persona:
            msgs.append({"role": "system", "content": persona})
    for c in worldbook_buckets["after_char"]:
        msgs.append({"role": "system", "content": c})
    player = (cfg.get("player_identity") or "").strip()
    if player:
        msgs.append({"role": "system", "content": "【玩家身份】\n" + player})
    if not tavern:
        appearance = (cfg.get("appearance_prompt") or "").strip()[:APPEARANCE_MAX_CHARS]
        if appearance:
            msgs.append({"role": "system", "content": "【角色外观】\n" + appearance})
    if cfg.get("enable_delai") and not tavern:
        msgs.append({"role": "system", "content": DELAI_RULES})
    for c in worldbook_buckets["after_an"]:
        msgs.append({"role": "system", "content": c})
    de = (cfg.get("dialogue_examples") or "").strip()
    if de:
        msgs.append({"role": "system", "content": "【示例对话】\n" + de})

    prev = []
    for b in summaries:
        t = b.get("text") or ""
        if not t:
            continue
        if b.get("type") == "merged":
            prev.append("【第 %d–%d 页合并摘要】\n%s" % (b.get("from"), b.get("to"), t))
        else:
            prev.append("【第 %d 页摘要】\n%s" % (b.get("page"), t))
    if prev:
        msgs.append({"role": "system",
                     "content": "【历史各分页摘要，用于保持长期记忆】\n" + "\n\n".join(prev)})

    if cfg.get("enable_bm25", True) and max_page > 1:
        try:
            q = _last_user_text(messages)
            idx, docs = bm25_result if bm25_result else (None, [])
            if idx is not None and idx.N and q:
                top_k = int(cfg.get("bm25_top_k", BM25_TOP_K))
                qt = tokenize(q)
                hits = idx.search(qt, top_k)
                if hits:
                    top_di = hits[0][0]
                    tf_top = idx.tf[top_di]
                    has_specific = any(
                        tf_top.get(w, 0) > 0
                        and idx.df.get(w, 0) <= BM25_MAX_DF
                        for w in set(qt)
                    )
                    if has_specific:
                        picked = []
                        for di, _sc in hits:
                            d = docs[di]
                            role = ("用户" if d["role"] == "user"
                                    else "AI" if d["role"] == "assistant" else d["role"])
                            content = d["content"]
                            if len(content) > BM25_MAX_DOC_CHARS:
                                content = content[:BM25_MAX_DOC_CHARS] + "…"
                            picked.append("【第 %d 页 · %s】%s" % (d["page"], role, content))
                        msgs.append({"role": "system",
                                     "content": "【相关历史片段（按 BM25 相关性召回，用于补充摘要未覆盖的细节，仅供参考）】\n"
                                                 + "\n\n".join(picked)})
        except Exception as e:
            print("BM25 检索失败（已跳过）:", e)

    msgs += [m for m in messages if m.get("role") in ("user", "assistant")]

    opening = (cfg.get("opening_message") or "").strip()
    if opening and max_page == 1 and len(messages) <= 1:
        for i in range(len(msgs)):
            if msgs[i].get("role") == "user":
                msgs.insert(i, {"role": "assistant", "content": opening})
                break

    depth_entries = sorted(worldbook_buckets.get("depth", []), key=lambda x: int(x[0]))
    if depth_entries:
        last_user_idx = None
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i].get("role") == "user":
                last_user_idx = i
                break
        if last_user_idx is not None:
            for depth, content in sorted(depth_entries, key=lambda x: -int(x[0])):
                pos = max(0, last_user_idx - int(depth))
                msgs.insert(pos, {"role": "system", "content": content})
        else:
            for _, content in depth_entries:
                msgs.append({"role": "system", "content": content})

    phi = PHI_TAVERN if tavern else PHI_CHAT
    for i in range(len(msgs) - 1, -1, -1):
        if msgs[i].get("role") == "user":
            msgs.insert(i, {"role": "system", "content": phi})
            break
    else:
        msgs.append({"role": "system", "content": phi})
    return msgs


def _last_user_text(messages):
    for m in reversed(messages):
        if m.get("role") == "user":
            c = (m.get("content") or "").strip()
            if c:
                return c
    return ""


# --------------------------------------------------------------------------- #
# 历史管理器（分页 + 摘要压缩 + rollover + BM25 缓存），同步阻塞版
# 调用方应在后台线程中调用（UI 线程只读状态）
# --------------------------------------------------------------------------- #
class HistoryManager:
    def __init__(self, cfg=None):
        self.cfg = cfg or load_config()
        os.makedirs(HISTORY_DIR, exist_ok=True)
        self.summaries = load_summaries()
        self.max_page = self._infer_max_page()
        if self.max_page < 1:
            # 新会话从第 1 页开始（无历史时占位，避免写入 page_0000）
            self.max_page = 1
            save_page_file(1, [])
        self.messages = load_page_file(self.max_page)
        self._bm25_index = None
        self._bm25_docs = None
        self._bm25_max_page = -1

    def _infer_max_page(self):
        mx = 0
        if os.path.isdir(HISTORY_DIR):
            for fn in os.listdir(HISTORY_DIR):
                if fn.startswith("page_") and fn.endswith(".json"):
                    try:
                        mx = max(mx, int(fn[5:-5]))
                    except Exception:
                        pass
        return mx

    def current(self):
        return [dict(m) for m in self.messages]

    def last_user_text(self):
        return _last_user_text(self.messages)

    def get_bm25(self):
        """构建（并缓存）旧页 BM25 索引；max_page 不变则复用。"""
        if self._bm25_index is not None and self._bm25_max_page == self.max_page:
            return self._bm25_index, self._bm25_docs
        docs = []
        for n in range(1, self.max_page):
            for m in load_page_file(n):
                c = (m.get("content") or "").strip()
                if len(c) < BM25_MIN_DOC_CHARS:
                    continue
                docs.append({"page": n, "role": m.get("role"), "content": c})
        idx = BM25Index([tokenize(d["content"]) for d in docs])
        self._bm25_index = idx
        self._bm25_docs = docs
        self._bm25_max_page = self.max_page
        return idx, docs

    def build_context(self):
        return build_context(self.cfg, self.messages, self.summaries,
                             self.max_page, bm25_result=self.get_bm25())

    def append_user(self, content):
        self.messages.append({"role": "user", "content": content})
        save_page_file(self.max_page, self.messages)

    def append_assistant(self, content):
        self.messages.append({"role": "assistant", "content": content})
        save_page_file(self.max_page, self.messages)

    def truncate_after_last_user(self):
        """保留到最后一条用户消息（含），删除其后的所有消息（用于重新生成/编辑重发）。
        返回被保留的那条用户消息文本；没有用户消息时返回 None 且不改动。"""
        idx = None
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].get("role") == "user":
                idx = i
                break
        if idx is None:
            return None
        text = self.messages[idx].get("content") or ""
        self.messages = self.messages[:idx + 1]
        save_page_file(self.max_page, self.messages)
        return text

    def rollover(self):
        """关闭当前页（生成该页摘要），开启新的一页。同步阻塞；须在后台线程调用。"""
        closed = self.max_page
        page_msgs = self.messages
        self.max_page += 1
        self.messages = []
        save_page_file(self.max_page, [])
        self._summarize_page(closed, page_msgs)

    def _summarize_page(self, p, msgs):
        convo = "\n".join(
            "%s: %s" % (m.get("role", "user"), m.get("content", "")) for m in msgs
        )
        prompt = (
            "请用一段简洁的中文摘要总结下面这段对话，保留：用户的重要偏好与设定、"
            "未完成的任务或约定、关键事实与结论；删除闲聊与重复内容，"
            "不要新增信息，不要寒暄。\n\n【对话内容（第 %d 页）】\n%s" % (p, convo)
        )
        try:
            text, _, _ = run_model_session([
                {"role": "system", "content": "你是记忆摘要助手，只输出摘要文本。"},
                {"role": "user", "content": prompt},
            ], self.cfg)
            text = text.strip()
        except Exception as e:
            print("页面摘要生成失败（已忽略）:", e)
            return
        if text:
            self.summaries.append({"type": "page", "page": p, "text": text})
            self.summaries.sort(
                key=lambda b: (b.get("from") if b.get("type") == "merged"
                               else b.get("page", 0))
            )
            save_summaries(self.summaries)
            self._maybe_merge_summaries()

    def _maybe_merge_summaries(self):
        page_blocks = [b for b in self.summaries if b.get("type") == "page"]
        if len(page_blocks) < MERGE_EVERY:
            return
        taken = page_blocks[:MERGE_EVERY]
        start = taken[0]["page"]
        end = taken[-1]["page"]
        taken_pages = [b["page"] for b in taken]
        new_list = [b for b in self.summaries
                    if not (b.get("type") == "page" and b["page"] in taken_pages)]
        insert_at = len(new_list)
        for i, b in enumerate(new_list):
            if b.get("type") == "page":
                insert_at = i
                break
        merged = {"type": "merged", "from": start, "to": end, "text": ""}
        new_list.insert(insert_at, merged)
        self.summaries = new_list
        save_summaries(self.summaries)

        texts = "\n\n".join(
            "【第 %d 页摘要】\n%s" % (b["page"], b["text"]) for b in taken
        )
        prompt = (
            "以下是连续 %d 页（第 %d–%d 页）的逐页摘要，请把它们合并成一段连贯的中文总摘要，"
            "保留跨页的用户重要偏好与设定、未完成的任务或约定、关键事实与结论；"
            "删除重复与闲聊，不要新增信息，不要寒暄。\n\n%s"
            % (len(taken), start, end, texts)
        )
        try:
            text, _, _ = run_model_session([
                {"role": "system", "content": "你是记忆摘要合并助手，只输出合并后的摘要文本。"},
                {"role": "user", "content": prompt},
            ], self.cfg)
            text = text.strip()
        except Exception as e:
            print("摘要合并失败（已忽略，还原为各页独立摘要）:", e)
            if merged in self.summaries:
                restored = [b for b in self.summaries if b is not merged]
                for i, b in enumerate(taken):
                    restored.insert(insert_at + i, b)
                self.summaries = restored
                save_summaries(self.summaries)
            return
        if text and merged in self.summaries:
            merged["text"] = text
            save_summaries(self.summaries)

    def new_chat(self):
        """清空当前页开新话题（翻页但不生成摘要，保持轻量）。"""
        closed = self.max_page
        page_msgs = self.messages
        self.max_page += 1
        self.messages = []
        save_page_file(self.max_page, [])
        if page_msgs:
            save_page_file(closed, page_msgs)


# --------------------------------------------------------------------------- #
# 透明计费统计
# --------------------------------------------------------------------------- #
def token_stats_path():
    return os.path.join(APP_DIR, "token_stats.json")


def load_token_stats():
    try:
        with open(token_stats_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_token_stats(stats):
    try:
        with open(token_stats_path(), "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# 自检（python ai_core.py）
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import tempfile
    _tmp = tempfile.mkdtemp(prefix="tavern_core_")
    APP_DIR = _tmp
    HISTORY_DIR = os.path.join(_tmp, "history")
    WORLDBOOK_DIR = os.path.join(_tmp, "worldbooks")
    SUMMARY_FILE = os.path.join(HISTORY_DIR, "summaries.json")
    CONFIG_PATH = os.path.join(_tmp, "config.json")
    os.makedirs(HISTORY_DIR, exist_ok=True)

    cfg = load_config()
    assert cfg["model"] == "deepseek-v4-flash"
    print("1) 配置加载 OK:", cfg["base_url"], cfg["model"])

    # 世界书存取往返
    wb = save_worldbook({"name": "测试世界", "entries": [
        {"title": "青云宗", "content": "十大正派之首", "status": "green",
         "position": "after_char", "primary_keywords": ["青云宗"]},
    ]})
    books = load_worldbooks()
    assert len(books) == 1 and books[0]["entries"][0]["primary_keywords"] == ["青云宗"]
    print("2) 世界书存取往返 OK")

    # 世界书匹配 + 分桶
    buckets = collect_worldbook_entries(cfg, [{"role": "user", "content": "我去了青云宗"}])
    assert buckets["after_char"] == ["十大正派之首"], buckets
    print("3) 世界书关键词触发 OK:", buckets["after_char"])

    # parse_choices
    sample = ("你走进酒馆。\n\n1. 走向吧台\n2. 找吟游诗人\n3. 坐下观察\n\n自由输入：> 自由行动")
    narr, choices = parse_choices(sample)
    assert len(choices) == 3 and "吧台" in choices[0]
    print("4) parse_choices OK:", len(choices), "个选项")

    # BM25
    idx = BM25Index([tokenize("我喜欢吃猫粮"), tokenize("今天下雨了")])
    hits = idx.search(tokenize("猫粮"), 1)
    assert hits and "猫粮" in "".join(idx.docs[hits[0][0]])
    print("5) BM25 检索 OK")

    # HistoryManager 往返
    hm = HistoryManager(cfg)
    hm.append_user("你好")
    hm.append_assistant("喵~")
    hm.rollover()
    hm2 = HistoryManager(cfg)
    assert hm2.max_page == 2 and len(hm2.messages) == 0
    print("6) HistoryManager 翻页持久化 OK, max_page =", hm2.max_page)

    # build_context 结构
    ctx = build_context(cfg, [{"role": "user", "content": "你好"}], [], 1, bm25_result=(None, []))
    roles = [m["role"] for m in ctx]
    assert roles[-1] == "user" and "system" in roles
    print("7) build_context 结构 OK, 消息数 =", len(ctx))

    print("ALL_CORE_TESTS_PASSED")

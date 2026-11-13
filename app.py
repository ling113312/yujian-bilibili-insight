# -*- coding: utf-8 -*-
"""
舆见 · B站评论区舆情洞察助手 (Real MVP)
纯 Python 标准库；抓取走 B站 WBI 签名接口，分析走大模型(OpenAI 兼容) + 规则兜底。
运行: python app.py   打开 http://127.0.0.1:7860
"""
import os
import re
import sys
import json
import time
import html
import math
import hashlib
import sqlite3
import threading
import urllib.parse
import urllib.request
import urllib.error
import webbrowser
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "yujian.db")
PORT = int(os.environ.get("PORT", "7860"))
HOST = os.environ.get("HOST", "0.0.0.0")

STATE = {
    "raw": [], "clean": [], "stats": None, "analysis": None,
    "meta": {}, "status": "", "chat": None, "cfg": {},
    "status_kind": "ok",
}
LOCK = threading.Lock()
LAST_LLM_ERR = {"msg": ""}

UA_PC = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

ALLOWED = ["内容质量", "剪辑制作", "价格付费", "态度互动", "广告推广", "其他"]

ASPECT_KEYWORDS = {
    "内容质量": ["内容", "选题", "干货", "信息量", "深度", "观点", "逻辑", "价值", "有用", "水", "蹭热点", "编"],
    "剪辑制作": ["剪辑", "节奏", "卡顿", "画质", "音质", "配音", "字幕", "糊", "拖沓", "转场", "BGM", "吵", "晃"],
    "价格付费": ["价格", "贵", "便宜", "收费", "付费", "会员", "性价比", "退钱", "割韭菜", "值"],
    "态度互动": ["态度", "回复", "互动", "语气", "敷衍", "傲慢", "真诚", "宠粉", "不理", "高冷", "暖心"],
    "广告推广": ["广告", "推广", "恰饭", "带货", "链接", "商单", "植入"],
}
POS = ["好", "棒", "赞", "喜欢", "支持", "优秀", "清晰", "有用", "干货", "值得", "真实", "满意",
       "厉害", "牛", "绝了", "爱了", "舒服", "专业", "良心", "学到", "感谢", "不错", "给力",
       "暖心", "真诚", "宠粉", "便宜", "性价比", "值", "好看", "好听"]
NEG = ["差", "烂", "垃圾", "无语", "失望", "敷衍", "贵", "卡", "糊", "拖", "傲慢", "恶心",
       "反感", "劝退", "退钱", "吐槽", "难听", "水", "割韭菜", "蹭热点", "不行", "拉胯",
       "烦", "吵", "假", "骗", "高冷", "广告", "恰饭"]
NEGATION = ["不", "没", "无", "别", "未", "非"]

SAMPLE = [
    "这期选题太好了，信息量很大，学到了很多，支持up主！",
    "内容干货满满，逻辑清晰，讲得比很多付费课都好。",
    "选题有点跟风蹭热点，内容水，没什么意思。",
    "整体不错，就是剪辑节奏有点拖沓，中间好长一段没信息。",
    "剪辑太碎了，转场晃得我头晕，能不能稳一点。",
    "画质和音质都很清晰，字幕也专业，看得舒服。",
    "配音有点出戏，建议换个声音或者自己配。",
    "这期节奏很好，废话少，干货多，爱了。",
    "付费内容值不值？我觉得挺值的，讲得细。",
    "价格太贵了，一个会员收这么多，割韭菜吧。",
    "收费可以理解，但希望能便宜点，学生党压力大。",
    "性价比一般，免费部分比付费部分还好。",
    "up主回复很真诚，问的问题都耐心答了，宠粉。",
    "私信不回，评论区也不理人，态度有点高冷。",
    "客服态度敷衍，问半天就回一句，很失望。",
    "互动做得不错，每条评论都尽量回，暖心。",
    "这期太棒了，观点很独特，值得反复看。",
    "内容深度不够，感觉是拼凑的，有点失望。",
    "选题很贴近生活，讲出了我们的心声，赞。",
    "剪辑越来越专业了，进步很大，支持！",
    "音质有点糊，戴耳机听很难受。",
    "价格能接受，内容质量对得起这个价。",
    "退钱！付费之后内容明显缩水，无语。",
    "up主态度很好，出了问题马上道歉并改进。",
    "这期有点水，感觉在凑时长。",
    "观点有逻辑，案例也真实，学到了。",
    "节奏拖沓，看了一半就关了。",
    "会员价格还行，就是更新太慢。",
    "评论区氛围很好，up主也经常互动。",
    "内容不错，但广告有点多，稍微影响体验。",
    "剪辑能不能别老用那种吓人的音效，烦。",
    "选题很棒，希望多出这类深度内容。",
    "讲得太浅了，都是常识，没什么新东西。",
    "画质提升了，看着很舒服，专业。",
    "收费没问题，但希望有试看。",
    "态度傲慢，提意见就被怼，取关了。",
    "这期干货真的多，做了笔记，感谢！",
    "内容有点假，感觉在编故事。",
    "节奏可以的，就是字幕有几处错别字。",
    "up主很真诚，会看评论，支持到底。",
    "价格偏贵，同类内容有更便宜的。",
    "剪辑节奏舒服，BGM也选得好。",
    "选题一般，没什么新意。",
    "这期广告太硬了，恰饭能不能自然点。",
    "整体质量很高，值得推荐给朋友。",
]


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize(text):
    text = re.sub(r"<[^>]+>", " ", str(text or ""))
    text = html.unescape(text)
    text = text.replace("\u200b", "").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


_OC_CFG = {"loaded": False, "key": "", "base": "", "model": ""}


def load_opencode_llm():
    if _OC_CFG["loaded"]:
        return _OC_CFG
    _OC_CFG["loaded"] = True
    try:
        p = os.path.join(os.path.expanduser("~"), ".config", "opencode", "opencode.json")
        data = json.load(open(p, encoding="utf-8"))
        provs = data.get("provider") or {}
        for name in ["cuc-copy", "cuc"]:
            pv = provs.get(name)
            if not pv:
                continue
            opts = pv.get("options") or {}
            key = opts.get("apiKey", "")
            bu = opts.get("baseURL", "")
            base = (bu.rstrip("/") + "/chat/completions") if bu else ""
            models = list((pv.get("models") or {}).keys())
            if key and base:
                _OC_CFG.update({"key": key, "base": base, "model": models[0] if models else ""})
                break
    except Exception:
        pass
    return _OC_CFG


_LOCAL_CFG = {"loaded": False, "key": "", "base": "", "model": ""}


def load_local_config():
    if _LOCAL_CFG["loaded"]:
        return _LOCAL_CFG
    _LOCAL_CFG["loaded"] = True
    try:
        p = os.path.join(BASE_DIR, "config.json")
        if os.path.exists(p):
            d = json.load(open(p, encoding="utf-8"))
            for k in ["key", "base", "model"]:
                if d.get(k):
                    _LOCAL_CFG[k] = str(d.get(k))
    except Exception:
        pass
    return _LOCAL_CFG


def llm_key(cfg):
    return ((cfg or {}).get("key") or os.environ.get("DEEPSEEK_API_KEY", "")
            or load_opencode_llm()["key"] or load_local_config()["key"])


def bili_headers(cookie):
    return {
        "User-Agent": UA_PC,
        "Referer": "https://www.bilibili.com/",
        "Accept": "application/json, text/plain, */*",
        "Cookie": cookie or "",
    }


def http_get(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA_PC})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def http_post_json(url, payload, headers, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


# ---------------- B站 WBI 签名 ----------------
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]


def ensure_buvid(cookie):
    if "buvid3=" in (cookie or ""):
        return cookie
    try:
        d = json.loads(http_get("https://api.bilibili.com/x/frontend/finger/spi",
                                bili_headers(cookie)))
        b3 = (d.get("data") or {}).get("b_3", "")
        b4 = (d.get("data") or {}).get("b_4", "")
        add = []
        if b3:
            add.append("buvid3=" + b3)
        if b4:
            add.append("buvid4=" + b4)
        if add:
            return (cookie + ("; " if cookie else "") + "; ".join(add))
    except Exception:
        pass
    return cookie or ""


def get_mixin_key(cookie):
    nav = json.loads(http_get("https://api.bilibili.com/x/web-interface/nav",
                              bili_headers(cookie)))
    wbi = (nav.get("data") or {}).get("wbi_img") or {}
    img = (wbi.get("img_url") or "").rsplit("/", 1)[-1].split(".")[0]
    sub = (wbi.get("sub_url") or "").rsplit("/", 1)[-1].split(".")[0]
    raw = img + sub
    if len(raw) < 64:
        raise RuntimeError("获取 B站 WBI key 失败，请检查 Cookie 或网络")
    return "".join(raw[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def sign_wbi(params, mixin_key):
    params = dict(params)
    params["wts"] = int(time.time())
    clean = {}
    for k, v in params.items():
        clean[k] = "".join(ch for ch in str(v) if ch not in "!'()*")
    query = urllib.parse.urlencode(sorted(clean.items()), quote_via=urllib.parse.quote)
    clean["w_rid"] = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
    return clean


def resolve_dynamic(did, cookie=""):
    try:
        url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/detail?id=" + str(did)
        d = json.loads(http_get(url, bili_headers(cookie)))
        item = (d.get("data") or {}).get("item") or {}
        md = (item.get("modules") or {}).get("module_dynamic") or {}
        arch = (md.get("major") or {}).get("archive") or {}
        if arch.get("bvid"):
            return arch["bvid"]
        for u in [(md.get("opus") or {}).get("jump_url", "")]:
            m = re.search(r"(BV[0-9A-Za-z]{10})", u or "")
            if m:
                return m.group(1)
    except Exception:
        pass
    return ""


def extract_bvid(text, cookie=""):
    text = (text or "").strip()
    if not text:
        return ""
    if re.match(r"^BV[0-9A-Za-z]{10}$", text):
        return text
    if re.match(r"^av\d+$", text, re.I):
        return text
    m = re.search(r"(BV[0-9A-Za-z]{10})", text)
    if m:
        return m.group(1)
    m = re.search(r"av(\d+)", text, re.I)
    if m:
        return "av" + m.group(1)
    m = re.search(r"(?:t\.bilibili\.com|bilibili\.com/opus)/(\d+)", text)
    if m:
        return resolve_dynamic(m.group(1), cookie)
    if text.startswith("http"):
        try:
            req = urllib.request.Request(text, headers={"User-Agent": UA_PC})
            with urllib.request.urlopen(req, timeout=15) as r:
                final = r.geturl()
            m = re.search(r"(BV[0-9A-Za-z]{10})", final)
            if m:
                return m.group(1)
        except Exception:
            pass
    return ""


def bili_video_info(bvid, cookie):
    if bvid.lower().startswith("av"):
        url = "https://api.bilibili.com/x/web-interface/view?aid=" + bvid[2:]
    else:
        url = "https://api.bilibili.com/x/web-interface/view?bvid=" + bvid
    d = json.loads(http_get(url, bili_headers(cookie)))
    if d.get("code") != 0:
        raise RuntimeError("视频信息获取失败：code=%s %s" % (d.get("code"), d.get("message")))
    data = d["data"]
    return {
        "aid": data["aid"], "bvid": data.get("bvid", bvid),
        "title": data.get("title", ""), "owner": (data.get("owner") or {}).get("name", ""),
        "view": data.get("stat", {}).get("view", 0),
        "reply": data.get("stat", {}).get("reply", 0),
    }


def _mk_comment(r, platform, aid, is_sub, root_id=""):
    msg = normalize((r.get("content") or {}).get("message", ""))
    ctime = r.get("ctime") or 0
    return {
        "platform": platform, "text": msg,
        "user": (r.get("member") or {}).get("uname", ""),
        "time": datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M") if ctime else "",
        "like": r.get("like", 0), "rpid": str(r.get("rpid", "")),
        "aid": str(aid), "is_sub": is_sub, "root": root_id,
    }


def fetch_sub_replies(aid, root_rpid, cookie, max_pages=2):
    out = []
    for pn in range(1, max_pages + 1):
        url = ("https://api.bilibili.com/x/v2/reply/reply?oid=%s&type=1&root=%s&ps=20&pn=%s"
               % (aid, root_rpid, pn))
        try:
            d = json.loads(http_get(url, bili_headers(cookie)))
        except Exception:
            break
        if d.get("code") != 0:
            break
        reps = (d.get("data") or {}).get("replies") or []
        if not reps:
            break
        for r in reps:
            out.append(_mk_comment(r, "B站", aid, True, root_rpid))
        if len(reps) < 20:
            break
    return out


def fetch_bili_comments(bvid, cookie, max_pages=3, include_sub=True):
    cookie = ensure_buvid(cookie)
    info = bili_video_info(bvid, cookie)
    aid = info["aid"]
    mixin = get_mixin_key(cookie)
    out = []
    seen_rpid = set()
    offset = ""
    pages_done = 0
    for _ in range(max(1, max_pages)):
        params = {
            "oid": aid, "type": 1, "mode": 3, "plat": 1,
            "web_location": 1315875, "ps": 20,
            "pagination_str": json.dumps({"offset": offset}, separators=(",", ":")),
        }
        signed = sign_wbi(params, mixin)
        url = "https://api.bilibili.com/x/v2/reply/wbi/main?" + urllib.parse.urlencode(signed)
        d = json.loads(http_get(url, bili_headers(cookie), timeout=20))
        code = d.get("code")
        if code != 0:
            if code in (-352, -412, -401):
                raise RuntimeError("B站触发风控/未登录（code=%s）。请粘贴最新且已登录的 Cookie。" % code)
            raise RuntimeError("评论接口错误：code=%s %s" % (code, d.get("message")))
        data = d.get("data") or {}
        reps = list(data.get("replies") or []) + list(data.get("top_replies") or [])
        for r in reps:
            rpid = str(r.get("rpid", ""))
            if rpid and rpid in seen_rpid:
                continue
            if rpid:
                seen_rpid.add(rpid)
            out.append(_mk_comment(r, "B站", aid, False))
            if include_sub and r.get("rcount", 0):
                for sc in fetch_sub_replies(aid, rpid, cookie, max_pages=3):
                    if sc["rpid"] and sc["rpid"] not in seen_rpid:
                        seen_rpid.add(sc["rpid"])
                        out.append(sc)
                    if len(out) >= 2000:
                        break
        cur = data.get("cursor") or {}
        pages_done += 1
        if cur.get("is_end"):
            break
        next_offset = ((cur.get("pagination_reply") or {}).get("next_offset")) or ""
        if not next_offset:
            break
        offset = next_offset
        time.sleep(0.6)
    return out, info, pages_done


# ---------------- 清洗 / 去重 / 对账 ----------------
def clean_and_dedup(raw):
    total = len(raw)
    seen = set()
    clean = []
    failed = deduped = 0
    for c in raw:
        t = normalize(c.get("text", ""))
        if len(t) < 2:
            failed += 1
            continue
        if c.get("rpid"):
            key = "%s|%s|%s" % (c.get("platform", ""), c.get("rpid"), t)
        else:
            key = t
        h = hashlib.md5(key.encode("utf-8")).hexdigest()
        if h in seen:
            deduped += 1
            continue
        seen.add(h)
        cc = dict(c)
        cc["text"] = t
        cc["hash"] = h
        clean.append(cc)
    stats = {
        "total": total, "inserted": len(clean), "deduped": deduped, "failed": failed,
        "ok": (len(clean) + deduped + failed == total),
        "top": sum(1 for c in clean if not c.get("is_sub")),
        "sub": sum(1 for c in clean if c.get("is_sub")),
    }
    return clean, stats


# ---------------- 规则兜底 ----------------
def rule_polarity(text):
    pos = neg = 0
    for w in POS:
        s = 0
        while True:
            i = text.find(w, s)
            if i < 0:
                break
            neg += 1 if (i > 0 and text[i - 1] in NEGATION) else 0
            pos += 0 if (i > 0 and text[i - 1] in NEGATION) else 1
            s = i + 1
    for w in NEG:
        s = 0
        while True:
            i = text.find(w, s)
            if i < 0:
                break
            pos += 1 if (i > 0 and text[i - 1] in NEGATION) else 0
            neg += 0 if (i > 0 and text[i - 1] in NEGATION) else 1
            s = i + 1
    return pos, neg


def rule_item(text):
    pos, neg = rule_polarity(text)
    lab = "正面" if pos > neg else ("负面" if neg > pos else "中性")
    matched = [k for k, ws in ASPECT_KEYWORDS.items() if any(w in text for w in ws)]
    if not matched:
        matched = ["其他"]
    intensity = min(5, max(1, abs(pos - neg)))
    if lab == "负面":
        intensity = min(5, 2 + abs(neg - pos))
    hits = [w for w in POS + NEG if w in text][:4]
    return {"sentiment": lab, "aspects": matched, "intensity": intensity,
            "reason": "命中词：" + "/".join(hits) if hits else "无明显情感词",
            "evidence": "/".join(hits), "by": "rule"}


# ---------------- 大模型分析 ----------------
def llm_chat(messages, cfg, json_mode=False, timeout=90):
    key = llm_key(cfg)
    if not key:
        return None
    oc = load_opencode_llm()
    lc = load_local_config()
    base = ((cfg or {}).get("base") or os.environ.get("LLM_BASE") or oc["base"] or lc["base"]
            or "https://openai.cuc.edu.cn/v1/chat/completions")
    model = ((cfg or {}).get("model") or os.environ.get("LLM_MODEL") or oc["model"] or lc["model"]
             or "cuc/deepseek")
    payload = {"model": model, "messages": messages, "temperature": 0.2}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        d = http_post_json(base, payload, {
            "Content-Type": "application/json", "Authorization": "Bearer " + key,
        }, timeout=timeout)
        return d["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "ignore")
        except Exception:
            body = ""
        LAST_LLM_ERR["msg"] = "HTTP %s %s" % (e.code, body[:160])
        return None
    except Exception as e:
        LAST_LLM_ERR["msg"] = "%s %s" % (type(e).__name__, str(e)[:120])
        return None


def llm_analyze_chunk(texts, cfg):
    sys_prompt = (
        "你是中文舆情分析师。对每条评论判断：\n"
        "1) sentiment：正面/中性/负面；\n"
        "2) intensity：1-5 的强度整数；\n"
        "3) aspects：从 [" + "/".join(ALLOWED) + "] 中选 1-3 个，无法归类用“其他”；\n"
        "4) reason：不超过 20 字的中文理由。\n"
        "只输出 JSON：{\"results\":[{\"id\":0,\"sentiment\":\"负面\",\"intensity\":4,"
        "\"aspects\":[\"剪辑制作\"],\"reason\":\"节奏拖沓\"}]}"
    )
    user = json.dumps({"comments": [{"id": i, "text": t} for i, t in enumerate(texts)]},
                      ensure_ascii=False)
    raw = llm_chat([{"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user}], cfg, json_mode=True)
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        arr = obj.get("results") or obj.get("data") or []
        out = {}
        for r in arr:
            try:
                i = int(r.get("id"))
            except Exception:
                continue
            senti = r.get("sentiment")
            if senti not in ("正面", "中性", "负面"):
                senti = "中性"
            asp = [a for a in (r.get("aspects") or []) if a in ALLOWED] or ["其他"]
            try:
                inten = int(r.get("intensity") or 3)
            except Exception:
                inten = 3
            out[i] = {"sentiment": senti, "aspects": asp[:3],
                      "intensity": max(1, min(5, inten)),
                      "reason": str(r.get("reason") or "")[:40],
                      "evidence": str(r.get("reason") or "")[:40], "by": "llm"}
        return out
    except Exception:
        return {}


def analyze_comments(clean, cfg):
    use_llm = bool(llm_key(cfg)) and (cfg or {}).get("engine") != "rule"
    if not use_llm:
        for c in clean:
            c.update(rule_item(c["text"]))
        return False
    size = int((cfg or {}).get("batch") or 15)
    chunks = [clean[i:i + size] for i in range(0, len(clean), size)]
    results = {}
    success = 0
    try:
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(llm_analyze_chunk, [c["text"] for c in ch], cfg): ch for ch in chunks}
            for f in as_completed(futs):
                ch = futs[f]
                try:
                    res = f.result()
                except Exception:
                    res = {}
                for idx, r in res.items():
                    if 0 <= idx < len(ch):
                        results[ch[idx]["hash"]] = r
                        success += 1
    except Exception:
        pass
    for c in clean:
        r = results.get(c["hash"])
        if r:
            c.update(r)
        else:
            c.update(rule_item(c["text"]))
    return success > 0


# ---------------- 聚合 / 洞察 ----------------
def aggregate(clean):
    aspects = {k: {"正面": 0, "中性": 0, "负面": 0, "intensity": 0,
                   "neg_ex": [], "pos_ex": []} for k in ALLOWED}
    overall = {"正面": 0, "中性": 0, "负面": 0}
    for c in clean:
        lab = c.get("sentiment", "中性")
        overall[lab] += 1
        for a in c.get("aspects") or ["其他"]:
            d = aspects.setdefault(a, {"正面": 0, "中性": 0, "负面": 0, "intensity": 0,
                                       "neg_ex": [], "pos_ex": []})
            d[lab] += 1
            if lab == "负面":
                d["intensity"] += c.get("intensity", 3)
                if len(d["neg_ex"]) < 4:
                    d["neg_ex"].append(c)
            if lab == "正面" and len(d["pos_ex"]) < 3:
                d["pos_ex"].append(c)
    for d in aspects.values():
        d["total"] = d["正面"] + d["中性"] + d["负面"]
        d["neg_ratio"] = d["负面"] / d["total"] if d["total"] else 0.0
        d["pos_ratio"] = d["正面"] / d["total"] if d["total"] else 0.0
    return overall, aspects


def compute_risk(overall, aspects, total):
    neg = overall["负面"]
    neg_ratio = neg / total if total else 0.0
    worst, wr = None, 0.0
    for k, d in aspects.items():
        if d["total"] >= 3 and d["neg_ratio"] > wr:
            worst, wr = k, d["neg_ratio"]
    level = "低"
    if neg_ratio >= 0.4 or (worst and wr >= 0.5):
        level = "高"
    elif neg_ratio >= 0.2 or (worst and wr >= 0.33):
        level = "中"
    if worst:
        reason = ("整体负面占比 %.0f%%，其中「%s」最集中（负面 %.0f%%，%d 条）。"
                  % (neg_ratio * 100, worst, wr * 100, aspects[worst]["负面"]))
    else:
        reason = "整体负面占比 %.0f%%，暂无明显集中吐槽。" % (neg_ratio * 100)
    return {"level": level, "reason": reason, "neg_ratio": neg_ratio, "worst": worst}


def rule_insights(clean, aspects, risk):
    negs = sorted([c for c in clean if c.get("sentiment") == "负面"],
                  key=lambda x: (-(x.get("intensity") or 0), -(x.get("like") or 0)))
    themes = []
    for k, d in sorted(aspects.items(), key=lambda kv: kv[1]["neg_ratio"], reverse=True):
        if d["total"] >= 2 and d["负面"] > 0:
            ex = d["neg_ex"][0]["text"] if d["neg_ex"] else ""
            themes.append({"theme": k, "count": d["负面"],
                           "evidence": ex[:60]})
    replies = []
    for c in negs[:3]:
        replies.append({"comment": c["text"][:80],
                        "reply": "抱歉给你带来不好的体验，你提到的“%s”我们已记录，会在下期重点改进，感谢反馈。"
                                 % ("、".join(c.get("aspects") or ["问题"]))})
    advice = {
        "内容质量": "减少跟风选题，补充独家信息与案例深度，开头明确本期价值点。",
        "剪辑制作": "优化节奏与转场，减少无效时长，检查音画质与字幕错漏。",
        "价格付费": "说明定价依据，提供试看/分层会员或限时优惠。",
        "态度互动": "固定回复时段与话术模板，对合理批评先共情再解释。",
        "广告推广": "降低广告密度、前置标注，选择与内容调性匹配的合作。",
        "其他": "补充关键词表，把未归类诉求纳入下一轮分析。",
    }
    suggestions = []
    for t in themes[:2]:
        suggestions.append(advice.get(t["theme"], advice["其他"]))
    if not suggestions:
        suggestions.append("整体口碑较好，保持节奏，并主动收集正向评论用于二次传播。")
    topics = []
    for k, d in aspects.items():
        if d["total"] >= 2 and d["pos_ratio"] >= 0.5:
            topics.append("围绕「%s」做进阶/答疑内容，承接正向口碑。" % k)
    for t in themes[:1]:
        topics.append("就「%s」的争议做一期说明或改进对比，转化负面情绪。" % t["theme"])
    topics.append("发起“下期想看什么”投票，提升互动与粘性。")
    return {"themes": themes[:5], "replies": replies,
            "suggestions": suggestions[:3], "topics": topics[:3],
            "summary": risk["reason"], "by": "rule"}


def llm_insights(clean, aspects, overall, risk, cfg):
    if not llm_key(cfg):
        return rule_insights(clean, aspects, risk)
    negs = sorted([c for c in clean if c.get("sentiment") == "负面"],
                  key=lambda x: (-(x.get("intensity") or 0), -(x.get("like") or 0)))[:12]
    stat_lines = []
    for k in ALLOWED:
        d = aspects.get(k)
        if d and d["total"]:
            stat_lines.append("%s: 负%d/共%d(%.0f%%)" % (k, d["负面"], d["total"], d["neg_ratio"] * 100))
    sys_prompt = (
        "你是资深创作者运营顾问。基于评论分析数据，输出 JSON：\n"
        "{\"summary\":\"一句话总体结论\",\"themes\":[{\"theme\":\"吐槽主题\",\"count\":整数,\"evidence\":\"代表性评论\"}],"
        "\"replies\":[{\"comment\":\"负面评论\",\"reply\":\"真诚、具体、可执行的回复话术\"}],"
        "\"suggestions\":[\"行动建议1\",\"建议2\",\"建议3\"],"
        "\"topics\":[\"下期选题1\",\"选题2\",\"选题3\"]}\n"
        "要求：中文；themes 最多5个；replies 针对最尖锐的3条；建议要具体可执行。"
    )
    user = json.dumps({
        "总数": len(clean), "情感": overall, "风险": risk, "方面": stat_lines,
        "负面评论样例": [{"text": c["text"][:100], "like": c.get("like", 0),
                          "aspects": c.get("aspects")} for c in negs],
    }, ensure_ascii=False)
    raw = llm_chat([{"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user}], cfg, json_mode=True)
    if not raw:
        return rule_insights(clean, aspects, risk)
    try:
        obj = json.loads(raw)
        fb = rule_insights(clean, aspects, risk)
        return {
            "summary": obj.get("summary") or fb["summary"],
            "themes": (obj.get("themes") or fb["themes"])[:5],
            "replies": (obj.get("replies") or fb["replies"])[:5],
            "suggestions": (obj.get("suggestions") or fb["suggestions"])[:3],
            "topics": (obj.get("topics") or fb["topics"])[:3],
            "by": "llm",
        }
    except Exception:
        return rule_insights(clean, aspects, risk)


def analyze(clean, cfg):
    LAST_LLM_ERR["msg"] = ""
    used_llm = analyze_comments(clean, cfg)
    overall, aspects = aggregate(clean)
    risk = compute_risk(overall, aspects, len(clean))
    insights = llm_insights(clean, aspects, overall, risk, cfg)
    err = LAST_LLM_ERR["msg"] if (llm_key(cfg) and not used_llm) else ""
    return {"total": len(clean), "overall": overall, "aspects": aspects,
            "risk": risk, "insights": insights, "used_llm": used_llm, "llm_error": err}


# ---------------- SQLite ----------------
def save_to_db(clean, stats, meta):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS comments(
            id INTEGER PRIMARY KEY AUTOINCREMENT, hash TEXT UNIQUE, platform TEXT,
            rpid TEXT, text TEXT, sentiment TEXT, aspects TEXT, reason TEXT, created_at TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS fetch_logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT, bvid TEXT, title TEXT, total INTEGER,
            inserted INTEGER, deduped INTEGER, failed INTEGER, created_at TEXT)""")
        for c in clean:
            try:
                cur.execute("INSERT INTO comments(hash,platform,rpid,text,sentiment,aspects,reason,created_at)"
                            " VALUES(?,?,?,?,?,?,?,?)",
                            (c["hash"], c.get("platform", ""), c.get("rpid", ""), c["text"],
                             c.get("sentiment", ""), ",".join(c.get("aspects") or []),
                             c.get("reason", ""), now()))
            except sqlite3.IntegrityError:
                pass
        cur.execute("INSERT INTO fetch_logs(bvid,title,total,inserted,deduped,failed,created_at)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (meta.get("bvid", ""), meta.get("title", ""), stats["total"],
                     stats["inserted"], stats["deduped"], stats["failed"], now()))
        conn.commit()
        conn.close()
    except Exception:
        pass


# ---------------- 图表 ----------------
COLORS = {"正面": "#2e9e5b", "中性": "#9aa0a6", "负面": "#d9534f"}
RISK_COLOR = {"高": "#d9534f", "中": "#e0a106", "低": "#2e9e5b"}


def svg_donut(counts):
    total = sum(counts.values()) or 1
    cx = cy = 60
    r = 44
    sw = 20
    circ = 2 * math.pi * r
    p = ['<svg viewBox="0 0 120 120" width="150" height="150">']
    p.append('<circle cx="%d" cy="%d" r="%d" fill="none" stroke="#eef0f2" stroke-width="%d"/>' % (cx, cy, r, sw))
    off = 0.0
    for lab in ["正面", "中性", "负面"]:
        v = counts.get(lab, 0)
        if v <= 0:
            continue
        dash = (v / total) * circ
        p.append('<circle cx="%d" cy="%d" r="%d" fill="none" stroke="%s" stroke-width="%d" '
                 'stroke-dasharray="%.2f %.2f" stroke-dashoffset="%.2f" transform="rotate(-90 %d %d)"/>'
                 % (cx, cy, r, COLORS[lab], sw, dash, circ - dash, -off, cx, cy))
        off += dash
    p.append("</svg>")
    return "".join(p)


def bars_html(aspects):
    maxt = max([aspects[k]["total"] for k in ALLOWED] + [1])
    rows = []
    for k in ALLOWED:
        d = aspects.get(k)
        if not d or d["total"] == 0:
            continue
        seg = []
        for lab in ["正面", "中性", "负面"]:
            v = d[lab]
            if v <= 0:
                continue
            seg.append('<span class="seg" style="width:%.2f%%;background:%s" title="%s %d"></span>'
                       % (v / maxt * 100, COLORS[lab], lab, v))
        rows.append(
            '<div class="barrow"><div class="barlabel">%s</div><div class="bartrack">%s</div>'
            '<div class="barnum">负 %d / 共 %d（%.0f%%）</div></div>'
            % (html.escape(k), "".join(seg), d["负面"], d["total"], d["neg_ratio"] * 100))
    return "".join(rows) or '<p class="muted">暂无方面数据。</p>'


# ---------------- 渲染 ----------------
CSS = """
:root{--bg:#f4f6f9;--card:#fff;--line:#e5e8ec;--txt:#1b1f24;--sub:#667085;--pri:#2f6feb;--pri2:#1e5bd8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.65}
header{background:linear-gradient(135deg,#22406f,#2f6feb 60%,#5b8def);color:#fff;padding:22px 18px}
header h1{margin:0;font-size:23px;letter-spacing:2px}
header p{margin:4px 0 0;opacity:.92;font-size:13px}
main{max-width:1000px;margin:0 auto;padding:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:14px 0;box-shadow:0 1px 2px rgba(16,24,40,.05)}
.card h2{font-size:17px;margin:0 0 12px}
.card h3{font-size:15px;margin:16px 0 6px}
label.opt{display:block;margin:6px 0;font-size:14px}
input[type=text],input[type=password],textarea,select{width:100%;padding:9px 10px;border:1px solid var(--line);border-radius:8px;font:inherit;background:#fff;color:var(--txt)}
textarea{min-height:80px;resize:vertical;font-family:ui-monospace,Consolas,monospace;font-size:12px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
@media(max-width:700px){.grid2,.grid3{grid-template-columns:1fr}}
button{background:var(--pri);color:#fff;border:0;border-radius:8px;padding:11px 18px;font:inherit;font-weight:700;cursor:pointer;margin-top:12px}
button:hover{background:var(--pri2)}
.banner{padding:10px 12px;border-radius:8px;font-size:13px;margin-bottom:10px;border:1px solid}
.ok{background:#eaf7ef;border-color:#bfe6cc;color:#1e6b3a}
.err{background:#fdecec;border-color:#f5c2c2;color:#8a1f1f}
.warn{background:#fff8e6;border-color:#ffe2a8;color:#7a5b00}
.muted{color:var(--sub);font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:6px 0}
.kpi{background:#f8fafc;border:1px solid var(--line);border-radius:10px;padding:10px;text-align:center}
.kpi b{display:block;font-size:22px}
@media(max-width:700px){.kpis{grid-template-columns:repeat(2,1fr)}}
.flex{display:flex;gap:20px;align-items:center;flex-wrap:wrap}
.legend span{display:inline-flex;align-items:center;margin-right:14px;font-size:13px}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:6px}
.barrow{display:grid;grid-template-columns:88px 1fr 160px;gap:8px;align-items:center;margin:8px 0;font-size:13px}
.bartrack{display:flex;height:16px;background:#f1f3f5;border-radius:8px;overflow:hidden}
.seg{height:100%;display:block}
@media(max-width:700px){.barrow{grid-template-columns:76px 1fr}.barnum{grid-column:1/3;color:var(--sub);font-size:12px}}
.risk{padding:12px;border-radius:10px;font-weight:700;margin:6px 0}
ul.tight{margin:6px 0;padding-left:20px}ul.tight li{margin:5px 0}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:8px 6px;text-align:left;vertical-align:top}
th{color:var(--sub);font-weight:600;background:#fafbfc;position:sticky;top:0}
.tag{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;color:#fff}
.q{background:#f1f5ff;border:1px solid #d6e2ff;border-radius:8px;padding:8px 10px;margin:6px 0}
.a{background:#f7f8fa;border:1px solid var(--line);border-radius:8px;padding:10px;margin:6px 0;white-space:pre-wrap}
.reply{background:#f2fbf5;border:1px solid #cdebd8;border-radius:8px;padding:10px;margin:8px 0}
.reply .c{color:var(--sub);font-size:12px;margin-bottom:4px}
a.btn{display:inline-block;background:#eef3ff;color:var(--pri);border:1px solid #d6e2ff;border-radius:8px;padding:8px 14px;text-decoration:none;font-weight:700;margin:6px 8px 0 0}
.scroll{max-height:420px;overflow:auto;border:1px solid var(--line);border-radius:8px}
footer{text-align:center;color:var(--sub);font-size:12px;padding:18px}
details summary{cursor:pointer;color:var(--pri);font-size:13px;margin:8px 0}
"""

HEAD = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>舆见 · B站评论区舆情洞察</title><style>' + CSS + '</style></head><body>')
HEADER = ('<header><h1>舆见</h1><p>B站评论抓取 · 去重对账 · 大模型方面级情感 · 负面预警 · 回复话术 · 对话追问</p></header>')
FOOTER = '<footer>舆见 · 数据仅存本地 SQLite（yujian.db）· Cookie/Key 只驻留内存，不落盘</footer></body></html>'


def mode_label():
    cfg = STATE.get("cfg") or {}
    a = []
    a.append("大模型：" + ("已配置" if llm_key(cfg) else "未配置（规则兜底）"))
    a.append("Cookie：" + ("已提供" if cfg.get("cookie") else "未提供"))
    return "；".join(a)


def form_html():
    cfg = STATE.get("cfg") or {}
    st = STATE.get("status", "")
    kind = STATE.get("status_kind", "ok")
    banner = ('<div class="banner %s">%s</div>' % (kind, html.escape(st))) if st else ""
    return ('<section class="card"><h2>① 抓取配置</h2>' + banner +
            '<form method="post" action="/analyze">'
            '<label class="opt"><b>B站视频/动态链接、BV号</b>（支持 bilibili.com/video、t.bilibili.com 动态、BV/av 号）</label>'
            '<input type="text" name="bvid" placeholder="粘贴视频/动态链接或 BV/av 号" value="%s">'
            '<label class="opt" style="margin-top:8px"><input type="checkbox" name="demo" value="1"> 使用内置示例数据（无需 Cookie，先体验全部功能）</label>'
            '<label class="opt" style="margin-top:10px"><b>登录 Cookie</b>（浏览器登录 B站 → F12 → Network → 任意请求 → 复制 Cookie 整段；不上传、不落盘）</label>'
            '<textarea name="cookie" placeholder="SESSDATA=...; bili_jct=...; buvid3=...（已保存则留空可复用）"></textarea>'
            '<div class="grid3" style="margin-top:10px">'
            '<div><label class="opt">抓取页数（每页20条）</label><input type="text" name="pages" value="3"></div>'
            '<div><label class="opt">含楼中楼</label><select name="sub"><option value="1" selected>是</option><option value="0">否</option></select></div>'
            '<div><label class="opt">情感引擎</label><select name="engine"><option value="llm">大模型（需填Key）</option><option value="rule">规则兜底</option></select></div>'
            '</div>'
            '<details><summary>大模型 API 设置（OpenAI 兼容；默认 DeepSeek）</summary>'
            '<div class="grid3" style="margin-top:8px">'
            '<div><label class="opt">API Key</label><input type="password" name="apikey" placeholder="sk-..." value=""></div>'
            '<div><label class="opt">Base URL</label><input type="text" name="base" value="%s"></div>'
            '<div><label class="opt">模型</label><input type="text" name="model" value="%s"></div>'
            '</div></details>'
            '<button type="submit">开始抓取并分析</button>'
            '<p class="muted">抓取+分析可能需要 10–90 秒。若提示风控(code=-352/-412)，说明 Cookie 失效或未登录，请重新复制。当前：%s</p>'
            '</form></section>') % (
        html.escape(cfg.get("bvid", "")),
        html.escape(cfg.get("base", "https://openai.cuc.edu.cn/v1/chat/completions")),
        html.escape(cfg.get("model", "cuc/deepseek")), html.escape(mode_label()))


def dashboard_html():
    a = STATE["analysis"]
    stats = STATE["stats"]
    meta = STATE.get("meta") or {}
    o = a["overall"]
    total = a["total"]
    ins = a["insights"]
    risk = a["risk"]

    kpis = ('<div class="kpis">'
            '<div class="kpi"><b>%d</b><span class="muted">有效评论</span></div>'
            '<div class="kpi"><b style="color:%s">%d</b><span class="muted">正面</span></div>'
            '<div class="kpi"><b>%d</b><span class="muted">中性</span></div>'
            '<div class="kpi"><b style="color:%s">%d</b><span class="muted">负面</span></div>'
            '</div>') % (total, COLORS["正面"], o["正面"], o["中性"], COLORS["负面"], o["负面"])

    recon = ('<p class="muted">数据对账：抓取总量 %d = 入库 %d + 去重 %d + 失败 %d %s'
             '（顶层 %d / 楼中楼 %d）</p>'
             % (stats["total"], stats["inserted"], stats["deduped"], stats["failed"],
                "✔ 通过" if stats["ok"] else "✘ 不一致", stats["top"], stats["sub"]))

    legend = ('<div class="legend">'
              '<span><i class="dot" style="background:%s"></i>正面 %d</span>'
              '<span><i class="dot" style="background:%s"></i>中性 %d</span>'
              '<span><i class="dot" style="background:%s"></i>负面 %d</span>'
              '</div>') % (COLORS["正面"], o["正面"], COLORS["中性"], o["中性"], COLORS["负面"], o["负面"])

    risk_html = ('<div class="risk" style="background:%s22;color:%s;border:1px solid %s55">'
                 '风险等级：%s　%s</div>'
                 % (RISK_COLOR[risk["level"]], RISK_COLOR[risk["level"]],
                    RISK_COLOR[risk["level"]], risk["level"], html.escape(risk["reason"])))

    themes = "".join('<li><b>%s</b>（%s 条）%s</li>' % (
        html.escape(str(t.get("theme", ""))), t.get("count", ""),
        ("　例：" + html.escape(str(t.get("evidence", ""))[:70])) if t.get("evidence") else "")
        for t in ins.get("themes", [])) or '<li class="muted">暂无</li>'
    sug = "".join("<li>%s</li>" % html.escape(str(x)) for x in ins.get("suggestions", []))
    topics = "".join("<li>%s</li>" % html.escape(str(x)) for x in ins.get("topics", []))
    replies = "".join('<div class="reply"><div class="c">评论：%s</div>建议回复：%s</div>'
                      % (html.escape(str(r.get("comment", ""))[:90]), html.escape(str(r.get("reply", ""))))
                      for r in ins.get("replies", [])) or '<p class="muted">暂无</p>'

    rows = []
    negs = sorted([c for c in STATE["clean"] if c.get("sentiment") == "负面"],
                  key=lambda x: (-(x.get("intensity") or 0), -(x.get("like") or 0)))[:20]
    for i, c in enumerate(negs, 1):
        rows.append('<tr><td>%d</td><td>%s</td><td><span class="tag" style="background:%s">%s</span></td>'
                    '<td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
                    % (i, html.escape(c.get("user", ""))[:12], COLORS["负面"], c.get("sentiment", ""),
                       html.escape("、".join(c.get("aspects") or [])), c.get("intensity", ""),
                       html.escape(c.get("reason", "")[:40]), html.escape(c.get("text", "")[:90])))
    neg_table = ('<div class="scroll"><table><thead><tr><th>#</th><th>用户</th><th>情感</th>'
                 '<th>方面</th><th>强度</th><th>理由</th><th>评论</th></tr></thead><tbody>'
                 + "".join(rows) + '</tbody></table></div>') if rows else '<p class="muted">无负面评论。</p>'

    all_rows = []
    for i, c in enumerate(STATE["clean"][:300], 1):
        lab = c.get("sentiment", "中性")
        all_rows.append('<tr><td>%d</td><td>%s</td><td>%s</td><td><span class="tag" style="background:%s">%s</span></td>'
                        '<td>%s</td><td>%s</td></tr>'
                        % (i, html.escape(c.get("user", ""))[:10], html.escape(c.get("time", ""))[:16],
                           COLORS.get(lab, "#9aa0a6"), lab,
                           html.escape("、".join(c.get("aspects") or [])), html.escape(c.get("text", "")[:100])))
    all_table = ('<div class="scroll"><table><thead><tr><th>#</th><th>用户</th><th>时间</th>'
                 '<th>情感</th><th>方面</th><th>评论</th></tr></thead><tbody>'
                 + "".join(all_rows) + '</tbody></table></div>')

    if a.get("used_llm"):
        eng = "大模型(%s)" % ins.get("by", "")
    else:
        eng = "规则兜底"
        if a.get("llm_error"):
            eng += "（大模型失败：%s）" % a["llm_error"]
    head_info = ('<p class="muted">视频：<b>%s</b>　UP主：%s　播放：%s　总评论：%s　分析引擎：%s</p>'
                 % (html.escape(str(meta.get("title", ""))), html.escape(str(meta.get("owner", ""))),
                    meta.get("view", ""), meta.get("reply", ""), eng))

    return ('<section class="card"><h2>② 分析看板</h2>' + head_info + kpis + recon +
            '<div class="flex" style="margin-top:12px"><div>%s</div><div>%s</div></div>' % (svg_donut(o), legend) +
            '<h3>方面级情感分布</h3>' + bars_html(a["aspects"]) +
            '<h3>风险预警</h3>' + risk_html +
            '<h3>核心吐槽主题</h3><ul class="tight">' + themes + '</ul>' +
            '<h3>行动建议</h3><ul class="tight">' + sug + '</ul>' +
            '<h3>下期选题建议</h3><ul class="tight">' + topics + '</ul>' +
            '<h3>回复话术建议</h3>' + replies +
            '<h3>负面评论 Top20</h3>' + neg_table +
            '<details><summary>查看全部评论（前300条）</summary>' + all_table + '</details>' +
            '<a class="btn" href="/export.csv">导出评论+分析 CSV</a>'
            '<a class="btn" href="/export.md">导出分析报告 Markdown</a>'
            '</section>')


def chat_html():
    qa = STATE.get("chat")
    block = ""
    if qa:
        block = ('<div class="q">你问：%s</div><div class="a">%s</div>'
                 % (html.escape(qa["q"]), html.escape(qa["a"])))
    return ('<section class="card"><h2>③ 对话追问</h2>' + block +
            '<form method="post" action="/chat">'
            '<input type="text" name="q" placeholder="例如：主要负面是什么？给我3条回复话术 / 下期选题建议">'
            '<button type="submit">提问</button></form>'
            '<p class="muted">已配置大模型则用大模型回答，否则用内置规则。</p></section>')


def render_page():
    parts = [HEAD, HEADER, '<main>', form_html()]
    if STATE.get("analysis"):
        parts.append(dashboard_html())
    parts.append(chat_html())
    parts.append('</main>')
    parts.append(FOOTER)
    return "".join(parts)


# ---------------- 对话 ----------------
def context_text():
    a = STATE.get("analysis")
    if not a:
        return ""
    o = a["overall"]
    ins = a["insights"]
    lines = ["评论总数 %d，正面 %d，中性 %d，负面 %d。" % (a["total"], o["正面"], o["中性"], o["负面"]),
             "风险 %s：%s" % (a["risk"]["level"], a["risk"]["reason"])]
    for k in ALLOWED:
        d = a["aspects"].get(k)
        if d and d["total"]:
            lines.append("%s：正%d 中%d 负%d，负面占比%.0f%%。" % (
                k, d["正面"], d["中性"], d["负面"], d["neg_ratio"] * 100))
    lines.append("吐槽主题：" + "；".join(str(t.get("theme")) for t in ins.get("themes", [])))
    lines.append("建议：" + "；".join(map(str, ins.get("suggestions", []))))
    lines.append("选题：" + "；".join(map(str, ins.get("topics", []))))
    return "\n".join(lines)


def rule_answer(q):
    a = STATE.get("analysis")
    if not a:
        return "请先在【① 抓取配置】里抓取一个视频的评论。"
    ins = a["insights"]
    if any(k in q for k in ["风险", "预警", "危机", "扩散"]):
        return a["risk"]["reason"] + "\n建议优先处理负面最集中的方面，并在评论区置顶回应。"
    if any(k in q for k in ["负面", "吐槽", "问题", "差评", "不满", "缺点"]):
        th = ins.get("themes", [])
        if not th:
            return "当前负面占比较低，暂未形成集中吐槽。"
        return "主要负面：" + "\n".join("· %s（%s 条）%s" % (t.get("theme"), t.get("count"), t.get("evidence", ""))
                                     for t in th[:4])
    if any(k in q for k in ["回复", "话术", "怎么回", "回应"]):
        rs = ins.get("replies", [])
        if not rs:
            return "暂无可生成的回复话术。"
        return "\n\n".join("评论：%s\n回复：%s" % (r.get("comment"), r.get("reply")) for r in rs[:3])
    if any(k in q for k in ["选题", "建议", "下一期", "改进", "怎么办", "怎么做"]):
        return "行动建议：\n" + "\n".join("· " + str(x) for x in ins.get("suggestions", [])) + \
               "\n下期选题：\n" + "\n".join("· " + str(x) for x in ins.get("topics", []))
    if any(k in q for k in ["正面", "优点", "好评", "亮点"]):
        pos = [k for k in ALLOWED if a["aspects"].get(k) and a["aspects"][k]["total"] >= 2
               and a["aspects"][k]["pos_ratio"] >= 0.5]
        return ("正面口碑较好：" + "、".join(pos) + "。可围绕这些优势做延伸与二次传播。") if pos else "正面反馈较分散。"
    o = a["overall"]
    return ("整体：%d 条评论，正面 %d、中性 %d、负面 %d，风险「%s」。%s"
            % (a["total"], o["正面"], o["中性"], o["负面"], a["risk"]["level"], a["risk"]["reason"]))


def chat_answer(q):
    cfg = STATE.get("cfg") or {}
    if llm_key(cfg):
        sys_prompt = ("你是「舆见」舆情分析助手，服务内容创作者。依据给定的评论分析数据，用简洁可执行的中文回答，"
                      "先结论后理由，最多5条要点。\n\n分析数据：\n" + context_text())
        ans = llm_chat([{"role": "system", "content": sys_prompt},
                        {"role": "user", "content": q}], cfg)
        if ans:
            return ans
    return rule_answer(q)


# ---------------- 主流程 ----------------
def run_pipeline(form):
    get = lambda k, d="": (form.get(k, [d])[0] or d)
    cfg = {
        "bvid": get("bvid"), "cookie": get("cookie"),
        "apikey": get("apikey"), "base": get("base"), "model": get("model"),
        "engine": get("engine", "llm"),
    }
    prev = STATE.get("cfg") or {}
    if cfg["apikey"]:
        cfg["key"] = cfg["apikey"]
    else:
        cfg["key"] = prev.get("key", "")
    if not cfg.get("cookie"):
        cfg["cookie"] = prev.get("cookie", "")
    with LOCK:
        STATE["cfg"] = {k: cfg.get(k) for k in ["bvid", "cookie", "base", "model", "key"]}

    pages = 3
    try:
        pages = max(1, min(20, int(get("pages", "3"))))
    except Exception:
        pass
    include_sub = get("sub", "1") == "1"
    demo = get("demo", "0") == "1"

    if demo:
        raw = [{"platform": "示例", "text": t, "time": "", "user": "示例用户",
                "like": 0, "rpid": "", "is_sub": False} for t in SAMPLE]
        info = {"aid": "", "bvid": "DEMO", "title": "内置示例数据（无需登录）",
                "owner": "舆见演示", "view": 0, "reply": len(raw)}
        pages_done = 0
    else:
        bvid = extract_bvid(cfg["bvid"], cfg["cookie"])
        if not bvid:
            STATE["status"] = "未识别到 B站视频/动态链接或 BV 号，请检查输入。"
            STATE["status_kind"] = "err"
            STATE["analysis"] = None
            return
        try:
            raw, info, pages_done = fetch_bili_comments(bvid, cfg["cookie"], pages, include_sub)
        except Exception as e:
            STATE["status"] = str(e)
            STATE["status_kind"] = "err"
            STATE["analysis"] = None
            STATE["stats"] = None
            return

    if not raw:
        STATE["status"] = "未抓到评论：可能评论区关闭或 Cookie 无权限。"
        STATE["status_kind"] = "err"
        STATE["analysis"] = None
        return

    clean, stats = clean_and_dedup(raw)
    if not clean:
        STATE["status"] = "抓取到 %d 条但清洗后为空。" % len(raw)
        STATE["status_kind"] = "err"
        STATE["analysis"] = None
        return

    analysis = analyze(clean, cfg)
    save_to_db(clean, stats, info)
    if analysis["used_llm"]:
        eng = "大模型"
        kind = "ok"
    elif analysis.get("llm_error"):
        eng = "规则兜底（大模型失败：%s）" % analysis["llm_error"]
        kind = "warn"
    elif cfg.get("engine") != "rule" and not llm_key(cfg):
        eng = "规则兜底（未配置大模型 Key，可在下方展开填写）"
        kind = "warn"
    else:
        eng = "规则兜底"
        kind = "ok"

    with LOCK:
        STATE["raw"] = raw
        STATE["clean"] = clean
        STATE["stats"] = stats
        STATE["analysis"] = analysis
        STATE["meta"] = info
        STATE["chat"] = None
        STATE["status"] = ("抓取完成：%s（%s）｜页码 %d｜抓取 %d 条 = 入库 %d + 去重 %d + 失败 %d｜分析引擎：%s"
                           % (info.get("title", ""), info.get("bvid", ""), pages_done,
                              stats["total"], stats["inserted"], stats["deduped"], stats["failed"], eng))
        STATE["status_kind"] = kind


# ---------------- 导出 ----------------
def csv_bytes():
    lines = ["序号,用户,时间,点赞,来源,评论内容,情感,强度,方面,理由"]
    def esc(x):
        return '"' + str(x).replace('"', '""') + '"'
    for i, c in enumerate(STATE.get("clean") or [], 1):
        lines.append(",".join([
            str(i), esc(c.get("user", "")), esc(c.get("time", "")), str(c.get("like", 0)),
            esc(c.get("platform", "")), esc(c.get("text", "")), esc(c.get("sentiment", "")),
            str(c.get("intensity", "")), esc("、".join(c.get("aspects") or [])), esc(c.get("reason", "")),
        ]))
    return ("\n".join(lines)).encode("utf-8-sig")


def report_md():
    a = STATE.get("analysis")
    if not a:
        return "暂无数据。".encode("utf-8")
    meta = STATE.get("meta") or {}
    stats = STATE.get("stats") or {}
    o = a["overall"]
    ins = a["insights"]
    L = []
    L.append("# 舆情分析报告 · %s\n" % meta.get("title", ""))
    L.append("- 视频：%s（%s）" % (meta.get("title", ""), meta.get("bvid", "")))
    L.append("- UP主：%s　播放：%s　总评论：%s" % (meta.get("owner", ""), meta.get("view", ""), meta.get("reply", "")))
    L.append("- 生成时间：%s" % now())
    L.append("- 分析引擎：%s\n" % ("大模型" if a.get("used_llm") else "规则兜底"))
    L.append("## 一、数据对账")
    L.append("抓取总量 %d = 入库 %d + 去重 %d + 失败 %d（%s）；顶层 %d，楼中楼 %d。\n"
             % (stats.get("total", 0), stats.get("inserted", 0), stats.get("deduped", 0),
                stats.get("failed", 0), "通过" if stats.get("ok") else "不一致",
                stats.get("top", 0), stats.get("sub", 0)))
    L.append("## 二、总体情感")
    L.append("正面 %d，中性 %d，负面 %d，共 %d 条。\n" % (o["正面"], o["中性"], o["负面"], a["total"]))
    L.append("## 三、方面级情感")
    L.append("| 方面 | 正面 | 中性 | 负面 | 负面占比 |")
    L.append("|---|---|---|---|---|")
    for k in ALLOWED:
        d = a["aspects"].get(k)
        if d and d["total"]:
            L.append("| %s | %d | %d | %d | %.0f%% |" % (k, d["正面"], d["中性"], d["负面"], d["neg_ratio"] * 100))
    L.append("")
    L.append("## 四、风险预警")
    L.append("**%s**：%s\n" % (a["risk"]["level"], a["risk"]["reason"]))
    L.append("## 五、核心吐槽主题")
    for t in ins.get("themes", []):
        L.append("- **%s**（%s 条）：%s" % (t.get("theme"), t.get("count"), t.get("evidence", "")))
    L.append("")
    L.append("## 六、行动建议")
    for x in ins.get("suggestions", []):
        L.append("- " + str(x))
    L.append("")
    L.append("## 七、下期选题")
    for x in ins.get("topics", []):
        L.append("- " + str(x))
    L.append("")
    L.append("## 八、回复话术建议")
    for r in ins.get("replies", []):
        L.append("- 评论：%s" % r.get("comment"))
        L.append("  - 建议回复：%s" % r.get("reply"))
    L.append("")
    L.append("## 九、负面评论 Top20")
    L.append("| 用户 | 情感 | 方面 | 强度 | 评论 |")
    L.append("|---|---|---|---|---|")
    negs = sorted([c for c in STATE.get("clean") or [] if c.get("sentiment") == "负面"],
                  key=lambda x: (-(x.get("intensity") or 0), -(x.get("like") or 0)))[:20]
    for c in negs:
        L.append("| %s | %s | %s | %s | %s |" % (c.get("user", ""), c.get("sentiment", ""),
                                                 "、".join(c.get("aspects") or []), c.get("intensity", ""),
                                                 str(c.get("text", "")).replace("|", "｜")[:80]))
    return ("\n".join(L)).encode("utf-8")


class AppServer(ThreadingHTTPServer):
    daemon_threads = True
    if os.name == "nt":
        allow_reuse_address = False
    else:
        allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            self._send(200, render_page())
        elif path == "/api/health":
            self._send(200, json.dumps({"ok": True, "time": now()}), "application/json; charset=utf-8")
        elif path == "/export.csv":
            self._send(200, csv_bytes(), "text/csv; charset=utf-8",
                       {"Content-Disposition": 'attachment; filename="yujian_comments.csv"'})
        elif path == "/export.md":
            self._send(200, report_md(), "text/markdown; charset=utf-8",
                       {"Content-Disposition": 'attachment; filename="yujian_report.md"'})
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        else:
            self._send(404, "Not Found", "text/plain; charset=utf-8")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except Exception:
            length = 0
        raw = self.rfile.read(length).decode("utf-8", "ignore") if length else ""
        form = urllib.parse.parse_qs(raw, keep_blank_values=True)
        if path == "/analyze":
            try:
                run_pipeline(form)
            except Exception as e:
                STATE["status"] = "处理失败：%s" % e
                STATE["status_kind"] = "err"
            self._send(303, b"", "text/plain", {"Location": "/"})
        elif path == "/chat":
            q = (form.get("q", [""])[0] or "").strip()
            if q:
                STATE["chat"] = {"q": q, "a": chat_answer(q)}
            self._send(200, render_page())
        else:
            self._send(404, "Not Found", "text/plain; charset=utf-8")


def main():
    srv = None
    port = PORT
    for p in range(PORT, PORT + 11):
        try:
            srv = AppServer((HOST, p), Handler)
            port = p
            break
        except OSError:
            continue
    if srv is None:
        print("启动失败：端口 %d-%d 都被占用。" % (PORT, PORT + 10))
        try:
            input("请关闭占用端口的程序后重试，按回车退出...")
        except Exception:
            pass
        return
    url = "http://127.0.0.1:%d" % port
    print("舆见 已启动：" + url)
    print("关闭本窗口即停止服务。")
    if os.environ.get("YUJIAN_NO_BROWSER") != "1":
        try:
            t = threading.Timer(1.5, lambda: webbrowser.open(url))
            t.daemon = True
            t.start()
        except Exception:
            pass
    srv.serve_forever()


if __name__ == "__main__":
    main()

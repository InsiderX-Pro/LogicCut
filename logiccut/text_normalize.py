from __future__ import annotations

import re
from functools import lru_cache


_FALLBACK_T2S_MAP = {
        "這": "这",
        "個": "个",
        "會": "会",
        "觀": "观",
        "場": "场",
        "門": "门",
        "眾": "众",
        "車": "车",
        "關": "关",
        "鍵": "键",
        "讓": "让",
        "轉": "转",
        "衝": "冲",
        "適": "适",
        "開": "开",
        "頭": "头",
        "強": "强",
        "創": "创",
        "構": "构",
        "謬": "谬",
        "裡": "里",
        "為": "为",
        "來": "来",
        "傳": "传",
        "發": "发",
        "續": "续",
        "語": "语",
        "義": "义",
        "視": "视",
        "頻": "频",
        "釋": "释",
        "顯": "显",
        "標": "标",
        "題": "题",
        "節": "节",
        "點": "点",
        "鋸": "锯",
        "齒": "齿",
        "狀": "状",
        "聲": "声",
        "導": "导",
        "覽": "览",
        "體": "体",
        "後": "后",
        "時": "时",
        "間": "间",
        "與": "与",
        "對": "对",
        "應": "应",
        "內": "内",
        "級": "级",
        "壓": "压",
        "過": "过",
        "設": "设",
        "計": "计",
        "數": "数",
        "據": "据",
        "現": "现",
        "產": "产",
        "長": "长",
        "驅": "驱",
        "動": "动",
        "論": "论",
        "閱": "阅",
        "灣": "湾",
        "網": "网",
        "評": "评",
        "領": "领",
        "卻": "却",
        "並": "并",
        "們": "们",
        "討": "讨",
        "啟": "启",
        "辦": "办",
        "連": "连",
        "覺": "觉",
        "麼": "么",
        "親": "亲",
        "該": "该",
        "範": "范",
        "軟": "软",
        "擊": "击",
        "詮": "诠",
        "師": "师",
        "業": "业",
        "飛": "飞",
        "躍": "跃",
        "極": "极",
        "興": "兴",
        "慮": "虑",
        "話": "话",
        "寫": "写",
        "實": "实",
        "驗": "验",
        "證": "证",
        "優": "优",
        "質": "质",
        "壞": "坏",
        "簡": "简",
        "擇": "择",
        "擴": "扩",
        "獲": "获",
        "斷": "断",
        "認": "认",
        "準": "准",
        "備": "备",
        "錄": "录",
        "輸": "输",
        "齊": "齐",
        "錯": "错",
        "總": "总",
        "結": "结",
        "墊": "垫",
        "補": "补",
        "張": "张",
        "國": "国",
        "還": "还",
        "環": "环",
        "鬆": "松",
        "緒": "绪",
        "說": "说",
}

_FALLBACK_T2S = str.maketrans(_FALLBACK_T2S_MAP)
_TRADITIONAL_CHARS = set(_FALLBACK_T2S_MAP.keys())


def normalize_display_text(value: object, *, strict: bool = True) -> str:
    text = " ".join(str(value or "").replace("\n", " ").split())
    if not text:
        return ""
    converted = _opencc_convert(text)
    simplified = _normalize_punctuation(converted.translate(_FALLBACK_T2S))
    if strict:
        assert_simplified_text(simplified)
    return simplified


def contains_traditional(value: object) -> bool:
    text = str(value or "")
    return any(char in _TRADITIONAL_CHARS for char in text)


def assert_simplified_text(value: object) -> None:
    text = str(value or "")
    residual = sorted({char for char in text if char in _TRADITIONAL_CHARS})
    if residual:
        sample = "".join(residual[:12])
        raise ValueError(f"text contains residual traditional Chinese characters: {sample}")


@lru_cache(maxsize=1)
def _opencc_converter():
    try:
        from opencc import OpenCC  # type: ignore
    except Exception:
        return None
    try:
        return OpenCC("t2s")
    except Exception:
        return None


def _opencc_convert(text: str) -> str:
    converter = _opencc_converter()
    if converter is None:
        return text
    try:
        return converter.convert(text)
    except Exception:
        return text


def _normalize_punctuation(text: str) -> str:
    text = text.replace("“", "“").replace("”", "”")
    text = text.replace("，", "，").replace("。", "。")
    text = re.sub(r"\s+([，。！？；：])", r"\1", text)
    return text

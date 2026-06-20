#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
マーケット・モニター(iPhone / モバイル最適化版)

iPhone だけで動かす方法:
  1. GitHub にこの market_monitor_app.py と requirements.txt を置く
  2. share.streamlit.io でそのリポジトリを指定してデプロイ
  3. 発行された https://〇〇.streamlit.app を Safari で開く
     (ホーム画面に追加するとアプリのように使えます)
"""

import time
from datetime import datetime

import pandas as pd
import streamlit as st

try:
    import yfinance as yf
except ImportError:
    st.error("yfinance が未インストールです: pip install --upgrade yfinance")
    st.stop()

# ---------------------------------------------------------------------------
# ページ設定 & モバイル向けスタイル
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="マーケット・モニター",
    page_icon="📈",
    layout="centered",            # スマホでは centered の方が余白が自然
    initial_sidebar_state="collapsed",
)

# 画面端の余白を詰め、メトリクスの文字を読みやすく(モバイル調整)
st.markdown(
    """
    <style>
    .block-container {padding: 1.0rem 0.8rem 2.5rem 0.8rem;}
    [data-testid="stMetricValue"] {font-size: 1.25rem;}
    [data-testid="stMetricLabel"] {font-size: 0.8rem;}
    [data-testid="stMetricDelta"] {font-size: 0.78rem;}
    h1 {font-size: 1.5rem;}
    h2, h3 {font-size: 1.15rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📈 マーケット・モニター")
st.caption(
    "データ元: Yahoo Finance ／ 上昇↑・下落↓"
    "（VIXは反転: 低下↑/上昇↓、ドル円は円安↑/円高↓）"
)

INSTRUMENTS = [
    {"name": "日経225先物", "symbol": "NIY=F", "invert": False, "labels": ("上昇", "下落")},
    {"name": "日経225現物", "symbol": "^N225",  "invert": False, "labels": ("上昇", "下落")},
    {"name": "S&P500",      "symbol": "^GSPC",  "invert": False, "labels": ("上昇", "下落")},
    {"name": "NASDAQ",      "symbol": "^IXIC",  "invert": False, "labels": ("上昇", "下落")},
    {"name": "ドル円",      "symbol": "JPY=X",  "invert": False, "labels": ("円安", "円高")},
    {"name": "VIX指数",     "symbol": "^VIX",   "invert": True,  "labels": ("低下", "上昇")},
]


# ---------------------------------------------------------------------------
# データ取得
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def fetch_all():
    results = []
    for inst in INSTRUMENTS:
        quote = _get_quote(inst["symbol"])
        if quote is None:
            results.append({**inst, "last": None, "prev": None,
                            "mark": "—", "label": "取得失敗", "change": None, "pct": None})
            continue
        last, prev = quote
        mark, label, change = _decide_mark(last, prev, inst["invert"], inst["labels"])
        pct = (change / prev * 100) if prev else 0.0
        results.append({**inst, "last": last, "prev": prev,
                        "mark": mark, "label": label, "change": change, "pct": pct})
    return results, datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _get_quote(symbol, retries=3):
    for attempt in range(1, retries + 1):
        try:
            hist = yf.Ticker(symbol).history(period="1mo", interval="1d", auto_adjust=False)
            if hist is None or hist.empty or "Close" not in hist.columns:
                raise ValueError("空のデータ")
            closes = hist["Close"].dropna()
            if len(closes) < 2:
                raise ValueError("データ不足")
            return float(closes.iloc[-1]), float(closes.iloc[-2])
        except Exception:
            if attempt < retries:
                time.sleep(1.5 * attempt)
    return None


def _decide_mark(last, prev, invert, labels):
    change = last - prev
    if change == 0:
        return "→", "変わらず", 0.0
    rising = change > 0
    show_up = rising if not invert else (not rising)
    if show_up:
        return "↑", labels[0], change
    return "↓", labels[1], change


# ---------------------------------------------------------------------------
# シグナル判定ロジック
# ---------------------------------------------------------------------------
def calc_score(nikkei, spx, ndx, usdjpy, vix):
    score = 0
    score += 2 if nikkei > 0 else -2 if nikkei < 0 else 0        # 日経現物
    score += 2 if spx > 0 else -2 if spx < 0 else 0              # S&P500
    score += 3 if ndx > 0 else -3 if ndx < 0 else 0             # NASDAQ(重み大)
    score += 2 if usdjpy > 0 else -2 if usdjpy < 0 else 0       # ドル円(円安=+)
    score += 3 if vix < 0 else -3 if vix > 0 else 0            # VIX(低下=買い材料)
    return score


def signal(score):
    if score >= 6:
        return "🔵 強い買い（ロング優勢）"
    elif 2 <= score < 6:
        return "🟢 弱い買い（押し目狙い）"
    elif -1 <= score <= 1:
        return "🟡 ノートレード（レンジ）"
    elif -5 <= score <= -2:
        return "🟠 弱い売り（戻り売り）"
    else:
        return "🔴 強い売り（ショート優勢）"


# ===========================================================================
# 更新ボタン
# ===========================================================================
if st.button("🔄 データ更新", type="primary", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

with st.spinner("データ取得中..."):
    rows, fetched_at = fetch_all()

st.caption(f"最終更新: {fetched_at}")
st.divider()

# ===========================================================================
# メトリクス表示(スマホ向けに2列)
# ===========================================================================
for i in range(0, len(rows), 2):
    cols = st.columns(2)
    for j, row in enumerate(rows[i:i + 2]):
        with cols[j]:
            if row["last"] is None:
                st.metric(label=row["name"], value="取得失敗")
            else:
                delta_str = (
                    f"{row['change']:+,.2f} ({row['pct']:+.2f}%) [{row['label']}]"
                    if row["change"] is not None else ""
                )
                st.metric(
                    label=f"{row['mark']} {row['name']}",
                    value=f"{row['last']:,.2f}",
                    delta=delta_str,
                    delta_color="normal",
                )

st.divider()

# ===========================================================================
# 一覧テーブル
# ===========================================================================
table_data = []
for row in rows:
    if row["last"] is None:
        table_data.append({"銘柄": row["name"], "現値": "—", "前日比": "—",
                           "騰落率": "—", "方向": "—", "状態": "—"})
    else:
        table_data.append({
            "銘柄":   row["name"],
            "現値":   f"{row['last']:,.2f}",
            "前日比": f"{row['change']:+,.2f}" if row["change"] is not None else "—",
            "騰落率": f"{row['pct']:+.2f}%" if row["pct"] is not None else "—",
            "方向":   row["mark"],
            "状態":   row["label"],
        })

st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

st.divider()

# ===========================================================================
# シグナル判定
# ===========================================================================
st.subheader("日経225先物 シグナル判定")

change_map = {row["name"]: (row["pct"] if row["pct"] is not None else 0.0)
              for row in rows}

with st.container(border=True):
    st.caption("各指標の変化（％）。ダッシュボードの値が自動入力されます。手で上書きも可能です。")

    # スマホ向けに2列で配置(5項目→3行)
    r1c1, r1c2 = st.columns(2)
    with r1c1:
        in_nikkei = st.number_input("日経現物 (%)", value=float(change_map.get("日経225現物", 0.0)),
                                    step=0.1, format="%.2f")
    with r1c2:
        in_spx = st.number_input("S&P500 (%)", value=float(change_map.get("S&P500", 0.0)),
                                 step=0.1, format="%.2f")

    r2c1, r2c2 = st.columns(2)
    with r2c1:
        in_ndx = st.number_input("NASDAQ (%)", value=float(change_map.get("NASDAQ", 0.0)),
                                 step=0.1, format="%.2f")
    with r2c2:
        in_usdjpy = st.number_input("ドル円 円安+ (%)", value=float(change_map.get("ドル円", 0.0)),
                                    step=0.1, format="%.2f")

    in_vix = st.number_input("VIX 低下=買い (%)", value=float(change_map.get("VIX指数", 0.0)),
                             step=0.1, format="%.2f")

    score = calc_score(in_nikkei, in_spx, in_ndx, in_usdjpy, in_vix)
    result = signal(score)

    m1, m2 = st.columns([1, 2])
    m1.metric("スコア", f"{score:+d}", help="最大 +12 / 最小 -12")
    m2.metric("判定", result)

    st.progress(int((score + 12) / 24 * 100))

st.caption(
    "配点: 日経±2 / S&P500±2 / NASDAQ±3 / ドル円(円安+)±2 / VIX±3（VIX低下=+3）。"
    "判定: ≧6=強い買い, 2〜5=弱い買い, -1〜1=ノートレード, -2〜-5=弱い売り, ≦-6=強い売り。"
)
st.caption("⚠️ 本シグナルは参考情報であり、投資判断や売買成績を保証するものではありません。")

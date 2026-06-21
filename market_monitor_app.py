#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
マーケット・モニター(iPhone / モバイル最適化版)
 - 上部: 各指標 + 右側に「総合判定」「勝率」サマリー
 - 下部: 判定の根拠(指標入力・配点) と バックテストの詳細
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
st.set_page_config(page_title="マーケット・モニター", page_icon="📈",
                   layout="centered", initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
    .block-container {padding: 1.0rem 0.8rem 2.5rem 0.8rem;}
    [data-testid="stMetricValue"] {font-size: 1.15rem;}
    [data-testid="stMetricLabel"] {font-size: 0.78rem;}
    [data-testid="stMetricDelta"] {font-size: 0.72rem;}
    h1 {font-size: 1.4rem;}
    h2, h3 {font-size: 1.1rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📈 マーケット・モニター")
st.caption("データ元: Yahoo Finance ／ 上昇↑・下落↓（VIXは反転、ドル円は円安↑）")

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
INSTRUMENTS = [
    {"name": "日経225先物", "symbol": "NIY=F", "invert": False, "labels": ("上昇", "下落")},
    {"name": "日経225現物", "symbol": "^N225",  "invert": False, "labels": ("上昇", "下落")},
    {"name": "S&P500",      "symbol": "^GSPC",  "invert": False, "labels": ("上昇", "下落")},
    {"name": "NASDAQ",      "symbol": "^IXIC",  "invert": False, "labels": ("上昇", "下落")},
    {"name": "ドル円",      "symbol": "JPY=X",  "invert": False, "labels": ("円安", "円高")},
    {"name": "VIX指数",     "symbol": "^VIX",   "invert": True,  "labels": ("低下", "上昇")},
]

_BT_SYMBOLS = {"nikkei": "^N225", "spx": "^GSPC", "ndx": "^IXIC",
               "usdjpy": "JPY=X", "vix": "^VIX"}
_BT_INVERT = {"nikkei": False, "spx": False, "ndx": False, "usdjpy": False, "vix": True}
_BUCKETS = ["🔵 強い買い（ロング優勢）", "🟢 弱い買い（押し目狙い）",
            "🟡 ノートレード（レンジ）", "🟠 弱い売り（戻り売り）", "🔴 強い売り（ショート優勢）"]


# ---------------------------------------------------------------------------
# 関数定義(レンダリング前にすべて定義)
# ---------------------------------------------------------------------------
def _fmt_asof(ts):
    """データ日付を日本時間で『M月D日』に整形(日付のみ)。失敗時 None。"""
    try:
        if getattr(ts, "tzinfo", None) is not None:
            ts = ts.tz_convert("Asia/Tokyo")
        return f"{ts.month}月{ts.day}日"
    except Exception:
        return None


def _get_quote(symbol, retries=3):
    """
    最新終値・前営業日終値・最新終値の日付(ts) を日足で取得。
    戻り値: (last, prev, ts) / 失敗時 None
    """
    for attempt in range(1, retries + 1):
        try:
            hist = yf.Ticker(symbol).history(period="1mo", interval="1d", auto_adjust=False)
            if hist is None or hist.empty or "Close" not in hist.columns:
                raise ValueError("空のデータ")
            closes = hist["Close"].dropna()
            if len(closes) < 2:
                raise ValueError("データ不足")
            return float(closes.iloc[-1]), float(closes.iloc[-2]), closes.index[-1]
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


@st.cache_data(ttl=60, show_spinner=False)
def fetch_all():
    results = []
    for inst in INSTRUMENTS:
        quote = _get_quote(inst["symbol"])
        if quote is None:
            results.append({**inst, "last": None, "prev": None, "asof": None,
                            "mark": "—", "label": "取得失敗", "change": None, "pct": None})
            continue
        last, prev, ts = quote
        mark, label, change = _decide_mark(last, prev, inst["invert"], inst["labels"])
        pct = (change / prev * 100) if prev else 0.0
        results.append({**inst, "last": last, "prev": prev, "asof": _fmt_asof(ts),
                        "mark": mark, "label": label, "change": change, "pct": pct})
    return results, datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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


def _mark_sign(pct, invert):
    if pct == 0:
        return 0
    rising = pct > 0
    show_up = rising if not invert else (not rising)
    return 1 if show_up else -1


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _fetch_close_history(symbol, period="5y"):
    for attempt in range(1, 4):
        try:
            df = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=False)
            if df is None or df.empty or "Close" not in df.columns:
                raise ValueError("空")
            s = df["Close"].dropna()
            s.index = s.index.tz_localize(None)
            return s
        except Exception:
            if attempt < 3:
                time.sleep(1.5 * attempt)
    return None


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def run_backtest(period="5y"):
    closes = {}
    for k, sym in _BT_SYMBOLS.items():
        s = _fetch_close_history(sym, period)
        if s is None:
            return None
        closes[k] = s
    df = pd.DataFrame(closes).dropna()
    if len(df) < 60:
        return None

    ret = (df.pct_change() * 100).iloc[1:].copy()
    ret["nikkei_next"] = (df["nikkei"].pct_change() * 100).shift(-1).reindex(ret.index)
    ret["score"] = ret.apply(
        lambda r: calc_score(r["nikkei"], r["spx"], r["ndx"], r["usdjpy"], r["vix"]), axis=1)
    ret["bucket"] = ret["score"].apply(signal)
    ret["pattern"] = ret.apply(
        lambda r: tuple(_mark_sign(r[k], _BT_INVERT[k])
                        for k in ["nikkei", "spx", "ndx", "usdjpy", "vix"]), axis=1)

    valid = ret.dropna(subset=["nikkei_next"])
    bucket_stats = []
    for b in _BUCKETS:
        sub = valid[valid["bucket"] == b]
        n = len(sub)
        up = (sub["nikkei_next"] > 0).mean() * 100 if n else None
        dn = (sub["nikkei_next"] < 0).mean() * 100 if n else None
        bucket_stats.append({"bucket": b, "n": n, "up": up, "dn": dn})

    span = f"{df.index.min():%Y-%m-%d} 〜 {df.index.max():%Y-%m-%d}（{len(df)}営業日）"
    return {"valid": valid, "bucket_stats": bucket_stats, "span": span}


# ===========================================================================
# 更新ボタン & データ取得
# ===========================================================================
if st.button("🔄 データ更新", type="primary", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

with st.spinner("データ取得中..."):
    rows, fetched_at = fetch_all()

# ライブ値からスコア・判定を算出
change_map = {row["name"]: (row["pct"] if row["pct"] is not None else 0.0) for row in rows}
live_score = calc_score(
    change_map.get("日経225現物", 0.0), change_map.get("S&P500", 0.0),
    change_map.get("NASDAQ", 0.0), change_map.get("ドル円", 0.0),
    change_map.get("VIX指数", 0.0),
)
live_result = signal(live_score)

# バックテスト(過去5年)を実行し、現在パターンの勝率を算出
with st.spinner("過去5年データを集計中..."):
    bt = run_backtest("5y")

today_pattern = tuple(
    _mark_sign(change_map.get(name, 0.0), inv)
    for name, inv in [("日経225現物", False), ("S&P500", False), ("NASDAQ", False),
                      ("ドル円", False), ("VIX指数", True)]
)
match = None
if bt is not None:
    match = bt["valid"][bt["valid"]["pattern"].apply(lambda p: p == today_pattern)]

st.caption(f"最終更新: {fetched_at}")
st.divider()

# ===========================================================================
# 上部: 各指標(左) + 総合判定・勝率サマリー(右)
# ===========================================================================
top_left, top_right = st.columns([1.25, 1])

# --- 左: 各指標メトリクス(2列グリッド) ---
with top_left:
    for i in range(0, len(rows), 2):
        gcols = st.columns(2)
        for j, row in enumerate(rows[i:i + 2]):
            with gcols[j]:
                if row["last"] is None:
                    st.metric(label=row["name"], value="取得失敗")
                else:
                    delta_str = (f"{row['change']:+,.1f} ({row['pct']:+.2f}%)"
                                 if row["change"] is not None else "")
                    st.metric(label=f"{row['mark']} {row['name']}",
                              value=f"{row['last']:,.0f}", delta=delta_str,
                              delta_color="normal")
                    st.caption(f"🗓 {row['asof']} 終値" if row.get("asof") else "🗓 日付不明")

# --- 右: 総合判定 + 勝率 ---
with top_right:
    st.markdown("**総合判定**")
    st.metric("判定", live_result)
    st.metric("スコア", f"{live_score:+d}", help="最大 +12 / 最小 -12")
    st.progress(int((live_score + 12) / 24 * 100))

    st.markdown("**現パターン勝率**")
    if bt is None:
        st.caption("勝率: 取得失敗")
    elif match is None or len(match) == 0:
        st.caption("過去5年に同一パターンなし")
    else:
        up_rate = (match["nikkei_next"] > 0).mean() * 100
        dn_rate = (match["nikkei_next"] < 0).mean() * 100
        st.metric("買い勝率", f"{up_rate:.0f}%",
                  help=f"翌日上昇 ／ 過去一致 {len(match)}回")
        st.metric("売り勝率", f"{dn_rate:.0f}%", help="翌日下落")
        if len(match) < 20:
            st.caption("⚠️ 一致が少なく参考値")

st.divider()

# ===========================================================================
# 一覧テーブル
# ===========================================================================
table_data = []
for row in rows:
    if row["last"] is None:
        table_data.append({"銘柄": row["name"], "現値": "—", "前日比": "—",
                           "騰落率": "—", "方向": "—", "状態": "—", "時点": "—"})
    else:
        table_data.append({
            "銘柄":   row["name"],
            "現値":   f"{row['last']:,.2f}",
            "前日比": f"{row['change']:+,.2f}" if row["change"] is not None else "—",
            "騰落率": f"{row['pct']:+.2f}%" if row["pct"] is not None else "—",
            "方向":   row["mark"],
            "状態":   row["label"],
            "時点":   row.get("asof") or "—",
        })
st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

st.divider()

# ===========================================================================
# 判定の根拠(指標の変化・配点) ※位置はそのまま
# ===========================================================================
st.subheader("判定の根拠（指標の変化）")

with st.container(border=True):
    st.caption("各指標の変化（％）。ダッシュボードの値が自動入力されます。手で上書きすると下の結果が再計算されます。")

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

    manual_score = calc_score(in_nikkei, in_spx, in_ndx, in_usdjpy, in_vix)
    manual_result = signal(manual_score)
    mm1, mm2 = st.columns([1, 2])
    mm1.metric("スコア(入力値)", f"{manual_score:+d}")
    mm2.metric("判定(入力値)", manual_result)

st.caption(
    "配点: 日経±2 / S&P500±2 / NASDAQ±3 / ドル円(円安+)±2 / VIX±3（VIX低下=+3）。"
    "判定: ≧6=強い買い, 2〜5=弱い買い, -1〜1=ノートレード, -2〜-5=弱い売り, ≦-6=強い売り。"
)

st.divider()

# ===========================================================================
# バックテストの詳細(スコア帯別 勝率) ※位置はそのまま
# ===========================================================================
st.subheader("バックテストの詳細（過去データ照合）")

if bt is None:
    st.error("過去データの取得に失敗しました。少し待ってから「データ更新」で再試行してください。")
else:
    st.caption(f"対象期間: {bt['span']} ／ 翌営業日の日経225(現物)の方向で判定")
    bt_table = []
    for s in bt["bucket_stats"]:
        is_buy = "買い" in s["bucket"]
        win = (s["up"] if is_buy else s["dn"]) if s["n"] else None
        bt_table.append({
            "判定": s["bucket"],
            "回数": s["n"],
            "翌日上昇": f"{s['up']:.1f}%" if s["up"] is not None else "—",
            "翌日下落": f"{s['dn']:.1f}%" if s["dn"] is not None else "—",
            "想定勝率": (f"{win:.1f}%" if win is not None else "—"),
        })
    st.dataframe(pd.DataFrame(bt_table), use_container_width=True, hide_index=True)
    st.caption("「想定勝率」= 買い判定はその翌日に上昇した割合、売り判定は下落した割合。")

st.caption(
    "⚠️ 過去の勝率は将来の成績を保証しません。米国指数とVIX・ドル円は日本市場のクローズ後にも動くため、"
    "同一日付の変化で翌営業日の日経を予測する簡易ルールで集計しています。本シグナルは参考情報です。"
)

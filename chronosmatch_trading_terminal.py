from __future__ import annotations
import os, statistics, time
from datetime import datetime
import pandas as pd
import streamlit as st

from market_data.simulator import SimulatedMarketData, INSTRUMENTS
from paper_trading import PaperTradingEngine

st.set_page_config(page_title="ChronosMatch | Trading Terminal", page_icon="⚡",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&display=swap');
:root{--bg:#080d16;--panel:#101a29;--panel2:#142235;--line:#26384d;--muted:#8fa4bc;--text:#edf4fc;--green:#20c997;--red:#ff637d;--blue:#68a8ff}
.stApp{background:var(--bg);color:var(--text);font-family:Manrope,sans-serif}
header[data-testid="stHeader"]{background:rgba(8,13,22,.92)}
.block-container{padding-top:1.2rem;max-width:1600px}
h1,h2,h3{color:var(--text);font-family:Manrope,sans-serif;letter-spacing:-.03em}
[data-testid="stMetric"]{background:linear-gradient(145deg,#142235,#0e1725);border:1px solid var(--line);padding:15px 17px;border-radius:13px}
[data-testid="stMetricLabel"]{color:var(--muted)}
[data-testid="stMetricValue"]{font-family:'DM Mono',monospace;color:var(--text)}
[data-testid="stDataFrame"],[data-testid="stTable"]{border:1px solid var(--line);border-radius:10px}
.stButton>button{border-radius:8px;border:1px solid var(--line);font-weight:700;min-height:2.5rem}
.stButton>button[kind="primary"]{background:#ff5267;border-color:#ff5267;color:white}
.stTextInput input,.stNumberInput input,.stSelectbox div[data-baseweb="select"]>div,.stTextArea textarea{background:#111e2e;color:var(--text);border-color:var(--line);border-radius:8px}
div[role="radiogroup"]{gap:.35rem}
div[role="radiogroup"] label{background:#111e2e;border:1px solid var(--line);padding:.55rem .85rem;border-radius:8px}
hr{border-color:var(--line)}
small,.muted{color:var(--muted)}
section[data-testid="stSidebar"]{background:#0b1320}
</style>
""", unsafe_allow_html=True)

def money(v): return f"₹{v:,.2f}"
def table(df, **kwargs):
    if df is None or df.empty: st.info("No records yet."); return
    st.dataframe(df, use_container_width=True, hide_index=True, **kwargs)

if "market" not in st.session_state:
    st.session_state.market = SimulatedMarketData()
if "paper" not in st.session_state:
    st.session_state.paper = PaperTradingEngine()
if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK"]
if "selected" not in st.session_state:
    st.session_state.selected = "RELIANCE"
if "ring_writes" not in st.session_state:
    st.session_state.ring_writes = 0
if "ring_reads" not in st.session_state:
    st.session_state.ring_reads = 0
if "ring_capacity" not in st.session_state:
    st.session_state.ring_capacity = 1024
if "latency_samples" not in st.session_state:
    st.session_state.latency_samples = []

market=st.session_state.market
paper=st.session_state.paper

# Header + navigation
head1,head2,head3=st.columns([3.4,1.3,1.3])
with head1:
    st.markdown("<h1 style='margin:0'>⚡ CHRONOSMATCH</h1><div style='color:#8fa4bc;font-size:.82rem;letter-spacing:.16em'>PAPER TRADING · LOW-LATENCY MATCHING LAB</div>",unsafe_allow_html=True)
with head2:
    status="RUNNING" if market.running else "PAUSED"
    color="#20c997" if market.running else "#ffb454"
    st.markdown(f"<div style='padding:12px;border:1px solid #26384d;border-radius:10px;text-align:center;color:{color};font-weight:800'>● {status}</div>",unsafe_allow_html=True)
with head3:
    st.markdown(f"<div style='padding:12px;border:1px solid #26384d;border-radius:10px;text-align:center;color:#8fa4bc'>DEMO · {datetime.now().strftime('%d %b %Y %H:%M:%S')}</div>",unsafe_allow_html=True)

pages=["Market Overview","Trading Terminal","Watchlist","Portfolio","Positions","Orders","History","Analytics","AI Agent","Backend & Engine"]
page=st.radio("Navigation",pages,horizontal=True,label_visibility="collapsed")
st.markdown("<div style='background:#332c14;border:1px solid #66521c;color:#f2c66d;padding:10px 14px;border-radius:9px;margin:.6rem 0 1rem'>DEMO MODE — all quotes, indices and liquidity are synthetic. Paper orders never reach an exchange or broker.</div>",unsafe_allow_html=True)

# Market controls are available on every page
ctl1,ctl2,ctl3,ctl4=st.columns([1,1,1,5])
with ctl1:
    if st.button("▶ Start feed",use_container_width=True): market.start(); st.rerun()
with ctl2:
    if st.button("Ⅱ Pause",use_container_width=True): market.pause(); st.rerun()
with ctl3:
    if st.button("↻ Advance tick",use_container_width=True):
        market.start(); market.tick(1); market.pause(); st.rerun()
with ctl4:
    st.caption("Start feed enables simulated updates when you advance the market. Use Advance tick to create a fresh price sample.")

# one market tick per page render while running
if market.running:
    market.tick(1)

quotes={q["symbol"]:q for q in market.quotes()}
marks={s:q["price"] for s,q in quotes.items()}
selected=st.session_state.selected
paper.ensure_instrument(selected,marks[selected])
portfolio=paper.portfolio(marks)
metrics=paper.metrics()
orders=paper.orders()
trades=paper.trades()

def show_indices():
    cols=st.columns(4)
    for col,item in zip(cols,market.indices()):
        with col:
            delta=item["change_pct"]
            st.metric(item["name"],f"{item['value']:,.2f}",f"{delta:+.2f}%")

def show_summary():
    total_orders=metrics["orders"]
    execs=metrics["executions"]
    notional=sum(t["value"] for t in trades)
    c=st.columns(4)
    c[0].metric("Available cash",money(portfolio["cash"]))
    c[1].metric("Market value",money(portfolio["market_value"]))
    c[2].metric("Total equity",money(portfolio["equity"]))
    c[3].metric("Total P&L",money(portfolio["total_pnl"]))
    d=st.columns(4)
    d[0].metric("Orders placed",f"{total_orders:,}")
    d[1].metric("Executions",f"{execs:,}")
    d[2].metric("Open orders",f"{metrics['open_orders']:,}")
    d[3].metric("Traded notional",money(notional))

def show_market_table(symbols=None):
    symbols=symbols or list(INSTRUMENTS)
    rows=[]
    for s in symbols:
        q=quotes[s]
        rows.append({"Symbol":s,"Company":q["company"],"Sector":q["sector"],
                     "Last price":money(q["price"]),"Change":f"{q['change']:+.2f}",
                     "Change %":f"{q['change_pct']:+.2f}%","Volume":f"{q['volume']:,}"})
    table(pd.DataFrame(rows))

def show_chart(symbol):
    bars=market.history(symbol,160)
    df=pd.DataFrame(bars)
    st.subheader(f"{symbol} · Price chart")
    if df.empty: st.info("Waiting for simulated ticks."); return
    interval=st.select_slider("Chart interval",options=["1m","5m","15m","1h","1D"],value="1m")
    # Synthetic ticks are grouped for display; they are not exchange historical candles.
    if interval!="1m":
        n={"5m":5,"15m":15,"1h":30,"1D":60}[interval]
        df=df.tail(max(n,1)).reset_index(drop=True)
    try:
        import plotly.graph_objects as go
        fig=go.Figure(data=[go.Candlestick(x=df["timestamp"],open=df["open"],high=df["high"],low=df["low"],close=df["close"],name=symbol)])
        fig.update_layout(template="plotly_dark",height=430,margin=dict(l=10,r=10,t=20,b=10),
                          paper_bgcolor="#101a29",plot_bgcolor="#101a29",
                          xaxis_rangeslider_visible=False)
        st.plotly_chart(fig,use_container_width=True)
    except ImportError:
        st.line_chart(df.set_index("timestamp")["close"],height=360)
    st.caption("Synthetic OHLC samples. Interval selection groups display samples; no historical NSE/BSE feed is connected.")

def show_depth(symbol):
    depth=paper.order_book(symbol,10,quotes[symbol]["price"])
    b=pd.DataFrame(depth["bids"]); a=pd.DataFrame(depth["asks"])
    for df in (b,a):
        if not df.empty: df["price"]=df["price"]/100
    left,right=st.columns(2)
    with left:
        st.markdown("**BID DEPTH**")
        table(b.rename(columns={"price":"Bid (₹)","quantity":"Quantity"}) if not b.empty else b)
    with right:
        st.markdown("**ASK DEPTH**")
        table(a.rename(columns={"price":"Ask (₹)","quantity":"Quantity"}) if not a.empty else a)

def order_ticket(symbol):
    quote=quotes[symbol]
    depth=paper.order_book(symbol,5,quote["price"])
    best_bid=depth["bids"][0]["price"]/100 if depth["bids"] else quote["price"]*.999
    best_ask=depth["asks"][0]["price"]/100 if depth["asks"] else quote["price"]*1.001
    st.markdown(f"**Bid {money(best_bid)} · Ask {money(best_ask)}**")
    with st.form("paper_order_form",clear_on_submit=False):
        side=st.radio("Side",["BUY","SELL"],horizontal=True)
        qty=st.number_input("Quantity",min_value=1,max_value=100000,value=1,step=1)
        limit=st.number_input("Limit price (₹)",min_value=.01,value=float(round(best_ask if side=="BUY" else best_bid,2)),step=.05,format="%.2f")
        submitted=st.form_submit_button("Submit paper order",type="primary",use_container_width=True)
    if submitted:
        try:
            result=paper.place_limit_order(symbol,side,int(qty),float(limit),quote["price"])
            if result["status"]=="REJECTED": st.error(result["message"])
            else: st.success(f"Order #{result['order_id']} submitted · {result['status']}")
            st.rerun()
        except Exception as exc: st.error(f"Order submission failed: {exc}")

if page=="Market Overview":
    st.title("Trading Performance & Statistics")
    st.caption("Comprehensive performance execution, account health and market activity.")
    show_indices(); st.markdown("### Account performance"); show_summary()
    left,right=st.columns([1.5,1])
    with left:
        st.subheader("Watchlist & market movers")
        show_market_table(st.session_state.watchlist)
    with right:
        st.subheader("Most active instruments")
        active=sorted(quotes.values(),key=lambda q:q["volume"],reverse=True)[:5]
        table(pd.DataFrame([{"Symbol":q["symbol"],"Volume":q["volume"],"Last":money(q["price"])} for q in active]))
    st.subheader("Recent executions")
    table(pd.DataFrame(trades[:8]))

elif page=="Trading Terminal":
    st.title("Trading Terminal")
    st.caption("Instrument selection · charting · market depth · paper order routing")
    symbol=st.selectbox("Instrument",list(INSTRUMENTS),index=list(INSTRUMENTS).index(selected))
    st.session_state.selected=symbol
    q=quotes[symbol]
    c=st.columns(4)
    c[0].metric(symbol,money(q["price"]),f"{q['change']:+.2f} ({q['change_pct']:+.2f}%)")
    c[1].metric("Volume",f"{q['volume']:,}")
    c[2].metric("Sector",q["sector"])
    c[3].metric("Exchange label","SIMULATED")
    chart_col,ticket_col=st.columns([2.2,1])
    with chart_col: show_chart(symbol)
    with ticket_col: st.subheader("Paper order ticket"); order_ticket(symbol)
    show_depth(symbol)

elif page=="Watchlist":
    st.title("Watchlist")
    col1,col2=st.columns([2,1])
    with col1: show_market_table(st.session_state.watchlist)
    with col2:
        add=st.selectbox("Add instrument",[s for s in INSTRUMENTS if s not in st.session_state.watchlist] or ["All added"])
        if st.button("＋ Add to watchlist",disabled=add=="All added"):
            st.session_state.watchlist.append(add); st.rerun()
        remove=st.selectbox("Remove instrument",st.session_state.watchlist)
        if st.button("Remove selected"):
            if len(st.session_state.watchlist)>1: st.session_state.watchlist.remove(remove)
            st.rerun()

elif page in ("Portfolio","Positions"):
    st.title("Portfolio & Positions")
    show_summary()
    pos=pd.DataFrame(portfolio["positions"])
    if not pos.empty:
        pos=pos.rename(columns={"symbol":"Symbol","quantity":"Quantity","average_cost":"Average cost","last_price":"Last price","market_value":"Market value","unrealized_pnl":"Unrealized P&L"})
        table(pos)
    else: st.info("No holdings yet. Submit a paper BUY order to create a position.")

elif page=="Orders":
    st.title("Order Management")
    st.caption("Open orders can be cancelled. Filled and cancelled orders remain in the audit history.")
    odf=pd.DataFrame(orders)
    if not odf.empty:
        table(odf)
        open_orders=[o for o in orders if o.get("status") in ("OPEN","PARTIAL") and o.get("order_id")]
        if open_orders:
            labels={f"#{o['order_id']} · {o['symbol']} · {o['side']} · {o['remaining_quantity']} remaining":o["order_id"] for o in open_orders}
            choice=st.selectbox("Select open order to cancel",list(labels))
            if st.button("Cancel selected order",type="primary"):
                if paper.cancel_order(labels[choice]): st.success("Order cancelled and reservation released."); st.rerun()
                else: st.error("Cancellation failed. The order may already be filled or absent from the book.")
        else: st.info("There are no cancellable open orders.")
    else: st.info("No orders submitted yet.")

elif page=="History":
    st.title("Trade & Order History")
    tab1,tab2=st.tabs(["Orders","Executions"])
    with tab1: table(pd.DataFrame(orders))
    with tab2: table(pd.DataFrame(trades))

elif page=="Analytics":
    st.title("Trading Analytics")
    show_summary()
    c1,c2=st.columns(2)
    with c1:
        st.subheader("Order lifecycle")
        odf=pd.DataFrame(orders)
        if not odf.empty:
            counts=odf["status"].value_counts()
            st.bar_chart(counts)
        else: st.info("Order statistics will appear after orders are submitted.")
    with c2:
        st.subheader("Activity by ticker")
        if trades:
            tdf=pd.DataFrame(trades)
            st.bar_chart(tdf.groupby("symbol")["value"].sum())
        else: st.info("Ticker activity will appear after executions.")
    if trades:
        tdf=pd.DataFrame(trades)
        st.metric("Cumulative traded notional",money(tdf["value"].sum()))
        st.line_chart(tdf.set_index("timestamp")["value"])

elif page=="AI Agent":
    st.title("ChronosMatch AI Agent")
    st.caption("Read-only educational assistant. It cannot submit, modify or cancel orders.")
    context=st.selectbox("Context instrument",list(INSTRUMENTS),index=list(INSTRUMENTS).index(selected))
    question=st.text_area("Ask about market, portfolio or engine",placeholder="Explain the current bid-ask spread, my P&L, or P99 latency.")
    if st.button("Ask ChronosMatch AI",type="primary"):
        q=quotes[context]; p=paper.portfolio(marks)
        depth=paper.order_book(context,5,quotes[context]["price"])
        bid=depth["bids"][0]["price"]/100 if depth["bids"] else None
        ask=depth["asks"][0]["price"]/100 if depth["asks"] else None
        lat=paper.metrics()["route_latencies_us"]
        p99=statistics.quantiles(lat,n=100)[98] if len(lat)>=100 else (max(lat) if lat else 0)
        prompt=(question or "Summarize the current demo market.").lower()
        if "spread" in prompt:
            answer=f"{context} best bid is {money(bid) if bid else 'N/A'} and best ask is {money(ask) if ask else 'N/A'}. The spread is {money(ask-bid) if bid and ask else 'unavailable'}. A BUY limit order needs to meet or exceed an available ask to execute."
        elif "p&l" in prompt or "pnl" in prompt or "portfolio" in prompt:
            answer=f"Your simulated portfolio equity is {money(p['equity'])}, cash is {money(p['cash'])}, market value is {money(p['market_value'])}, and unrealized P&L is {money(p['unrealized_pnl'])}, and realized P&L is {money(p['realized_pnl'])}. Values are based on synthetic marks."
        elif "latency" in prompt or "p99" in prompt:
            answer=f"Recorded local paper-order route samples: {len(lat)}. Approximate observed P99 sample is {p99:.2f} microseconds. This is application-level local timing, not exchange/network latency."
        else:
            answer=f"{context} is at {money(q['price'])} ({q['change_pct']:+.2f}%). Simulated volume is {q['volume']:,}. The market feed is synthetic. This assistant provides educational context only and does not provide financial advice."
        st.markdown("### Analysis"); st.write(answer)
    st.warning("AI explanations are deterministic local analytics in this build. Connect a model provider separately if you want generative responses.")

elif page=="Backend & Engine":
    st.title("Backend Control Room")
    st.caption("Operational view of the local paper-trading stack.")
    m=paper.metrics(); lat=m["route_latencies_us"]
    p95=statistics.quantiles(lat,n=20)[18] if len(lat)>=20 else (max(lat) if lat else 0)
    p99=statistics.quantiles(lat,n=100)[98] if len(lat)>=100 else (max(lat) if lat else 0)
    cols=st.columns(4)
    cols[0].metric("Paper orders",m["orders"]); cols[1].metric("Executions",m["executions"])
    cols[2].metric("Open orders",m["open_orders"]); cols[3].metric("Rejected",m["rejected"])
    cols=st.columns(4)
    cols[0].metric("P95 route latency",f"{p95:.2f} µs")
    cols[1].metric("P99 route latency",f"{p99:.2f} µs")
    cols[2].metric("Ring writes",m["ring_writes"])
    cols[3].metric("Ring reads",m["ring_reads"])
    st.subheader("Backend architecture")
    st.code("SyntheticMarketData → Streamlit UI → PaperTradingEngine\n                                  ↓\n                         mmap RingBuffer (local FIFO)\n                                  ↓\n                         Cython OrderBook (native matching)\n                                  ↓\n                    Trades → Portfolio → Analytics",language="text")
    st.caption("The current ring-buffer demonstration is synchronous within one Streamlit process. This is not cross-process IPC, exchange connectivity or production HFT infrastructure.")
    st.subheader("Cython order book · selected instrument")
    show_depth(selected)
    st.subheader("Latency samples")
    if lat: st.line_chart(pd.Series(lat,name="Route latency (µs)"))
    else: st.info("Latency samples appear after paper orders are submitted.")
    st.subheader("Runtime component status")
    status_df=pd.DataFrame([
        {"Component":"Cython OrderBook","Status":"Loaded","Role":"Price-time priority matching"},
        {"Component":"mmap RingBuffer","Status":"Loaded","Role":"Local FIFO hand-off demonstration"},
        {"Component":"Synthetic Market Feed","Status":"Running" if market.running else "Paused","Role":"Generated quote updates"},
        {"Component":"Broker Gateway","Status":"Not connected","Role":"No live order routing"},
        {"Component":"Persistent Database","Status":"Not configured","Role":"Session state only"},
    ])
    table(status_df)

st.markdown("---")
st.caption("CHRONOSMATCH · Educational paper-trading prototype · Synthetic market data · No live quotes, broker execution or investment advice.")

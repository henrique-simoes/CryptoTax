# CryptoTax.py  –  PnL + MTM (FIFO / LIFO / HIFO)  com PTAX diário
# https://github.com/henrique-simoes/CryptoTax

import pandas as pd, requests, datetime as dt, argparse, re, pathlib

# ─── CONFIG ────────────────────────────────────────────────────────────────
ARQ_XLS = pathlib.Path(__file__).with_name("Transacoes.xlsx")
OUT_DIR = ARQ_XLS.parent

# ─── CLI ───────────────────────────────────────────────────────────────────
cli = argparse.ArgumentParser()
cli.add_argument("-m", "--method", choices=["FIFO", "LIFO", "HIFO"], default="FIFO")
cli.add_argument("--mtm", action="store_true")
args = cli.parse_args()
METODO = args.method.upper()

# ─── PTAX ------------------------------------------------------------------
BC = ("https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
      "CotacaoDolarPeriodo(dataInicial=@di,dataFinalCotacao=@df)"
      "?@di='{di}'&@df='{df}'&$select=cotacaoVenda,dataHoraCotacao&$format=json")

def load_ptax(ini,fim):
    url = BC.format(
        di=dt.datetime.strptime(ini,"%Y-%m-%d").strftime("%m-%d-%Y"),
        df=dt.datetime.strptime(fim,"%Y-%m-%d").strftime("%m-%d-%Y"))
    out={}
    while url:
        j=requests.get(url,timeout=10).json()
        for v in j["value"]:
            out[v["dataHoraCotacao"][:10]] = float(v["cotacaoVenda"])
        url = j.get("@odata.nextLink")
    return out

def rate_for(day,mp):
    d=dt.date.fromisoformat(day)
    for _ in range(7):
        if d.isoformat() in mp: return mp[d.isoformat()]
        d -= dt.timedelta(days=1)
    return 5.2

fmt_brl = lambda v: "R$ "+f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X",".")

# ─── DATA PARSE ------------------------------------------------------------
re_date = re.compile(r"^date\s*\(utc", re.I)
def detect_date(df): return next(c for c in df.columns if re_date.match(c.replace("\u2011","-")))
def parse_dt(v,c):
    if pd.isna(v): return pd.NaT
    d=pd.to_datetime(v,format="%Y-%m-%d %H:%M:%S",errors="coerce",dayfirst=True)
    m=re.search(r"UTC([+-]\d+)?",c.replace("\u2011","-")); off=int(m.group(1)or 0) if m else 0
    return d-pd.Timedelta(hours=off)

# ─── LOTES -----------------------------------------------------------------
def retirar(lots,qty,met):
    cost=0; rem=qty
    while rem>1e-12 and lots:
        idx=0 if met=="FIFO" else -1
        if met=="HIFO": idx=max(range(len(lots)), key=lambda i: lots[i][1]/lots[i][0])
        q,c=lots[idx]; take=min(rem,q); cost+=c*(take/q); q-=take
        lots[idx:(idx+1)] = [(q,c*q/(q+take))] if q>1e-12 else []
        rem-=take
    return cost

# ─── CARREGA PLANILHA ------------------------------------------------------
xls  = pd.ExcelFile(ARQ_XLS)
abas = {n: xls.parse(n) for n in xls.sheet_names}
for n,df in abas.items():
    col = detect_date(df); df["dt"] = df[col].apply(lambda v: parse_dt(v,col))

trade, compras = abas["trade"], abas["Compras"]
deps,  depsBRL = abas["Depositos"], abas["Depositos_BRL"]

datas = pd.concat([df["dt"] for df in abas.values()]).dropna().dt.strftime("%Y-%m-%d")
ptax  = load_ptax(datas.min(), datas.max())

# ─── TRANSAÇÕES ------------------------------------------------------------
TX=[]
acq  = lambda d,m,a,q,c: TX.append((d,m,a,"acq", q,c,0.0))
sale = lambda d,m,a,q,p: TX.append((d,m,a,"sale",q,0.0,p))

# depósitos cripto  (usa Cost BRL se existir)
for _,r in deps.iterrows():
    if pd.isna(r["dt"]): continue
    mes  = r["dt"].strftime("%Y-%m")
    qty  = float(r["Valor"])
    custo = float(r["Cost BRL"]) if "Cost BRL" in r and not pd.isna(r["Cost BRL"]) \
            else qty * rate_for(r["dt"].strftime("%Y-%m-%d"), ptax)
    acq(r["dt"], mes, r["Moeda"], qty, custo)

# depósitos BRL
for _,r in depsBRL.iterrows():
    if pd.isna(r["dt"]): continue
    val=float(str(r["Receive Amount"]).split()[0])
    acq(r["dt"], r["dt"].strftime("%Y-%m"), "BRL", val, val)

# compras BRL→cripto
for _,r in compras.iterrows():
    if pd.isna(r["dt"]): continue
    q,a = str(r["Receive Amount"]).split()
    acq(r["dt"], r["dt"].strftime("%Y-%m"), a, float(q),
        float(r["Spend Amount"].split()[0]))

# ─── trades ────────────────────────────────────────────────────────────────
for _, r in trade.iterrows():
    if pd.isna(r["dt"]):
        continue

    a = r["Base Asset"]
    if a in ("USDT", "BRL"):
        continue

    dia = r["dt"].strftime("%Y-%m-%d")
    rate = rate_for(dia, ptax)

    price, qty = float(r["Price"]), float(r["Amount"])
    fee, feeC = float(r["Fee"]), r["Fee Coin"]

    mes = r["dt"].strftime("%Y-%m")
    in_brl = (r["Quote Asset"] == "BRL")
    fx = 1 if in_brl else rate

    if r["Type"].upper() == "BUY":
        net_qty = qty - (fee if feeC == a else 0)
        total_cost = price * qty * fx
        if feeC == "USDT" and not in_brl:
            total_cost += fee * fx
        acq(r["dt"], mes, a, net_qty, total_cost)

    else:  # SELL
        net_qty = qty - (fee if feeC == a else 0)
        gross_procs = price * qty
        fee_usdt = (fee * fx) if feeC == "USDT" and not in_brl else 0
        net_procs = gross_procs * fx - fee_usdt
        sale(r["dt"], mes, a, net_qty, net_procs)

# ─── INVENTÁRIO & PnL ------------------------------------------------------
df_tx=pd.DataFrame(TX,columns=["dt","mes","ativo","tipo","qty","cost","proc"]).sort_values("dt")
inv,avg,mesmap={}, {}, {}
for _,r in df_tx.iterrows():
    inv.setdefault(r.ativo,[]); avg.setdefault(r.ativo,0)
    rec=mesmap.setdefault(r.mes,{}).setdefault(r.ativo,{"b":0,"s":0,"r":0,"g":0,"sales":[]})
    if r.tipo=="acq":
        inv[r.ativo].append([r.qty,r.cost]); rec["b"]+=r.qty
        tq=sum(q for q,_ in inv[r.ativo]); tc=sum(c for _,c in inv[r.ativo])
        avg[r.ativo]=tc/tq if tq else 0
    else:
        rec["s"]+=r.qty; pnl=r.proc-retirar(inv[r.ativo],r.qty,METODO)
        rec["g"]+=pnl; rec["sales"].append((r["dt"],pnl))
    rec["r"]=sum(q for q,_ in inv[r.ativo])

# ─── CSV RESUMO ------------------------------------------------------------
rows=[]
for mes in sorted(mesmap):
    y,mn=map(int,mes.split("-")); fim=dt.datetime(y,mn,1)+pd.offsets.MonthEnd()
    for a,d in mesmap[mes].items():
        g30=g14=g7=0
        for ds,p in d["sales"]:
            dias=(fim-ds)/pd.Timedelta("1d")
            if dias<=30:g30+=p
            if dias<=14:g14+=p
            if dias<=7 :g7 +=p
        desc=(f"Cripto {a} – {mes}\n"
              f"Comprado: {d['b']:.4f} | Vendido: {d['s']:.4f}\n"
              f"Restante: {d['r']:.4f}\n"
              f"Custo médio: {fmt_brl(avg[a])}\n"
              f"{'Lucro' if d['g']>=0 else 'Prejuízo'}: {fmt_brl(d['g'])}")
        rows.append([mes,a,d["b"],d["s"],d["r"],
                     fmt_brl(d["g"]),fmt_brl(g30),fmt_brl(g14),fmt_brl(g7),
                     desc,fmt_brl(avg[a])])

pd.DataFrame(rows,columns=[
    "Mês","Ativo","Quantidade Comprada","Quantidade Vendida","Quantidade Restante",
    "Ganho Total (BRL)","Ganho Últimos 30 dias (BRL)","Ganho Últimos 14 dias (BRL)",
    "Ganho Últimos 7 dias (BRL)","Descrição","Custo Médio de Compra (BRL)"
]).to_csv(OUT_DIR/f"Visao_Mensal_{METODO}.csv",sep=';',index=False,encoding="utf-8-sig")

# ─── MTM (opcional) --------------------------------------------------------
if args.mtm:
    hist = {}
    for _, r in trade.iterrows():
        if pd.isna(r["dt"]): continue
        if r["Type"].upper() not in {"BUY", "SELL"}: continue
        dia = r["dt"].strftime("%Y-%m-%d")
        
        # Base Asset
        ativo_base = r["Base Asset"]
        preco_base = float(r["Price"])
        hist.setdefault(ativo_base, {})
        if dia not in hist[ativo_base] or preco_base > hist[ativo_base][dia]:
            hist[ativo_base][dia] = preco_base

        # Quote Asset (caso não seja BRL)
        ativo_quote = r["Quote Asset"]
        if ativo_quote != "BRL":
            preco_quote = float(r["Price"])
            hist.setdefault(ativo_quote, {})
            if dia not in hist[ativo_quote] or preco_quote > hist[ativo_quote][dia]:
                hist[ativo_quote][dia] = preco_quote

    mtm_rows=[]
    for mes in sorted(mesmap):
        y,mn=map(int,mes.split("-"))
        last=(dt.datetime(y,mn,1)+pd.offsets.MonthEnd()).date()
        for a,d in mesmap[mes].items():
            qty=d["r"]
            if qty==0 or a not in hist: continue
            price = next(
                (hist[a][(last - dt.timedelta(days=i)).isoformat()]
                 for i in range(8)
                 if (last - dt.timedelta(days=i)).isoformat() in hist[a]),
                0
            )
            rate=rate_for(last.isoformat(),ptax)
            mtm_rows.append([mes,a,qty,price,last.isoformat(),fmt_brl(rate),
                             fmt_brl(price*qty*rate-avg[a]*qty)])

    pd.DataFrame(mtm_rows,columns=[
        "Mês","Ativo","Qtd Restante","Preço USDT","Data","Cotação BRL","MTM Mensal"
    ]).to_csv(OUT_DIR/f"MTM_{METODO}.csv",sep=';',index=False,encoding="utf-8-sig")

print("CSVs gerados com sucesso em", OUT_DIR)

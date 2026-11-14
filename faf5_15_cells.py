# %% [Cell 1] Business Problem + Setup
# CELL 1 | SETUP, CONFIGURATION AND BUSINESS PROBLEM
import os, zipfile, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from IPython.display import display

warnings.filterwarnings("ignore")
pd.set_option("display.max_columns", 40); pd.set_option("display.width", 160)
pd.set_option("display.float_format", lambda v: f"{v:,.2f}")

BUSINESS_PROBLEM = """
BUSINESS PROBLEM
Stakeholder : Freight strategy / logistics planning team (public agency or logistics operator).
Question    : Where is U.S. freight demand concentrated, how is it changing, and how is it
              expected to evolve to 2050 by trade type, transport mode, commodity, corridor and distance?
Decisions   : (1) which modes/corridors/gateways need capacity first, (2) which commodity segments
              are worth prioritising (volume vs value), (3) where are the risks (concentration, dips).
Data        : FHWA/BTS Freight Analysis Framework v5.7.1 (FAF5): tons, value, ton-miles.
Units       : tons = thousand tons | value = million 2017 USD (constant) | tmiles = million ton-miles.
"""
print(BUSINESS_PROBLEM)

# ---------- PATHS (edit ZIP_PATH) ----------
# Recommended: upload FAF5_7_1.zip to Google Drive, then run:  from google.colab import drive; drive.mount('/content/drive')
ZIP_PATH = "/content/drive/MyDrive/FAF5_7_1.zip"
WORK_DIR = Path("/content/faf5"); WORK_DIR.mkdir(parents=True, exist_ok=True)
CSV_PATH, META_PATH = WORK_DIR / "FAF5.7.1.csv", WORK_DIR / "FAF5_metadata.xlsx"
if not (CSV_PATH.exists() and META_PATH.exists()):
    with zipfile.ZipFile(ZIP_PATH) as z:
        z.extractall(WORK_DIR)
OUT_DIR = WORK_DIR / "outputs"; OUT_DIR.mkdir(exist_ok=True)

# ---------- STYLE ----------
NAVY, TEAL, SAFFRON, RED, GREY = "#0B2545", "#13A89E", "#F4A259", "#D1495B", "#8D99AE"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titleweight": "bold", "axes.titlesize": 12, "axes.titlecolor": NAVY,
                     "axes.grid": True, "grid.color": "#E6EAF0", "axes.axisbelow": True})
HIST = list(range(2017, 2025)); FCST = [2030, 2035, 2040, 2045, 2050]
print("CSV:", CSV_PATH, "| exists:", CSV_PATH.exists())

# %% [Cell 2] Data Collection (code books)
# CELL 2 | DATA COLLECTION: official code books from the metadata workbook
xl = pd.ExcelFile(META_PATH)
print("Sheets:", xl.sheet_names)

def codebook(sheet, label_col):
    t = xl.parse(sheet, dtype=str)
    t.columns = [c.strip() for c in t.columns]
    return dict(zip(t["Numeric Label"].str.strip(), t[label_col].str.strip()))

STATE   = codebook("State", "Description")
ZONE    = codebook("FAF Zone (Domestic)", "Short Description")
FOREIGN = codebook("FAF Zone (Foreign)", "Description")
COMM    = codebook("Commodity (SCTG2)", "Description")
MODE    = codebook("Mode", "Description")
DIST    = codebook("Distance Band", "Description")
TRADE   = {"1": "Domestic", "2": "Import", "3": "Export"}
MODE_SHORT = {"1": "Truck", "2": "Rail", "3": "Water", "4": "Air", "5": "Multiple modes & mail",
              "6": "Pipeline", "7": "Other/unknown", "8": "No domestic mode"}
DIST_ORDER = [DIST[str(i)] for i in range(1, 9)]

print({k: len(v) for k, v in dict(STATE=STATE, ZONE=ZONE, FOREIGN=FOREIGN, COMM=COMM, MODE=MODE, DIST=DIST).items()})
display(pd.DataFrame({"field": ["tons_YYYY", "value_YYYY", "tmiles_YYYY", "current_value_YYYY"],
                      "meaning": ["Weight shipped", "Value in constant 2017 USD", "Ton-miles (domestic portion only)", "Value in current USD of each year"],
                      "unit": ["thousand tons", "million USD", "million ton-miles", "million USD"]}))

# %% [Cell 3] Data Collection (load raw data)
# CELL 3 | LOAD THE RAW DATA (2.67 million rows; only the columns this analysis needs)
CODE_COLS = ["fr_orig", "dms_orig", "dms_dest", "fr_dest", "fr_inmode", "dms_mode", "fr_outmode", "sctg2", "trade_type", "dist_band"]
NUM_COLS = ([f"{m}_{y}" for m in ("tons", "value", "tmiles") for y in HIST]
            + [f"{m}_{y}" for m in ("tons", "value") for y in FCST])

# codes such as '011' or '01' have leading zeros -> read them as TEXT first (never as numbers), then store as category
dtypes = {**{c: str for c in CODE_COLS}, **{c: "float64" for c in NUM_COLS}}
df = pd.read_csv(CSV_PATH, usecols=CODE_COLS + NUM_COLS, dtype=dtypes)
for c in CODE_COLS:
    df[c] = df[c].astype("category")

print(f"Rows: {len(df):,} | Columns loaded: {df.shape[1]} | Memory: {df.memory_usage(deep=True).sum()/1e6:,.0f} MB")
display(df.head(3).T.head(14))

# %% [Cell 4] Data Cleaning: quality audit
# CELL 4 | DATA QUALITY AUDIT (nulls, structure, duplicates, impossible values, unknown codes)
n = len(df)
nulls = df[CODE_COLS].isna().sum().to_frame("nulls"); nulls["pct"] = nulls.nulls / n * 100
print("1) Missing values in code columns (foreign fields are EXPECTED to be blank for some trade types):")
display(nulls)

print("\n2) Share of rows with the foreign fields filled, by trade type (1=Domestic, 2=Import, 3=Export):")
display(df.groupby("trade_type", observed=True)[["fr_orig", "fr_dest", "fr_inmode", "fr_outmode"]]
          .agg(lambda s: s.notna().mean()).round(2))

num = df[NUM_COLS]
qc = pd.Series({
    "rows": n,
    "duplicate rows on the 10 key columns": int(df.duplicated(subset=CODE_COLS).sum()),
    "missing numeric cells": int(num.isna().sum().sum()),
    "negative numeric cells": int((num < 0).sum().sum()),
    "rows with zero tons in every year 2017-2024": int((df[[f"tons_{y}" for y in HIST]].sum(axis=1) == 0).sum()),
    "rows with tons_2024 = 0 but value_2024 > 0": int(((df.tons_2024 == 0) & (df.value_2024 > 0)).sum()),
}, name="value")
print("\n3) Integrity checks:"); display(qc.to_frame())

vpt = (df.value_2024 * 1000 / df.tons_2024.replace(0, np.nan)).dropna()      # USD per ton
print("\n4) Value per ton, 2024 (USD/ton) - percentiles:"); display(vpt.quantile([.01, .5, .99, .9999]).to_frame("USD/ton"))

print("\n5) Codes not found in the official code books:")
for col, book in [("dms_orig", ZONE), ("dms_dest", ZONE), ("fr_orig", FOREIGN), ("fr_dest", FOREIGN), ("sctg2", COMM),
                  ("dms_mode", MODE), ("fr_inmode", MODE), ("fr_outmode", MODE), ("dist_band", DIST), ("trade_type", TRADE)]:
    print(f"   {col:<11}", sorted(set(df[col].cat.categories) - set(book)) or "none")
del num, vpt

# %% [Cell 5] Data Cleaning: enrichment
# CELL 5 | DATA CLEANING AND ENRICHMENT (labels, states, analysis cube)
n0 = len(df)
df = df.drop_duplicates(subset=CODE_COLS)                       # key columns should be unique
print(f"Duplicate rows dropped: {n0 - len(df):,}")

df["trade"]      = df["trade_type"].map(TRADE)
df["dom_mode"]   = df["dms_mode"].map(MODE_SHORT)
df["commodity"]  = df["sctg2"].map(COMM)
df["dist_label"] = df["dist_band"].map(DIST)
df["orig_zone"]  = df["dms_orig"].map(ZONE)
df["dest_zone"]  = df["dms_dest"].map(ZONE)
# the first two digits of a FAF zone code are the state FIPS code
state_of = lambda z: STATE.get(str(z)[:2], "Unknown")
df["orig_state"] = df["dms_orig"].map({c: state_of(c) for c in df["dms_orig"].cat.categories})
df["dest_state"] = df["dms_dest"].map({c: state_of(c) for c in df["dms_dest"].cat.categories})

# Pre-aggregated "cube": trade type x mode x commodity x distance band (a few thousand rows, instant to query)
GROUP = ["trade", "dom_mode", "commodity", "dist_label"]
cube = df.groupby(GROUP, observed=True)[NUM_COLS].sum().reset_index()
print(f"Analysis cube: {cube.shape[0]:,} rows | all-year totals reconcile: "
      f"{np.isclose(cube.tons_2024.sum(), df.tons_2024.sum())}")

# reusable helpers (units: tons=thousand, value=million USD, tmiles=million)
def cagr(a, b, years):
    return ((b / a) ** (1 / years) - 1) * 100

def summarise(by, y0=2017, y1=2024, data=None):
    """Tons / value / ton-miles for year y1 with shares, CAGR since y0, value per ton and average haul."""
    d = cube if data is None else data
    a = d.groupby(by, observed=True)[[f"tons_{y0}", f"tons_{y1}", f"value_{y0}", f"value_{y1}", f"tmiles_{y1}"]].sum()
    a.columns = ["t0", "t1", "v0", "v1", "m1"]
    return pd.DataFrame({
        "tons_mt": a.t1 / 1e3, "tons_share_%": a.t1 / a.t1.sum() * 100,
        "value_bn": a.v1 / 1e3, "value_share_%": a.v1 / a.v1.sum() * 100,
        "tmiles_share_%": a.m1 / a.m1.sum() * 100,
        "tons_cagr_%": cagr(a.t0, a.t1, y1 - y0), "value_cagr_%": cagr(a.v0, a.v1, y1 - y0),
        "value_per_ton_usd": a.v1 * 1e3 / a.t1, "avg_haul_miles": a.m1 * 1e3 / a.t1,
    })

# %% [Cell 6] EDA 1: trends
# CELL 6 | EDA 1: OVERALL TRENDS 2017-2024 (tons, value, ton-miles) AND THE 2020 SHOCK
yearly = pd.DataFrame({
    "tons_mt":   [cube[f"tons_{y}"].sum() / 1e3 for y in HIST],     # million tons
    "value_bn":  [cube[f"value_{y}"].sum() / 1e3 for y in HIST],    # billion USD (2017 constant)
    "tmiles_bn": [cube[f"tmiles_{y}"].sum() / 1e3 for y in HIST],   # billion ton-miles
}, index=HIST)
yearly["value_per_ton_usd"] = yearly.value_bn * 1e9 / (yearly.tons_mt * 1e6)
yearly["avg_haul_miles"]    = yearly.tmiles_bn * 1e9 / (yearly.tons_mt * 1e6)
yoy = yearly[["tons_mt", "value_bn", "tmiles_bn"]].pct_change() * 100
display(yearly.join(yoy.add_suffix("_yoy_%")))

CAGR_17_24 = {k: float(cagr(yearly[k].iloc[0], yearly[k].iloc[-1], 7)) for k in ["tons_mt", "value_bn", "tmiles_bn"]}
TMILES_VS_2017 = float(yearly.tmiles_bn.iloc[-1] / yearly.tmiles_bn.iloc[0] * 100 - 100)
COVID = {k: float(yoy.loc[2020, k]) for k in yoy.columns}
print("CAGR 2017-2024 (%):", {k: round(float(v), 2) for k, v in CAGR_17_24.items()})
print("2020 change vs 2019 (%):", {k: round(v, 2) for k, v in COVID.items()})

fig, axes = plt.subplots(1, 3, figsize=(17, 4.6))
for ax, (col, ttl, c) in zip(axes, [("tons_mt", "Tonnage (million tons)", NAVY), ("value_bn", "Value (billion 2017 USD)", TEAL),
                                    ("tmiles_bn", "Ton-miles (billion)", SAFFRON)]):
    ax.plot(yearly.index, yearly[col], marker="o", lw=2.6, color=c)
    ax.axvspan(2019.5, 2020.5, color=RED, alpha=0.10)
    for x_, v in zip(yearly.index, yearly[col]): ax.annotate(f"{v:,.0f}", (x_, v), xytext=(0, 7), textcoords="offset points", ha="center", fontsize=8)
    ax.set_title(ttl); ax.set_ylim(yearly[col].min() * 0.9, yearly[col].max() * 1.08)
fig.suptitle("U.S. freight 2017-2024 (shaded = 2020)", x=0.01, ha="left", fontweight="bold", color=NAVY)
plt.tight_layout(); plt.show()

# %% [Cell 7] EDA 2: trade type and mode
# CELL 7 | EDA 2: TRADE TYPE AND TRANSPORT MODE
by_trade = summarise("trade")
by_mode  = summarise("dom_mode").sort_values("tons_mt", ascending=False)
print("By trade type (2024):"); display(by_trade.round(1))
print("By domestic mode (2024; for imports/exports this is the domestic leg):"); display(by_mode.round(1))

fig, axes = plt.subplots(1, 2, figsize=(16, 5))
pal = {"tons_share_%": NAVY, "value_share_%": TEAL, "tmiles_share_%": SAFFRON}
for ax, tbl, ttl in [(axes[0], by_trade, "Share by trade type, 2024"), (axes[1], by_mode.head(6), "Share by domestic mode, 2024 (top 6 by tons)")]:
    tbl[list(pal)].plot.bar(ax=ax, color=list(pal.values()), width=0.8)
    ax.set_title(ttl); ax.set_ylabel("% of total"); ax.set_xlabel(""); ax.tick_params(axis="x", rotation=20)
    ax.legend(["Tons", "Value", "Ton-miles"], frameon=False)
plt.tight_layout(); plt.show()

# %% [Cell 8] EDA 3: commodities
# CELL 8 | EDA 3: COMMODITIES - VOLUME vs VALUE
by_comm = summarise("commodity").sort_values("value_bn", ascending=False)
by_comm["cum_value_share_%"] = by_comm["value_share_%"].cumsum()
TOP10_VALUE_SHARE = float(by_comm["value_share_%"].head(10).sum())
N_FOR_80 = int((by_comm["cum_value_share_%"] < 80).sum() + 1)
print(f"Top 10 commodities = {TOP10_VALUE_SHARE:.1f}% of value; {N_FOR_80} of {len(by_comm)} commodities make up 80% of value")
display(by_comm.head(10).round(1))
print("Top 10 by tonnage:"); display(by_comm.sort_values("tons_mt", ascending=False).head(10)[["tons_mt", "tons_share_%", "value_per_ton_usd", "tons_cagr_%"]].round(1))

fig, axes = plt.subplots(1, 2, figsize=(17, 6))
t10v = by_comm.head(10)[::-1]
axes[0].barh(t10v.index, t10v.value_bn, color=TEAL); axes[0].set_title("Top 10 commodities by value (billion 2017 USD, 2024)")
for y_, v in enumerate(t10v.value_bn): axes[0].text(v, y_, f" {v:,.0f}", va="center", fontsize=8.5)
sc = axes[1].scatter(by_comm.tons_mt, by_comm.value_bn, s=60, c=np.log10(by_comm.value_per_ton_usd), cmap="viridis")
for name, r in by_comm.head(6).iterrows(): axes[1].annotate(name, (r.tons_mt, r.value_bn), xytext=(5, 4), textcoords="offset points", fontsize=8)
for name, r in by_comm.sort_values("tons_mt", ascending=False).head(4).iterrows(): axes[1].annotate(name, (r.tons_mt, r.value_bn), xytext=(5, -10), textcoords="offset points", fontsize=8)
axes[1].set_xscale("log"); axes[1].set_yscale("log"); axes[1].set_xlabel("Tons (million, log)"); axes[1].set_ylabel("Value (billion USD, log)")
axes[1].set_title("Volume vs value (colour = log10 value per ton)"); plt.colorbar(sc, ax=axes[1], label="log10 USD per ton")
plt.tight_layout(); plt.show()

# %% [Cell 9] EDA 4: geography
# CELL 9 | EDA 4: GEOGRAPHY - STATES (domestic flows) AND GATEWAYS (imports / exports)
dom = df.loc[df.trade_type == "1", ["orig_state", "dest_state", "orig_zone", "dest_zone", "tons_2024", "value_2024"]]
out_s = dom.groupby("orig_state", observed=True)[["tons_2024", "value_2024"]].sum()
in_s  = dom.groupby("dest_state", observed=True)[["tons_2024", "value_2024"]].sum()
geo = out_s.join(in_s, lsuffix="_out", rsuffix="_in", how="outer").fillna(0)
geo["net_out_tons_mt"] = (geo.tons_2024_out - geo.tons_2024_in) / 1e3
TOP_ORIG, TOP_DEST = geo.tons_2024_out.idxmax(), geo.tons_2024_in.idxmax()
print(f"Largest origin state: {TOP_ORIG} | largest destination state: {TOP_DEST}")

imp = df.loc[df.trade_type == "2", ["orig_zone", "tons_2024", "value_2024"]].groupby("orig_zone", observed=True).sum().sort_values("value_2024", ascending=False)
exp = df.loc[df.trade_type == "3", ["dest_zone", "tons_2024", "value_2024"]].groupby("dest_zone", observed=True).sum().sort_values("value_2024", ascending=False)

fig, axes = plt.subplots(2, 2, figsize=(17, 11))
(geo.tons_2024_out.sort_values().tail(10) / 1e3).plot.barh(ax=axes[0, 0], color=NAVY, title="Top 10 origin states (domestic tons shipped, million, 2024)")
(geo.tons_2024_in.sort_values().tail(10) / 1e3).plot.barh(ax=axes[0, 1], color=TEAL, title="Top 10 destination states (domestic tons received, million, 2024)")
net = geo.net_out_tons_mt.sort_values(); netp = pd.concat([net.head(6), net.tail(6)])
netp.plot.barh(ax=axes[1, 0], color=[RED if v < 0 else TEAL for v in netp], title="Net outbound tons by state (million; red = net receiver)")
(imp.value_2024.head(8)[::-1] / 1e3).plot.barh(ax=axes[1, 1], color=SAFFRON, title="Top import entry regions by value (billion USD, 2024)")
for ax in axes.ravel(): ax.set_ylabel("")
plt.tight_layout(); plt.show()
TOP_ORIG_SHARE = float(geo.tons_2024_out.max() / geo.tons_2024_out.sum() * 100)
IMPORT_TOP3_SHARE = float(imp.value_2024.head(3).sum() / imp.value_2024.sum() * 100)
print(f"{TOP_ORIG} ships {TOP_ORIG_SHARE:.1f}% of domestic tons (including flows within the state); top 3 import entry regions = {IMPORT_TOP3_SHARE:.0f}% of import value")
print("Top 5 import entry regions (tons in million, value in billion USD):"); display((imp.head(5) / 1e3).round(1))
print("Top 5 export exit regions:"); display((exp.head(5) / 1e3).round(1))

# %% [Cell 10] EDA 5: distance and mode choice
# CELL 10 | EDA 5: DISTANCE BANDS AND MODE CHOICE (domestic flows)
d = cube[cube.trade == "Domestic"]
band = d.groupby("dist_label", observed=True)[["tons_2024", "value_2024", "tmiles_2024"]].sum().reindex(DIST_ORDER)
band["tons_share_%"] = band.tons_2024 / band.tons_2024.sum() * 100
band["value_per_ton_usd"] = band.value_2024 * 1e3 / band.tons_2024
display(band.round(1))
SHORT_HAUL_SHARE = float(band["tons_share_%"].iloc[:3].sum())     # below 500 miles
print(f"Share of domestic tons moving under 500 miles: {SHORT_HAUL_SHARE:.1f}%")

mode_band = d.pivot_table(index="dist_label", columns="dom_mode", values="tons_2024", aggfunc="sum", observed=True).reindex(DIST_ORDER).fillna(0)
mode_band = mode_band.div(mode_band.sum(axis=1), axis=0) * 100
mode_band = mode_band[[c for c in ["Truck", "Rail", "Water", "Pipeline", "Air", "Multiple modes & mail", "Other/unknown"] if c in mode_band]]

fig, axes = plt.subplots(1, 2, figsize=(17, 5.4), gridspec_kw={"width_ratios": [1.25, 1]})
sns.heatmap(mode_band, annot=True, fmt=".0f", cmap="YlGnBu", ax=axes[0], cbar_kws={"label": "% of tons in band"}, linewidths=1, linecolor="white")
axes[0].set_title("Mode mix by distance band (% of domestic tons)"); axes[0].set_xlabel(""); axes[0].set_ylabel("Distance band (miles)"); axes[0].grid(False)
axes[1].bar(band.index, band["tons_share_%"], color=NAVY); axes[1].set_title("Domestic tons by distance band (% of total)")
axes[1].tick_params(axis="x", rotation=35); axes[1].set_ylabel("%")
plt.tight_layout(); plt.show()

# %% [Cell 11] Analysis 1: corridors and foreign trade
# CELL 11 | ANALYSIS 1: CORRIDOR CONCENTRATION AND FOREIGN TRADE BALANCE
od = dom.groupby(["orig_zone", "dest_zone"], observed=True)[["tons_2024", "value_2024"]].sum().sort_values("tons_2024", ascending=False)
od["lane"] = od.index.get_level_values(0).astype(str) + "  ->  " + od.index.get_level_values(1).astype(str)
tot_t = od.tons_2024.sum()
TOP100_SHARE = float(od.tons_2024.head(100).sum() / tot_t * 100)
SAME_ZONE_SHARE = float(od[od.index.get_level_values(0) == od.index.get_level_values(1)].tons_2024.sum() / tot_t * 100)
TOP100_SAME = int((od.head(100).index.get_level_values(0) == od.head(100).index.get_level_values(1)).sum())
print(f"{len(od):,} origin-destination zone pairs | top 100 pairs = {TOP100_SHARE:.1f}% of domestic tons | same-zone flows = {SAME_ZONE_SHARE:.1f}%")
display(od.head(10)[["lane", "tons_2024", "value_2024"]].assign(tons_mt=lambda t: t.tons_2024 / 1e3, value_bn=lambda t: t.value_2024 / 1e3)[["lane", "tons_mt", "value_bn"]].round(1))
display(od.sort_values("value_2024", ascending=False).head(10)[["lane", "value_2024"]].assign(value_bn=lambda t: t.value_2024 / 1e3)[["lane", "value_bn"]].round(1))

od_x = od[od.index.get_level_values(0) != od.index.get_level_values(1)]           # corridors BETWEEN two different zones
print("Top 10 corridors between different zones (tons, million):")
display(od_x.head(10)[["lane", "tons_2024"]].assign(tons_mt=lambda t: t.tons_2024 / 1e3)[["lane", "tons_mt"]].round(1))
TOP_CORRIDORS = od_x.head(3).lane.tolist()

fi = df.loc[df.trade_type == "2", ["fr_orig", "value_2017", "value_2024", "tons_2024"]].groupby("fr_orig", observed=True).sum()
fe = df.loc[df.trade_type == "3", ["fr_dest", "value_2017", "value_2024", "tons_2024"]].groupby("fr_dest", observed=True).sum()
fi.index = fi.index.map(FOREIGN); fe.index = fe.index.map(FOREIGN)
fx = pd.DataFrame({"imports_bn": fi.value_2024 / 1e3, "exports_bn": fe.value_2024 / 1e3,
                   "imports_cagr_%": cagr(fi.value_2017, fi.value_2024, 7), "exports_cagr_%": cagr(fe.value_2017, fe.value_2024, 7)}).fillna(0)
fx["balance_bn"] = fx.exports_bn - fx.imports_bn
fx = fx.sort_values("balance_bn")
display(fx.round(1))
TRADE_BALANCE = float(fx.balance_bn.sum())
big = fx[fx.imports_bn >= 100]
FAST_IMPORT, SLOW_IMPORT = big["imports_cagr_%"].idxmax(), big["imports_cagr_%"].idxmin()

fig, axes = plt.subplots(1, 2, figsize=(16, 5))
top_l = od.head(10)[::-1].assign(m=lambda t: t.tons_2024 / 1e3)
axes[0].barh([l if len(l) <= 40 else l[:38] + ".." for l in top_l.lane], top_l.m, color=NAVY)
axes[0].set_title("Top 10 domestic lanes by tons (million, 2024)"); axes[0].set_ylabel("")
fx.balance_bn.plot.barh(ax=axes[1], color=[RED if v < 0 else TEAL for v in fx.balance_bn])
axes[1].set_title("Trade balance by region, 2024 (bn USD; red = import-heavy)"); axes[1].set_ylabel("")
plt.tight_layout(); plt.show()

# %% [Cell 12] Analysis 2: forecast to 2050
# CELL 12 | ANALYSIS 2: FORECAST TO 2050 (baseline scenario in the file)
def fc_table(by):
    a = cube.groupby(by, observed=True)[["tons_2024", "tons_2030", "tons_2050", "value_2024", "value_2030", "value_2050"]].sum()
    return pd.DataFrame({"tons_2024_mt": a.tons_2024 / 1e3, "tons_2050_mt": a.tons_2050 / 1e3,
                         "added_tons_mt": (a.tons_2050 - a.tons_2024) / 1e3,
                         "tons_cagr_24_50_%": cagr(a.tons_2024, a.tons_2050, 26),
                         "value_2024_bn": a.value_2024 / 1e3, "value_2050_bn": a.value_2050 / 1e3,
                         "added_value_bn": (a.value_2050 - a.value_2024) / 1e3,
                         "value_cagr_24_50_%": cagr(a.value_2024, a.value_2050, 26)})
fc_trade = fc_table("trade"); fc_mode = fc_table("dom_mode").sort_values("added_tons_mt", ascending=False); fc_comm = fc_table("commodity")
print("Forecast by trade type:"); display(fc_trade.round(1))
print("Forecast by domestic mode:"); display(fc_mode.round(1))
print("Top 8 commodities by added tons:"); display(fc_comm.sort_values("added_tons_mt", ascending=False).head(8).round(1))

path_years = HIST + FCST
tot_t = [cube[f"tons_{y}"].sum() / 1e3 for y in path_years]; tot_v = [cube[f"value_{y}"].sum() / 1e3 for y in path_years]
TONS_2050, VALUE_2050 = tot_t[-1], tot_v[-1]
TONS_CAGR_FC, VALUE_CAGR_FC = cagr(tot_t[HIST.index(2024)], tot_t[-1], 26), cagr(tot_v[HIST.index(2024)], tot_v[-1], 26)
GROWTH_T, GROWTH_V = (tot_t[-1] / tot_t[7] - 1) * 100, (tot_v[-1] / tot_v[7] - 1) * 100
TRUCK_ADDED_SHARE = float(fc_mode.loc["Truck", "added_tons_mt"] / (tot_t[-1] - tot_t[7]) * 100)
print(f"Total 2024 -> 2050: tons {tot_t[7]:,.0f} -> {TONS_2050:,.0f} Mt ({TONS_CAGR_FC:.2f}%/yr); value {tot_v[7]:,.0f} -> {VALUE_2050:,.0f} bn ({VALUE_CAGR_FC:.2f}%/yr)")

fig, axes = plt.subplots(1, 3, figsize=(18, 4.8))
for ax, series, ttl, c in [(axes[0], tot_t, "Total tons (million): history + forecast", NAVY), (axes[1], tot_v, "Total value (billion 2017 USD)", TEAL)]:
    ax.plot(path_years[:8], series[:8], marker="o", color=c, lw=2.6, label="History 2017-2024")
    ax.plot([2024] + path_years[8:], [series[7]] + series[8:], marker="o", ls="--", color=RED, lw=2.2, label="Forecast")
    ax.set_title(ttl); ax.legend(frameon=False)
x = np.arange(len(fc_mode.head(5))); w = 0.38; fm = fc_mode.head(5)
axes[2].bar(x - w / 2, fm["tons_cagr_24_50_%"], w, color=NAVY, label="Tons CAGR %"); axes[2].bar(x + w / 2, fm["value_cagr_24_50_%"], w, color=TEAL, label="Value CAGR %")
axes[2].set_xticks(x); axes[2].set_xticklabels(fm.index, rotation=20); axes[2].set_title("Forecast growth by mode, 2024-2050 (%/yr)"); axes[2].legend(frameon=False)
plt.tight_layout(); plt.show()

# %% [Cell 13] Analysis 3: commodity segmentation
# CELL 13 | ANALYSIS 3: STRATEGIC COMMODITY SEGMENTATION (value density x forecast growth)
seg = fc_comm.join(by_comm[["value_per_ton_usd", "value_share_%", "tons_share_%"]])
med_density, med_growth = seg.value_per_ton_usd.median(), seg["tons_cagr_24_50_%"].median()
def label(r):
    hi_d, hi_g = r.value_per_ton_usd >= med_density, r["tons_cagr_24_50_%"] >= med_growth
    return ("High-value growth" if hi_d and hi_g else "Premium, steady" if hi_d else "Bulk growth" if hi_g else "Bulk, steady")
seg["segment"] = seg.apply(label, axis=1)
print(f"Medians used as thresholds: value density = {med_density:,.0f} USD/ton | tons growth = {med_growth:.2f}%/yr")
display(seg.groupby("segment").agg(commodities=("segment", "size"), value_2024_bn=("value_2024_bn", "sum"), added_tons_mt=("added_tons_mt", "sum"), added_value_bn=("added_value_bn", "sum")).round(1))
display(seg.sort_values("added_value_bn", ascending=False).head(8)[["segment", "value_per_ton_usd", "tons_cagr_24_50_%", "added_value_bn", "added_tons_mt"]].round(1))

HV_N = int((seg.segment == "High-value growth").sum())
HV_VALUE_SHARE = float(seg.loc[seg.segment == "High-value growth", "value_2024_bn"].sum() / seg.value_2024_bn.sum() * 100)
HV_ADDED_SHARE = float(seg.loc[seg.segment == "High-value growth", "added_value_bn"].sum() / seg.added_value_bn.sum() * 100)
print(f"High-value growth segment: {HV_N} commodities, {HV_VALUE_SHARE:.0f}% of 2024 value, {HV_ADDED_SHARE:.0f}% of the value added by 2050")
colors = {"High-value growth": TEAL, "Premium, steady": NAVY, "Bulk growth": SAFFRON, "Bulk, steady": GREY}
fig, ax = plt.subplots(figsize=(12, 7))
for s_, g in seg.groupby("segment"):
    ax.scatter(g.value_per_ton_usd, g["tons_cagr_24_50_%"], s=g.value_2024_bn * 0.30 + 20, c=colors[s_], alpha=0.8, label=s_, edgecolor="white")
for name, r in seg.sort_values("value_2024_bn", ascending=False).head(8).iterrows():
    ax.annotate(name, (r.value_per_ton_usd, r["tons_cagr_24_50_%"]), xytext=(6, 4), textcoords="offset points", fontsize=8.5)
ax.axvline(med_density, color=GREY, ls="--"); ax.axhline(med_growth, color=GREY, ls="--"); ax.set_xscale("log")
ax.set_xlabel("Value per ton, 2024 (USD, log scale)"); ax.set_ylabel("Forecast tons growth 2024-2050 (%/yr)")
ax.set_title("Commodity portfolio: value density vs forecast growth (bubble = 2024 value)"); ax.legend(frameon=False, loc="lower right", markerscale=0.6)
plt.tight_layout(); plt.show()

# %% [Cell 14] Dashboard
# CELL 14 | EXECUTIVE DASHBOARD (one page, saved as PNG)
fig = plt.figure(figsize=(20, 12.4), facecolor="white")
hd = fig.add_axes([0, 0.925, 1, 0.075]); hd.axis("off"); hd.add_patch(plt.Rectangle((0, 0), 1, 1, transform=hd.transAxes, color=NAVY))
hd.text(0.03, 0.6, "U.S. Freight Analytics Dashboard  |  FAF5 v5.7.1", color="white", fontsize=25, fontweight="bold", va="center")
hd.text(0.03, 0.17, "Demand, modes, commodities, corridors and the 2050 outlook (value in constant 2017 USD)", color="#BFD0E6", fontsize=12.5, va="center")

truck_share = float(by_mode.loc["Truck", "tons_share_%"]) if "Truck" in by_mode.index else np.nan
cards = [("2024 TONNAGE", f"{yearly.tons_mt.iloc[-1]:,.0f} Mt", f"{CAGR_17_24['tons_mt']:+.1f}%/yr since 2017", NAVY),
         ("2024 VALUE", f"${yearly.value_bn.iloc[-1]:,.0f} bn", f"{CAGR_17_24['value_bn']:+.1f}%/yr since 2017", TEAL),
         ("2020 SHOCK", f"{COVID['tons_mt']:+.1f}% tons", f"{COVID['value_bn']:+.1f}% value vs 2019", RED),
         ("TRUCK SHARE (TONS)", f"{truck_share:.0f}%", f"{by_mode.loc['Truck','value_share_%']:.0f}% of value", SAFFRON),
         ("2050 OUTLOOK", f"{TONS_2050:,.0f} Mt", f"{TONS_CAGR_FC:+.1f}%/yr tons | {VALUE_CAGR_FC:+.1f}%/yr value", NAVY)]
for i, (lab, val, sub, col) in enumerate(cards):
    ax = fig.add_axes([0.03 + i * 0.1925, 0.805, 0.18, 0.105]); ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes, color="#F4F6FA")); ax.add_patch(plt.Rectangle((0, 0.94), 1, 0.06, transform=ax.transAxes, color=col))
    ax.text(0.5, 0.72, lab, ha="center", fontsize=10.5, color=GREY, fontweight="bold"); ax.text(0.5, 0.43, val, ha="center", va="center", fontsize=22, color=col, fontweight="bold")
    ax.text(0.5, 0.13, sub, ha="center", fontsize=9, color="#5B6677")

gs = fig.add_gridspec(2, 3, left=0.075, right=0.985, top=0.765, bottom=0.115, hspace=0.5, wspace=0.42)
ax = fig.add_subplot(gs[0, 0]); idx = yearly[["tons_mt", "value_bn", "tmiles_bn"]] / yearly[["tons_mt", "value_bn", "tmiles_bn"]].iloc[0] * 100
for col, c, l in [("tons_mt", NAVY, "Tons"), ("value_bn", TEAL, "Value"), ("tmiles_bn", SAFFRON, "Ton-miles")]: ax.plot(idx.index, idx[col], marker="o", color=c, lw=2.3, label=l)
ax.axvspan(2019.5, 2020.5, color=RED, alpha=0.1); ax.legend(frameon=False, fontsize=8.5); ax.set_title("1. Index of freight activity (2017 = 100)", loc="left")
ax = fig.add_subplot(gs[0, 1]); t_ = by_trade[["tons_share_%", "value_share_%", "tmiles_share_%"]]; t_.plot.bar(ax=ax, color=[NAVY, TEAL, SAFFRON], width=0.8, legend=False)
ax.set_title("2. Share by trade type", loc="left"); ax.set_xlabel(""); ax.tick_params(axis="x", rotation=0); ax.set_ylabel("%"); ax.legend(["Tons", "Value", "Ton-miles"], frameon=False, fontsize=8.5)
ax = fig.add_subplot(gs[0, 2]); m_ = by_mode.head(5)[["tons_share_%", "value_share_%"]]; m_.plot.bar(ax=ax, color=[NAVY, TEAL], width=0.8, legend=False)
ax.set_title("3. Mode share: tons vs value (top 5 modes)", loc="left"); ax.set_xlabel(""); ax.tick_params(axis="x", rotation=20); ax.set_ylabel("%"); ax.legend(["Tons", "Value"], frameon=False, fontsize=8.5)
ax = fig.add_subplot(gs[1, 0]); c_ = by_comm.head(8)[::-1]; ax.barh([n[:24] for n in c_.index], c_.value_bn, color=TEAL); ax.set_title("4. Top commodities by value (bn USD)", loc="left"); ax.tick_params(axis="y", labelsize=8.5)
ax = fig.add_subplot(gs[1, 1]); o_ = (geo.tons_2024_out.sort_values().tail(8) / 1e3); ax.barh(o_.index, o_.values, color=NAVY); ax.set_title("5. Top origin states (domestic Mt shipped)", loc="left"); ax.tick_params(axis="y", labelsize=8.5)
ax = fig.add_subplot(gs[1, 2]); ax.plot(path_years[:8], tot_t[:8], marker="o", color=NAVY, lw=2.4); ax.plot([2024] + path_years[8:], [tot_t[7]] + tot_t[8:], marker="o", ls="--", color=RED, lw=2.2)
ax.set_title("6. Tons: history and 2050 forecast (Mt)", loc="left")

notes = (f"Reading guide: {TOP10_VALUE_SHARE:.0f}% of value sits in 10 commodities; {SHORT_HAUL_SHARE:.0f}% of domestic tons move under 500 miles; "
         f"{SAME_ZONE_SHARE:.0f}% of domestic tons stay inside one FAF zone. Rows in FAF are zone-to-zone flows, not individual shipments. Forecast = baseline scenario in the file.")
fig.text(0.03, 0.06, notes, fontsize=10.5, color="#2B3547")
fig.text(0.03, 0.02, "Source: FHWA / BTS Freight Analysis Framework v5 (FAF5.7.1) | Tons = thousand tons, value = million 2017 USD | Analysis: own calculations",
         fontsize=8.5, color=GREY)
fig.savefig(OUT_DIR / "faf5_dashboard.png", dpi=170, facecolor="white"); plt.show()
print("Saved:", OUT_DIR / "faf5_dashboard.png")

# %% [Cell 15] Insights, Recommendations, Executive Summary
# CELL 15 | INSIGHTS, RECOMMENDATIONS, EXECUTIVE SUMMARY (generated from the numbers above) + EXPORTS
top_v, top_t = by_comm.index[0], by_comm.sort_values("tons_mt", ascending=False).index[0]
material = fc_mode.loc[[m for m in fc_mode.index if by_mode.loc[m, "tons_share_%"] >= 1]]   # modes with at least 1% of tons
fast_mode = material["tons_cagr_24_50_%"].idxmax()
top_add = fc_comm.sort_values("added_tons_mt", ascending=False).head(3).index.tolist()
flat = all(abs(v) < 0.5 for v in CAGR_17_24.values())
trend_word = "essentially flat" if flat else "changed slowly"

INSIGHTS = f"""# Insights Report: U.S. Freight (FAF5 v5.7.1)
1. **Scale and trend.** Freight reached {yearly.tons_mt.iloc[-1]:,.0f} million tons and ${yearly.value_bn.iloc[-1]:,.0f} billion (2017 USD) in 2024. Since 2017 it has been {trend_word}: tons {CAGR_17_24['tons_mt']:+.2f}%/yr, value {CAGR_17_24['value_bn']:+.2f}%/yr, ton-miles {CAGR_17_24['tmiles_bn']:+.2f}%/yr (ton-miles are {TMILES_VS_2017:+.1f}% vs 2017).
2. **2020 shock.** Versus 2019, tons fell {abs(COVID['tons_mt']):.1f}%, value {abs(COVID['value_bn']):.1f}% and ton-miles {abs(COVID['tmiles_bn']):.1f}%. Ton-miles fell the most, so average hauls shortened. By 2024 tonnage is {yearly.tons_mt.iloc[-1] / yearly.tons_mt.loc[2019] * 100 - 100:+.1f}% vs 2019, but ton-miles are {yearly.tmiles_bn.iloc[-1] / yearly.tmiles_bn.loc[2019] * 100 - 100:+.1f}%.
3. **Trade mix.** Domestic flows are {by_trade.loc['Domestic','tons_share_%']:.0f}% of tons and {by_trade.loc['Domestic','value_share_%']:.0f}% of value; imports {by_trade.loc['Import','tons_share_%']:.0f}% of tons but {by_trade.loc['Import','value_share_%']:.0f}% of value; exports {by_trade.loc['Export','tons_share_%']:.0f}% / {by_trade.loc['Export','value_share_%']:.0f}%. Imports are worth about ${by_trade.loc['Import','value_per_ton_usd']:,.0f} per ton versus ${by_trade.loc['Domestic','value_per_ton_usd']:,.0f} domestically.
4. **Modes.** Truck carries {truck_share:.0f}% of tons and {by_mode.loc['Truck','value_share_%']:.0f}% of value (average haul {by_mode.loc['Truck','avg_haul_miles']:,.0f} miles). Pipeline carries {by_mode.loc['Pipeline','tons_share_%']:.0f}% of tons but {by_mode.loc['Pipeline','value_share_%']:.0f}% of value. Air carries {by_mode.loc['Air','tons_share_%']:.2f}% of tons but {by_mode.loc['Air','value_share_%']:.1f}% of value.
5. **Volume is not value.** {top_t} leads tonnage while {top_v} leads value. The top 10 commodities hold {TOP10_VALUE_SHARE:.0f}% of value and {N_FOR_80} of {len(by_comm)} commodities make up 80%.
6. **Local and short-haul dominates.** {SHORT_HAUL_SHARE:.0f}% of domestic tons move under 500 miles and {SAME_ZONE_SHARE:.0f}% stay inside a single FAF zone. The top 100 zone pairs carry {TOP100_SHARE:.0f}% of domestic tons ({TOP100_SAME} of them are within-zone flows). Largest corridors between different zones: {'; '.join(TOP_CORRIDORS)}.
7. **Geography.** {TOP_ORIG} ships {TOP_ORIG_SHARE:.0f}% of domestic tons (within-state flows included). The top 3 import entry regions handle {IMPORT_TOP3_SHARE:.0f}% of import value.
8. **Foreign trade.** Goods flows show an import surplus of ${-TRADE_BALANCE:,.0f} billion in 2024 (2017 USD). Imports from {FAST_IMPORT} grew {fx.loc[FAST_IMPORT,'imports_cagr_%']:.1f}%/yr since 2017, while imports from {SLOW_IMPORT} changed {fx.loc[SLOW_IMPORT,'imports_cagr_%']:.1f}%/yr.
9. **Outlook to 2050 (baseline).** Tons rise {GROWTH_T:.0f}% to {TONS_2050:,.0f} Mt ({TONS_CAGR_FC:+.2f}%/yr) and value {GROWTH_V:.0f}% to ${VALUE_2050:,.0f} bn ({VALUE_CAGR_FC:+.2f}%/yr), so the mix shifts toward higher-value goods. Truck absorbs {TRUCK_ADDED_SHARE:.0f}% of added tons; {fast_mode} grows fastest among larger modes; biggest tonnage additions: {', '.join(top_add)}.
10. **Portfolio.** {HV_N} 'high-value growth' commodities hold {HV_VALUE_SHARE:.0f}% of 2024 value and deliver {HV_ADDED_SHARE:.0f}% of the value added by 2050.
"""

RECOMMENDATIONS = f"""# Business Recommendations
1. **Prioritise regional and metro truck capacity.** Trucks carry {truck_share:.0f}% of tons, {SHORT_HAUL_SHARE:.0f}% of domestic tons move under 500 miles and {SAME_ZONE_SHARE:.0f}% stay within one zone. Focus first on intra-regional distribution, drayage and terminal access.
2. **Plan around the gateways.** The top 3 import entry regions handle {IMPORT_TOP3_SHARE:.0f}% of import value; run gateway-level capacity and resilience reviews there.
3. **Segment by value density, not tonnage alone.** Protect reliability and speed for the {N_FOR_80} commodities that make up 80% of value (e.g. {', '.join(by_comm.index[:3])}); manage bulk commodities such as {top_t} on cost and volume.
4. **Build shock resilience.** The 2020 drop ({abs(COVID['tons_mt']):.1f}% in tons, {abs(COVID['tmiles_bn']):.1f}% in ton-miles) shows exposure; keep flexible capacity and alternative modes.
5. **Watch sourcing shifts.** Imports from {FAST_IMPORT} grew {fx.loc[FAST_IMPORT,'imports_cagr_%']:.1f}%/yr; check whether gateway and corridor plans match the changing origins.
6. **Use the 2050 outlook as a scenario.** Trucks absorb {TRUCK_ADDED_SHARE:.0f}% of the extra tons; test infrastructure and fleet plans against this and refresh when FAF updates.
7. **Close data gaps before committing capital.** Add costs, congestion, shipment-level data and monthly volumes."""

EXEC_SUMMARY = f"""# Executive Summary
U.S. freight in 2024 totals {yearly.tons_mt.iloc[-1]:,.0f} million tons worth ${yearly.value_bn.iloc[-1]:,.0f} billion (2017 USD). Activity has been {trend_word} since 2017 apart from a {abs(COVID['tons_mt']):.1f}% tonnage drop in 2020. Trucks carry {truck_share:.0f}% of tons and {by_mode.loc['Truck','value_share_%']:.0f}% of value, {SHORT_HAUL_SHARE:.0f}% of domestic tons move under 500 miles, and value is concentrated in a few commodities ({TOP10_VALUE_SHARE:.0f}% in ten). The baseline forecast implies {GROWTH_T:.0f}% more tons and {GROWTH_V:.0f}% more value by 2050, with trucks absorbing most of the growth. Priorities: regional truck capacity, gateway resilience, value-based commodity segmentation and scenario planning.
Limits: FAF figures are modelled estimates; value is in constant 2017 dollars; the file holds one forecast scenario with forecast years from 2030; rows are zone-to-zone flows, not shipments; ton-miles cover the domestic leg only."""

for name, text in [("insights_report.md", INSIGHTS), ("business_recommendations.md", RECOMMENDATIONS), ("executive_summary.md", EXEC_SUMMARY)]:
    (OUT_DIR / name).write_text(text, encoding="utf-8"); print(text, "\n" + "-" * 90)
for name, tbl in [("yearly_trend", yearly), ("by_trade", by_trade), ("by_mode", by_mode), ("by_commodity", by_comm), ("forecast_by_mode", fc_mode),
                  ("forecast_by_commodity", fc_comm), ("commodity_segments", seg), ("foreign_trade_balance", fx), ("top_lanes", od.head(50))]:
    tbl.to_csv(OUT_DIR / f"{name}.csv")
print("Exports written to:", OUT_DIR)
# In Colab you can download them: from google.colab import files; files.download(str(OUT_DIR / "faf5_dashboard.png"))

import os, sys, io, csv, math, random, hashlib, datetime as dt, numpy as np, boto3, urllib.request
from botocore import UNSIGNED
from botocore.config import Config
from concurrent.futures import ThreadPoolExecutor
from obspy import read, UTCDateTime
NET, DAYS = sys.argv[1], [int(x) for x in sys.argv[2].split(",")]
YEAR, NS, R_ST, R_EV, WIN, FS, NPOS, NNEG = 2023, 12, 75.0, 60.0, 60.0, 50, 70, 35
OUT = "examples"; TMP = "tmp_" + NET; os.makedirs(OUT, exist_ok=True); os.makedirs(TMP, exist_ok=True)
s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED, max_pool_connections=64), region_name="us-west-2")
B = "scedc-pds" if NET == "CI" else "ncedc-pds"
CHA = "HHZ" if NET == "CI" else "EHZ"
def keys(prefix):
    out, tok = [], None
    while True:
        kw = dict(Bucket=B, Prefix=prefix)
        if tok: kw["ContinuationToken"] = tok
        r = s3.list_objects_v2(**kw); out += [c["Key"] for c in r.get("Contents", [])]
        if not r.get("IsTruncated"): return out
        tok = r["NextContinuationToken"]
def stations(day):
    t0 = dt.datetime(YEAR, 1, 1) + dt.timedelta(days=day - 1); t1 = t0 + dt.timedelta(days=1)
    host = "service.scedc.caltech.edu" if NET == "CI" else "service.ncedc.org"
    url = "https://%s/fdsnws/station/1/query?net=%s&cha=%s&level=channel&format=text&starttime=%s&endtime=%s" % (host, NET, CHA, t0.strftime("%Y-%m-%dT%H:%M:%S"), t1.strftime("%Y-%m-%dT%H:%M:%S"))
    st = {}
    for ln in urllib.request.urlopen(url).read().decode().splitlines()[1:]:
        f = ln.split("|")
        if len(f) < 15 or float(f[14]) != 100: continue
        st[f[1]] = dict(loc=f[2], lat=float(f[4]), lon=float(f[5]), elev=float(f[6]), scale=float(f[11]))
    return st
def catalog():
    ev = []
    if NET == "CI":
        txt = s3.get_object(Bucket=B, Key="earthquake_catalogs/SCEC_DC/%d.catalog" % YEAR)["Body"].read().decode()
        for ln in txt.splitlines():
            if ln.startswith("#") or len(ln) < 60: continue
            p = ln.split()
            t = UTCDateTime(p[0].replace("/", "-") + "T" + p[1])
            ev.append(dict(t=t, lat=float(p[6]), lon=float(p[7]), mag=float(p[4]), eq=p[2] == "eq"))
    else:
        txt = s3.get_object(Bucket=B, Key="earthquake_catalogs/NCEDC/%d.ehpcsv" % YEAR)["Body"].read().decode()
        for r in csv.DictReader(io.StringIO(txt)):
            ev.append(dict(t=UTCDateTime(r["time"]), lat=float(r["latitude"]), lon=float(r["longitude"]), mag=float(r["mag"] or 0), eq=r["type"] == "eq"))
    return ev
def xy(lat, lon, lat0, lon0):
    return (lon - lon0) * 111.19 * math.cos(math.radians(lat0)), (lat - lat0) * 111.19
CAT = catalog()
def run(day):
    rng = random.Random(int(hashlib.md5(("%s-%d" % (NET, day)).encode()).hexdigest()[:8], 16))
    st = stations(day)
    if NET == "CI": pref = "continuous_waveforms/%d/%d_%03d/" % (YEAR, YEAR, day)
    else: pref = "continuous_waveforms/NC/%d/%d.%03d/" % (YEAR, YEAR, day)
    files = {}
    for k in keys(pref):
        n = k.split("/")[-1]
        if NET == "CI":
            if n[7:10] == CHA and n[:2] == "CI": files[n[2:7].rstrip("_")] = k
        else:
            p = n.split(".")
            if len(p) > 3 and p[2] == CHA: files[p[0]] = k
    st = {s: v for s, v in st.items() if s in files}
    d0 = UTCDateTime(YEAR, 1, 1) + (day - 1) * 86400
    evs = [e for e in CAT if d0 - 120 <= e["t"] < d0 + 86400 + 120]
    plans = []
    pos = [e for e in evs if e["eq"] and d0 + 300 <= e["t"] < d0 + 86400 - 300]
    rng.shuffle(pos)
    for e in pos[:NPOS]:
        a, r = rng.uniform(0, 2 * math.pi), 30 * math.sqrt(rng.random())
        lat0 = e["lat"] + r * math.sin(a) / 111.19; lon0 = e["lon"] + r * math.cos(a) / (111.19 * math.cos(math.radians(e["lat"])))
        plans.append((lat0, lon0, e["t"] - rng.uniform(2, 50)))
    anchors = [e for e in CAT if e["eq"] and abs(e["t"] - d0) > 3 * 86400]
    for _ in range(NNEG):
        e = rng.choice(anchors); a, r = rng.uniform(0, 2 * math.pi), 30 * math.sqrt(rng.random())
        lat0 = e["lat"] + r * math.sin(a) / 111.19; lon0 = e["lon"] + r * math.cos(a) / (111.19 * math.cos(math.radians(e["lat"])))
        plans.append((lat0, lon0, d0 + 300 + rng.uniform(0, 86400 - 700)))
    rng.shuffle(plans)
    sel = []
    for lat0, lon0, t0 in plans:
        dd = sorted((math.hypot(*xy(v["lat"], v["lon"], lat0, lon0)), s) for s, v in st.items())
        near = [s for d, s in dd if d <= R_ST][:NS]
        if len(near) < 5: continue
        if any(abs(t0 - q[2]) < WIN and set(near) & set(q[3]) for q in sel): continue
        sel.append((lat0, lon0, t0, near))
    need = sorted({s for *_, near in sel for s in near})
    def get(s):
        f = os.path.join(TMP, "%s_%03d" % (s, day))
        if not os.path.exists(f): s3.download_file(B, files[s], f)
        return s, f
    with ThreadPoolExecutor(32) as ex: paths = dict(ex.map(get, need))
    nW = len(sel); XA = np.zeros((nW, NS, int(WIN * FS)), np.float32); MA = np.zeros((nW, NS), np.uint8); PA = np.zeros((nW, NS, 3), np.float32)
    uses = {}
    for w, (lat0, lon0, t0, near) in enumerate(sel):
        for i, s in enumerate(near): uses.setdefault(s, []).append((w, i, lat0, lon0, t0))
    for s in need:
        try: full = read(paths[s]).merge(fill_value=0)[0]
        except Exception: full = None
        os.remove(paths[s])
        if full is None: continue
        for w, i, lat0, lon0, t0 in uses[s]:
            tr = full.slice(t0 - 10, t0 + WIN + 10).copy()
            if tr.stats.npts < (WIN + 18) * 100 or tr.stats.sampling_rate != 100: continue
            tr.detrend("demean"); tr.taper(0.05); tr.filter("bandpass", freqmin=1.0, freqmax=20.0, corners=4, zerophase=True)
            tr.decimate(2, no_filter=True)
            tr = tr.slice(t0, t0 + WIN)
            v = tr.data[:int(WIN * FS)].astype(np.float64) / st[s]["scale"] * 1e9
            if len(v) < int(WIN * FS) or not np.isfinite(v).all() or np.abs(v).max() == 0: continue
            XA[w, i] = v; MA[w, i] = 1; ex_, ey_ = xy(st[s]["lat"], st[s]["lon"], lat0, lon0); PA[w, i] = (ex_, ey_, st[s]["elev"])
        del full
    X, M, P, L, D = [], [], [], [], []; sel2 = []
    for w, (lat0, lon0, t0, near) in enumerate(sel):
        x, m, pos_ = XA[w], MA[w], PA[w]
        if m.sum() < 5: continue
        lab, dc = [], []
        for e in evs:
            ot = e["t"] - t0; ex_, ey_ = xy(e["lat"], e["lon"], lat0, lon0); r = math.hypot(ex_, ey_)
            if e["eq"] and 0 <= ot < WIN and r <= R_EV: lab.append((ot, ex_, ey_, e["mag"]))
            elif -30 <= ot < WIN + 10 and r <= 200: dc.append((ot, ex_, ey_, e["mag"]))
        X.append(x); M.append(m); P.append(pos_); L.append(lab); D.append(dc); sel2.append((lat0, lon0, t0, near))
    np.savez_compressed(os.path.join(OUT, "%s_d%03d.npz" % (NET, day)), X=np.array(X), M=np.array(M), P=np.array(P), L=np.array([repr(l) for l in L]), D=np.array([repr(d) for d in D]), T=np.array([float(q[2] - d0) for q in sel2]))
    print(NET, day, "windows", len(X), "with events", sum(1 for l in L if l), "events", sum(len(l) for l in L), flush=True)
for d in DAYS: run(d)
print("DONE", flush=True)

import os, re, json, csv, time, requests
from datetime import datetime, timezone

# ── Credenciales ──────────────────────────────────────────────────────────────
SUPABASE_URL       = os.environ["SUPABASE_URL"]
SUPABASE_KEY       = os.environ["SUPABASE_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

SB_HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=minimal",
}

# ── Supabase REST ─────────────────────────────────────────────────────────────
def sb_get(table, params=""):
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?{params}", headers=SB_HEADERS)
    return r.json()

def sb_upsert(table, data):
    h = {**SB_HEADERS, "Prefer": "resolution=merge-duplicates,return=minimal"}
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=h, json=data)
    if r.status_code not in (200, 201, 204):
        print(f"  SUPABASE ERROR {r.status_code}: {r.text[:200]}")

def sb_insert(table, data):
    requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=SB_HEADERS, json=data)

def get_snapshot(certificado):
    rows = sb_get("medicamentos", f"certificado=eq.{certificado}&select=*")
    return rows[0] if rows else None

# ── Telegram ──────────────────────────────────────────────────────────────────
def telegram_send(text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    )

# ── VNM Scraper ───────────────────────────────────────────────────────────────
BASE  = "https://servicios.pami.org.ar/vademecum"
ZK_AU = f"{BASE}/zkau"

def init_session():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
    r = s.get(f"{BASE}/views/consultaPublica/listado.zul")
    dtid = re.search(r"dt:'([^']*)'", r.text).group(1)
    return s, dtid, 1

def buscar_por_certificado(session, dtid, sid, certificado):
    session.post(ZK_AU, data={
        "dtid": dtid, "cmd_0": "onChange",
        "uuid_0": "zk_comp_67",
        "data_0": json.dumps({"value": str(certificado), "start": len(str(certificado))})
    }, headers={"zk-sid": str(sid)})
    res = session.post(ZK_AU, data={
        "dtid": dtid, "cmd_0": "onClick",
        "uuid_0": "zk_comp_80", "data_0": '{"which":1}'
    }, headers={"zk-sid": str(sid+1)})
    session.post(ZK_AU, data={
        "dtid": dtid, "cmd_0": "onClick",
        "uuid_0": "zk_comp_81", "data_0": '{"which":1}'
    }, headers={"zk-sid": str(sid+2)})
    return res.text, sid+3

def parsear_primera_fila(content):
    uv = {}
    for m in re.finditer(r"'zk_comp_(\d+)'[^}]*value:'([^']*)'", content):
        uv[int(m.group(1))] = m.group(2).strip()
    candidatos = sorted(n for n,v in uv.items() if re.match(r'^\d{4,6}$', v))
    if not candidatos:
        return None
    base = candidatos[0]
    return {
        "certificado":      uv.get(base, ''),
        "laboratorio":      uv.get(base+2, ''),
        "nombre_comercial": uv.get(base+4, ''),
        "gtin":             uv.get(base+10, ''),
        "generico":         uv.get(base+12, '').strip(),
        "btn_ver":          base+14,
    }

def extraer_detalle(session, dtid, sid, btn_num):
    session.post(ZK_AU, data={
        "dtid": dtid, "cmd_0": "onClick",
        "uuid_0": f"zk_comp_{btn_num}", "data_0": '{"which":1}'
    }, headers={"zk-sid": str(sid)})
    time.sleep(0.3)
    r = session.get(f"{BASE}/views/consultaPublica/presentacion.zul")
    all_values = re.findall(r"value:'([^']*)'", r.text)
    ESTADOS = {"ACTIVO", "INACTIVO"}
    LABEL_MAP = {
        "Vía de Administración:":                              "via_admin",
        "Condición de Expendio:":                             "condicion_expendio",
        "Posee Biodisponibilidad/ Bioequivalencia Aceptada:": "bioequivalencia",
        "Disponibilidad en el Mercado:":                      "disponibilidad",
    }
    ALL_LABELS = set(LABEL_MAP) | {
        "Nº de Certificado:","Laboratorio:","Nombre Comercial:",
        "Nombre Genérico:","Forma Farmacéutica:","Nº de Troquel:",
        "Fórmula:","Posee Bioexencion Aceptada:","Presentación:",
        "GTIN:","Etiquetas Trazabilidad:","Retiro del Mercado:",
    }
    resultado = {"estado": "", "condicion_expendio": "", "disponibilidad": ""}
    i = 0
    while i < len(all_values):
        val = all_values[i].strip()
        if val in ESTADOS and not resultado["estado"]:
            resultado["estado"] = val
        elif val in LABEL_MAP:
            campo = LABEL_MAP[val]
            for j in range(i+1, min(i+6, len(all_values))):
                nv = all_values[j].strip()
                if nv and nv not in ALL_LABELS and nv not in ESTADOS:
                    resultado[campo] = nv
                    break
        i += 1
    if resultado["disponibilidad"] in ESTADOS:
        resultado["disponibilidad"] = ""
    m = re.search(r'_totalSize:(\d+)', r.text)
    resultado["retiro_count"] = int(m.group(1)) if m else 0
    return resultado, sid+1

# ── Detección de cambios ──────────────────────────────────────────────────────
CAMPOS_MONITOREADOS = ["estado", "disponibilidad", "condicion_expendio", "retiro_count"]
EMOJIS = {
    "disponibilidad":     "🔴",
    "estado":             "🔴",
    "retiro_count":       "🟠",
    "condicion_expendio": "🟡",
}

def detectar_cambios(certificado, nombre, snap_ant, datos_nuevos):
    if not snap_ant:
        return
    cambios = []
    for campo in CAMPOS_MONITOREADOS:
        anterior = str(snap_ant.get(campo, ""))
        nuevo    = str(datos_nuevos.get(campo, ""))
        if anterior != nuevo:
            cambios.append((campo, anterior, nuevo))
            sb_insert("alertas", {
                "certificado":      certificado,
                "nombre_comercial": nombre,
                "campo":            campo,
                "valor_anterior":   anterior,
                "valor_nuevo":      nuevo,
            })
    if cambios:
        emoji = EMOJIS.get(cambios[0][0], "🔔")
        lineas = [f"{emoji} <b>ALERTA FarmaCheck</b>",
                  f"💊 <b>{nombre}</b> (cert. {certificado})", ""]
        for campo, anterior, nuevo in cambios:
            lineas += [f"<b>{campo.upper()}</b>",
                       f"  Antes: {anterior or '(vacío)'}",
                       f"  Ahora: {nuevo or '(vacío)'}"]
        telegram_send("\n".join(lineas))
        print(f"  ⚠️  ALERTA: {nombre} — {[c[0] for c in cambios]}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"FarmaCheck Cron — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    telegram_send("🔄 <b>FarmaCheck</b> — cron iniciado")

    session, dtid, sid = init_session()
    print(f"DTID: {dtid}")

    with open("semilla.csv") as f:
        semilla = list(csv.DictReader(f))

    ok, errores = 0, 0
    for i, row in enumerate(semilla):
        cert   = row["certificado"].strip()
        nombre = row["nombre_comercial"].strip()
        print(f"[{i+1:02d}/{len(semilla)}] {nombre:<35}", end=" ", flush=True)
        try:
            if sid > 90:
                session, dtid, sid = init_session()
                time.sleep(0.5)

            content, sid = buscar_por_certificado(session, dtid, sid, cert)
            fila = parsear_primera_fila(content)

            if not fila:
                print("sin resultados")
                errores += 1
                continue

            detalle, sid = extraer_detalle(session, dtid, sid, fila["btn_ver"])
            time.sleep(0.4)

            snap_ant   = get_snapshot(cert)
            datos_nuevos = {
                "certificado":      cert,
                "nombre_comercial": fila["nombre_comercial"],
                "laboratorio":      fila["laboratorio"],
                "generico":         fila["generico"],
                "gtin":             fila["gtin"],
                **detalle,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            detectar_cambios(cert, nombre, snap_ant, datos_nuevos)
            sb_upsert("medicamentos", datos_nuevos)

            estado = detalle.get("estado", "?")
            disp   = "⚠️ ALERTA" if detalle.get("disponibilidad") else "ok"
            print(f"{estado} — {disp}")
            ok += 1

        except Exception as e:
            print(f"ERROR: {e}")
            errores += 1
            try:
                session, dtid, sid = init_session()
            except:
                pass

    telegram_send(
        f"✅ <b>FarmaCheck cron completado</b>\n"
        f"📊 {ok} ok | {errores} errores\n"
        f"🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    print(f"\n✅ {ok} ok | {errores} errores")

if __name__ == "__main__":
    main()

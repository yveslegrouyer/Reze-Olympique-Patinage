#!/usr/bin/env python3
"""
ROP Site — weekly results updater
Run every Monday morning to refresh match data from the roller-rop.fr API.

Usage:
  python3 update_results.py

To schedule on Mac (runs every Monday at 8:00):
  crontab -e
  Add: 0 8 * * 1 /usr/bin/python3 /path/to/update_results.py >> /tmp/rop_update.log 2>&1
"""

import json, os, re, urllib.request, sys
from datetime import datetime

HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
API_BASE  = "https://www.roller-rop.fr/api/results.php?league="

# ROP team IDs per league (from rolskanet)
ROP_IDS = {"R2": 7082, "N3": 6668, "PN": 7020, "U17": 7083, "U15": 7576}

LEAGUES = [
    ("n3",  "N3",  "N3"),
    ("pn",  "N4",  "PN"),
    ("r2",  "R2",  "R2"),
    ("u17", "U17", "U17"),
    ("u15", "U15", "U15"),
]

OPP_CLEANUP = [
    "01261 - ","01692 - ","01179 - ","02006 - ","00784 - ","00829 - ",
    "01228 - ","00421 - ","01660 - ","01256 - ","00458 - ","E1017 - ",
    "E1038 - ","E1045 - ","E1005 - ","E1019 - ","E1046 - ","ENT. ",
]


def fetch_matches(api_code, rop_id):
    url = API_BASE + api_code
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.load(r)
    except Exception as e:
        print(f"  ERROR fetching {api_code}: {e}")
        return []

    matches = []
    for m in data["data"]["data"]:
        rec  = m["receveur"]
        vis  = m["visiteur"]
        info = m.get("infosRencontre", {})
        date = info.get("date_rencontre", "")[:10] if info else ""
        rop_home = rec["id"] == rop_id
        opp_team = vis if rop_home else rec
        opp = opp_team["libelle_court"]
        for prefix in OPP_CLEANUP:
            opp = opp.replace(prefix, "")
        opp = re.sub(r"\s*-\s*(R2|N3|U15|U17A?|U17B?|PN)\s*$", "", opp).strip()

        rop_s = opp_s = None
        for s in m["score"]:
            if s["equipe_id"] == rop_id:
                rop_s = s["score"]
            else:
                opp_s = s["score"]

        if rop_s is None or opp_s is None:
            continue  # unplayed

        matches.append({
            "date": date,
            "opp":  opp,
            "rop":  rop_s,
            "opp_s": opp_s,
            "loc":  "D" if rop_home else "E",
        })
    return matches


def stats(matches):
    w = sum(1 for m in matches if m["rop"] > m["opp_s"])
    d = sum(1 for m in matches if m["rop"] == m["opp_s"])
    l = sum(1 for m in matches if m["rop"] < m["opp_s"])
    return w, d, l, sum(m["rop"] for m in matches), sum(m["opp_s"] for m in matches)


def rows_html(matches):
    parts = []
    for m in reversed(matches):
        r, o = m["rop"], m["opp_s"]
        res = "V" if r > o else ("D" if r < o else "N")
        col = {"V": "var(--green-b)", "D": "#ff6b6b", "N": "var(--fg2)"}[res]
        lbl = {"V": "Victoire", "D": "Défaite", "N": "Nul"}[res]
        ll  = "Domicile" if m["loc"] == "D" else "Extérieur"
        lb  = "rgba(0,158,69,.15)" if m["loc"] == "D" else "rgba(255,255,255,.07)"
        parts.append(
            f'<div class="res-row">'
            f'<span class="res-date">{m["date"]}</span>'
            f'<span class="res-loc" style="background:{lb}">{ll}</span>'
            f'<span class="res-opp">{m["opp"]}</span>'
            f'<span class="res-score">{r} <span class="res-dash">&#8211;</span> {o}</span>'
            f'<span class="res-result" style="color:{col};border-color:{col}40">{lbl}</span>'
            f'</div>'
        )
    return "".join(parts)


def stat_block(w, d, l, gf, ga):
    return (
        f'<div class="res-stats">'
        f'<div class="res-stat"><div class="n">{w}<span class="u"> V</span></div><div class="t">Victoires</div></div>'
        f'<div class="res-stat"><div class="n">{d}<span class="u"> N</span></div><div class="t">Nuls</div></div>'
        f'<div class="res-stat"><div class="n">{l}<span class="u"> D</span></div><div class="t">Défaites</div></div>'
        f'<div class="res-stat"><div class="n">{gf}<span class="u"> ↑</span></div><div class="t">Buts marqués</div></div>'
        f'<div class="res-stat"><div class="n">{ga}<span class="u"> ↓</span></div><div class="t">Buts encaissés</div></div>'
        f'</div>'
    )


def build_section(all_matches):
    tab_ids = [lid for lid, _, _ in LEAGUES]
    tabs_h  = "".join(
        f'<button class="res-tab{" active" if i == 0 else ""}" onclick="showTab(\'{lid}\')">{ln}</button>'
        for i, (lid, ln, _) in enumerate(LEAGUES)
    )
    panels_h = "".join(
        f'<div id="tab-{lid}" class="res-panel{" active" if i == 0 else ""}">'
        f'{stat_block(*stats(ms))}'
        f'<div class="res-list">{rows_html(ms)}</div>'
        f'</div>'
        for i, (lid, _, api_code) in enumerate(LEAGUES)
        for ms in [all_matches[api_code]]
    )
    show_tab = (
        "\n  function showTab(id){"
        f"var tabs={json.dumps(tab_ids)};"
        "document.querySelectorAll('.res-tab').forEach(function(t,i){t.classList.toggle('active',tabs[i]===id);});"
        "document.querySelectorAll('.res-panel').forEach(function(p){p.classList.remove('active');});"
        "document.getElementById('tab-'+id).classList.add('active');}"
    )
    section = (
        "\n\n<!-- ============ RÉSULTATS ============ -->"
        "\n<section class=\"block\" id=\"resultats\" data-screen-label=\"Résultats\">"
        "\n<div class=\"wrap\"><div class=\"sec-head reveal\"><div class=\"l\">"
        "\n<div class=\"bar\"></div><div class=\"eyebrow\">Saison 2025–2026</div>"
        "\n<h2 class=\"display\">Les résultats</h2>"
        "\n<p>Tous les scores de la saison, match par match.</p>"
        "\n</div></div>"
        f"\n<div class=\"res-tabs\">{tabs_h}</div>"
        f"\n{panels_h}"
        "\n</div></section>\n\n"
    )
    return section, show_tab


def update():
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Fetching results...")

    all_matches = {}
    for lid, ln, api_code in LEAGUES:
        rop_id = ROP_IDS[api_code]
        ms = fetch_matches(api_code, rop_id)
        all_matches[api_code] = ms
        w, d, l, gf, ga = stats(ms)
        print(f"  {ln}: {len(ms)} matches — {w}V {d}N {l}D  {gf}:{ga}")

    section_html, show_tab_js = build_section(all_matches)

    with open(HTML_PATH, "r") as f:
        content = f.read()

    # Extract and parse template
    tm = re.search(r'\n("<!DOCTYPE html>.*?")\n', content, re.DOTALL)
    if not tm:
        print("ERROR: template not found in HTML file")
        sys.exit(1)
    html = json.loads(tm.group(1))

    # Remove old results section
    while "<!-- ============ RÉSULTATS ============ -->" in html:
        s = html.find("<!-- ============ RÉSULTATS ============ -->")
        e = html.find("<!-- ============ CTA ============ -->", s)
        html = html[:s] + html[e:]

    # Remove old showTab
    while "function showTab" in html:
        idx = html.find("function showTab")
        depth = 0
        for i, c in enumerate(html[idx:]):
            if c == "{": depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    html = html[:idx] + html[idx + i + 1:]
                    break

    # Clean lingering junk in script tail
    p_anchor = "media.style.transform = `translate(${x}px, ${y}px)`;\n    });\n  }\n"
    p_idx = html.find(p_anchor)
    if p_idx > 0:
        p_end = p_idx + len(p_anchor)
        sc_idx = html.rfind("</script>")
        html = html[:p_end] + html[sc_idx:]

    # Insert new section
    html = html.replace("<!-- ============ CTA ============ -->", section_html + "<!-- ============ CTA ============ -->", 1)

    # Insert showTab JS
    p_idx = html.find(p_anchor)
    p_end = p_idx + len(p_anchor)
    sc_idx = html.rfind("</script>")
    html = html[:p_end] + show_tab_js + "\n" + html[sc_idx:]

    # Encode and write back
    encoded = json.dumps(html).replace("</script>", "<\\/script>")
    content = content[:tm.start() + 1] + encoded + content[tm.end() - 1:]

    with open(HTML_PATH, "w") as f:
        f.write(content)

    print(f"Done. Updated {HTML_PATH}")


if __name__ == "__main__":
    update()

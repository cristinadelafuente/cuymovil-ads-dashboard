"""Fase 0.5 — Runner del checklist de conexiones (SOLO LECTURA).

Ejecuta la prueba mínima de lectura de cada plataforma y produce:
  - una tabla en consola,
  - phase05/checklist_resultado.md  (entregable de la Fase 0.5).

Uso:
    pip install -r phase05/requirements-phase05.txt
    # cargar credenciales (ver phase05/.env.example) y luego:
    python phase05/run_checklist.py
"""
import datetime as dt
import importlib
import os

MODULES = ["test_meta", "test_google_ads", "test_ga4", "test_clarity"]


def _status_label(r: dict) -> str:
    if r["connected"] is True:
        return "✅ Conecta"
    if r["connected"] is False and r["feasible"] is None:
        return "⛔ Bloqueo de accesos"
    if r["connected"] is False:
        return "❌ No conecta"
    return "❔ Sin evaluar"


def main():
    results = []
    for name in MODULES:
        mod = importlib.import_module(f"phase05.{name}") if __package__ else importlib.import_module(name)
        try:
            results.append(mod.run())
        except Exception as e:  # noqa: BLE001
            results.append({"source": name, "connected": False,
                            "evidence": "", "blocker": f"excepción: {e}", "feasible": False})

    # Consola
    print(f"\n=== Checklist Fase 0.5 — {dt.date.today()} ===\n")
    for r in results:
        print(f"[{_status_label(r)}] {r['source']}")
        if r["evidence"]:
            print(f"    evidencia: {r['evidence']}")
        if r["blocker"]:
            print(f"    bloqueo:   {r['blocker']}")

    # Entregable markdown
    lines = [
        f"# Checklist técnico — Fase 0.5 (solo lectura)",
        f"_Generado: {dt.datetime.now():%Y-%m-%d %H:%M}_",
        "",
        "| Fuente | Estado | Prueba mínima / evidencia | Bloqueo |",
        "| --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(
            f"| {r['source']} | {_status_label(r)} | "
            f"{r['evidence'] or '—'} | {r['blocker'] or '—'} |"
        )
    ok = sum(1 for r in results if r["connected"] is True)
    meta_ok = any(r["source"] == "Meta Ads" and r["connected"] for r in results)
    cierre = ("CUMPLE" if (meta_ok and ok >= 2) else "NO CUMPLE")
    lines += [
        "",
        f"**Fuentes que leen datos reales:** {ok}/4",
        f"**Criterio de cierre (Meta + ≥1 fuente adicional):** {cierre}",
    ]
    out = os.path.join(os.path.dirname(__file__), "checklist_resultado.md")
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nEntregable escrito en: {out}")


if __name__ == "__main__":
    main()

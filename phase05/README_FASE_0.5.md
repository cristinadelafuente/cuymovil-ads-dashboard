# Fase 0.5 — Prueba de conexiones (solo lectura)

Objetivo: probar la conexión y una extracción mínima de cada plataforma en
entorno **solo lectura**, e identificar bloqueos antes de prometer dashboard,
IA o automatización.

## Qué se cambió en el repo

1. **Modo solo-lectura (crítico).** `app.py` ahora define un flag `READ_ONLY`
   (por defecto **True**). `pause_campaign()` y `set_daily_budget()` están
   protegidas: si `READ_ONLY` es True, lanzan `WriteBlockedError` y **no tocan
   ninguna cuenta**. Los botones de ejecución de la UI aparecen deshabilitados y
   el aviso de la sidebar indica el modo. Para habilitar escritura (Fase 2) hay
   que fijar explícitamente `READ_ONLY=false` en los secrets.

2. **Scripts de prueba de conexión** en `phase05/`, uno por fuente. Cada uno
   hace una lectura mínima y devuelve `{connected, evidence, blocker, feasible}`.

## Cómo correr las pruebas

```bash
pip install -r phase05/requirements-phase05.txt
cp phase05/.env.example .env    # y rellena las credenciales
set -a && . ./.env && set +a    # cargar variables al shell
python phase05/run_checklist.py
```

El runner imprime una tabla y escribe el entregable en
`phase05/checklist_resultado.md`.

## Prueba mínima por fuente

| Fuente | Acceso / rol requerido | Prueba mínima |
| --- | --- | --- |
| Meta Ads | `ads_read` sobre `act_4207…` y `act_1015…` | insights por `date_preset` + `debug_token` (alcance/caducidad) |
| Google Ads | Developer token + OAuth lectura + login-customer-id | 1 campaña: cost_micros, impressions, clicks, ctr |
| GA4 | GCP + service account con rol Viewer en la propiedad | `runReport`: sesiones/eventos por fecha |
| Clarity | Token de proyecto (Data Export) | rage/dead clicks / scroll de un rango |

## Criterio de cierre

Al menos **Meta + una fuente adicional** (idealmente GA4) leen datos reales en
entorno demo, con permisos mapeados y sin tocar producción.

## Bloqueos conocidos a resolver primero

- **GA4:** desbloquear el rol de Cristina en GCP y crear la service account con
  rol *Viewer* sobre la propiedad.
- **Meta:** confirmar caducidad del token de usuario; evaluar token de sistema /
  long-lived.
- **Google Ads:** el developer token de nivel *test* solo lee cuentas de prueba;
  para cuentas reales hace falta acceso *basic* aprobado.

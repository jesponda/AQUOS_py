# AQUOS (Django) — E0, E1 y E2

Allegion Querétaro Unified Operating System. Piloto en localhost: MDI 1 y MDI 2, área Ensamble.
Especificación y mockups: `..\AQUOS_Docs\`. Fuentes originales (solo lectura): `..\AQUOS_Context\`.

## Requisitos
Python 3.15 (probado con 3.15.2). Dependencias en `requirements.txt` (Django 6.1.2, django-simple-history 3.13.0).

## Primer arranque
```powershell
cd AQUOS_py
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_e0 --users     # catálogos + usuarios hourly, salary, manager (contraseñas aleatorias, se muestran una vez)
.\.venv\Scripts\python.exe manage.py runserver
```
Abre http://127.0.0.1:8000/ .

## Pruebas
```powershell
.\.venv\Scripts\python.exe manage.py test
```

## Base de datos
SQLite en `%LOCALAPPDATA%\AQUOS\db.sqlite3` (fuera de OneDrive a propósito: la sincronización puede dañar el archivo). Se cambia con la variable `AQUOS_DB_PATH`. Respaldo y restauración: entrega E6.

## Estructura
- `config/` ajustes y URLs.
- `apps/core/` catálogos (áreas, turnos, categorías) y Administración de solo lectura.
- `apps/accounts/` perfil con rol (hourly, salary, manager), matriz de permisos (`permissions.py`) y decorador `permission_required`.
- `templates/`, `static/` interfaz con el estilo aprobado en los mockups.

## Reglas
Los permisos se validan en el servidor (documento 10). Ocultar un enlace no es autorización.
Sin IA, sin integraciones externas. Cambios de alcance se señalan antes de implementarlos.

## Qué incluye E1
- `/reporte/` reporte del día (Salary y Manager): producción Knob y Lever, borrador, cierre; reapertura solo Manager con motivo.
- `/areas/ensamble/` MDI 2: Calidad (Yield) y Entrega (Cumplimiento, Plan vs Real) por día, semana y mes.
- `/plan/` calendario de días hábiles con contador y plan SIOP mensual.
- Metas en `IndicatorTarget` (editables en `/admin/`).

## Qué incluye E2
- El reporte del día captura los cinco pilares en orden SQDCP; MDI 2 muestra Seguridad, Calidad, Entrega, Costos y Personal con metas y estados.
- Manual por ahora: observaciones, horas ganadas y pagadas, personal.

## Pendiente
Iconografía profesional (D31, E6), edición de catálogos en pantalla, Process Check (E3), Rails y acciones (E4), MDI 1 y Scorecard (E5).

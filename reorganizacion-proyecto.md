# Reorganizacion Proyecto

## Goal
Limpiar la raiz del repositorio y documentar la estructura sin romper la aplicacion.

## Tasks
- [x] Inventariar ficheros de raiz y referencias internas -> Verify with `git ls-files` and `rg`.
- [x] Mover documentos, logs y scripts auxiliares a carpetas de archivo -> Verify `git status` shows renames only for selected files.
- [x] Crear `docs/ESTRUCTURA_PROYECTO.md` -> Verify Mermaid sections and structure tables exist.
- [x] Ejecutar validaciones enfocadas backend/frontend -> Verify commands complete or document blockers.
- [x] Revisar diff final -> Verify no secrets, DBs or generated dependency folders are staged.

## Done When
- [x] La raiz queda mas limpia, la documentacion existe y las validaciones estan reportadas.

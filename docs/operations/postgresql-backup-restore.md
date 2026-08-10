# Respaldo y restauracion de PostgreSQL

Estos respaldos protegen la base interna del portal: usuarios, sesiones, auditoria, configuracion, programaciones y metadatos. No incluyen ni reemplazan los archivos `.bak` de SQL Server administrados por el modulo Backups.

## Politica instalada

- respaldo diario `pg_dump` en formato custom;
- validacion inmediata con `pg_restore --list`;
- hash SHA-256 y bitacora JSON Lines;
- 14 archivos diarios;
- los respaldos de domingo se clasifican como semanales y se conservan 8;
- copia adicional a `OffsiteRoot` cuando se configure.

Los archivos quedan bajo `D:\DataExpress\GestorPrimee\backups\postgresql` con la configuracion predeterminada. Tener el respaldo en la misma unidad no protege ante perdida fisica de `D:`.

## Crear un respaldo manual

En PowerShell como administrador:

```powershell
& 'D:\DataExpress\GestorPrimee\installer\Backup-GestorPrimee.ps1'
```

Para forzar su clasificacion semanal:

```powershell
& 'D:\DataExpress\GestorPrimee\installer\Backup-GestorPrimee.ps1' -Weekly
```

La bitacora no contiene contrasenas y se guarda en `logs\maintenance\postgres-backup.jsonl`.

## Probar una restauracion

La rutina rechaza cualquier archivo fuera de `BackupRoot` y nunca acepta el nombre de la base productiva como destino.

```powershell
& 'D:\DataExpress\GestorPrimee\installer\Restore-GestorPrimee.ps1' `
  -DumpPath 'D:\DataExpress\GestorPrimee\backups\postgresql\daily\gestor_primee-AAAAMMDD-HHMMSS.dump'
```

Solicita la contrasena del superusuario PostgreSQL y restaura a una base temporal con fecha. Comprueba que exista la revision Alembic. Agregue `-DropAfterValidation` para eliminar la base temporal despues de aprobar la prueba.

No existe una promocion automatica a produccion. Una recuperacion real debe planear una ventana, detener los servicios del portal, crear un respaldo final, validar nuevamente el archivo elegido y documentar el intercambio de base.

## Frecuencia de prueba

Ejecute una restauracion con `-DropAfterValidation` una vez al mes. Revise que el evento diario se ejecute:

```powershell
Get-ScheduledTaskInfo -TaskName 'DataExpress-GestorPrimee-PostgreSQL-Backup'
```

Configure `OffsiteRoot` tan pronto exista una segunda unidad o una ruta UNC con permisos para la cuenta `SYSTEM`. Si la ruta de red no permite acceso a `SYSTEM`, use una cuenta de servicio administrada para la tarea programada.

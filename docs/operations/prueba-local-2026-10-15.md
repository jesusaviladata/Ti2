# Pruebas locales con Railway — 15 de octubre de 2026

El usuario autorizó vincular este PC con el panel y probar únicamente la base sintética DataExpress_Prueba_20261015 y las carpetas de `%LOCALAPPDATA%/DataExpressTests/20261015`. No se opera sobre las demás bases de la instancia.

## Evidencia
- Instancia `(localdb)\MSSQLLocalDB`, SQL Server Express 17.0.4025.3, iniciada bajo el usuario propietario de Windows.
- Vinculación HTTPS del agente aceptada con 201; heartbeat y comandos firmados aceptados con 200.
- Full ejecutado desde el panel: BAK de 4,640,768 bytes, ZIP de 486,589 bytes. Manifiesto con `restore_verifyonly`, CRC del ZIP y SHA-256 del BAK correctos.
- Restauración real en DataExpress_Prueba_20261015_RecuperadaFull: 1,000 filas idénticas; DBCC CHECKDB correcto.
- Diez filas sintéticas agregadas después del Full. Diferencial ejecutado desde el panel; ZIP de 94,466 bytes. Restauración Full + diferencial en DataExpress_Prueba_20261015_RecuperadaDiff: 1,010 filas idénticas; DBCC CHECKDB correcto.
- Ejecutor de archivos probado localmente: Full de dos archivos, incremental de un archivo modificado, archivo sin cambios omitido, `.tmp` excluido y contenido recuperado idéntico. Esta prueba de archivos no pasó por la UI del panel.
- 74 pruebas del agente aprobadas, incluidas ocho de conexión LocalDB y conservación del cifrado en destinos SQL normales.
- Paquete Windows x64 0.5.1 construido con PyInstaller; Smoke-TestRelease aprobado. Ejecutable iniciado bajo el mismo usuario e identidad; heartbeat confirma versión 0.5.1.
- Plan `Prueba automática PC 0951` creado desde Railway para jueves a las 09:51 CDMX, solo para DataExpress_Prueba_20261015. Ejecución automática completada; ZIP de 487,781 bytes. CRC, SHA-256, RESTORE VERIFYONLY y restauración real en DataExpress_Prueba_20261015_RecuperadaAuto correctos, con 1,010 filas idénticas y DBCC CHECKDB sin errores.
- Panel al finalizar: tres respaldos completados, cero fallidos. Ambos planes de prueba quedaron pausados; el primer plan conservó la hora inicial 02:00 porque el llenado automatizado del control de tiempo no actualizó React. Se pausó sin ejecutarlo y se creó el plan correcto usando teclado, verificando la hora guardada.

## Entrega y alcance pendiente
Paquete y SHA-256 en `entregas/agente-railway-20261015`, junto con reportes JSON y Controlar-PruebaLocal.ps1. El agente queda ejecutándose bajo el usuario, sin servicio ni inicio automático. No se copiaron identidades al paquete. Siguen pendientes las pruebas en Windows Server, instalación como servicio con cuenta autorizada y destinos remotos/SMB. La prueba de archivos fue local al ejecutor.

## Defectos encontrados
1. ODBC 17 rechaza `Encrypt=yes` contra LocalDB con error 08001/20. Se reproduce y corrige exclusivamente para el patrón exacto `(localdb)\instancia`; servidores, TCP y destinos ambiguos conservan `Encrypt=yes`. El acceso sigue siendo integrado de Windows. Referencia del transporte local y contexto de usuario: [Microsoft LocalDB](https://learn.microsoft.com/en-us/sql/database-engine/configure-windows/sql-server-express-localdb).
2. El formulario automático enviaba todas las bases del catálogo, sin permitir elegir. Se agrega selección explícita, inicialmente vacía, y solo se envían las bases seleccionadas que siguen presentes en el catálogo. La selección se borra al cambiar de agente, instancia o al cerrar el formulario. Esto permite probar la programación sin incluir bases ajenas a la prueba.

## Archivos de evidencia local
`resultado-full.json`, `resultado-differential.json`, `resultado-archivos.json`, logs y respaldos permanecen bajo la carpeta aislada indicada. Las identidades, el código de vinculación y las claves no se incorporan al repositorio. La primera ejecución fue con el paquete 0.5.0; las pruebas SQL exitosas usaron el código corregido bajo el usuario propietario de LocalDB.

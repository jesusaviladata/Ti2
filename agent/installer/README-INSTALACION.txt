DATA EXPRESS AGENT 0.5.0 - INSTALACION
========================================

NO abra DataExpressAgent.exe con doble clic.

Contenido:
- ..\DataExpressAgent\DataExpressAgent.exe: agente de Data Express.
- ..\DataExpressAgent.Service.exe: WinSW 2.12.0 para ejecutar el agente como servicio.
- DataExpressAgent.Service.xml: configuracion del servicio.
- Install-DataExpressAgent.ps1: instalador.
- Test-InstallPrerequisites.ps1: diagnostico previo sin cambios en el equipo.
- Smoke-TestRelease.ps1: verificacion de integridad y estructura del paquete.
- Uninstall-DataExpressAgent.ps1: desinstalador.

Antes de instalar necesita solamente un codigo de vinculacion vigente generado en el panel.
El paquete oficial ya incluye el dominio de control y la confianza criptografica.

DIAGNOSTICO PREVIO:

  .\Test-InstallPrerequisites.ps1

INSTALACION RAPIDA:
1. Extraiga TODO el archivo ZIP.
2. Ejecute Instalar-DataExpressAgent.cmd.
3. Acepte la solicitud de permisos administrativos.
4. Pegue el codigo temporal cuando se solicite.
5. Espere la confirmacion de vinculacion con el backend.

INSTALACION MANUAL PARA SOPORTE:
1. Abra PowerShell como administrador dentro de "installer".
2. Ejecute:

   Set-ExecutionPolicy -Scope Process Bypass

   .\Install-DataExpressAgent.ps1

3. Cuando se solicite, pegue el codigo temporal del panel y presione Enter.

Solo para migrar una instalacion 0.4.2 con perfiles locales:

   .\Install-DataExpressAgent.ps1 -MigrationMode -ProfilesFile ".\agent-profiles.json"

4. Compruebe:

   Get-Service DataExpressAgent

Debe mostrar el estado Running. El instalador no informa exito hasta observar un
heartbeat confirmado por el backend. El agente solo realiza conexiones HTTPS salientes.
Si el servicio ya existe, use Update-DataExpressAgent.ps1; el instalador nuevo se niega
a sobrescribir una identidad o configuracion existente.

IMPORTANTE: este paquete no contiene contrasenas de Windows, RDP, SFTP ni base de datos.

PERMISOS
El servicio se ejecuta como NT AUTHORITY\NetworkService. El perfil SQL usa autenticacion
integrada de Windows. Esta cuenta debe tener
permiso BACKUP DATABASE en cada base seleccionable y lectura de la raiz configurada.
La cuenta del servicio de SQL Server debe tener escritura en esa raiz (por ejemplo D:\),
porque el motor SQL es quien crea los .bak. En un dominio, NetworkService accede a SMB
como la cuenta de maquina DOMINIO\SERVIDOR$. Conceda a esa cuenta permisos de recurso
compartido y NTFS. En equipos fuera de dominio use una cuenta de servicio administrada
segun la politica de la organizacion y valide el acceso antes de respaldar.
Para SFTP se recomienda una llave privada local con permisos exclusivos para la cuenta
del servicio. Nunca agregue password o connectionString al archivo de perfiles.

COMPATIBILIDAD

- Mantiene heartbeat cada 30 segundos aunque SQL Server tarde varios minutos.
- Reporta capacidad de los discos y bloquea el inicio si invadiria la reserva critica.
- Permite Full directo a SMB para bases grandes, sin ZIP ni copia temporal local.
- Incluye motor piloto de archivos Full, incremental y diferencial para local y SMB.
- Guarda Full directamente en Fecha\Backup_Fecha.zip y diferencial en Fecha\DIFERENCIAL\Backup_Fecha.zip.
- Nombra los archivos Base_Fecha.bak y Base_Fecha_DIF.bak.
- Permite administrar perfiles SQL y destinos desde el dashboard con secretos cifrados para este agente.
- Conserva compatibilidad con agentes y perfiles 0.4.2 durante una actualizacion escalonada.
- Usa una carpeta temporal por lote y elimina los .bak despues de validar y transferir el ZIP.
- Si la compresion o transferencia falla, conserva los .bak temporales para recuperacion.
- Usa compresion ZIP rapida para reducir el tiempo de CPU.
- Acepta huellas SFTP en formato OpenSSH o Base64 con relleno.
- Permite eliminar directamente los logs estructurales validados por una simulacion,
  con limites por cantidad y tamano y omision de archivos cambiados o inaccesibles.
- Guarda los archivos internos con nombres legibles, por ejemplo BASE_FULL.bak,
  sin agregar el identificador tecnico del lote despues del tipo de backup.
- Marca el backup como completado al terminar la validacion y transferencia del ZIP;
  la eliminacion de los .bak temporales continua en segundo plano y se reintenta.

ACTUALIZACION DE UNA INSTALACION EXISTENTE

Abra PowerShell como administrador dentro de la carpeta installer y ejecute:

  Set-ExecutionPolicy -Scope Process Bypass
  .\Update-DataExpressAgent.ps1

El actualizador conserva agent.json, la identidad, las llaves SFTP y el emparejamiento.
Espera a que el servicio se detenga, instala la nueva version y exige un heartbeat
confirmado por el backend. Si no lo recibe dentro de 90 segundos, restaura la version
y la configuracion anteriores de forma automatica. Antes de modificar la instalacion
valida todos los archivos contra SHA256SUMS.txt y detiene el agente nuevo antes del rollback.
Las instalaciones heredadas que aun usan LocalService migran a NetworkService; una cuenta
de servicio personalizada se conserva sin cambios. El rollback restaura tambien la cuenta.

La configuracion normal de conexiones se realiza desde Dashboard > Agentes > Conexiones.
El archivo agent-profiles.json se conserva solo para compatibilidad durante la migracion.


DATA EXPRESS AGENT - INSTALACION DE PRUEBA
===========================================

NO abra DataExpressAgent.exe con doble clic.

Contenido:
- ..\DataExpressAgent\DataExpressAgent.exe: agente de Data Express.
- ..\DataExpressAgent.Service.exe: WinSW 2.12.0 para ejecutar el agente como servicio.
- DataExpressAgent.Service.xml: configuracion del servicio.
- Install-DataExpressAgent.ps1: instalador.
- Uninstall-DataExpressAgent.ps1: desinstalador.

Antes de instalar necesita solamente un codigo de vinculacion vigente generado en el panel.
El paquete oficial ya incluye el dominio de control y la confianza criptografica.

Instalacion:
1. Extraiga TODO el archivo ZIP.
2. Abra PowerShell como administrador.
3. Entre a la carpeta "installer".
4. Ejecute:

   Set-ExecutionPolicy -Scope Process Bypass

   .\Install-DataExpressAgent.ps1

5. Cuando se solicite, pegue el codigo temporal del panel y presione Enter.

Solo para migrar una instalacion 0.4.2 con perfiles locales:

   .\Install-DataExpressAgent.ps1 -MigrationMode -ProfilesFile ".\agent-profiles.json"

6. Compruebe:

   Get-Service DataExpressAgent

Debe mostrar el estado Running. El agente solo realiza conexiones HTTPS salientes.

IMPORTANTE: este paquete no contiene contrasenas de Windows, RDP, SFTP ni base de datos.

PERMISOS
El perfil SQL usa autenticacion integrada de Windows. La cuenta del servicio debe tener
permiso BACKUP DATABASE en cada base seleccionable y lectura de la raiz configurada.
La cuenta del servicio de SQL Server debe tener escritura en esa raiz (por ejemplo D:\),
porque el motor SQL es quien crea los .bak. Para SMB, la cuenta del agente (LocalService
sale a la red como la cuenta del servidor) debe tener acceso al recurso compartido.
Para SFTP se recomienda una llave privada local con permisos exclusivos para la cuenta
del servicio. Nunca agregue password o connectionString al archivo de perfiles.

COMPATIBILIDAD

- Mantiene heartbeat cada 30 segundos aunque SQL Server tarde varios minutos.
- Reporta capacidad de los discos y bloquea el inicio si invadiria la reserva critica.
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
y la configuracion anteriores de forma automatica.

La configuracion normal de conexiones se realiza desde Dashboard > Agentes > Conexiones.
El archivo agent-profiles.json se conserva solo para compatibilidad durante la migracion.


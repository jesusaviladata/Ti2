DATA EXPRESS AGENT - INSTALACION DE PRUEBA
===========================================

NO abra DataExpressAgent.exe con doble clic.

Contenido:
- ..\DataExpressAgent\DataExpressAgent.exe: agente de Data Express.
- ..\DataExpressAgent.Service.exe: WinSW 2.12.0 para ejecutar el agente como servicio.
- DataExpressAgent.Service.xml: configuracion del servicio.
- Install-DataExpressAgent.ps1: instalador.
- Uninstall-DataExpressAgent.ps1: desinstalador.

Antes de instalar necesita:
1. URL HTTPS del backend de Railway.
2. Clave publica de firma de ordenes.
3. Identificador de esa clave.
4. Codigo de vinculacion vigente generado en el panel.
5. Archivo agent-profiles.json adaptado desde agent-profiles.example.json.

Instalacion:
1. Extraiga TODO el archivo ZIP.
2. Abra PowerShell como administrador.
3. Entre a la carpeta "installer".
4. Ejecute:

   Set-ExecutionPolicy -Scope Process Bypass

   .\Install-DataExpressAgent.ps1 `
     -ServerUrl "https://ti2.up.railway.app" `
     -CommandSigningPublicKey "CLAVE_PUBLICA" `
     -CommandSigningKeyId "railway-2026-01" `
     -PairingCode "CODIGO_DEL_PANEL" `
     -ProfilesFile ".\agent-profiles.json"

5. Compruebe:

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

FUNCIONES DE LA VERSION 0.2.10

- Usa una carpeta temporal por lote y elimina los .bak despues de validar y transferir el ZIP.
- Si la compresion o transferencia falla, conserva los .bak temporales para recuperacion.
- Usa compresion ZIP rapida para reducir el tiempo de CPU.
- Acepta huellas SFTP en formato OpenSSH o Base64 con relleno.
- Permite eliminar directamente los logs estructurales validados por una simulacion,
  con limites por cantidad y tamano y omision de archivos cambiados o inaccesibles.
- Guarda los archivos internos con nombres legibles, por ejemplo BASE_FULL.bak,
  sin agregar el identificador tecnico del lote despues del tipo de backup.

ACTUALIZACION DE UNA INSTALACION EXISTENTE

Abra PowerShell como administrador dentro de la carpeta installer y ejecute:

  Set-ExecutionPolicy -Scope Process Bypass
  .\Update-DataExpressAgent.ps1

El actualizador conserva agent.json, la identidad, las llaves SFTP y el emparejamiento.
- Exploracion de discos y carpetas.
- Simulacion de limpieza estructural.
- Movimiento reversible a cuarentena, restauracion y purga.
- Descubrimiento de bases por instancia SQL configurada.
- Backups .bak/.trn en D:\AAAA-MM-DD y ZIP diario. Cuando SQL Server Express
  no permite RESTORE VERIFYONLY sin privilegios amplios, valida tamano y SHA-256
  del .bak antes de comprimir, y la integridad del ZIP despues de crearlo.
- Transferencia opcional del ZIP por SFTP o SMB.


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
     -PairingCode "CODIGO_DEL_PANEL"

5. Compruebe:

   Get-Service DataExpressAgent

Debe mostrar el estado Running. El agente solo realiza conexiones HTTPS salientes.

IMPORTANTE: este paquete no contiene contrasenas de Windows, RDP, SFTP ni base de datos.


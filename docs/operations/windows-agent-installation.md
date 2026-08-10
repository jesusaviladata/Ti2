# Instalación de Data Express Agent en Windows Server

## Requisitos

- Windows Server 2019 o posterior con actualizaciones vigentes.
- Salida HTTPS hacia el dominio de Railway.
- Un código de vinculación nuevo generado por un administrador en Configuración.
- El paquete firmado con `DataExpressAgent.exe`, `DataExpressAgent.Service.exe` (WinSW), XML e instalador.

No abra puertos entrantes y no capture credenciales de RDP, SMB o SFTP.

## Instalación

1. Copie el paquete al servidor y abra PowerShell como administrador.
2. Ejecute `Install-DataExpressAgent.ps1` con la URL HTTPS, clave pública de órdenes, identificador de clave y código de vinculación.
3. El servicio se ejecuta como `LOCAL SERVICE`, crea su identidad Ed25519 y protege la clave privada con DPAPI.
4. El código temporal se elimina después de una vinculación exitosa.
5. Confirme en el panel que el equipo aparece como conectado.

El agente no será administrador local. Conceda a `LOCAL SERVICE` únicamente lectura y modificación sobre la raíz seleccionada, por ejemplo `D:\Ipsofactu`, cuando se habiliten simulación y cuarentena.

## Actualización y reemplazo

Conserve `%ProgramData%\DataExpress\Agent\identity.json` para actualizar la misma instalación. Si se pierde o reinstala Windows, use **Reemplazar agente** en el panel; la identidad anterior se revoca solo cuando la nueva termina de vincularse.

## Diagnóstico

- Servicio: `Get-Service DataExpressAgent`.
- Registros rotativos: carpeta de instalación del agente.
- Estado en el panel: última conexión, versión y error acotado.
- Nunca copie la identidad, las claves o los códigos a tickets o registros.

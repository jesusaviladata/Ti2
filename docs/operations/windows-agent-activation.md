# Activación de Windows Agent en Railway

El módulo se despliega inicialmente con `AGENT_MODULE_ENABLED=false`.

Antes de activarlo:

1. Ejecutar `python backend/scripts/generate_agent_signing_key.py --key-id railway-AAAA-MM` en un equipo seguro.
2. Guardar `privateKey` como `AGENT_COMMAND_SIGNING_PRIVATE_KEY` en Railway.
3. Guardar `keyId` como `AGENT_COMMAND_SIGNING_KEY_ID` en Railway.
4. Incorporar únicamente `publicKey` y `keyId` al paquete firmado del agente. La clave privada nunca se copia al servidor Windows ni al repositorio.
5. Ejecutar la migración `0004`, probar la vinculación con un agente piloto y revisar la auditoría.
6. Cambiar `AGENT_MODULE_ENABLED=true` y volver a desplegar.

Si falta una clave válida mientras el módulo está habilitado, el backend rechazará el arranque. Para rollback se desactiva el módulo; no debe ejecutarse el downgrade de `0004` mientras exista un servidor con transporte `agent`.


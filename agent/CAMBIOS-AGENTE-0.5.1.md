# Agente 0.5.1

Corrige la conexión con SQL Server Express LocalDB bajo el usuario propietario de Windows. La excepción de transporte se limita a `(localdb)\instancia`; conexiones de SQL Server normales mantienen el cifrado configurado por el agente.

Validación: 74 pruebas automatizadas aprobadas. Pruebas reales desde Railway de Full y diferencial con restauración y comparación de datos sintéticos. Los perfiles y la identidad existentes se conservan al actualizar.

Para LocalDB, ejecutar el agente bajo el mismo usuario dueño de la instancia. El servicio instalado como LocalSystem no ve la instancia privada de ese usuario. La prueba de PC usa ejecución interactiva en segundo plano; la validación como servicio en Windows Server continúa siendo una prueba independiente.

La selección de bases para programación automática se actualiza en el panel; no requiere cambiar el protocolo del agente.

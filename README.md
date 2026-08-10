# Infra Platform

Plataforma web de administración de infraestructura empresarial. Gestiona backups de SQL Server, acceso remoto (SSH / RDP / FTP / VNC), monitoreo y reportes desde un único panel centralizado.

---

## Tecnologías

| Capa | Tecnología |
|---|---|
| Frontend | Next.js 16 · React 19 · TypeScript · Tailwind CSS |
| Backend | FastAPI · Python 3.11+ · JWT · sesiones HttpOnly |
| Base de datos (producción) | PostgreSQL 17 |
| Publicación (producción) | IIS + URL Rewrite + ARR + HTTPS |
| Servicios (producción) | WinSW + APScheduler embebido; sin Docker, Redis ni Celery |

---

## Requisitos previos

Instalar en el equipo antes de continuar:

- **Python 3.11+** — https://www.python.org/downloads/
  - Marcar ✅ "Add Python to PATH" durante la instalación
- **Node.js 20.9+** — https://nodejs.org/
- **ODBC Driver 17 for SQL Server** — https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server
  - Requerido solo si se va a conectar a un servidor SQL Server real

---

## Instalación y ejecución (modo desarrollo)

### 1. Clonar o copiar el proyecto

```bash
git clone <url-del-repositorio>
cd infra-platform
```

> Si copias la carpeta manualmente, asegúrate de **no incluir** `frontend/node_modules/` ni `frontend/.next/`.

---

### 2. Instalar dependencias del Backend

```cmd
cd backend
pip install fastapi "uvicorn[standard]" PyJWT bcrypt python-multipart pyodbc apscheduler paramiko
```

> Si `pip` no es reconocido, usa: `python -m pip install ...`

---

### 3. Instalar dependencias del Frontend

```cmd
cd frontend
npm install
```

---

### 4. Compilar el Frontend

```cmd
npm run build
```

> Solo se necesita hacer una vez, o cada vez que haya cambios en el código.

---

### 5. Arrancar la aplicación

Desde la raíz del proyecto, doble clic en **`start.bat`**, o desde terminal:

```cmd
.\start.bat
```

Esto abre dos ventanas:
- **Backend** corriendo en `http://localhost:8000`
- **Frontend** corriendo en `http://localhost:3000`

---

### 6. Abrir en el navegador

```
http://localhost:3000
```

---

## Credenciales de prueba

| Campo | Valor |
|---|---|
| Email | `admin@primee.local` |
| Contraseña | `Admin1234!` |

---

## Estructura del proyecto

```
infra-platform/
├── backend/
│   ├── dev_server.py        # Servidor de desarrollo (sin PostgreSQL ni Docker)
│   ├── requirements.txt     # Dependencias para producción
│   └── app/                 # Código de producción (FastAPI completo)
│       ├── api/v1/          # Endpoints REST
│       ├── services/        # Lógica de negocio
│       ├── models/          # Modelos de base de datos
│       └── tasks/           # Tareas Celery
├── frontend/
│   ├── src/
│   │   ├── app/             # Páginas (Next.js App Router)
│   │   ├── components/      # Componentes reutilizables
│   │   ├── hooks/           # React hooks personalizados
│   │   ├── services/        # Llamadas a la API
│   │   ├── store/           # Estado global (Zustand)
│   │   └── types/           # Tipos TypeScript
│   ├── package.json
│   └── next.config.ts
├── nginx/
│   └── nginx.conf           # Proxy inverso (producción)
├── docker-compose.yml       # Stack completo en contenedores
├── .env.example             # Variables de entorno de ejemplo
├── start.bat                # Script de arranque (Windows)
└── README.md
```

---

## Variables de entorno (opcional)

Para conectar un servidor SQL Server real, configura estas variables **antes** de ejecutar `start.bat`:

**PowerShell:**
```powershell
$env:SQLSERVER_SERVER   = "192.168.1.10"
$env:SQLSERVER_PORT     = "1433"
$env:SQLSERVER_USER     = "sa"
$env:SQLSERVER_PASSWORD = "tuPassword"
```

**CMD:**
```cmd
set SQLSERVER_SERVER=192.168.1.10
set SQLSERVER_PASSWORD=tuPassword
```

---

## Solución de problemas comunes

### `ModuleNotFoundError: No module named 'bcrypt'`
```cmd
pip install bcrypt
```

### `npm : No se puede cargar el archivo npm.ps1` (PowerShell)
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```
O usa `cmd.exe` en lugar de PowerShell.

### El backend arranca pero el login falla
Verifica que el backend esté corriendo abriendo `http://localhost:8000/docs` en el navegador.

### Puerto 3000 o 8000 ya en uso
```cmd
netstat -ano | findstr :3000
taskkill /PID <numero_pid> /F
```

---

## Ejecución en red local

Para que otros equipos de la misma red puedan acceder, el backend ya escucha en `0.0.0.0:8000`. Solo comparte la IP del equipo servidor:

```
http://IP_DEL_SERVIDOR:3000
```

---

## Producción con Docker (opcional)

Requiere Docker Desktop instalado.

```bash
cp .env.example .env
# Editar .env con tus valores reales

docker compose up -d
```

Acceder en `http://localhost` (puerto 80 vía Nginx).

---

## Módulos disponibles

- **Dashboard** — métricas generales y estado del sistema
- **Backups** — programación y ejecución de backups SQL Server
- **Acceso Remoto** — conexiones SSH, RDP, FTP, VNC, SFTP
- **Gestor de Archivos** — explorador de archivos remoto vía SSH/SFTP
- **Notificaciones** — alertas de eventos críticos en tiempo real

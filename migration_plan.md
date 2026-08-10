# 🚀 PLAN DE DESARROLLO — Plataforma Web de Administración de Infraestructura

> **Versión:** 1.0.0  
> **Fecha:** 2026-05-08  
> **Estado:** En planificación  
> **Stack:** FastAPI + React + SQL Server / PostgreSQL

---

## 📋 Índice

1. [Visión General](#visión-general)
2. [Stack Tecnológico](#stack-tecnológico)
3. [Arquitectura del Sistema](#arquitectura-del-sistema)
4. [Estructura de Carpetas](#estructura-de-carpetas)
5. [Módulos y APIs REST](#módulos-y-apis-rest)
6. [Plan de Desarrollo por Fases](#plan-de-desarrollo-por-fases)
7. [Sistema Multiempresa](#sistema-multiempresa)
8. [Notificaciones](#notificaciones)
9. [Seguridad](#seguridad)
10. [Reportes](#reportes)
11. [Infraestructura y Despliegue](#infraestructura-y-despliegue)
12. [Estimación de Esfuerzo](#estimación-de-esfuerzo)
13. [Changelog](#changelog)

---

## 🌐 Visión General

Plataforma web empresarial integral para la administración de infraestructura, respaldos y accesos remotos. Diseñada para entornos **multiempresa / multicliente**, con dashboard centralizado, automatización de tareas y auditoría completa.

### Módulos Principales
| # | Módulo | Prioridad |
|---|--------|-----------|
| 1 | Limpieza Inteligente de Archivos | Alta |
| 2 | Backups y Administración SQL Server | Alta |
| 3 | Acceso Remoto tipo Cyber | Alta |
| 4 | Dashboard Centralizado | Alta |
| 5 | Sistema de Notificaciones | Media |
| 6 | Reportes Automáticos | Media |
| 7 | API REST pública | Baja |

---

## 🛠️ Stack Tecnológico

### Backend
```
FastAPI (Python 3.11+)
├── Autenticación: JWT + OAuth2 + 2FA (pyotp)
├── ORM: SQLAlchemy + Alembic (migraciones)
├── Tareas programadas: APScheduler / Celery + Redis
├── WebSockets: para alertas en tiempo real
└── Docs automáticas: Swagger UI / ReDoc
```

### Frontend
```
React 19 + TypeScript
├── UI Components: shadcn/ui + Tailwind CSS v3.4.17
├── Animaciones: GSAP 3 (ScrollTrigger) — gsap.context() en useEffect
├── Iconos: Lucide React
├── Estado global: Zustand
├── Gráficas: Recharts / ApexCharts
├── HTTP client: Axios + React Query
├── Routing: Next.js App Router
└── Build: Next.js 15
```

---

## 🎨 Sistema de Diseño — Preset "Organic Tech"

> Identidad: Puente entre laboratorio de investigación y revista de lujo avant-garde.
> El frontend NO es un sitio web genérico — es un **instrumento digital de operaciones**.

### Paleta de Colores
| Nombre | Hex | Uso |
|--------|-----|-----|
| Musgo | `#2E4036` | Fondos primarios, headers |
| Arcilla | `#CC5833` | CTAs, alertas, acentos |
| Crema | `#F2F0E9` | Fondos claros, textos sobre oscuro |
| Carbón | `#1A1A1A` | Texto principal, fondos profundos |

### Tipografía
| Rol | Fuente | Uso |
|-----|--------|-----|
| Títulos | Plus Jakarta Sans + Outfit | Headings, navegación |
| Drama | Cormorant Garamond Italic | Estadísticas grandes, hero |
| Datos | IBM Plex Mono | Métricas, logs, código |

### Mood Visual
```
Bosque oscuro · Texturas orgánicas · Cristalería de laboratorio
```

---

## 🏛️ Arquitectura de Componentes UI

### 1. HEADER
- Contenedor tipo **píldora**, centrado y fijo
- Transición: transparente → blur al hacer scroll
- `rounded-[2rem]` con backdrop-blur

### 2. DASHBOARD HERO (página principal tras login)
- Altura `100dvh`, métricas a sangre con degradado
- Tipografía: contraste entre sans bold y Cormorant Garamond italic masivo
- Indicadores en tiempo real como elementos cinematográficos

### 3. MÓDULOS — Tarjetas con micro-UIs funcionales
| Módulo | Micro-UI |
|--------|----------|
| Backups | Typewriter de estado de backup en tiempo real |
| Limpieza | Shuffler de archivos detectados |
| Acceso Remoto | Scheduler con cursor animado de sesiones activas |
| Dashboard | Gráficas animadas con GSAP ScrollTrigger |

### 4. SECCIONES DE MÓDULO
- Fondo oscuro Carbón `#1A1A1A` con textura orgánica en parallax
- Tarjetas de pantalla completa que se apilan con GSAP ScrollTrigger
- Animaciones SVG únicas por módulo (ondas para backups, grid para limpieza)

### 5. FOOTER
- Fondo Carbón profundo con bordes superiores `rounded-[3rem]`
- Indicador de estado del sistema: punto verde pulsante
- IBM Plex Mono para datos del sistema

---

## ⚙️ Sistema de Diseño Fijo (NUNCA CAMBIAR)

```css
/* Textura visual global */
/* SVG feTurbulence overlay con opacidad 0.05 en toda la app */

/* Contenedores */
border-radius: rounded-[2rem] a rounded-[3rem] — sin esquinas afiladas

/* Botones magnéticos */
transform: scale(1.03) en hover
transition: color mediante capas <span> deslizantes

/* Animaciones */
gsap.context() dentro de useEffect
easing: power3.out para todas las entradas
```

---

## 🖼️ Imágenes (Unsplash — Mood Organic Tech)
```
Hero Dashboard:   bosque oscuro, luz difusa
Módulo Backups:   cristalería de laboratorio, datos
Módulo Limpieza:  texturas orgánicas, orden minimalista
Módulo Acceso:    arquitectura de servidores, iluminación tenue
```

### Base de Datos
```
SQL Server (producción) / PostgreSQL (desarrollo)
├── Redis → caché y colas de tareas
└── Alembic → control de migraciones
```

### Automatización
```
├── Python Scripts (lógica de negocio)
├── PowerShell (comandos Windows Server)
└── SQL Agent Jobs (backups SQL Server)
```

### Infraestructura
```
Docker + Docker Compose
├── Windows Server 2019/2022 o Linux (Ubuntu 22.04)
├── Nginx (reverse proxy)
└── Certbot (SSL/TLS)
```

---

## 🏗️ Arquitectura del Sistema

```
┌─────────────────────────────────────────────────┐
│                   CLIENTE WEB                   │
│              React + TypeScript                 │
└──────────────────────┬──────────────────────────┘
                       │ HTTPS / WebSocket
┌──────────────────────▼──────────────────────────┐
│                  NGINX (Proxy)                  │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│              FASTAPI BACKEND                    │
│  ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ Auth API │ │ Admin API│ │ WebSocket Hub  │  │
│  └──────────┘ └──────────┘ └────────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │Backup API│ │Access API│ │  Cleanup API   │  │
│  └──────────┘ └──────────┘ └────────────────┘  │
└──────────┬──────────────────────────────────────┘
           │
┌──────────▼──────────┐    ┌──────────────────────┐
│  SQL Server / PG    │    │    Redis (Cache)      │
└─────────────────────┘    └──────────────────────┘
           │
┌──────────▼──────────┐    ┌──────────────────────┐
│  Celery Workers     │    │  Servidor Secundario  │
│  (tareas async)     │    │  NAS / Nube Privada   │
└─────────────────────┘    └──────────────────────┘
```

---

## 📁 Estructura de Carpetas

```
infra-platform/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── auth.py
│   │   │   │   ├── cleanup.py
│   │   │   │   ├── backups.py
│   │   │   │   ├── access.py
│   │   │   │   ├── dashboard.py
│   │   │   │   ├── notifications.py
│   │   │   │   └── reports.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── database.py
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   ├── client.py
│   │   │   ├── backup.py
│   │   │   ├── cleanup_log.py
│   │   │   └── access_log.py
│   │   ├── schemas/
│   │   ├── services/
│   │   │   ├── backup_service.py
│   │   │   ├── cleanup_service.py
│   │   │   ├── access_service.py
│   │   │   └── notification_service.py
│   │   ├── tasks/
│   │   │   ├── scheduled_cleanup.py
│   │   │   └── scheduled_backup.py
│   │   └── main.py
│   ├── alembic/
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ui/          ← shadcn/ui components
│   │   │   ├── dashboard/
│   │   │   ├── backups/
│   │   │   ├── cleanup/
│   │   │   └── access/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── store/           ← Zustand
│   │   ├── services/        ← Axios calls
│   │   └── App.tsx
│   ├── package.json
│   └── Dockerfile
│
├── docker-compose.yml
├── nginx/
│   └── nginx.conf
└── .env.example
```

---

## 🔌 Módulos y APIs REST

### 🧹 Módulo 1 — Limpieza Inteligente

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/v1/cleanup/scan` | Escanear carpetas configuradas |
| POST | `/api/v1/cleanup/execute` | Ejecutar limpieza manual |
| GET | `/api/v1/cleanup/history` | Historial de archivos eliminados |
| GET | `/api/v1/cleanup/trash` | Ver papelera temporal |
| DELETE | `/api/v1/cleanup/trash/{id}` | Eliminar definitivamente |
| POST | `/api/v1/cleanup/restore/{id}` | Restaurar desde papelera |
| GET | `/api/v1/cleanup/schedules` | Ver programaciones activas |
| POST | `/api/v1/cleanup/schedules` | Crear nueva programación |
| PUT | `/api/v1/cleanup/schedules/{id}` | Editar programación |
| DELETE | `/api/v1/cleanup/schedules/{id}` | Eliminar programación |

**Reglas BCK:**
```json
{
  "rule": "keep_last_bck",
  "extensions": [".rar"],
  "pattern": "*BCK*",
  "keep": "latest",
  "example": "sistema_BCK_2026.rar"
}
```

---

### 💾 Módulo 2 — Backups SQL Server

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/v1/backups` | Listar todos los backups |
| POST | `/api/v1/backups/manual` | Ejecutar backup manual |
| GET | `/api/v1/backups/{id}/status` | Estado de un backup |
| POST | `/api/v1/backups/migrate` | Migrar al servidor secundario |
| DELETE | `/api/v1/backups/purge` | Aplicar política de retención |
| GET | `/api/v1/backups/schedules` | Ver programaciones |
| POST | `/api/v1/backups/schedules` | Crear programación |
| GET | `/api/v1/backups/integrity/{id}` | Validar integridad |
| GET | `/api/v1/backups/logs` | Logs de operaciones |

**Tipos de backup:**
```json
{
  "types": ["full", "differential", "incremental"],
  "destinations": ["local", "nas", "secondary_server", "private_cloud"],
  "retention": {
    "keep_last_n": 10,
    "keep_by_date": "30d",
    "keep_critical": true
  }
}
```

---

### 🖥️ Módulo 3 — Acceso Remoto

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/v1/access/sessions` | Crear sesión remota |
| GET | `/api/v1/access/sessions` | Listar sesiones activas |
| PUT | `/api/v1/access/sessions/{id}/close` | Cerrar sesión |
| GET | `/api/v1/access/logs` | Historial completo de accesos |
| GET | `/api/v1/access/logs/{id}` | Detalle de una sesión |
| POST | `/api/v1/access/permissions` | Asignar permisos |
| GET | `/api/v1/access/alerts` | Accesos sospechosos |

**Log de sesión (estructura):**
```json
{
  "session_id": "uuid",
  "user": "tecnico_01",
  "client": "Empresa ABC",
  "server": "SRV-PROD-01",
  "ip": "192.168.1.100",
  "tool": "RDP",
  "reason": "Mantenimiento preventivo",
  "start": "2026-05-08T10:00:00",
  "end": "2026-05-08T11:30:00",
  "duration_min": 90,
  "role": "Técnico"
}
```

---

### 📊 Módulo 4 — Dashboard

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/v1/dashboard/summary` | Resumen general |
| GET | `/api/v1/dashboard/metrics` | CPU, RAM, Disco en tiempo real |
| GET | `/api/v1/dashboard/alerts` | Alertas activas |
| GET | `/api/v1/dashboard/storage-growth` | Crecimiento de almacenamiento |
| GET | `/api/v1/dashboard/backup-history` | Historial de backups (gráfica) |
| WS | `/ws/dashboard` | WebSocket para tiempo real |

---

## 📅 Plan de Desarrollo por Fases

### Fase 0 — Setup (Semana 1)
- [ ] Inicializar repositorio Git (monorepo)
- [ ] Configurar Docker Compose (backend + frontend + DB + Redis)
- [ ] Setup FastAPI base + autenticación JWT
- [ ] Setup React + Vite + Tailwind + shadcn/ui
- [ ] Configurar Alembic + modelos base
- [ ] Variables de entorno y configuración

### Fase 1 — Autenticación y Base (Semanas 2-3)
- [ ] Login / Logout con JWT
- [ ] Roles: Administrador, Técnico, Supervisor, Cliente
- [ ] 2FA con TOTP (Google Authenticator)
- [ ] Gestión de usuarios y clientes (multiempresa)
- [ ] Pantalla de login minimalista
- [ ] Middleware de auditoría (registro de todo cambio)

### Fase 2 — Módulo Backups (Semanas 4-6)
- [ ] Conexión con SQL Server (pyodbc)
- [ ] Ejecución de backups Full / Diferencial / Incremental
- [ ] Programación con APScheduler / Celery
- [ ] Migración automática a destino secundario
- [ ] Política de retención
- [ ] Encriptación con AES-256
- [ ] UI: lista de backups, estado, programaciones
- [ ] Alertas por fallo

### Fase 3 — Módulo Limpieza (Semanas 7-9)
- [ ] Escaneo de carpetas configuradas
- [ ] Reglas de conservación BCK
- [ ] Papelera temporal
- [ ] Historial de archivos eliminados
- [ ] Programación automática
- [ ] UI: explorador de archivos, reglas, historial

### Fase 4 — Módulo Acceso Remoto (Semanas 10-12)
- [ ] CRUD de sesiones remotas
- [ ] Logs automáticos de entrada/salida
- [ ] Control de permisos por rol
- [ ] Restricción por horario
- [ ] Detección de accesos sospechosos
- [ ] UI: panel de sesiones activas, historial, alertas

### Fase 5 — Dashboard y Tiempo Real (Semanas 13-14)
- [ ] WebSocket para métricas en vivo
- [ ] Gráficas de almacenamiento y backups
- [ ] Centro de alertas críticas
- [ ] UI: dashboard principal con widgets

### Fase 6 — Notificaciones y Reportes (Semanas 15-16)
- [ ] Email (SMTP)
- [ ] Telegram Bot
- [ ] WhatsApp (Twilio / WA Business API)
- [ ] Microsoft Teams (webhooks)
- [ ] Reportes PDF (WeasyPrint / ReportLab)
- [ ] Reportes Excel (openpyxl)
- [ ] Envío programado de reportes

### Fase 7 — Hardening y Producción (Semanas 17-18)
- [ ] Tests unitarios e integración (pytest + Vitest)
- [ ] Documentación de API (Swagger completo)
- [ ] SSL/TLS con Certbot
- [ ] Rate limiting y protección DDoS
- [ ] Monitoreo con Prometheus + Grafana (opcional)
- [ ] Deploy en servidor de producción

---

## 🏢 Sistema Multiempresa

```
Tenant (Empresa)
├── tiene muchos → Clientes
├── tiene muchos → Usuarios (con roles)
├── tiene muchos → Servidores
├── tiene muchos → Backups
├── tiene muchos → Logs de Acceso
└── tiene muchos → Logs de Limpieza
```

Cada entidad en la base de datos incluye `tenant_id` para aislamiento total de datos entre empresas.

---

## 🔔 Sistema de Notificaciones

| Canal | Librería / Servicio | Casos de uso |
|-------|-------------------|--------------|
| Email | `fastapi-mail` + SMTP | Fallos de backup, reportes |
| Telegram | `python-telegram-bot` | Alertas críticas en tiempo real |
| WhatsApp | Twilio / WA Business API | Alertas críticas |
| Teams | Incoming Webhooks | Notificaciones de equipo |

**Eventos que disparan notificación:**
- Backup fallido
- Espacio en disco crítico (< 10%)
- Acceso remoto fuera de horario
- Error de sincronización
- Limpieza completada con errores

---

## 🔒 Seguridad

- **Autenticación:** JWT (access + refresh tokens)
- **2FA:** TOTP compatible con Google Authenticator
- **Encriptación:** AES-256 para backups
- **Auditoría:** Registro de toda acción en tabla `audit_log`
- **Rate limiting:** SlowAPI
- **CORS:** configurado estrictamente por dominio
- **Roles y permisos:** RBAC (Role-Based Access Control)
- **Validación de integridad:** hash SHA-256 en cada backup
- **HTTPS:** obligatorio en producción

---

## 📄 Reportes

| Tipo | Formato | Frecuencia |
|------|---------|------------|
| Resumen de backups | PDF / Excel | Diario / Semanal |
| Historial de accesos | PDF / Excel | Semanal / Mensual |
| Espacio liberado por limpieza | PDF | Mensual |
| Incidentes y alertas | PDF | Bajo demanda |

---

## 🐳 Infraestructura y Despliegue

```yaml
# docker-compose.yml (resumen)
services:
  backend:    # FastAPI — puerto 8000
  frontend:   # React (Nginx) — puerto 3000
  db:         # PostgreSQL — puerto 5432
  redis:      # Redis — puerto 6379
  celery:     # Workers de tareas asíncronas
  nginx:      # Reverse proxy — puertos 80/443
```

### Comandos de arranque
```bash
# Desarrollo
docker-compose up --build

# Producción
docker-compose -f docker-compose.prod.yml up -d

# Migraciones
docker exec backend alembic upgrade head
```

---

## ⏱️ Estimación de Esfuerzo

| Fase | Duración | Complejidad |
|------|----------|-------------|
| Fase 0 — Setup | 1 semana | Baja |
| Fase 1 — Auth + Base | 2 semanas | Media |
| Fase 2 — Backups | 3 semanas | Alta |
| Fase 3 — Limpieza | 3 semanas | Media |
| Fase 4 — Acceso Remoto | 3 semanas | Alta |
| Fase 5 — Dashboard | 2 semanas | Media |
| Fase 6 — Notificaciones/Reportes | 2 semanas | Media |
| Fase 7 — Hardening | 2 semanas | Media |
| **TOTAL** | **~18 semanas** | |

> Estimación para **1 desarrollador full-stack**. Con equipo de 2-3 personas se reduce a ~8-10 semanas.

---

## 📝 Changelog

### [1.0.0] — 2026-05-08
#### Agregado
- Documento inicial de planificación
- Definición de 4 módulos principales
- Stack tecnológico seleccionado: FastAPI + React + SQL Server
- Plan de 7 fases de desarrollo
- Diseño de APIs REST por módulo
- Arquitectura multiempresa
- Sistema de notificaciones (Email, Telegram, WhatsApp, Teams)
- Infraestructura Docker definida

---


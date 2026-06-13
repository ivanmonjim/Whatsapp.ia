# WhatsApp IA - Sistema de Citas Multiempresa

Sistema de atención automática por WhatsApp desarrollado con FastAPI, SQLAlchemy y la API de WhatsApp Cloud de Meta.

## Funcionalidades

* Gestión de múltiples empresas.
* Atención automática mediante IA.
* Agendamiento de citas por WhatsApp.
* Cancelación de citas.
* Reprogramación de citas.
* Gestión de servicios por empresa.
* Registro de conversaciones.
* Integración con OpenAI.
* Integración con WhatsApp Cloud API.

## Tecnologías

* Python 3.14
* FastAPI
* SQLAlchemy
* SQLite
* OpenAI API
* Meta WhatsApp Cloud API
* Uvicorn

## Instalación

### Clonar repositorio

```bash
git clone https://github.com/ivanmonjim/Whatsapp.ia.git
cd Whatsapp.ia
```

### Crear entorno virtual

```bash
python -m venv venv
```

### Activar entorno virtual

Mac/Linux:

```bash
source venv/bin/activate
```

Windows:

```bash
venv\Scripts\activate
```

### Instalar dependencias

```bash
pip install -r requirements.txt
```

## Variables de entorno

Crear un archivo `.env` en la raíz del proyecto:

```env
OPENAI_API_KEY=tu_api_key

META_VERIFY_TOKEN=tu_verify_token
META_ACCESS_TOKEN=tu_access_token

DATABASE_URL=sqlite:///./whatsapp.db
```

## Ejecutar el proyecto

```bash
uvicorn app.main:app --reload
```

Servidor disponible en:

```text
http://127.0.0.1:8000
```

Documentación Swagger:

```text
http://127.0.0.1:8000/docs
```

## Estructura del proyecto

```text
whatsapp-ia/
│
├── app/
│   ├── main.py
│   ├── models.py
│   ├── database.py
│   └── config.py
│
├── requirements.txt
├── .env
├── .gitignore
└── README.md
```

## Flujo de citas

### Agendar cita

1. Seleccionar servicio.
2. Proporcionar nombre.
3. Proporcionar fecha.
4. Proporcionar hora.
5. Confirmación automática.

### Cancelar cita

1. Buscar cita activa.
2. Solicitar confirmación.
3. Cambiar estado a CANCELADA.

### Reprogramar cita

1. Buscar cita activa.
2. Solicitar nueva fecha.
3. Solicitar nueva hora.
4. Actualizar cita existente.

## Autor

Iván Montelongo, Aaron Galarza

Proyecto de automatización de citas mediante WhatsApp e Inteligencia Artificial.

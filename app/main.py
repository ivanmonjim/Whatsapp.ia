import requests
from openai import OpenAI
from app.config import OPENAI_API_KEY, META_VERIFY_TOKEN
from app.config import META_ACCESS_TOKEN
from fastapi import FastAPI, Depends, Request, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from fastapi import Request
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from sqlalchemy import Boolean, Float

from app.database import engine, SessionLocal
from app.models import Base, Conversacion, Empresa, NumeroWhatsApp, Cita, Servicio

Base.metadata.create_all(bind=engine)

app = FastAPI()

scheduler = BackgroundScheduler()

client = OpenAI(api_key=OPENAI_API_KEY)


class MensajeEntrada(BaseModel):
    telefono: str
    numero_receptor: str
    mensaje: str


class EmpresaEntrada(BaseModel):
    nombre: str
    giro: str
    prompt_base: str


class NumeroWhatsAppEntrada(BaseModel):
    empresa_id: int
    telefono: str
    phone_number_id: str
    token: str


class WebhookMeta(BaseModel):
    data: dict

def limpiar_flujos_activos(
    db: Session,
    empresa_id: int,
    telefono_cliente: str
):
    flujos = (
        db.query(Conversacion)
        .filter(
            Conversacion.empresa_id == empresa_id,
            Conversacion.telefono == telefono_cliente,
            Conversacion.paso != None
        )
        .all()
    )

    for flujo in flujos:
        flujo.paso = None

    db.commit()

def normalizar_telefono(telefono: str):
    telefono = telefono.strip()
    telefono = telefono.replace(" ", "")
    telefono = telefono.replace("-", "")
    telefono = telefono.replace("(", "")
    telefono = telefono.replace(")", "")

    if telefono.startswith("+"):
        telefono = telefono[1:]

    # Corrección para números de México que llegan como 521...
    if telefono.startswith("521") and len(telefono) == 13:
        telefono = "52" + telefono[3:]

    return telefono


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def inicio():
    return {"status": "ok", "mensaje": "WhatsApp IA funcionando"}


@app.post("/empresas")
def crear_empresa(data: EmpresaEntrada, db: Session = Depends(get_db)):
    empresa = Empresa(
        nombre=data.nombre.strip(),
        giro=data.giro.strip(),
        prompt_base=data.prompt_base.strip(),
        status="ACTIVA",
    )

    db.add(empresa)
    db.commit()
    db.refresh(empresa)

    return {
        "status": "ok",
        "mensaje": "Empresa creada correctamente",
        "empresa": {
            "id": empresa.id,
            "nombre": empresa.nombre,
            "giro": empresa.giro,
            "prompt_base": empresa.prompt_base,
            "status": empresa.status,
        },
    }


@app.get("/empresas")
def listar_empresas(db: Session = Depends(get_db)):
    empresas = db.query(Empresa).all()

    return [
        {
            "id": empresa.id,
            "nombre": empresa.nombre,
            "giro": empresa.giro,
            "prompt_base": empresa.prompt_base,
            "status": empresa.status,
        }
        for empresa in empresas
    ]


@app.put("/empresas/{empresa_id}")
def actualizar_empresa(
    empresa_id: int, data: EmpresaEntrada, db: Session = Depends(get_db)
):
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()

    if not empresa:
        return {"status": "error", "mensaje": "Empresa no encontrada"}

    empresa.nombre = data.nombre.strip()
    empresa.giro = data.giro.strip()
    empresa.prompt_base = data.prompt_base.strip()

    db.commit()
    db.refresh(empresa)

    return {
        "status": "ok",
        "mensaje": "Empresa actualizada correctamente",
        "empresa": {
            "id": empresa.id,
            "nombre": empresa.nombre,
            "giro": empresa.giro,
            "prompt_base": empresa.prompt_base,
            "status": empresa.status,
        },
    }


@app.delete("/empresas/{empresa_id}")
def desactivar_empresa(empresa_id: int, db: Session = Depends(get_db)):
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()

    if not empresa:
        return {"status": "error", "mensaje": "Empresa no encontrada"}

    empresa.status = "INACTIVA"

    db.commit()
    db.refresh(empresa)

    return {
        "status": "ok",
        "mensaje": "Empresa desactivada correctamente",
        "empresa": {
            "id": empresa.id,
            "nombre": empresa.nombre,
            "status": empresa.status,
        },
    }


@app.put("/empresas/{empresa_id}/activar")
def activar_empresa(empresa_id: int, db: Session = Depends(get_db)):
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()

    if not empresa:
        return {"status": "error", "mensaje": "Empresa no encontrada"}

    empresa.status = "ACTIVA"

    db.commit()
    db.refresh(empresa)

    return {
        "status": "ok",
        "mensaje": "Empresa activada correctamente",
        "empresa": {
            "id": empresa.id,
            "nombre": empresa.nombre,
            "status": empresa.status,
        },
    }


@app.post("/numeros-whatsapp")
def crear_numero_whatsapp(data: NumeroWhatsAppEntrada, db: Session = Depends(get_db)):
    telefono_normalizado = normalizar_telefono(data.telefono)

    empresa = db.query(Empresa).filter(Empresa.id == data.empresa_id).first()

    if not empresa:
        return {"status": "error", "mensaje": "Empresa no encontrada"}

    numero_existente = (
        db.query(NumeroWhatsApp)
        .filter(NumeroWhatsApp.telefono == telefono_normalizado)
        .first()
    )

    if numero_existente:
        return {
            "status": "error",
            "mensaje": "Ese número ya está vinculado",
            "numero": {
                "id": numero_existente.id,
                "empresa_id": numero_existente.empresa_id,
                "telefono": numero_existente.telefono,
            },
        }

    numero = NumeroWhatsApp(
        empresa_id=data.empresa_id,
        telefono=telefono_normalizado,
        phone_number_id=data.phone_number_id.strip(),
        token=data.token.strip(),
        status="ACTIVO",
    )

    db.add(numero)
    db.commit()
    db.refresh(numero)

    return {
        "status": "ok",
        "mensaje": "Número de WhatsApp vinculado",
        "numero": {
            "id": numero.id,
            "empresa_id": numero.empresa_id,
            "telefono": numero.telefono,
            "phone_number_id": numero.phone_number_id,
        },
    }


@app.get("/numeros-whatsapp")
def listar_numeros(db: Session = Depends(get_db)):
    numeros = db.query(NumeroWhatsApp).all()

    return [
        {
            "id": n.id,
            "empresa_id": n.empresa_id,
            "telefono": n.telefono,
            "phone_number_id": n.phone_number_id,
        }
        for n in numeros
    ]


@app.get("/empresas/{empresa_id}/numeros")
def numeros_empresa(empresa_id: int, db: Session = Depends(get_db)):
    numeros = (
        db.query(NumeroWhatsApp).filter(NumeroWhatsApp.empresa_id == empresa_id).all()
    )

    return [
        {"id": n.id, "telefono": n.telefono, "phone_number_id": n.phone_number_id}
        for n in numeros
    ]


@app.get("/empresas/{empresa_id}/conversaciones")
def conversaciones_empresa(empresa_id: int, db: Session = Depends(get_db)):
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()

    if not empresa:
        return {"status": "error", "mensaje": "Empresa no encontrada"}

    conversaciones = (
        db.query(Conversacion).filter(Conversacion.empresa_id == empresa_id).all()
    )

    return {
        "status": "ok",
        "empresa": {"id": empresa.id, "nombre": empresa.nombre},
        "total_conversaciones": len(conversaciones),
        "conversaciones": [
            {
                "id": c.id,
                "telefono": c.telefono,
                "mensaje": c.mensaje,
                "respuesta": c.respuesta,
            }
            for c in conversaciones
        ],
    }


@app.get("/citas/activas")
def obtener_citas_activas(db: Session = Depends(get_db)):
    return db.query(Cita).filter(Cita.status == "AGENDADA").all()


@app.delete("/citas/pruebas")
def limpiar_citas(db: Session = Depends(get_db)):
    db.query(Cita).delete()
    db.commit()

    return {"mensaje": "Todas las citas eliminadas"}


@app.delete("/conversaciones/pruebas")
def limpiar_conversaciones(db: Session = Depends(get_db)):
    db.query(Conversacion).delete()
    db.commit()

    return {"mensaje": "Todas las conversaciones eliminadas"}


@app.get("/citas")
def listar_citas(db: Session = Depends(get_db)):
    citas = db.query(Cita).all()

    resultado = []

    for c in citas:
        servicio = None

        if c.servicio_id:
            servicio = db.query(Servicio).filter(Servicio.id == c.servicio_id).first()

        resultado.append(
            {
                "id": c.id,
                "empresa_id": c.empresa_id,
                "servicio_id": c.servicio_id,
                "servicio": servicio.nombre if servicio else None,
                "nombre": c.nombre,
                "telefono": c.telefono,
                "fecha": c.fecha,
                "hora": c.hora,
                "status": c.status,
            }
        )

    return resultado


import requests


def enviar_mensaje_whatsapp(
    phone_number_id: str, token: str, telefono_cliente: str, mensaje: str
):
    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    payload = {
        "messaging_product": "whatsapp",
        "to": telefono_cliente,
        "type": "text",
        "text": {"body": mensaje},
    }

    response = requests.post(url, headers=headers, json=payload)

    print("DESTINO:", telefono_cliente)
    print("TOKEN:", token[:20])
    print("META STATUS:", response.status_code)
    print("META RESPONSE:", response.text)

    return response.json()


def enviar_recordatorios():
    print("EJECUTANDO RECORDATORIOS...")
    db = SessionLocal()

    try:
        ahora = datetime.now()
        manana = ahora + timedelta(days=1)

        fecha_manana = manana.strftime("%d/%m/%Y")

        print("FECHA MAÑANA:", fecha_manana)

        citas = (
            db.query(Cita)
            .filter(
                Cita.status.in_(["AGENDADA", "CONFIRMADA"]),
                Cita.fecha == fecha_manana,
                Cita.recordatorio_enviado == False,
            )
            .all()
        )
        print("CITAS ENCONTRADAS:", len(citas))

        print(f"RECORDATORIOS: {len(citas)} citas encontradas")

        for cita in citas:
            numero = (
                db.query(NumeroWhatsApp)
                .filter(NumeroWhatsApp.empresa_id == cita.empresa_id)
                .first()
            )

            empresa = db.query(Empresa).filter(Empresa.id == cita.empresa_id).first()

            if not numero or not empresa:
                continue

            mensaje = (
                f"Hola {cita.nombre}. "
                f"Te recordamos que tienes una cita mañana "
                f"{cita.fecha} a las {cita.hora} "
                f"en {empresa.nombre}."
            )

            enviar_mensaje_whatsapp(
                phone_number_id=numero.phone_number_id,
                token=numero.token,
                telefono_cliente=cita.telefono,
                mensaje=mensaje,
            )
            cita.recordatorio_enviado = True
            db.commit()

    except Exception as e:
        print("ERROR RECORDATORIOS:", e)

    finally:
        db.close()


scheduler.add_job(enviar_recordatorios, "cron", hour=9, minute=0)

scheduler.start()


def obtener_historial_conversacion(
    db: Session, empresa_id: int, telefono_cliente: str, limite: int = 6
):
    conversaciones = (
        db.query(Conversacion)
        .filter(
            Conversacion.empresa_id == empresa_id,
            Conversacion.telefono == telefono_cliente,
        )
        .order_by(Conversacion.id.desc())
        .limit(limite)
        .all()
    )

    conversaciones = list(reversed(conversaciones))

    historial = ""

    for c in conversaciones:
        historial += f"Cliente: {c.mensaje}\n"
        historial += f"Asistente: {c.respuesta}\n"

    return historial


def detectar_datos_cita(texto: str):
    import json
    import re

    respuesta = client.responses.create(
        model="gpt-4.1-mini",
        input=f"""
Extrae los datos de una cita desde este historial.

Si ya existe nombre, fecha, hora y el cliente confirma con palabras como:
"correcto", "correcta", "sí", "confirmo", "está bien",
entonces "completo" debe ser true.

Responde SOLO JSON válido, sin markdown, sin explicación.

Formato:
{{
  "quiere_agendar": true,
  "nombre": "Aaron Galarza",
  "fecha": "10/06/2026",
  "hora": "16:00",
  "completo": true
}}

Texto:
{texto}
""",
    )

    texto_respuesta = respuesta.output_text.strip()
    print("RESPUESTA DETECTOR:", texto_respuesta)

    match = re.search(r"\{.*\}", texto_respuesta, re.DOTALL)

    if not match:
        raise ValueError("No se encontró JSON en la respuesta del detector")

    return json.loads(match.group(0))


def obtener_flujo_activo(db: Session, empresa_id: int, telefono_cliente: str):
    return (
        db.query(Conversacion)
        .filter(
            Conversacion.empresa_id == empresa_id,
            Conversacion.telefono == telefono_cliente,
            Conversacion.paso.in_([
                "PEDIR_SERVICIO",
                "PEDIR_NOMBRE",
                "PEDIR_FECHA",
                "PEDIR_HORA",
                "CONFIRMAR_CANCELACION",
                "REPROGRAMAR_FECHA",
                "REPROGRAMAR_HORA",
            ]),
        )
        .order_by(Conversacion.id.desc())
        .first()
    )


@app.post("/webhook-whatsapp")
async def recibir_webhook_whatsapp(data: dict, db: Session = Depends(get_db)):
    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        metadata = value["metadata"]
        numero_receptor = normalizar_telefono(metadata["display_phone_number"])

        mensaje_data = value["messages"][0]
        telefono_cliente = normalizar_telefono(mensaje_data["from"])
        mensaje = mensaje_data["text"]["body"]

    except Exception:
        return {"status": "evento ignorado"}

    numero = (
        db.query(NumeroWhatsApp)
        .filter(NumeroWhatsApp.telefono == numero_receptor)
        .first()
    )

    if not numero:
        return {"status": "error", "mensaje": "Número no registrado"}

    empresa = db.query(Empresa).filter(Empresa.id == numero.empresa_id).first()

    if not empresa:
        return {"status": "error", "mensaje": "Empresa no encontrada"}

    if empresa.status != "ACTIVA":
        return {"status": "error", "mensaje": "Empresa inactiva"}

    mensaje_lower = mensaje.lower().strip()

    print("MENSAJE ORIGINAL:", mensaje)
    print("MENSAJE LOWER:", mensaje_lower)

    flujo = obtener_flujo_activo(
        db=db, empresa_id=empresa.id, telefono_cliente=telefono_cliente
    )
    print("FLUJO ACTUAL:", flujo.paso if flujo else None)

    if mensaje_lower in ["hola", "buenas", "buenos dias", "buenas tardes", "buenas noches"]:

        cita_activa = (
        db.query(Cita)
        .filter(
            Cita.empresa_id == empresa.id,
            Cita.telefono == telefono_cliente,
            Cita.status.in_(["AGENDADA", "CONFIRMADA"])
        )
        .first()
    )

        if cita_activa:
            respuesta = (
            "¡Hola! 👋\n\n"
            "Encontramos una cita agendada.\n\n"
            f"📅 Fecha: {cita_activa.fecha}\n"
            f"🕒 Hora: {cita_activa.hora}\n\n"
            "Si deseas cancelarla escribe:\n"
            "👉 Cancelar cita\n\n"
            "Si deseas reprogramarla escribe:\n"
            "👉 Reprogramar cita"
        )
        else:
            respuesta = (
            "¡Hola! 👋\n\n"
            "¿En qué puedo ayudarte hoy?\n\n"
            "Si deseas agendar una cita escribe:\n"
            "👉 Quiero agendar una cita"
        )

        enviar_mensaje_whatsapp(
        phone_number_id=numero.phone_number_id,
        token=numero.token,
        telefono_cliente=telefono_cliente,
        mensaje=respuesta,
    )

        return {"status": "saludo"}

    if (
    "cancelar" in mensaje_lower
    and "cita" in mensaje_lower
    and (not flujo or flujo.paso in ["PEDIR_SERVICIO", "PEDIR_NOMBRE", "PEDIR_FECHA", "PEDIR_HORA"])
):
        print("ENTRO A CANCELAR CITA")

        cita_activa = (
            db.query(Cita)
            .filter(
                Cita.empresa_id == empresa.id,
                Cita.telefono == telefono_cliente,
                Cita.status.in_(["AGENDADA", "CONFIRMADA"])
            )
            .first()
        )

        if not cita_activa:
            respuesta = "No encontré ninguna cita activa para cancelar."

            enviar_mensaje_whatsapp(
                phone_number_id=numero.phone_number_id,
                token=numero.token,
                telefono_cliente=telefono_cliente,
                mensaje=respuesta
            )

            return {"status": "sin_cita_activa"}

        servicio = None

        if cita_activa.servicio_id:
            servicio = (
                db.query(Servicio)
                .filter(Servicio.id == cita_activa.servicio_id)
                .first()
            )

        nombre_servicio = servicio.nombre if servicio else "Servicio no especificado"

        respuesta = (
            "Encontré tu cita:\n\n"
            f"Servicio: {nombre_servicio}\n"
            f"Fecha: {cita_activa.fecha}\n"
            f"Hora: {cita_activa.hora}\n\n"
            "¿Deseas cancelarla?\n"
            "Responde: Sí cancelar o No"
        )

        db.query(Conversacion).filter(
           Conversacion.empresa_id == empresa.id,
           Conversacion.telefono == telefono_cliente
        ).delete()

        db.commit()

        conversacion = Conversacion(
            empresa_id=empresa.id,
            telefono=telefono_cliente,
            mensaje=mensaje,
            respuesta=respuesta,
            paso="CONFIRMAR_CANCELACION",
            servicio_id=cita_activa.servicio_id,
            nombre=cita_activa.nombre,
            fecha=cita_activa.fecha,
            hora=cita_activa.hora
        )

        db.add(conversacion)
        db.commit()

        enviar_mensaje_whatsapp(
            phone_number_id=numero.phone_number_id,
            token=numero.token,
            telefono_cliente=telefono_cliente,
            mensaje=respuesta
        )

        return {"status": "confirmar_cancelacion"}
    
    if (
    "reprogramar" in mensaje_lower
    and "cita" in mensaje_lower
    and (not flujo or flujo.paso in ["PEDIR_SERVICIO", "PEDIR_NOMBRE", "PEDIR_FECHA", "PEDIR_HORA"])
):
        print("ENTRO A REPROGRAMAR CITA")

        cita_activa = (
            db.query(Cita)
            .filter(
                Cita.empresa_id == empresa.id,
                Cita.telefono == telefono_cliente,
                Cita.status.in_(["AGENDADA", "CONFIRMADA"]),
            )
            .first()
        )

        if not cita_activa:
            respuesta = "No encontré ninguna cita activa para reprogramar."

            enviar_mensaje_whatsapp(
                phone_number_id=numero.phone_number_id,
                token=numero.token,
                telefono_cliente=telefono_cliente,
                mensaje=respuesta,
            )

            return {"status": "sin_cita_activa"}

        servicio = None

        if cita_activa.servicio_id:
            servicio = (
                db.query(Servicio)
                .filter(Servicio.id == cita_activa.servicio_id)
                .first()
            )

        nombre_servicio = servicio.nombre if servicio else "Servicio no especificado"

        respuesta = (
            "Encontré tu cita actual:\n\n"
            f"Servicio: {nombre_servicio}\n"
            f"Fecha: {cita_activa.fecha}\n"
            f"Hora: {cita_activa.hora}\n\n"
            "¿Para qué nueva fecha deseas reprogramarla?"
        )
        db.query(Conversacion).filter(
          Conversacion.empresa_id == empresa.id,
          Conversacion.telefono == telefono_cliente
        ).delete()

        db.commit()

        conversacion = Conversacion(
            empresa_id=empresa.id,
            telefono=telefono_cliente,
            mensaje=mensaje,
            respuesta=respuesta,
            paso="REPROGRAMAR_FECHA",
            servicio_id=cita_activa.servicio_id,
            nombre=cita_activa.nombre,
            fecha=cita_activa.fecha,
            hora=cita_activa.hora,
        )

        db.add(conversacion)
        db.commit()

        enviar_mensaje_whatsapp(
            phone_number_id=numero.phone_number_id,
            token=numero.token,
            telefono_cliente=telefono_cliente,
            mensaje=respuesta,
        )

        return {"status": "reprogramar_fecha"}

    if flujo and flujo.paso == "PEDIR_SERVICIO":
        servicios = (
            db.query(Servicio)
            .filter(Servicio.empresa_id == empresa.id, Servicio.activo == True)
            .all()
        )

        servicio_seleccionado = None

        if mensaje_lower.isdigit():
            indice = int(mensaje_lower) - 1

            if 0 <= indice < len(servicios):
                servicio_seleccionado = servicios[indice]

        else:
            for servicio in servicios:
                if servicio.nombre.lower() == mensaje_lower:
                    servicio_seleccionado = servicio
                    break

        if not servicio_seleccionado:
            respuesta = (
                "No encontré ese servicio. "
                "Por favor responde con el número o el nombre exacto del servicio."
            )
        else:
            flujo.servicio_id = servicio_seleccionado.id
            flujo.paso = "PEDIR_NOMBRE"
            db.commit()

            respuesta = (
                f"Perfecto, seleccionaste {servicio_seleccionado.nombre}. "
                f"¿Cuál es tu nombre completo?"
            )

        conversacion = Conversacion(
            empresa_id=empresa.id,
            telefono=telefono_cliente,
            mensaje=mensaje,
            respuesta=respuesta,
            paso=flujo.paso,
            servicio_id=flujo.servicio_id,
        )

        db.add(conversacion)
        db.commit()

        enviar_mensaje_whatsapp(
            phone_number_id=numero.phone_number_id,
            token=numero.token,
            telefono_cliente=telefono_cliente,
            mensaje=respuesta,
        )

        return {"status": "ok", "paso": flujo.paso}

    if flujo and flujo.paso == "PEDIR_NOMBRE":
        flujo.nombre = mensaje.strip()
        flujo.paso = "PEDIR_FECHA"
        db.commit()

        respuesta = (
            f"Perfecto, {flujo.nombre}.\n\n"
            "¿Qué fecha deseas para tu cita?\n\n"
            "📅 Utiliza el formato:\n"
            "DD/MM/YYYY\n\n"
            "Ejemplo:\n"
            "18/06/2026"
        )

        conversacion = Conversacion(
            empresa_id=empresa.id,
            telefono=telefono_cliente,
            mensaje=mensaje,
            respuesta=respuesta,
            paso=flujo.paso,
            servicio_id=flujo.servicio_id,
            nombre=flujo.nombre,
        )

        db.add(conversacion)
        db.commit()

        enviar_mensaje_whatsapp(
            phone_number_id=numero.phone_number_id,
            token=numero.token,
            telefono_cliente=telefono_cliente,
            mensaje=respuesta,
        )

        return {"status": "ok", "paso": flujo.paso}

    if flujo and flujo.paso == "PEDIR_FECHA":
        flujo.fecha = mensaje.strip()
        flujo.paso = "PEDIR_HORA"
        db.commit()

        respuesta = (
            f"Perfecto. Registré la fecha {flujo.fecha}.\n\n"
            "🕒 ¿A qué hora deseas tu cita?\n\n"
            "Utiliza formato 24 horas:\n"
            "HH:MM\n\n"
            "Ejemplo:\n"
            "15:00"
        )

        conversacion = Conversacion(
            empresa_id=empresa.id,
            telefono=telefono_cliente,
            mensaje=mensaje,
            respuesta=respuesta,
            paso=flujo.paso,
            servicio_id=flujo.servicio_id,
            nombre=flujo.nombre,
            fecha=flujo.fecha,
        )

        db.add(conversacion)
        db.commit()

        enviar_mensaje_whatsapp(
            phone_number_id=numero.phone_number_id,
            token=numero.token,
            telefono_cliente=telefono_cliente,
            mensaje=respuesta,
        )

        return {"status": "ok", "paso": flujo.paso}

    if flujo and flujo.paso == "PEDIR_HORA":
        print("ENTRO A PEDIR HORA")
        flujo.hora = mensaje.strip()

        servicio = db.query(Servicio).filter(Servicio.id == flujo.servicio_id).first()

        cita_existente = (
            db.query(Cita)
            .filter(
                Cita.empresa_id == empresa.id,
                Cita.telefono == telefono_cliente,
                Cita.status.in_(["AGENDADA", "CONFIRMADA"]),
            )
            .first()
        )

        if cita_existente:
            respuesta = (
                f"Ya tienes una cita agendada para el "
                f"{cita_existente.fecha} a las {cita_existente.hora}. "
                f"Si deseas cambiarla, escribe: Reprogramar cita."
            )

            enviar_mensaje_whatsapp(
                phone_number_id=numero.phone_number_id,
                token=numero.token,
                telefono_cliente=telefono_cliente,
                mensaje=respuesta,
            )

            db.delete(flujo)
            db.commit()

            return {"status": "cita_existente"}

        cita = Cita(
            empresa_id=empresa.id,
            servicio_id=flujo.servicio_id,
            nombre=flujo.nombre,
            telefono=telefono_cliente,
            fecha=flujo.fecha,
            hora=flujo.hora,
            status="CONFIRMADA",
        )

        nombre_cliente = flujo.nombre
        fecha_cita = flujo.fecha
        hora_cita = flujo.hora
        servicio_id = flujo.servicio_id
        nombre_servicio = servicio.nombre if servicio else "el servicio seleccionado"

        db.add(cita)
        db.commit()
        db.refresh(cita)

        db.delete(flujo)
        db.commit()

        respuesta = (
            "✅ Cita confirmada\n\n"
            f"Servicio: {nombre_servicio}\n"
            f"Nombre: {nombre_cliente}\n"
            f"Fecha: {fecha_cita}\n"
            f"Hora: {hora_cita}\n\n"
            "Gracias por agendar con nosotros.\n\n"
            "Si deseas cancelar tu cita escribe:\n"
            "👉 Cancelar cita\n\n"
            "Si deseas reprogramarla escribe:\n"
            "👉 Reprogramar cita"
        )

        conversacion = Conversacion(
            empresa_id=empresa.id,
            telefono=telefono_cliente,
            mensaje=mensaje,
            respuesta=respuesta,
            paso=None,
            servicio_id=servicio_id,
            nombre=nombre_cliente,
            fecha=fecha_cita,
            hora=hora_cita,
        )

        db.add(conversacion)
        db.commit()

        enviar_mensaje_whatsapp(
            phone_number_id=numero.phone_number_id,
            token=numero.token,
            telefono_cliente=telefono_cliente,
            mensaje=respuesta,
        )

        return {
            "status": "ok",
            "paso": "CITA_CONFIRMADA",
            "cita_id": cita.id,
        }
        

    if flujo and flujo.paso == "CONFIRMAR_CANCELACION":

        if mensaje_lower in ["si", "sí", "si cancelar", "sí cancelar", "confirmo", "confirmar"]:

            cita_activa = (
                db.query(Cita)
                .filter(
                    Cita.empresa_id == empresa.id,
                    Cita.telefono == telefono_cliente,
                    Cita.status.in_(["AGENDADA", "CONFIRMADA"])
                )
                .first()
            )

            if cita_activa:
                cita_activa.status = "CANCELADA"
                db.commit()

                respuesta = (
                    "✅ Cita cancelada correctamente\n\n"
                    f"Fecha: {cita_activa.fecha}\n"
                    f"Hora: {cita_activa.hora}"
                )
            else:
                respuesta = "No encontré ninguna cita activa para cancelar."

            db.delete(flujo)
            db.commit()

            enviar_mensaje_whatsapp(
                phone_number_id=numero.phone_number_id,
                token=numero.token,
                telefono_cliente=telefono_cliente,
                mensaje=respuesta
            )

            return {"status": "cita_cancelada"}

        if mensaje_lower in ["no", "no cancelar"]:

            respuesta = "Perfecto, tu cita sigue activa."

            db.delete(flujo)
            db.commit()

            enviar_mensaje_whatsapp(
                phone_number_id=numero.phone_number_id,
                token=numero.token,
                telefono_cliente=telefono_cliente,
                mensaje=respuesta
            )

            return {"status": "cancelacion_rechazada"}

    if "agendar" in mensaje_lower and "cita" in mensaje_lower and not flujo:
        servicios = (
            db.query(Servicio)
            .filter(Servicio.empresa_id == empresa.id, Servicio.activo == True)
            .all()
        )

        if not servicios:
            respuesta = (
                "Por el momento no hay servicios disponibles para agendar. "
                "Por favor intenta más tarde."
            )

        else:
            lista_servicios = "\n".join(
                [
                    f"{i + 1}. {servicio.nombre} - ${servicio.precio}"
                    for i, servicio in enumerate(servicios)
                ]
            )

            respuesta = (
                "Claro. ¿Para qué servicio deseas agendar?\n\n"
                f"{lista_servicios}\n\n"
                "Puedes responder con el número o el nombre del servicio."
            )

            conversacion = Conversacion(
                empresa_id=empresa.id,
                telefono=telefono_cliente,
                mensaje=mensaje,
                respuesta=respuesta,
                paso="PEDIR_SERVICIO",
            )

            db.add(conversacion)
            db.commit()

        enviar_mensaje_whatsapp(
            phone_number_id=numero.phone_number_id,
            token=numero.token,
            telefono_cliente=telefono_cliente,
            mensaje=respuesta,
        )

        return {"status": "ok", "paso": "PEDIR_SERVICIO"}


    if flujo and flujo.paso == "REPROGRAMAR_FECHA":
        print("ENTRO A REPROGRAMAR_FECHA")

        flujo.fecha = mensaje.strip()
        flujo.paso = "REPROGRAMAR_HORA"
        db.commit()

        respuesta = (
            f"Perfecto. Nueva fecha: {flujo.fecha}.\n\n"
            "🕒 ¿A qué hora deseas reprogramarla?\n\n"
            "Utiliza formato 24 horas:\n"
            "HH:MM\n\n"
            "Ejemplo:\n"
            "15:00"
        )

        conversacion = Conversacion(
            empresa_id=empresa.id,
            telefono=telefono_cliente,
            mensaje=mensaje,
            respuesta=respuesta,
            paso="REPROGRAMAR_HORA",
            servicio_id=flujo.servicio_id,
            nombre=flujo.nombre,
            fecha=flujo.fecha,
            hora=flujo.hora,
        )

        db.add(conversacion)
        db.commit()

        enviar_mensaje_whatsapp(
            phone_number_id=numero.phone_number_id,
            token=numero.token,
            telefono_cliente=telefono_cliente,
            mensaje=respuesta,
        )

        return {"status": "reprogramar_hora"}

    if flujo and flujo.paso == "REPROGRAMAR_HORA":
        print("ENTRO A REPROGRAMAR_HORA")

        nueva_hora = mensaje.strip()

        cita_activa = (
            db.query(Cita)
            .filter(
                Cita.empresa_id == empresa.id,
                Cita.telefono == telefono_cliente,
                Cita.status.in_(["AGENDADA", "CONFIRMADA"]),
            )
            .first()
        )

        if not cita_activa:
            respuesta = "No encontré ninguna cita activa para reprogramar."
        else:
            cita_activa.fecha = flujo.fecha
            cita_activa.hora = nueva_hora
            cita_activa.recordatorio_enviado = False
            db.commit()

            servicio = None

            if cita_activa.servicio_id:
                servicio = (
                    db.query(Servicio)
                    .filter(Servicio.id == cita_activa.servicio_id)
                    .first()
                )

            nombre_servicio = servicio.nombre if servicio else "Servicio no especificado"

            respuesta = (
                "✅ Cita reprogramada correctamente\n\n"
                f"Servicio: {nombre_servicio}\n"
                f"Nombre: {cita_activa.nombre}\n"
                f"Fecha: {cita_activa.fecha}\n"
                f"Hora: {cita_activa.hora}\n\n"
                "Si deseas cancelar tu cita escribe:\n"
                "👉 Cancelar cita\n\n"
                "Si deseas volver a cambiarla escribe:\n"
                "👉 Reprogramar cita"
            )

        db.delete(flujo)
        db.commit()

        enviar_mensaje_whatsapp(
            phone_number_id=numero.phone_number_id,
            token=numero.token,
            telefono_cliente=telefono_cliente,
            mensaje=respuesta,
        )

        return {"status": "cita_reprogramada"}

    historial = obtener_historial_conversacion(
        db=db, empresa_id=empresa.id, telefono_cliente=telefono_cliente
    )

    try:
        respuesta_openai = client.responses.create(
            model="gpt-4.1-mini",
            input=f"""
{empresa.prompt_base}

Responde de forma breve, amable y profesional.
No inventes información que la empresa no haya proporcionado.

Si el cliente quiere agendar una cita, pide los datos necesarios paso a paso:
1. nombre completo
2. día deseado
3. hora deseada
4. confirma la cita

Historial de conversación:
{historial}

Nuevo mensaje del cliente:
{mensaje}
""",
        )

        respuesta = respuesta_openai.output_text

    except Exception as e:
        print(f"ERROR OPENAI: {e}")
        respuesta = (
            "Lo siento, en este momento el asistente no está disponible. "
            "Por favor intenta nuevamente en unos minutos."
        )

    texto_para_cita = f"""
Historial de conversación:
{historial}

Último mensaje del cliente:
{mensaje}

Última respuesta del asistente:
{respuesta}
"""
    cita_existente = None

    try:
        datos_cita = detectar_datos_cita(texto_para_cita)

        if datos_cita.get("completo") is True:
            cita_existente = (
                db.query(Cita)
                .filter(
                    Cita.empresa_id == empresa.id,
                    Cita.telefono == telefono_cliente,
                    Cita.status.in_(["AGENDADA", "CONFIRMADA"]),
                )
                .first()
            )

        if cita_existente:
            respuesta = (
                f"Ya tienes una cita agendada para el "
                f"{cita_existente.fecha} a las {cita_existente.hora}. "
                f"Si deseas cambiarla, escribe: Reprogramar cita. "
                f"Si deseas cancelarla, escribe: Cancelar cita."
            )

        else:
            hora_cita = datetime.strptime(datos_cita["hora"], "%H:%M").time()
            hora_inicio = datetime.strptime(empresa.horario_inicio, "%H:%M").time()
            hora_fin = datetime.strptime(empresa.horario_fin, "%H:%M").time()

            if hora_cita < hora_inicio or hora_cita > hora_fin:
                respuesta = (
                    f"Lo siento, nuestro horario de atención es "
                    f"de {empresa.horario_inicio} a {empresa.horario_fin}. "
                    f"Por favor indícame otro horario."
                )

                enviar_mensaje_whatsapp(
                    phone_number_id=numero.phone_number_id,
                    token=numero.token,
                    telefono_cliente=telefono_cliente,
                    mensaje=respuesta,
                )

                return {"status": "horario_fuera_de_rango"}

            cita = Cita(
                empresa_id=empresa.id,
                nombre=datos_cita.get("nombre"),
                telefono=telefono_cliente,
                fecha=datos_cita.get("fecha"),
                hora=datos_cita.get("hora"),
                status="CONFIRMADA",
            )

            db.add(cita)
            db.commit()
            db.refresh(cita)

            respuesta = (
                f"Perfecto {datos_cita.get('nombre')}, tu cita quedó registrada "
                f"para el {datos_cita.get('fecha')} a las {datos_cita.get('hora')}."
            )
    except Exception as e:
        print(f"ERROR DETECTANDO CITA: {e}")

    conversacion = Conversacion(
        empresa_id=empresa.id,
        telefono=telefono_cliente,
        mensaje=mensaje,
        respuesta=respuesta,
    )

    db.add(conversacion)
    db.commit()
    db.refresh(conversacion)

    meta_response = enviar_mensaje_whatsapp(
        phone_number_id=numero.phone_number_id,
        token=numero.token,
        telefono_cliente=telefono_cliente,
        mensaje=respuesta,
    )

    return {
        "status": "ok",
        "empresa": {"id": empresa.id, "nombre": empresa.nombre},
        "telefono_cliente": telefono_cliente,
        "numero_receptor": numero_receptor,
        "mensaje_recibido": mensaje,
        "respuesta_generada": respuesta,
        "conversacion_id": conversacion.id,
        "meta_response": meta_response,
    }


@app.post("/servicios")
def crear_servicio(
    empresa_id: int,
    nombre: str,
    descripcion: str,
    duracion: int,
    precio: float,
    db: Session = Depends(get_db),
):
    servicio = Servicio(
        empresa_id=empresa_id,
        nombre=nombre,
        descripcion=descripcion,
        duracion=duracion,
        precio=precio,
        activo=True,
    )

    db.add(servicio)
    db.commit()
    db.refresh(servicio)

    return servicio


@app.get("/servicios")
def listar_servicios(db: Session = Depends(get_db)):
    return db.query(Servicio).all()


@app.get("/empresas/{empresa_id}/servicios")
def servicios_empresa(empresa_id: int, db: Session = Depends(get_db)):
    return (
        db.query(Servicio)
        .filter(Servicio.empresa_id == empresa_id, Servicio.activo == True)
        .all()
    )


@app.get("/servicios/{servicio_id}")
def obtener_servicio(servicio_id: int, db: Session = Depends(get_db)):
    servicio = db.query(Servicio).filter(Servicio.id == servicio_id).first()

    if not servicio:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    return servicio


@app.put("/servicios/{servicio_id}")
def actualizar_servicio(
    servicio_id: int,
    nombre: str = None,
    descripcion: str = None,
    duracion: int = None,
    precio: float = None,
    db: Session = Depends(get_db),
):
    servicio = db.query(Servicio).filter(Servicio.id == servicio_id).first()

    if not servicio:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    if nombre:
        servicio.nombre = nombre

    if descripcion:
        servicio.descripcion = descripcion

    if duracion:
        servicio.duracion = duracion

    if precio:
        servicio.precio = precio

    db.commit()
    db.refresh(servicio)

    return servicio


@app.delete("/servicios/{servicio_id}")
def eliminar_servicio(servicio_id: int, db: Session = Depends(get_db)):
    servicio = db.query(Servicio).filter(Servicio.id == servicio_id).first()

    if not servicio:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    servicio.activo = False

    db.commit()

    return {"mensaje": "Servicio desactivado"}


@app.delete("/servicios/pruebas")
def limpiar_servicios(db: Session = Depends(get_db)):
    db.query(Servicio).delete()
    db.commit()

    return {"mensaje": "Todos los servicios eliminados"}


@app.get("/dashboard/resumen")
def dashboard_resumen(db: Session = Depends(get_db)):
    empresas = db.query(Empresa).count()

    citas_agendadas = db.query(Cita).filter(Cita.status == "AGENDADA").count()

    citas_confirmadas = db.query(Cita).filter(Cita.status == "CONFIRMADA").count()

    citas_canceladas = db.query(Cita).filter(Cita.status == "CANCELADA").count()

    return {
        "empresas": empresas,
        "citas_agendadas": citas_agendadas,
        "citas_confirmadas": citas_confirmadas,
        "citas_canceladas": citas_canceladas,
    }


@app.post("/mensaje")
def recibir_mensaje(data: MensajeEntrada, db: Session = Depends(get_db)):
    telefono_cliente = normalizar_telefono(data.telefono)
    numero_receptor = normalizar_telefono(data.numero_receptor)
    mensaje = data.mensaje.strip()

    numero = (
        db.query(NumeroWhatsApp)
        .filter(NumeroWhatsApp.telefono == numero_receptor)
        .first()
    )

    if not numero:
        return {"status": "error", "mensaje": "Número de WhatsApp no registrado"}

    empresa = db.query(Empresa).filter(Empresa.id == numero.empresa_id).first()

    if not empresa:
        return {"status": "error", "mensaje": "Empresa no encontrada"}

    # BLOQUEAR EMPRESAS INACTIVAS
    if empresa.status != "ACTIVA":
        return {"status": "error", "mensaje": "La empresa está inactiva"}

    try:
        respuesta_openai = client.responses.create(
            model="gpt-4.1-mini",
            input=f"""
{empresa.prompt_base}

Cliente:
{mensaje}
""",
        )

        respuesta = respuesta_openai.output_text

    except Exception as e:
        print(f"ERROR OPENAI: {e}")

        respuesta = (
            "Lo siento, en este momento el asistente no está disponible. "
            "Por favor intenta nuevamente más tarde."
        )

    conversacion = Conversacion(
        telefono=telefono_cliente, mensaje=mensaje, respuesta=respuesta
    )

    db.add(conversacion)
    db.commit()
    db.refresh(conversacion)

    return {
        "status": "ok",
        "empresa": {"id": empresa.id, "nombre": empresa.nombre, "giro": empresa.giro},
        "telefono_cliente": telefono_cliente,
        "numero_receptor": numero_receptor,
        "mensaje_recibido": mensaje,
        "respuesta": respuesta,
        "conversacion_id": conversacion.id,
    }

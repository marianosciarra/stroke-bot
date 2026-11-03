# Bot de Telegram - Soporte ACV (Stroke)

Bot de Telegram para triaje y soporte preliminar de ACV. Corre en Vercel
(plan gratuito) por webhook, sin servidor encendido 24/7, y usa la API
gratuita de Gemini para analizar imágenes.

Comandos: /stroke (menú), /nihss.

Módulos:
1. Calculadora NIHSS (15 puntajes, puntaje total y categoría de gravedad).
2. Mismatch DWI / FLAIR (se envían las dos imágenes, de a una).
3. Territorio vascular (arterial con rama / venoso).
4. Volumen de isquemia (estimación ABC/2, baja confiabilidad desde capturas).

Todos los reportes incluyen un descargo de responsabilidad clínico.

## Cómo funciona sin guardar estado

- NIHSS: los puntajes viajan dentro de los botones (callback_data).
- Imágenes: el bot pide la imagen "respondiendo a su mensaje"; ese mensaje
  lleva un marcador `[[...]]` (en el mismatch incluye el file_id de la DWI).
  No borres esa línea del mensaje del bot.
- Seguridad: el webhook exige un secreto de Telegram y el bot solo responde
  a los IDs de `ALLOWED_USER_IDS`.

## Puesta en marcha (todo gratis)

1. Telegram: hablá con @BotFather, `/newbot`, copiá el token.
2. Gemini: creá una API key en https://aistudio.google.com/apikey.
   Revisá el modelo vigente en https://ai.google.dev/gemini-api/docs/models
   y ajustá `GEMINI_MODEL` si hace falta.
3. Vercel: subí esta carpeta a un repo de GitHub e importalo en vercel.com
   (o usá `vercel` desde la terminal). Cargá estas variables de entorno:
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` (una cadena larga al azar),
   `GEMINI_API_KEY`, `GEMINI_MODEL`, `ALLOWED_USER_IDS` (vacío al principio).
4. Registrá el webhook (reemplazá la URL por la de tu proyecto):

       TELEGRAM_BOT_TOKEN=... TELEGRAM_WEBHOOK_SECRET=... \
       python scripts/set_webhook.py https://TU-PROYECTO.vercel.app/api/webhook

5. Escribile `/start` al bot: te va a decir "No autorizado. Tu ID es N".
   Cargá ese N en `ALLOWED_USER_IDS` en Vercel y hacé un redeploy.
6. Probá `/stroke`.

## Privacidad

En el nivel gratuito de Gemini, Google puede usar los datos enviados para
mejorar sus productos. Enviá solo imágenes anonimizadas (sin nombre, DNI ni
fecha de nacimiento). Para uso con datos identificables, pasá a un nivel de
pago o a un modelo local.

## Pruebas

    pip install -r requirements.txt pytest
    pytest

## Siguiente etapa posible

MedGemma 1.5 4B (`google/medgemma-1.5-4b-it`, modelo restringido: hay que
aceptar los términos en Hugging Face) como reemplazo de Gemini en las
imágenes, alojado en un Space o endpoint de Hugging Face. Hoy no se usa
porque la inferencia gratuita de un modelo de 4B no es confiable.

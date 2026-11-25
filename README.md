# Bot de Telegram para operaciones

El bot agrega las operaciones al final de la tabla A:F de **Hoja1** en Google Sheets, con sus encabezados en la fila 4. Usa valores numéricos para USD y el prefijo $ para pesos en las columnas de precio. Cada compra suma unidades en el balance H:L y agrega el instrumento si falta. El máximo de compra se actualiza con precios en USD. Una compra en ARS suma unidades sin modificar ese máximo. Las ventas se registran en A:F.

## Configuración de Google Sheets

1. Habilitá **Google Sheets API** en tu proyecto de Google Cloud. Creá una cuenta de servicio y descargá su clave JSON.
2. Abrí una hoja nativa de Google Sheets y compartila como **Editor** con el correo `client_email` que figura en el JSON.
3. Completá estas dos variables en `.env`. El ID es lo que figura entre `/d/` y `/edit` en el enlace. Pegá el JSON completo en una sola línea, entre comillas simples, conservando los caracteres literales `\n` de la clave.

```dotenv
GOOGLE_SHEETS_SPREADSHEET_ID=ID_DE_TU_HOJA
GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
```

El JSON de arriba es ilustrativo. Usá el archivo real y mantené privado tu `.env`. Usá una hoja de cálculo que ya tenga la pestaña **Hoja1** con la tabla de movimientos.

## Puesta en marcha en PowerShell

1. Creá un bot en Telegram con **@BotFather** y guardá su token.
2. Desde esta carpeta, instalá la dependencia y configurá las variables para esta sesión. Si ya tenés un archivo .env junto a bot.py, el bot lo carga automáticamente. También podés configurar estas variables en PowerShell. Reemplazá los valores de ejemplo por tus datos y mantené las claves privadas.

```powershell
py -m pip install -r requirements.txt
$env:TELEGRAM_BOT_TOKEN = 'TOKEN_DE_BOTFATHER'
$env:TELEGRAM_USER_ID = 'TU_ID_NUMERICO_DE_TELEGRAM'
$env:OPENAI_API_KEY = 'TU_CLAVE_DE_OPENAI'
py bot.py
```

Para averiguar tu ID, enviá un mensaje privado a tu bot antes de iniciarlo y ejecutá este comando en tu PowerShell. Buscá `from.id` en el mensaje que enviaste.

```powershell
(Invoke-RestMethod "https://api.telegram.org/bot$env:TELEGRAM_BOT_TOKEN/getUpdates").result.message.from
```

El bot responde solo al usuario configurado en un chat privado. Dejá PowerShell abierto mientras lo uses y ejecutá una sola instancia.

## Uso

- `/compra PAMP 10 1,90 USD`
- `/venta PAMP 4 2,30 USD`
- Si omitís la moneda, el bot usa USD. También admite ARS y punto decimal.
- Enviá una foto o un PDF con una sola operación. Revisá la fecha, el instrumento, la cantidad, el precio unitario y la moneda antes de enviar `/confirmar`. Usá `/cancelar` para descartarla. Si reiniciás el bot, reenviá el comprobante para generar otra vista previa.
- La lectura envía el comprobante a la API de OpenAI y requiere su clave. Los comandos manuales funcionan sin esa clave.


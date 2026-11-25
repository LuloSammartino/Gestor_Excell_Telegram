from datetime import date
from decimal import Decimal
import json
import os
import re

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials
from requests import RequestException

TAB = "Hoja1"
HEADERS = (
    "MOVIMIENTO", "INSTRUMENTO", "CANTIDAD", "PRECIO C/U: PESOS / DOLARES",
    "PRECIO TOTAL: PESOS / DOLARES", "FECHA",
)
METADATA_KEY = "telegram_operacion"


class SheetsError(Exception):
    pass


class Sheets:
    def __init__(self):
        spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", spreadsheet_id):
            raise SheetsError("Configurá GOOGLE_SHEETS_SPREADSHEET_ID con el ID de la hoja.")
        try:
            info = json.loads(os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON", ""))
            credentials = Credentials.from_service_account_info(
                info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )
        except (ValueError, TypeError, AttributeError, GoogleAuthError):
            raise SheetsError("Configurá GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON con el JSON de la cuenta de servicio.") from None
        self.session = AuthorizedSession(credentials)
        self.url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"

    def request(self, method, path="", **options):
        try:
            response = self.session.request(method, self.url + path, timeout=20, **options)
            response.raise_for_status()
            return response.json()
        except (GoogleAuthError, RequestException) as error:
            response = getattr(error, "response", None)
            if response is not None and response.status_code in (403, 404):
                raise SheetsError("Google Sheets no está accesible. Revisá el ID, la API y el permiso de Editor.") from None
            raise SheetsError("Google Sheets no confirmó el guardado. Revisá la hoja antes de reenviar.") from None

    def record(self, update_id, day, trade):
        matches = self.request("POST", "/developerMetadata:search", json={
            "dataFilters": [{"developerMetadataLookup": {
                "metadataKey": METADATA_KEY,
                "metadataValue": str(update_id),
            }}],
        })
        if matches.get("matchedDeveloperMetadata"):
            return
        data = self.request("GET", params={"fields": "sheets(properties(sheetId,title,gridProperties(rowCount)))"})
        tab = next((item["properties"] for item in data.get("sheets", [])
                    if item["properties"]["title"] == TAB), None)
        if tab is None:
            raise SheetsError("No encontré la pestaña Hoja1.")

        rows = self.request("GET", f"/values/{TAB}!A4:F", params={"valueRenderOption": "FORMULA"}).get("values", [])
        if not rows or tuple(str(value).strip().upper() for value in rows[0]) != HEADERS:
            raise SheetsError("Los encabezados de Hoja1 cambiaron. Revisá A4:F4 antes de guardar.")

        # shortcut: ejecutar una sola instancia del bot, coordinar escrituras si se agregan más.
        row = len(rows) + 3
        sheet_id = tab["sheetId"]
        destination = {"sheetId": sheet_id, "startRowIndex": row, "endRowIndex": row + 1,
                       "startColumnIndex": 0, "endColumnIndex": 6}
        side, ticker, quantity, price, currency = trade
        balance_updates = []
        balance_row = row
        if side == "compra":
            balance_row, balance_updates = self.purchase_balance(sheet_id, ticker, quantity, price, currency)

        requests = []
        extra_rows = max(row, balance_row) + 1 - tab["gridProperties"]["rowCount"]
        if extra_rows > 0:
            requests.append({"appendDimension": {"sheetId": sheet_id, "dimension": "ROWS", "length": extra_rows}})
        if row > 4:
            source = dict(destination, startRowIndex=row - 1, endRowIndex=row)
            requests.append({"copyPaste": {"source": source, "destination": destination,
                                           "pasteType": "PASTE_FORMAT"}})

        total = quantity * price
        if currency == "ARS":
            price, total = (f"${amount:f}".replace(".", ",") for amount in (price, total))
        values = (side.capitalize(), ticker, quantity, price, total, (day - date(1899, 12, 30)).days)
        cells = [{"userEnteredValue": {"stringValue": value} if isinstance(value, str)
                  else {"numberValue": float(value)}} for value in values]
        cells[5]["userEnteredFormat"] = {"numberFormat": {"type": "DATE", "pattern": "dd/mm/yyyy"}}
        requests.extend([
            {"updateCells": {"range": destination, "rows": [{"values": cells}], "fields": "userEnteredValue"}},
            {"updateCells": {
                "start": {"sheetId": sheet_id, "rowIndex": row, "columnIndex": 5},
                "rows": [{"values": [cells[5]]}], "fields": "userEnteredFormat.numberFormat",
            }},
            {"createDeveloperMetadata": {"developerMetadata": {
                "metadataKey": METADATA_KEY,
                "metadataValue": str(update_id),
                "location": {"dimensionRange": {
                    "sheetId": sheet_id, "dimension": "ROWS", "startIndex": row, "endIndex": row + 1,
                }},
                "visibility": "DOCUMENT",
            }}},
        ])
        self.request("POST", ":batchUpdate", json={"requests": requests + balance_updates})


    def purchase_balance(self, sheet_id, ticker, quantity, price, currency):
        rows = self.request("GET", f"/values/{TAB}!H4:L", params={
            "valueRenderOption": "UNFORMATTED_VALUE",
        }).get("values", [])
        if not rows or rows[0] != ["INSTRUMENTO", "CANTIDAD", "TOTAL USD", "C/U USD", "MAX COMPRA"]:
            raise SheetsError("Los encabezados del balance de Hoja1 cambiaron. Revisá H4:L4.")

        matches = [(index, values) for index, values in enumerate(rows[1:], 4)
                   if values and str(values[0]).strip().upper() == ticker]
        if len(matches) > 1:
            raise SheetsError(f"{ticker} figura más de una vez en el balance de Hoja1.")

        def value_update(row, column, value):
            return {"updateCells": {
                "start": {"sheetId": sheet_id, "rowIndex": row, "columnIndex": column},
                "rows": [{"values": [{"userEnteredValue": value}]}],
                "fields": "userEnteredValue",
            }}

        updates = []
        if matches:
            row, previous = matches[0]
        else:
            row = next((index for index, values in enumerate(rows[1:], 4)
                        if all(not str(value).strip() for value in values)), len(rows) + 3)
            previous = []
            updates.append(value_update(row, 7, {"stringValue": ticker}))

        def number_at(index):
            raw = previous[index] if len(previous) > index else ""
            try:
                value = Decimal(str(raw).strip().replace(",", ".") or "0")
                if value.is_finite():
                    return value
            except ArithmeticError:
                pass
            raise SheetsError(f"Revisá la cantidad o el máximo de {ticker} en el balance de Hoja1.")

        updates.append(value_update(row, 8, {"numberValue": float(number_at(1) + quantity)}))
        if currency == "USD" and price > number_at(4):
            updates.append(value_update(row, 11, {"numberValue": float(price)}))
        return row, updates

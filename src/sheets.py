from __future__ import annotations

import os
from dataclasses import dataclass

import gspread
from google.oauth2.service_account import Credentials


@dataclass
class SheetsConfig:
    spreadsheet_id: str
    sheet_name: str
    credentials_file: str


class SheetsClient:
    def __init__(self, cfg: SheetsConfig) -> None:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
        ]
        creds = Credentials.from_service_account_file(cfg.credentials_file, scopes=scopes)
        gc = gspread.authorize(creds)
        self.ws = gc.open_by_key(cfg.spreadsheet_id).worksheet(cfg.sheet_name)

    @staticmethod
    def from_env() -> "SheetsClient":
        sheet_id = os.getenv("SPREADSHEET_ID")
        sheet_name = os.getenv("SHEET_NAME", "Sheet1")
        creds_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not sheet_id or not creds_file:
            raise RuntimeError("Missing SPREADSHEET_ID or GOOGLE_APPLICATION_CREDENTIALS")
        return SheetsClient(SheetsConfig(sheet_id, sheet_name, creds_file))

    def ensure_header(self, fields: list[str]) -> list[str]:
        existing = self.ws.row_values(1)
        if not existing:
            self.ws.update("A1", [fields])
            return fields

        merged = list(existing)
        for field in fields:
            if field not in merged:
                merged.append(field)

        if merged != existing:
            self.ws.update("A1", [merged])

        return merged

    def append_row(self, header: list[str], data: dict) -> None:
        row = [data.get(field, "") for field in header]
        self.ws.append_row(row, value_input_option="RAW")

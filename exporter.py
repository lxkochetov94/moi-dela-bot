"""Two-sheet plain Excel, safe from accidental formula execution."""
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

HEAD = ["Тип", "Задача", "Приоритет", "Статус", "Срок", "Напоминания", "Доп. информация", "Создано", "Сделано"]
PRIORITY = {"red":"Срочно", "yellow":"Важно", "green":"Не горит"}
STATUS = {"not_started":"Не начато", "in_progress":"В работе", "done":"Сделано"}


def safe(value):
    if value is None:
        return ""
    value = str(value)
    # Prevent spreadsheet formula injection in user-provided task names or notes.
    if value and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def excel(tasks, zone="Europe/Moscow"):
    tz = ZoneInfo(zone)
    book = Workbook()
    work = book.active
    work.title = "Работа"
    home = book.create_sheet("Личное")
    sheets = {"work": work, "personal": home}
    for sheet in sheets.values():
        sheet.append(HEAD)
        sheet.freeze_panes = "A2"
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="DCE7F3")
        widths = [13,40,17,17,21,35,60,21,21]
        for i,w in enumerate(widths,1): sheet.column_dimensions[get_column_letter(i)].width=w
    for task in sorted((t for t in tasks if not t.get("deleted")), key=lambda t:(t.get("created",0), t["id"])):
        sheet=sheets.get(task.get("kind"),home)
        fmt=lambda stamp: datetime.fromtimestamp(stamp,tz).strftime("%d.%m.%Y %H:%M") if stamp else ""
        notes="\n".join(x["text"] for x in task.get("notes",[]))
        reminders="; ".join(fmt(x["at"]) for x in task.get("reminders",[]))
        sheet.append(["Работа" if task.get("kind")=="work" else "Личное",
                      safe(task.get("title")), PRIORITY.get(task.get("priority"),""),
                      STATUS.get(task.get("status"),""),fmt(task.get("deadline")),
                      reminders,safe(notes),fmt(task.get("created")),fmt(task.get("completed"))])
        color={"red":"FCE8E6", "yellow":"FFF2CC", "green":"E2F0D9"}.get(task.get("priority"))
        if color: sheet.cell(sheet.max_row, 3).fill=PatternFill("solid",fgColor=color)
    for sheet in sheets.values():
        sheet.auto_filter.ref=f"A1:I{sheet.max_row}"
    stream=BytesIO();book.save(stream);return stream.getvalue()

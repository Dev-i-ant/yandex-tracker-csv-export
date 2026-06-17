#!/usr/bin/env python3
"""
Отчёт по задачам Яндекс Трекера в CSV.

Получает список задач по языку запросов, для каждой — историю смены статусов
и выгружает даты первого перехода в заданные статусы.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

import requests
from dotenv import load_dotenv

API_BASE = "https://api.tracker.yandex.net/v3"

CSV_COLUMNS = [
    "Ключ",
    "Название",
    "Дата создания",
    "Дата перехода в В работе",
    "Дата перехода в Демонстрация заказчику",
    "Дедлайн",
]

DEFAULT_STATUS_IN_PROGRESS = "В работе"
DEFAULT_STATUS_DEMO = "Демонстрация заказчику"


@dataclass
class ReportConfig:
    token: str
    org_id: str | None
    cloud_org_id: str | None
    queue: str | None
    project: str | None
    date_from: str
    date_to: str
    status_in_progress: str
    status_demo: str
    output_path: str
    per_page: int
    request_delay: float


class TrackerClient:
    def __init__(self, config: ReportConfig) -> None:
        self.config = config
        self.session = requests.Session()
        headers: dict[str, str] = {
            "Authorization": f"OAuth {config.token}",
            "Content-Type": "application/json",
        }
        if config.cloud_org_id:
            headers["X-Cloud-Org-ID"] = config.cloud_org_id
            self.org_header = "X-Cloud-Org-ID"
        elif config.org_id:
            headers["X-Org-ID"] = config.org_id
            self.org_header = "X-Org-ID"
        else:
            raise ValueError("Укажите TRACKER_ORG_ID или TRACKER_CLOUD_ORG_ID")
        self.session.headers.update(headers)

    def _raise_for_status(self, response: requests.Response, method: str) -> None:
        if response.ok:
            return

        body = response.text.strip()
        try:
            payload = response.json()
            if isinstance(payload, dict):
                body = payload.get("errorMessage") or payload.get("message") or body
        except ValueError:
            pass

        hints: list[str] = []
        if response.status_code == 401:
            hints.append("Проверьте TRACKER_OAUTH_TOKEN и права tracker:read у OAuth-приложения")
        elif response.status_code == 403:
            hints.append(
                "Токен принят, но нет прав. Проверьте:\n"
                f"  1. Правильный заголовок: сейчас {self.org_header}\n"
                "     Yandex 360 → TRACKER_ORG_ID + X-Org-ID\n"
                "     Yandex Cloud → TRACKER_CLOUD_ORG_ID + X-Cloud-Org-ID\n"
                "  2. В .env не заданы оба ID одновременно (приоритет у Cloud)\n"
                "  3. У аккаунта токена есть доступ к очереди в интерфейсе Трекера"
            )

        message = (
            f"HTTP {response.status_code} {response.reason}\n"
            f"{method} {response.url}\n"
            f"Ответ API: {body or '(пусто)'}"
        )
        if hints:
            message += "\n\n" + "\n".join(hints)
        raise RuntimeError(message)

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        max_retries: int = 5,
    ) -> requests.Response:
        for attempt in range(max_retries):
            response = self.session.request(method, url, params=params, json=json, timeout=60)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 2 ** attempt))
                print(
                    f"  Лимит API (429), пауза {retry_after} с...",
                    file=sys.stderr,
                )
                time.sleep(retry_after)
                continue

            if response.status_code >= 500 and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue

            self._raise_for_status(response, method)
            if self.config.request_delay > 0:
                time.sleep(self.config.request_delay)
            return response

        self._raise_for_status(response, method)
        return response

    def verify_access(self) -> dict[str, Any]:
        response = self._request("GET", f"{API_BASE}/myself")
        return response.json()

    def search_issues(self, query: str) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        page = 1

        while True:
            url = f"{API_BASE}/issues/_search"
            params = {"perPage": self.config.per_page, "page": page}
            response = self._request("POST", url, params=params, json={"query": query})
            batch = response.json()

            if not batch:
                break

            issues.extend(batch)
            total_pages = int(response.headers.get("X-Total-Pages", page))
            total_count = response.headers.get("X-Total-Count", "?")
            print(
                f"Загружено задач: {len(issues)} / {total_count} (страница {page}/{total_pages})",
                file=sys.stderr,
            )

            if page >= total_pages:
                break
            page += 1

        return issues

    def get_status_changelog(self, issue_key: str) -> Iterable[dict[str, Any]]:
        url = f"{API_BASE}/issues/{issue_key}/changelog"
        params: dict[str, Any] = {
            "perPage": 100,
            "field": "status",
            "type": "IssueWorkflow",
        }

        while True:
            response = self._request("GET", url, params=params)
            records = response.json()
            yield from records

            next_link = response.links.get("next", {}).get("url")
            if not next_link:
                break
            url = next_link
            params = None


def build_query(config: ReportConfig) -> str:
    parts: list[str] = []

    if config.queue:
        parts.append(f"Queue: {config.queue}")
    if config.project:
        parts.append(f'Project: "{config.project}"')

    if not parts:
        raise ValueError("Укажите очередь (--queue) и/или проект (--project)")

    parts.append(f'Created: "{config.date_from}".."{config.date_to}"')
    parts.append('"Sort By": Created ASC')
    return "\n".join(parts)


def format_tracker_date(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return value[:10] if len(value) >= 10 else value


def find_first_status_dates(
    changelog: Iterable[dict[str, Any]],
    status_in_progress: str,
    status_demo: str,
) -> tuple[str | None, str | None]:
    in_progress_date: str | None = None
    demo_date: str | None = None

    for record in changelog:
        updated_at = record.get("updatedAt")
        for field in record.get("fields", []):
            if field.get("field", {}).get("id") != "status":
                continue

            to_value = field.get("to")
            if not isinstance(to_value, dict):
                continue

            display = to_value.get("display", "")
            if display == status_in_progress and in_progress_date is None:
                in_progress_date = updated_at
            if display == status_demo and demo_date is None:
                demo_date = updated_at

        if in_progress_date and demo_date:
            break

    return in_progress_date, demo_date


def issue_to_row(
    issue: dict[str, Any],
    client: TrackerClient,
    status_in_progress: str,
    status_demo: str,
) -> dict[str, str]:
    issue_key = issue["key"]
    changelog = client.get_status_changelog(issue_key)
    in_progress_date, demo_date = find_first_status_dates(
        changelog,
        status_in_progress,
        status_demo,
    )

    return {
        "Ключ": issue_key,
        "Название": issue.get("summary", ""),
        "Дата создания": format_tracker_date(issue.get("createdAt")),
        "Дата перехода в В работе": format_tracker_date(in_progress_date),
        "Дата перехода в Демонстрация заказчику": format_tracker_date(demo_date),
        "Дедлайн": format_tracker_date(issue.get("deadline")),
    }


def write_csv(rows: list[dict[str, str]], output_path: str) -> None:
    with open(output_path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Формирование CSV-отчёта по задачам Яндекс Трекера",
    )
    parser.add_argument(
        "--queue",
        default=os.getenv("TRACKER_QUEUE"),
        help="Ключ очереди (переменная TRACKER_QUEUE)",
    )
    parser.add_argument(
        "--project",
        default=os.getenv("TRACKER_PROJECT"),
        help="Название проекта в Трекере (переменная TRACKER_PROJECT)",
    )
    parser.add_argument(
        "--date-from",
        default="2025-07-01",
        help="Начало периода по дате создания (по умолчанию: 2025-07-01)",
    )
    parser.add_argument(
        "--date-to",
        default="2026-06-17",
        help="Конец периода по дате создания (по умолчанию: 2026-06-17)",
    )
    parser.add_argument(
        "--status-in-progress",
        default=DEFAULT_STATUS_IN_PROGRESS,
        help=f'Статус «в работе» (по умолчанию: «{DEFAULT_STATUS_IN_PROGRESS}»)',
    )
    parser.add_argument(
        "--status-demo",
        default=DEFAULT_STATUS_DEMO,
        help=f'Статус «демонстрация» (по умолчанию: «{DEFAULT_STATUS_DEMO}»)',
    )
    parser.add_argument(
        "-o",
        "--output",
        default="tracker_report.csv",
        help="Путь к выходному CSV (по умолчанию: tracker_report.csv)",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=100,
        help="Задач на страницу при поиске (по умолчанию: 100)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Проверить токен и ID организации (GET /v3/myself)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="Пауза между запросами к API в секундах (по умолчанию: 0.1)",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()

    token = os.getenv("TRACKER_OAUTH_TOKEN")
    if not token:
        print("Ошибка: задайте TRACKER_OAUTH_TOKEN в .env или окружении", file=sys.stderr)
        return 1

    config = ReportConfig(
        token=token,
        org_id=os.getenv("TRACKER_ORG_ID"),
        cloud_org_id=os.getenv("TRACKER_CLOUD_ORG_ID"),
        queue=args.queue,
        project=args.project,
        date_from=args.date_from,
        date_to=args.date_to,
        status_in_progress=args.status_in_progress,
        status_demo=args.status_demo,
        output_path=args.output,
        per_page=args.per_page,
        request_delay=args.delay,
    )

    try:
        query = build_query(config)
    except ValueError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    client = TrackerClient(config)

    try:
        user = client.verify_access()
        print(
            f"Авторизация OK: {user.get('display', '?')} "
            f"({user.get('login', user.get('uid', '?'))})",
            file=sys.stderr,
        )
        print(f"Заголовок организации: {client.org_header}", file=sys.stderr)
    except RuntimeError as exc:
        print(f"Ошибка доступа к API:\n{exc}", file=sys.stderr)
        return 1

    if args.check:
        print("Проверка пройдена. Запустите без --check для формирования отчёта.")
        return 0

    print("Запрос к Трекеру:", file=sys.stderr)
    print(query, file=sys.stderr)
    print(file=sys.stderr)

    try:
        issues = client.search_issues(query)
    except RuntimeError as exc:
        print(f"Ошибка поиска задач:\n{exc}", file=sys.stderr)
        return 1

    if not issues:
        print("Задачи по фильтру не найдены.", file=sys.stderr)
        write_csv([], config.output_path)
        print(f"Создан пустой файл: {config.output_path}")
        return 0

    rows: list[dict[str, str]] = []
    for index, issue in enumerate(issues, start=1):
        issue_key = issue["key"]
        print(f"[{index}/{len(issues)}] {issue_key}", file=sys.stderr)
        rows.append(
            issue_to_row(
                issue,
                client,
                config.status_in_progress,
                config.status_demo,
            )
        )

    write_csv(rows, config.output_path)
    print(f"Готово: {config.output_path} ({len(rows)} задач)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

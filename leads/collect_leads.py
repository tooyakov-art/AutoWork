#!/usr/bin/env python3
"""Сбор бизнес-лидов с телефонами из каталога 2ГИС.

Пример:
    python3 leads/collect_leads.py --city Алматы --query автосервис --query "салон красоты" --pages 10

Результат: leads/out/<город>.csv (все поля) и leads/out/<город>_whatsapp.txt (только номера, по одному в строке).
Ключ API: переменная окружения DGIS_KEY. Бесплатный ключ выдают на https://dev.2gis.com/.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

API = "https://catalog.api.2gis.com"
FIELDS = "items.contact_groups,items.rubrics,items.reviews,items.point,items.org"
UA = "AutoWork-leads/0.1"


def get(url: str, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    return {}


def find_region(city: str, key: str) -> int:
    q = urllib.parse.quote(city)
    d = get(f"{API}/2.0/region/search?q={q}&key={key}")
    items = d.get("result", {}).get("items") or []
    if not items:
        sys.exit(f"Город не найден в 2ГИС: {city}")
    return int(items[0]["id"])


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    return "+" + digits if digits else ""


def is_mobile_kz_ru(phone: str) -> bool:
    """+77xx — мобильные Казахстана, +79xx — мобильные России. Стационарные в WhatsApp обычно нет."""
    return phone.startswith("+77") or phone.startswith("+79")


def clean_url(v: str) -> str:
    """2ГИС оборачивает сайты в редирект link.2gis.ru/...?http://site — берём реальный адрес."""
    if "link.2gis.ru" in v and "?" in v:
        return v.split("?", 1)[1]
    return v


def parse_item(item: dict, query: str) -> dict:
    phones, emails, sites, socials, wa_numbers = [], [], [], [], []
    for g in item.get("contact_groups") or []:
        for c in g.get("contacts") or []:
            t = c.get("type")
            v = c.get("value") or c.get("text") or ""
            if t == "phone":
                p = normalize_phone(v)
                if p and p not in phones:
                    phones.append(p)
            elif t == "email":
                emails.append(v)
            elif t == "website":
                sites.append(clean_url(v))
            elif t == "whatsapp":
                m = re.search(r"wa\.me/(\d+)", v)
                if m:
                    wa_numbers.append(normalize_phone(m.group(1)))
                socials.append("whatsapp:" + v.split("?")[0])
            elif t in ("instagram", "telegram", "vkontakte", "facebook"):
                socials.append(f"{t}:{v}")
    reviews = item.get("reviews") or {}
    rubrics = ", ".join(r.get("name", "") for r in item.get("rubrics") or [])
    point = item.get("point") or {}
    mobile = [p for p in phones if is_mobile_kz_ru(p)]
    wa = wa_numbers[0] if wa_numbers else (mobile[0] if mobile else "")
    return {
        "query": query,
        "name": item.get("name", ""),
        "rubrics": rubrics,
        "address": item.get("address_name", ""),
        "phones": " ".join(phones),
        "whatsapp_candidate": wa,
        "whatsapp_confirmed": "yes" if wa_numbers else "",
        "email": " ".join(emails),
        "website": " ".join(sites),
        "socials": " ".join(socials),
        "rating": reviews.get("general_rating", ""),
        "review_count": reviews.get("general_review_count", ""),
        "lat": point.get("lat", ""),
        "lon": point.get("lon", ""),
        "id": item.get("id", ""),
    }


def collect(region_id: int, query: str, key: str, pages: int, delay: float) -> list[dict]:
    rows = []
    q = urllib.parse.quote(query)
    for page in range(1, pages + 1):
        url = (f"{API}/3.0/items?q={q}&region_id={region_id}&page={page}&page_size=50"
               f"&fields={FIELDS}&key={key}")
        d = get(url)
        code = d.get("meta", {}).get("code")
        if code != 200:
            print(f"  [{query}] стр.{page}: {d.get('meta', {}).get('error')}", file=sys.stderr)
            break
        items = d.get("result", {}).get("items") or []
        if not items:
            break
        rows.extend(parse_item(i, query) for i in items)
        print(f"  [{query}] стр.{page}: +{len(items)} (всего в 2ГИС: {d['result'].get('total')})")
        time.sleep(delay)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--city", required=True, help="Город, как в 2ГИС (Алматы, Москва, Астана...)")
    ap.add_argument("--query", action="append", required=True, help="Ниша. Можно указать несколько раз.")
    ap.add_argument("--pages", type=int, default=5, help="Страниц по 50 на каждую нишу (по умолчанию 5)")
    ap.add_argument("--delay", type=float, default=0.5, help="Пауза между запросами, сек")
    ap.add_argument("--no-website-only", action="store_true", help="Оставить только тех, у кого нет сайта")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "out"))
    args = ap.parse_args()

    key = os.environ.get("DGIS_KEY")
    if not key:
        sys.exit("Нужен ключ 2ГИС: export DGIS_KEY=... (бесплатно на https://dev.2gis.com/)")

    region_id = find_region(args.city, key)
    print(f"Город {args.city}: region_id={region_id}")

    rows: list[dict] = []
    for q in args.query:
        rows.extend(collect(region_id, q, key, args.pages, args.delay))

    # Дедупликация по id организации и по номеру
    seen_ids, seen_phones, uniq = set(), set(), []
    for r in rows:
        if r["id"] in seen_ids or not r["phones"]:
            continue
        if args.no_website_only and r["website"]:
            continue
        first = r["phones"].split()[0]
        if first in seen_phones:
            continue
        seen_ids.add(r["id"])
        seen_phones.add(first)
        uniq.append(r)

    os.makedirs(args.out, exist_ok=True)
    slug = re.sub(r"\W+", "_", args.city.lower())
    csv_path = os.path.join(args.out, f"{slug}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(uniq[0].keys()) if uniq else ["name"], delimiter=";")
        w.writeheader()
        w.writerows(uniq)

    uniq.sort(key=lambda r: (r["whatsapp_confirmed"] != "yes", -(float(r["review_count"] or 0))))
    wa = [r["whatsapp_candidate"] for r in uniq if r["whatsapp_candidate"]]
    wa_path = os.path.join(args.out, f"{slug}_whatsapp.txt")
    with open(wa_path, "w", encoding="utf-8") as f:
        f.write("\n".join(wa) + "\n")

    confirmed = sum(1 for r in uniq if r["whatsapp_confirmed"])
    print(f"\nСобрано: {len(rows)} записей, уникальных с телефоном: {len(uniq)}, "
          f"номеров для WhatsApp: {len(wa)} (из них подтверждённых wa.me: {confirmed})")
    print(f"CSV: {csv_path}\nНомера: {wa_path}")


if __name__ == "__main__":
    main()

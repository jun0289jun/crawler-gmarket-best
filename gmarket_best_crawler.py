from __future__ import annotations

import argparse
import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

BEST_URL = "https://www.gmarket.co.kr/n/best"
DEFAULT_OUT_DIR = Path("output")
DEFAULT_MAX_ITEMS = 200

RED_PRICE_RGB = "rgb(218, 18, 13)"  # #DA120D
BLACK_PRICE_RGB = "rgb(66, 66, 66)"  # #424242


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/Item") or url.startswith("/item"):
        return "https://item.gmarket.co.kr" + url
    if url.startswith("/"):
        return "https://www.gmarket.co.kr" + url
    return url


def extract_goodscode(url: str) -> str:
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "goodscode" in qs and qs["goodscode"]:
            return qs["goodscode"][0]
    except Exception:
        return ""
    m = re.search(r"goodscode=(\d+)", url, flags=re.I)
    if m:
        return m.group(1)
    m = re.search(r"/product/(\d+)", url)
    return m.group(1) if m else ""


def text_from_selector(root: Any, selector: str) -> str:
    node = root.select_one(selector)
    return normalize_space(node.get_text(" ", strip=True)) if node else ""


def price_number(value: str) -> str:
    m = re.search(r"([0-9][0-9,]*)\s*원?", value or "")
    return m.group(1).replace(",", "") if m else ""


def percent_number(value: str) -> str:
    m = re.search(r"(\d+)\s*%", value or "")
    return m.group(1) if m else ""


def fallback_parse_text(card_text: str) -> dict[str, str]:
    data = {
        "discount_rate_percent": "",
        "original_price_krw": "",
        "sale_price_krw": "",
        "coupon_applied_price_krw": "",
        "shipping_info": "",
        "fulfillment_info": "",
        "arrival_info": "",
    }
    if m := re.search(r"할인율\s*(\d+)\s*%", card_text):
        data["discount_rate_percent"] = m.group(1)
    if m := re.search(r"원가\s*([0-9,]+)\s*원", card_text):
        data["original_price_krw"] = m.group(1).replace(",", "")
    if m := re.search(r"판매가\s*([0-9,]+)\s*원", card_text):
        data["sale_price_krw"] = m.group(1).replace(",", "")
    if m := re.search(r"쿠폰적용가\s*([0-9,]+)\s*원", card_text):
        data["coupon_applied_price_krw"] = m.group(1).replace(",", "")
    if "무료배송" in card_text:
        data["shipping_info"] = "무료배송"
    elif m := re.search(r"배송비\s*([0-9,]+)\s*원", card_text):
        data["shipping_info"] = f"배송비 {m.group(1)}원"
    if "풀필먼트 스타배송" in card_text:
        data["fulfillment_info"] = "풀필먼트 스타배송"
    elif "스타배송" in card_text:
        data["fulfillment_info"] = "스타배송"
    if m := re.search(r"((?:내일|\d+/\d+)\([^)]*\)\s*도착보장)", card_text):
        data["arrival_info"] = normalize_space(m.group(1))
    return data


def parse_next_items(soup: BeautifulSoup) -> dict[str, dict[str, Any]]:
    script = soup.select_one("script#__NEXT_DATA__")
    if not script or not script.string:
        return {}
    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        return {}

    def walk(obj: Any) -> list[dict[str, Any]] | None:
        if isinstance(obj, dict):
            if "items" in obj and isinstance(obj["items"], list) and obj["items"]:
                first = obj["items"][0]
                if isinstance(first, dict) and ("goodsCode" in first or "goodsName" in first):
                    return obj["items"]
            for value in obj.values():
                found = walk(value)
                if found is not None:
                    return found
        elif isinstance(obj, list):
            for value in obj:
                found = walk(value)
                if found is not None:
                    return found
        return None

    items = walk(data) or []
    return {str(item.get("goodsCode", "")).strip(): item for item in items if item.get("goodsCode")}


def normalized_color(node: Any) -> str:
    color = node.get("data-computed-color", "") or node.get("style", "")
    color = color.replace(" ", "").lower()
    if "#da120d" in color or "rgb(218,18,13)" in color:
        return "red"
    if "#424242" in color or "rgb(66,66,66)" in color:
        return "black"
    return ""


def extract_final_price_from_dom(li: Any, parsed: dict[str, str]) -> tuple[str, str, str]:
    """Return final price, coupon-applied price, and extraction note.

    최종가격은 사용자 요구사항에 따라 `.box__price-seller span.text.text__value`에서
    빨간색 `#DA120D` 가격을 최우선으로 사용하고, 빨간색 가격이 없으면 검정색
    `#424242` 가격을 사용한다. Playwright가 각 가격 노드에 `data-computed-color`를
    추가하므로 CSS 클래스명이 바뀌어도 실제 렌더링 색상 기준으로 판별한다.
    """
    price_area = li.select_one(".box__item-price") or li
    coupon_applied_price = parsed.get("coupon_applied_price_krw", "")

    for node in price_area.select(
        ".box__price-coupon, .box__price-couponapply, .box__price-coupon-apply, "
        ".box__price-original, .box__coupon-price"
    ):
        txt = normalize_space(node.get_text(" ", strip=True))
        if "쿠폰" in txt:
            coupon_applied_price = price_number(txt) or coupon_applied_price

    final_value_nodes = price_area.select(".box__price-seller span.text.text__value")
    if final_value_nodes:
        red_prices: list[str] = []
        black_prices: list[str] = []
        other_prices: list[str] = []
        for node in final_value_nodes:
            value = price_number(normalize_space(node.get_text(" ", strip=True)))
            if not value:
                continue
            color = normalized_color(node)
            if color == "red":
                red_prices.append(value)
            elif color == "black":
                black_prices.append(value)
            else:
                other_prices.append(value)

        if red_prices:
            return red_prices[-1], coupon_applied_price, "pc_dom:red:#DA120D .box__price-seller span.text.text__value"
        if black_prices:
            return black_prices[-1], coupon_applied_price, "pc_dom:black:#424242 .box__price-seller span.text.text__value"
        if other_prices:
            return other_prices[-1], coupon_applied_price, "pc_dom:unknown_color .box__price-seller span.text.text__value"

    value_nodes = [
        node
        for node in price_area.select("span.text.text__value")
        if not (node.find_parent(class_="box__discount") or node.find_parent(class_="box__price-original"))
    ]
    if value_nodes:
        final_price = price_number(normalize_space(value_nodes[-1].get_text(" ", strip=True)))
        if final_price:
            return final_price, coupon_applied_price, "pc_dom:fallback span.text.text__value"

    return parsed.get("sale_price_krw", ""), coupon_applied_price, "fallback:sale_price_text"


def fetch_rendered_html(
    url: str,
    max_items: int,
    timeout_ms: int,
    headless: bool,
    browser_executable_path: str,
) -> str:
    with sync_playwright() as p:
        launch_options: dict[str, Any] = {
            "headless": headless,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        }
        if browser_executable_path:
            launch_options["executable_path"] = browser_executable_path
        browser = p.chromium.launch(**launch_options)
        context = browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 1800},
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_selector("li.list-item", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            page.wait_for_load_state("networkidle", timeout=timeout_ms)

        body_text = page.locator("body").inner_text(timeout=5000)
        if "봇 확인" in body_text or "간단한 확인 안내" in body_text:
            raise RuntimeError(
                "G마켓이 현재 브라우저 실행 방식을 봇으로 판별했습니다. "
                "GitHub Actions에서는 시스템 Chrome/Chromium을 BROWSER_EXECUTABLE_PATH로 지정하고 "
                "xvfb-run과 --headed 옵션으로 실행하세요."
            )

        previous_count = -1
        stable_rounds = 0
        for _ in range(30):
            count = page.locator("li.list-item").count()
            if count >= max_items:
                break
            if count == previous_count:
                stable_rounds += 1
            else:
                stable_rounds = 0
                previous_count = count
            if stable_rounds >= 5:
                break
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(500)

        page.evaluate(
            """
            () => {
              document.querySelectorAll('.box__price-seller span.text.text__value').forEach((node) => {
                node.setAttribute('data-computed-color', window.getComputedStyle(node).color);
              });
            }
            """
        )
        html = page.content()
        context.close()
        browser.close()
        return html


def parse_products(html: str, max_items: int) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    next_items = parse_next_items(soup)

    rows: list[dict[str, str]] = []
    seen_goodscode: set[str] = set()

    for li in soup.select("li.list-item"):
        a = li.select_one('a.link[href*="goodscode="]') or li.select_one('a[href*="goodscode="]')
        if not a:
            continue

        link = normalize_url(a.get("href", ""))
        goodscode = extract_goodscode(link)
        if goodscode and goodscode in seen_goodscode:
            continue
        if goodscode:
            seen_goodscode.add(goodscode)

        rank_text = text_from_selector(li, ".box__rank") or text_from_selector(li, ".rank")
        if not rank_text:
            img = li.select_one("img.image")
            img_alt = img.get("alt", "") if img else ""
            rank_text = img_alt.replace("위", "")
        if not rank_text:
            m = re.match(r"\s*(\d{1,3})\b", normalize_space(a.get_text(" ", strip=True)))
            rank_text = m.group(1) if m else ""
        if not str(rank_text).isdigit():
            continue
        rank = int(rank_text)
        if rank > max_items:
            continue

        product_name = (
            text_from_selector(li, ".text__item")
            or text_from_selector(li, ".box__item-title")
            or text_from_selector(li, ".itemname")
        )
        whole_text = normalize_space(a.get_text(" ", strip=True))
        parsed = fallback_parse_text(whole_text)
        if not product_name:
            tmp = re.sub(r"^\s*\d{1,3}\s+", "", whole_text)
            tmp = re.split(r"\s+할인율\s+|\s+원가\s+|\s+판매가\s+|\s+쿠폰적용가\s+", tmp, maxsplit=1)[0]
            product_name = normalize_space(tmp)

        sale_price_text = (
            text_from_selector(li, ".box__price-seller span.text.text__value")
            or text_from_selector(li, ".box__price-seller strong")
            or text_from_selector(li, ".box__price-seller")
        )
        original_price_text = text_from_selector(li, ".box__price-original")
        discount_text = text_from_selector(li, ".box__discount")
        shipping_text = text_from_selector(li, ".box__tag") or text_from_selector(li, ".box__delivery")

        sale_price_krw = price_number(sale_price_text) or parsed["sale_price_krw"]
        original_price_krw = price_number(original_price_text) or parsed["original_price_krw"]
        discount_rate_percent = percent_number(discount_text) or parsed["discount_rate_percent"]
        final_price_krw, coupon_applied_price_krw, extraction_note = extract_final_price_from_dom(li, parsed)

        item = next_items.get(goodscode, {})
        if item:
            product_name = product_name or str(item.get("goodsName", ""))
            if not sale_price_krw:
                sale_price_krw = re.sub(r"\D", "", str(item.get("discountPrice", "")))
            if not original_price_krw and item.get("price") and str(item.get("price")) != str(item.get("discountPrice")):
                original_price_krw = re.sub(r"\D", "", str(item.get("price", "")))
            if not discount_rate_percent and item.get("discountRate"):
                discount_rate_percent = str(item.get("discountRate"))

        img = li.select_one("img.image") or li.select_one('img[src*="gdimg.gmarket"]')
        image_url = normalize_url(img.get("src") or img.get("data-src") or "") if img else ""
        if not image_url and item.get("imageUrl"):
            image_url = normalize_url(str(item.get("imageUrl")))

        benefit_labels = []
        for label in li.select(".box__item-info span, .box__tag, .box__delivery"):
            txt = normalize_space(label.get_text(" ", strip=True))
            if txt and ("결제할인" in txt or "도착보장" in txt or "스타배송" in txt):
                benefit_labels.append(txt)
        if item.get("lmos"):
            benefit_labels.extend([str(x) for x in item.get("lmos", []) if x])
        benefit_labels = list(dict.fromkeys(benefit_labels))

        rows.append(
            {
                "rank": str(rank),
                "product_name": product_name,
                "final_price_krw": final_price_krw,
                "sale_price_krw": sale_price_krw,
                "coupon_applied_price_krw": coupon_applied_price_krw,
                "original_price_krw": original_price_krw,
                "discount_rate_percent": discount_rate_percent,
                "payment_benefit_info": " | ".join(benefit_labels),
                "shipping_info": shipping_text or parsed["shipping_info"],
                "fulfillment_info": parsed["fulfillment_info"],
                "arrival_info": parsed["arrival_info"],
                "review_count": str(item.get("reviewCount", "")),
                "avg_star_point": str(item.get("avgStarPoint", "")),
                "seller_name": str((item.get("miniShopInfo") or {}).get("nickName", "")),
                "goodscode": goodscode,
                "product_url": link,
                "image_url": image_url,
                "final_price_extraction_note": extraction_note,
                "raw_text": whole_text,
            }
        )

    rows.sort(key=lambda r: int(r["rank"]) if r["rank"].isdigit() else 9999)
    return rows[:max_items]


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "rank",
        "product_name",
        "final_price_krw",
        "sale_price_krw",
        "coupon_applied_price_krw",
        "original_price_krw",
        "discount_rate_percent",
        "payment_benefit_info",
        "shipping_info",
        "fulfillment_info",
        "arrival_info",
        "review_count",
        "avg_star_point",
        "seller_name",
        "goodscode",
        "product_url",
        "image_url",
        "final_price_extraction_note",
        "raw_text",
    ]
    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="G마켓 베스트 1~200위 상품을 크롤링해 CSV로 저장합니다.")
    parser.add_argument("--url", default=BEST_URL, help="크롤링할 G마켓 베스트 URL")
    parser.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS, help="수집할 최대 상품 수")
    parser.add_argument("--output", default="", help="CSV 출력 경로. 미지정 시 output/gmarket_best_YYYYMMDD_HHMMSS.csv")
    parser.add_argument("--timeout-ms", type=int, default=60000, help="페이지 로딩 타임아웃(ms)")
    parser.add_argument("--headed", action="store_true", help="가상 디스플레이 등에서 headed 브라우저로 실행")
    parser.add_argument(
        "--browser-executable-path",
        default=os.getenv("BROWSER_EXECUTABLE_PATH", ""),
        help="시스템 Chrome/Chromium 실행 파일 경로. 미지정 시 Playwright 번들 Chromium 사용",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = Path(args.output) if args.output else DEFAULT_OUT_DIR / f"gmarket_best_{datetime.now():%Y%m%d_%H%M%S}.csv"

    html = fetch_rendered_html(
        args.url,
        args.max_items,
        args.timeout_ms,
        headless=not args.headed,
        browser_executable_path=args.browser_executable_path,
    )
    rows = parse_products(html, args.max_items)
    if not rows:
        raise RuntimeError("수집된 상품이 없습니다. 페이지 구조 또는 네트워크 상태를 확인하세요.")

    write_csv(rows, output_path)
    print(f"rows={len(rows)}")
    print(f"output={output_path}")
    print(f"first_rank={rows[0].get('rank')} first_price={rows[0].get('final_price_krw')}")
    print(f"last_rank={rows[-1].get('rank')} last_price={rows[-1].get('final_price_krw')}")


if __name__ == "__main__":
    main()

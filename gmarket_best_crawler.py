from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import shutil
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

BEST_URL = "https://www.gmarket.co.kr/n/best"
DEFAULT_OUT_DIR = Path("output")
DEFAULT_MAX_ITEMS = 200

# 크롤링 대상 카테고리 목록 (대분류, 소분류, groupCode, subGroupCode)
CATEGORIES: list[tuple[str, str, str, str]] = [
    ("가공식품", "냉동/간편조리식품",  "100000005", "200000036"),
    ("가공식품", "건강/다이어트식품",  "100000005", "200000037"),
    ("가공식품", "과자/간식",         "100000005", "200000034"),
    ("가공식품", "커피/음료/생수",     "100000005", "200000038"),
    ("가공식품", "캔/오일/조미료",     "100000005", "200000035"),
    ("생필품/육아", "화장지/물티슈",      "100000007", "200000045"),
    ("생필품/육아", "세제/일회용품",      "100000007", "200001001"),
    ("생필품/육아", "구강/위생용품",      "100000007", "200001003"),
    ("생필품/육아", "기저귀/분유/이유식", "100000007", "200006002"),
    ("생필품/육아", "유아동의류/잡화",    "100000007", "200006003"),
    ("생필품/육아", "출산/유아용품",      "100000007", "200006004"),
    ("생필품/육아", "장난감/완구",        "100000007", "200006005"),
    ("생활/주방", "주방용품",          "100001001", "200001012"),
    ("생활/주방", "쿡웨어/식기/용기",   "100001001", "200001009"),
    ("생활/주방", "생활잡화/보안/수납", "100001001", "200001007"),
    ("생활/주방", "욕실/청소",         "100001001", "200001006"),
    ("생활/주방", "자동차용품",        "100001001", "200006006"),
    ("생활/주방", "공구",             "100001001", "200006007"),
    ("생활/주방", "안전/산업용품",     "100001001", "200006008"),
    ("패션/잡화", "여성의류",       "100000001", "200000004"),
    ("패션/잡화", "남성의류",       "100000001", "200000005"),
    ("패션/잡화", "언더웨어",       "100000001", "200000006"),
    ("패션/잡화", "캐주얼의류",     "100000001", "200013001"),
    ("패션/잡화", "브랜드잡화/명품", "100000001", "200003001"),
    ("패션/잡화", "신발",          "100000001", "200003003"),
    ("패션/잡화", "가방/잡화",     "100000001", "200003002"),
    ("패션/잡화", "액세서리",      "100000001", "200006001"),
    ("뷰티", "스킨케어",          "100000003", "200000017"),
    ("뷰티", "바디/헤어케어",      "100000003", "200014001"),
    ("뷰티", "메이크업",          "100000003", "200000019"),
    ("뷰티", "클렌징/팩/미용소품", "100000003", "200003008"),
    ("뷰티", "남성화장품",        "100000003", "200000023"),
    ("가구/홈", "가구/DIY",     "100001004", "200003010"),
    ("가구/홈", "침구/홈",      "100001004", "200006015"),
    ("가구/홈", "인테리어/소품", "100001004", "200001025"),
    ("스포츠/건강", "마스크/의료",       "100001002", "200006009"),
    ("스포츠/건강", "안마/정수기/비데",   "100001002", "200006010"),
    ("스포츠/건강", "스포츠의류/운동화",  "100001002", "200006011"),
    ("스포츠/건강", "등산/아웃도어",     "100001002", "200006012"),
    ("스포츠/건강", "캠핑/낚시",        "100001002", "200006013"),
    ("스포츠/건강", "구기/라켓/수영",    "100001002", "200006014"),
    ("스포츠/건강", "골프/자전거",       "100001002", "200007001"),
    ("스포츠/건강", "렌탈 서비스",       "100001002", "200015001"),
    ("취미/문구/펫", "악기/취미",    "100001003", "200001018"),
    ("취미/문구/펫", "꽃/이벤트용품", "100001003", "200001020"),
    ("취미/문구/펫", "문구/사무용품", "100001003", "200001021"),
    ("취미/문구/펫", "반려동물",     "100001003", "200001022"),
]

CATEGORY_CRAWL_DELAY_SEC = 3  # 카테고리 간 요청 딜레이 (봇 차단 방지)
DETAIL_PAGE_DELAY_SEC = 0.5  # 상품 상세 페이지 간 요청 딜레이

RED_PRICE_RGB = "rgb(218, 18, 13)"  # #DA120D
BLACK_PRICE_RGB = "rgb(66, 66, 66)"  # #424242

DETAIL_PRICE_SELECTORS = [
    ".price_real",
    ".price .price_real",
    ".box__price .text__value",
    ".box__price-seller span.text.text__value",
    ".item-topinfo .price",
    ".item_price",
    ".price_total",
    ".price_sale",
    "[class*='price'] strong",
    "[class*='price'] span",
]

DETAIL_INFO_SELECTORS = [
    "#itemcase_basic",
    ".item-topinfo",
    ".item-topinfowrap",
    ".vip-content",
    ".box__item-info",
    ".box__benefit",
    "[class*='benefit']",
    "[class*='discount']",
]

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

STEALTH_INIT_SCRIPT = r"""
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR', 'ko', 'en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
window.chrome = window.chrome || { runtime: {} };
const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
if (originalQuery) {
  window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : originalQuery(parameters)
  );
}
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
  if (parameter === 37445) return 'Intel Inc.';
  if (parameter === 37446) return 'Intel Iris OpenGL Engine';
  return getParameter.call(this, parameter);
};
"""


class BlockedByBotError(RuntimeError):
    pass


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


def digits_only(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def percent_number(value: str) -> str:
    m = re.search(r"(\d+)\s*%", value or "")
    return m.group(1) if m else ""


def parse_price_int(value: Any) -> int:
    digits = digits_only(value)
    return int(digits) if digits else 0


def money_amount_from_text(value: str) -> int:
    text = normalize_space(value).replace(",", "")
    if m := re.search(r"(\d+(?:\.\d+)?)\s*만\s*원?", text):
        return int(float(m.group(1)) * 10000)
    if m := re.search(r"(\d+(?:\.\d+)?)\s*천\s*원?", text):
        return int(float(m.group(1)) * 1000)
    if m := re.search(r"([0-9]+)\s*원", text):
        return int(m.group(1))
    return 0


def extract_payment_benefit_labels(text: str) -> list[str]:
    benefit_text = normalize_space(text)
    if not benefit_text:
        return []
    pattern = re.compile(
        r"결제\s*할인\s*(?:최대\s*)?(?:\d+(?:\.\d+)?\s*%|\d+(?:,\d{3})*(?:\.\d+)?\s*(?:만|천)?\s*원?)"
    )
    return list(dict.fromkeys(normalize_space(match.group(0)) for match in pattern.finditer(benefit_text)))


def merge_pipe_values(*values: str) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values:
        for part in str(value or "").split("|"):
            item = normalize_space(part)
            if item and item not in seen:
                seen.add(item)
                merged.append(item)
    return " | ".join(merged)


def append_extraction_note(row: dict[str, str], note: str) -> None:
    if not note:
        return
    row["final_price_extraction_note"] = merge_pipe_values(row.get("final_price_extraction_note", ""), note)


def best_payment_benefit_discount(price: int, benefit_info: str) -> tuple[int, str]:
    if price <= 0 or not benefit_info:
        return 0, ""

    best_discount = 0
    best_label = ""
    for label in extract_payment_benefit_labels(benefit_info):
        discount = 0
        if m := re.search(r"(\d+(?:\.\d+)?)\s*%", label):
            discount = int(price * float(m.group(1)) / 100)
        else:
            discount = money_amount_from_text(label)
        discount = max(0, min(discount, price))
        if discount > best_discount:
            best_discount = discount
            best_label = label
    return best_discount, best_label


def apply_payment_benefit_to_row(row: dict[str, str], source: str) -> None:
    base_price = parse_price_int(
        row.get("final_price_krw") or row.get("coupon_applied_price_krw") or row.get("sale_price_krw")
    )
    discount, label = best_payment_benefit_discount(base_price, row.get("payment_benefit_info", ""))
    if not discount:
        return
    row["final_price_krw"] = str(max(base_price - discount, 0))
    append_extraction_note(row, f"{source}:payment_benefit:{label}:discount={discount}")


def is_bot_page(html_or_text: str) -> bool:
    text = html_or_text or ""
    return any(keyword in text for keyword in ["봇 확인", "간단한 확인 안내", "captcha", "cf-chl", "Cloudflare"])


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


def extract_next_items(soup: BeautifulSoup) -> list[dict[str, Any]]:
    script = soup.select_one("script#__NEXT_DATA__")
    if not script or not script.string:
        return []
    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        return []

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

    return walk(data) or []


def parse_next_items(soup: BeautifulSoup) -> dict[str, dict[str, Any]]:
    return {str(item.get("goodsCode", "")).strip(): item for item in extract_next_items(soup) if item.get("goodsCode")}


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


def next_item_final_price(item: dict[str, Any]) -> tuple[str, str, str, str]:
    price = digits_only(item.get("price"))
    discount_price = digits_only(item.get("discountPrice"))
    sell_price = digits_only(item.get("sellPrice"))
    discount_rate = str(item.get("discountRate", "") or "")

    if discount_price and (discount_price != price or digits_only(discount_rate) not in ["", "0"]):
        return discount_price, sell_price or discount_price, price, "next_data:discountPrice_proxy_for_red_discount_price"
    if price:
        return price, sell_price or price, "", "next_data:price_proxy_for_black_price"
    return sell_price, sell_price, "", "next_data:sellPrice_fallback"


def fetch_static_html(url: str, timeout_sec: int) -> str:
    session = requests.Session()
    response = session.get(url, headers=REQUEST_HEADERS, timeout=timeout_sec, allow_redirects=True)
    response.raise_for_status()
    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    has_next_items = bool(extract_next_items(soup))
    has_dom_items = bool(soup.select("li.list-item"))
    if is_bot_page(html) and not (has_next_items or has_dom_items):
        raise BlockedByBotError("requests 방식이 G마켓 봇 확인 페이지를 받았습니다.")
    if not (has_next_items or has_dom_items):
        raise RuntimeError("requests 방식으로 상품 데이터가 포함된 HTML을 찾지 못했습니다.")
    return html


def fetch_rendered_html(
    url: str,
    max_items: int,
    timeout_ms: int,
    headless: bool,
    browser_executable_path: str,
) -> str:
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    ]
    with sync_playwright() as p:
        launch_options: dict[str, Any] = {
            "headless": headless,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--window-size=1440,1800",
            ],
        }
        if browser_executable_path:
            launch_options["executable_path"] = browser_executable_path
        browser = p.chromium.launch(**launch_options)
        context = browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            user_agent=random.choice(user_agents),
            viewport={"width": 1440, "height": 1800},
            extra_http_headers={
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        context.add_init_script(STEALTH_INIT_SCRIPT)
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_selector("li.list-item", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            page.wait_for_load_state("networkidle", timeout=timeout_ms)

        body_text = page.locator("body").inner_text(timeout=5000)
        if is_bot_page(body_text):
            raise BlockedByBotError(
                "G마켓이 현재 브라우저 실행 방식을 봇으로 판별했습니다. "
                "GitHub Actions 서버 IP 자체가 차단될 수 있으므로 README의 대안을 확인하세요."
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


def parse_products_from_next_data(soup: BeautifulSoup, max_items: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen_goodscode: set[str] = set()
    for index, item in enumerate(extract_next_items(soup), start=1):
        goodscode = str(item.get("goodsCode", "")).strip()
        if not goodscode or goodscode in seen_goodscode:
            continue
        seen_goodscode.add(goodscode)
        rank = int(item.get("rank") or index)
        if rank > max_items:
            continue
        final_price_krw, sale_price_krw, original_price_krw, extraction_note = next_item_final_price(item)
        delivery_fee = digits_only(item.get("deliveryFee"))
        shipping_info = "무료배송" if delivery_fee in ["", "0"] else f"배송비 {delivery_fee}원"
        lmos = item.get("lmos") if isinstance(item.get("lmos"), list) else []
        mini_shop = item.get("miniShopInfo") if isinstance(item.get("miniShopInfo"), dict) else {}
        image_url = normalize_url(str(item.get("imageUrl", "")))
        product_url = normalize_url(str(item.get("linkUrl") or f"https://item.gmarket.co.kr/Item?goodscode={goodscode}"))
        rows.append(
            {
                "rank": str(rank),
                "product_name": str(item.get("goodsName", "")),
                "final_price_krw": final_price_krw,
                "sale_price_krw": sale_price_krw,
                "coupon_applied_price_krw": "",
                "original_price_krw": original_price_krw,
                "discount_rate_percent": digits_only(item.get("discountRate")),
                "payment_benefit_info": " | ".join(str(x) for x in lmos if x),
                "shipping_info": shipping_info,
                "fulfillment_info": "스타배송" if item.get("starDeliveryType") else "",
                "arrival_info": str(item.get("arrivalShippingInfo", "")),
                "review_count": str(item.get("reviewCount", "")),
                "avg_star_point": str(item.get("avgStarPoint", "")),
                "seller_name": str(mini_shop.get("nickName", "")),
                "goodscode": goodscode,
                "product_url": product_url,
                "image_url": image_url,
                "final_price_extraction_note": extraction_note,
                "raw_text": "",
            }
        )
    rows.sort(key=lambda r: int(r["rank"]) if r["rank"].isdigit() else 9999)
    return rows[:max_items]


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
                sale_price_krw = digits_only(item.get("discountPrice"))
            if not original_price_krw and item.get("price") and str(item.get("price")) != str(item.get("discountPrice")):
                original_price_krw = digits_only(item.get("price"))
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
                "seller_name": str(item.get("miniShopInfo", {}).get("nickName", "")) if isinstance(item.get("miniShopInfo"), dict) else "",
                "goodscode": goodscode,
                "product_url": link,
                "image_url": image_url,
                "final_price_extraction_note": extraction_note,
                "raw_text": whole_text,
            }
        )

    if not rows and next_items:
        rows = parse_products_from_next_data(soup, max_items)

    rows.sort(key=lambda r: int(r["rank"]) if r["rank"].isdigit() else 9999)
    return rows[:max_items]


CSV_FIELDNAMES = [
    "category_sub",
    "rank",
    "product_name",
    "final_price_krw",
    "product_url",
    "image_url",
    "category_main",
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
    "final_price_extraction_note",
    "raw_text",
]


def write_csv(rows: list[dict[str, str]], output_path: Path, append: bool = False) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    write_header = not append or not output_path.exists()
    with output_path.open(mode, newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def crawl_one(
    url: str,
    max_items: int,
    timeout_ms: int,
    request_timeout_sec: int,
    mode: str,
    headed: bool,
    browser_executable_path: str,
) -> str:
    """단일 URL을 크롤링해 HTML 반환. 실패 시 예외를 그대로 raise."""
    html = ""
    if mode in ["auto", "requests"]:
        try:
            html = fetch_static_html(url, request_timeout_sec)
            print("  fetch_method=requests")
        except Exception as exc:
            if mode == "requests":
                raise
            print(f"  fetch_method=requests_failed reason={type(exc).__name__}: {exc}")

    if not html:
        html = fetch_rendered_html(
            url,
            max_items,
            timeout_ms,
            headless=not headed,
            browser_executable_path=browser_executable_path,
        )
        print("  fetch_method=browser")
    return html


def price_from_detail_text(text: str) -> tuple[str, str]:
    normalized = normalize_space(text)
    label_patterns = [
        (r"(?:최종혜택가|최종\s*혜택가|최종가|혜택가)\s*([0-9][0-9,]*)\s*원", "detail_text:final_benefit_price"),
        (r"(?:쿠폰적용가|쿠폰\s*적용가)\s*([0-9][0-9,]*)\s*원", "detail_text:coupon_price"),
        (r"(?:즉시할인가|할인가|판매가)\s*([0-9][0-9,]*)\s*원", "detail_text:sale_price"),
    ]
    for pattern, note in label_patterns:
        if m := re.search(pattern, normalized):
            return m.group(1).replace(",", ""), note
    return "", ""


def extract_detail_page_info(page: Any) -> dict[str, str]:
    page.evaluate(
        """
        () => {
          document.querySelectorAll("[class*='price'], [id*='price']").forEach((node) => {
            node.setAttribute('data-computed-color', window.getComputedStyle(node).color);
          });
        }
        """
    )

    selector_prices: list[str] = []
    for selector in DETAIL_PRICE_SELECTORS:
        texts = page.locator(selector).all_inner_texts()
        for text in texts:
            value = price_number(normalize_space(text))
            if value:
                selector_prices.append(value)
        if selector_prices:
            break

    detail_text_parts: list[str] = []
    for selector in DETAIL_INFO_SELECTORS:
        for text in page.locator(selector).all_inner_texts():
            normalized = normalize_space(text)
            if normalized:
                detail_text_parts.append(normalized)

    body_text = page.locator("body").inner_text(timeout=5000)
    detail_text = normalize_space(" ".join(detail_text_parts)) or body_text
    benefit_labels = extract_payment_benefit_labels(detail_text)
    detail_price, note = price_from_detail_text(detail_text)
    if not detail_price and selector_prices:
        detail_price = selector_prices[-1]
        note = "detail_dom:price_selector"
    if not benefit_labels:
        benefit_labels = extract_payment_benefit_labels(body_text)

    return {
        "final_price_krw": detail_price,
        "payment_benefit_info": " | ".join(benefit_labels),
        "final_price_extraction_note": note,
    }


def enrich_rows_with_detail_pages(
    rows: list[dict[str, str]],
    timeout_ms: int,
    headed: bool,
    browser_executable_path: str,
    delay_sec: float,
) -> None:
    if not rows:
        return

    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    ]
    with sync_playwright() as p:
        launch_options: dict[str, Any] = {
            "headless": not headed,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--window-size=1440,1800",
            ],
        }
        if browser_executable_path:
            launch_options["executable_path"] = browser_executable_path
        browser = p.chromium.launch(**launch_options)
        context = browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            user_agent=random.choice(user_agents),
            viewport={"width": 1440, "height": 1800},
            extra_http_headers={
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        context.add_init_script(STEALTH_INIT_SCRIPT)
        page = context.new_page()

        for idx, row in enumerate(rows, start=1):
            product_url = row.get("product_url", "")
            if not product_url:
                apply_payment_benefit_to_row(row, "list")
                continue
            try:
                page.goto(product_url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except PlaywrightTimeoutError:
                    pass
                page.wait_for_timeout(500)

                body_text = page.locator("body").inner_text(timeout=5000)
                if is_bot_page(body_text):
                    raise BlockedByBotError("상품 상세 페이지가 봇 확인 페이지를 반환했습니다.")

                detail = extract_detail_page_info(page)
                if detail["final_price_krw"]:
                    row["final_price_krw"] = detail["final_price_krw"]
                    append_extraction_note(row, detail["final_price_extraction_note"])
                row["payment_benefit_info"] = merge_pipe_values(
                    row.get("payment_benefit_info", ""),
                    detail["payment_benefit_info"],
                )
                apply_payment_benefit_to_row(row, "detail")
                print(f"    detail={idx}/{len(rows)} ok")
            except Exception as exc:
                apply_payment_benefit_to_row(row, "list")
                append_extraction_note(row, f"detail_failed:{type(exc).__name__}")
                print(f"    detail={idx}/{len(rows)} failed reason={type(exc).__name__}: {exc}")
            if idx < len(rows) and delay_sec > 0:
                time.sleep(delay_sec)

        context.close()
        browser.close()


def zip_output_dir(dir_path: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for csv_file in sorted(dir_path.glob("*.csv")):
            zf.write(csv_file, csv_file.name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="G마켓 베스트 전 카테고리 상품을 크롤링해 CSV로 저장합니다.")
    parser.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS, help="카테고리당 수집할 최대 상품 수")
    parser.add_argument("--output-dir", default="", help="출력 디렉터리. 미지정 시 output/YYYYMMDD/")
    parser.add_argument("--timeout-ms", type=int, default=60000, help="페이지 로딩 타임아웃(ms)")
    parser.add_argument("--request-timeout-sec", type=int, default=30, help="requests SSR 시도 타임아웃(초)")
    parser.add_argument("--mode", choices=["auto", "requests", "browser"], default="auto", help="수집 방식")
    parser.add_argument("--headed", action="store_true", help="headed 브라우저로 실행")
    parser.add_argument("--delay-sec", type=float, default=CATEGORY_CRAWL_DELAY_SEC, help="카테고리 간 딜레이(초)")
    parser.add_argument("--detail-delay-sec", type=float, default=DETAIL_PAGE_DELAY_SEC, help="상품 상세 페이지 간 딜레이(초)")
    parser.add_argument("--skip-detail-pages", action="store_true", help="상품 상세 페이지 열람 및 결제할인 보강을 건너뜁니다")
    parser.add_argument(
        "--browser-executable-path",
        default=os.getenv("BROWSER_EXECUTABLE_PATH", ""),
        help="시스템 Chrome/Chromium 실행 파일 경로",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    date_str = datetime.now().strftime("%Y%m%d")
    out_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUT_DIR / date_str
    out_dir.mkdir(parents=True, exist_ok=True)

    combined_path = out_dir / f"gmarket_best_ALL_{date_str}.csv"
    summary: list[dict[str, str]] = []
    failed_categories: list[str] = []

    total = len(CATEGORIES)
    for idx, (cat_main, cat_sub, group_code, sub_group_code) in enumerate(CATEGORIES, start=1):
        url = f"{BEST_URL}?groupCode={group_code}&subGroupCode={sub_group_code}"
        safe_name = cat_sub.replace("/", "_")
        cat_csv = out_dir / f"{cat_main}_{safe_name}.csv"

        print(f"\n[{idx}/{total}] {cat_main} > {cat_sub}")
        print(f"  url={url}")

        try:
            html = crawl_one(
                url,
                args.max_items,
                args.timeout_ms,
                args.request_timeout_sec,
                args.mode,
                args.headed,
                args.browser_executable_path,
            )
            rows = parse_products(html, args.max_items)
            if not rows:
                raise RuntimeError("수집된 상품이 없습니다.")

            # 카테고리 컬럼 추가
            for row in rows:
                row["category_main"] = cat_main
                row["category_sub"] = cat_sub

            if args.skip_detail_pages:
                for row in rows:
                    apply_payment_benefit_to_row(row, "list")
            else:
                enrich_rows_with_detail_pages(
                    rows,
                    args.timeout_ms,
                    args.headed,
                    args.browser_executable_path,
                    args.detail_delay_sec,
                )

            # 카테고리별 개별 CSV
            write_csv(rows, cat_csv)
            # 전체 합본 CSV에 append
            write_csv(rows, combined_path, append=True)

            print(f"  rows={len(rows)}  saved={cat_csv.name}")
            summary.append({"category": f"{cat_main} > {cat_sub}", "rows": str(len(rows)), "status": "ok"})

        except Exception as exc:
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            failed_categories.append(f"{cat_main} > {cat_sub}")
            summary.append({"category": f"{cat_main} > {cat_sub}", "rows": "0", "status": f"error: {exc}"})

        # 마지막 카테고리가 아니면 딜레이
        if idx < total:
            time.sleep(args.delay_sec)

    # 결과 요약 출력
    print("\n" + "=" * 60)
    print(f"완료: {total - len(failed_categories)}/{total} 카테고리 성공")
    print(f"합본 CSV: {combined_path}")
    if failed_categories:
        print(f"실패 카테고리 ({len(failed_categories)}개):")
        for cat in failed_categories:
            print(f"  - {cat}")

    # ZIP 압축 (이메일 첨부용)
    zip_path = DEFAULT_OUT_DIR / f"gmarket_best_{date_str}.zip"
    zip_output_dir(out_dir, zip_path)
    print(f"ZIP: {zip_path}")

    if len(failed_categories) == total:
        raise RuntimeError("모든 카테고리 크롤링에 실패했습니다.")


if __name__ == "__main__":
    main()

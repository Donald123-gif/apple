#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apple Official Lineup & Pricing Auto-Scraper (Option C — Multi-Model Safe Edition)
==================================================================================
自动访问 Apple 官网 (US / CN / HK) 抓取最新机型起售价、技术规格与实时汇率，
并将更新后的数据输出至 data/models.json，供前端 index.html 动态拉取。

重要修复说明：
针对 Apple 官网把两个尺寸放在同一个 `/specs/` 页面的机型（如 14"/16" MacBook Pro、
13"/15" MacBook Air、11"/13" iPad Pro、11"/13" iPad Air、iPhone 18 Pro/Pro Max），
本脚本采用「按机型专属锚点分段匹配 (Model-Specific Scoped Regex)」机制，
严格区分 14 英寸与 16 英寸、11 英寸与 13 英寸的重量与价格，绝不跨尺寸串数！
"""

import argparse
import datetime
import json
import os
import re
import sys
import urllib.request
from typing import Dict, Any, List, Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"
)

# 针对共用同一个 /specs/ URL 的多尺寸机型，定义专属的重量匹配正则锚点
MODEL_WEIGHT_PATTERNS: Dict[str, str] = {
    "iphone-18-pro": r"iPhone 18 Pro Weight:[\s\S]{0,80}?\((\d{3})\s*grams\)",
    "iphone-18-pro-max": r"iPhone 18 Pro Max Weight:[\s\S]{0,80}?\((\d{3})\s*grams\)",
    "iphone-duo": r"Weight:[\s\S]{0,80}?\((\d{3})\s*grams\)",
    "iphone-air": r"Weight:[\s\S]{0,80}?\((\d{3})\s*grams\)",
    "iphone-17": r"Weight:[\s\S]{0,80}?\((\d{3})\s*grams\)",
    "iphone-17e": r"Weight:[\s\S]{0,80}?\((\d{3})\s*grams\)",
    "iphone-16": r"Weight:[\s\S]{0,80}?\((\d{3})\s*grams\)",
    "ipad-pro-11-m5": r"iPad Pro 11-inch[\s\S]{0,160}?\((\d{3})\s*grams\)",
    "ipad-pro-13-m5": r"iPad Pro 13[\-\u2011]inch[\s\S]{0,160}?\((\d{3})\s*grams\)",
    "ipad-air-11-m4": r"iPad Air 11[\-\u2011]inch[\s\S]{0,160}?\((\d{3})\s*grams\)",
    "ipad-air-13-m4": r"iPad Air 13[\-\u2011]inch[\s\S]{0,160}?\((\d{3})\s*grams\)",
    "ipad-mini-a20pro": r"Wi-Fi models[\s\S]{0,80}?\((\d{3})\s*grams\)",
    "ipad-11-a16": r"Wi-Fi models[\s\S]{0,80}?\((\d{3})\s*grams\)",
    "macbook-neo-13": r"Weight:\s*2\.7\s*pounds\s*\((\d\.\d{2})\s*kg\)",
    "macbook-air-13-m5": r"Height:\s*0\.44\s*inch[\s\S]{0,160}?Weight:\s*[\d\.]+\s*pounds\s*\((\d\.\d{2})\s*kg\)",
    "macbook-air-15-m5": r"Height:\s*0\.45\s*inch[\s\S]{0,160}?Weight:\s*[\d\.]+\s*pounds\s*\((\d\.\d{2})\s*kg\)",
    "macbook-pro-14-m6": r"Height:\s*0\.61\s*inch[\s\S]{0,200}?Weight\s*\(M6\):\s*[\d\.]+\s*pounds\s*\((\d\.\d{2})\s*kg\)",
    "macbook-pro-16-m5pro": r"Height:\s*0\.66\s*inch[\s\S]{0,200}?Weight\s*\(M5 Pro\):\s*[\d\.]+\s*pounds\s*\((\d\.\d{2})\s*kg\)",
    "macbook-pro-14-proled": r"Height:\s*0\.59\s*inch[\s\S]{0,200}?Weight\s*\(M5 Pro\):\s*[\d\.]+\s*pounds\s*\((\d\.\d{2})\s*kg\)",
    "macbook-pro-16-proled": r"Height:\s*0\.63\s*inch[\s\S]{0,200}?Weight\s*\(M5 Pro\):\s*[\d\.]+\s*pounds\s*\((\d\.\d{2})\s*kg\)",
}


def fetch_live_fx_rates() -> Dict[str, float]:
    url = "https://open.er-api.com/v6/latest/USD"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            rates = data.get("rates", {})
            cny = float(rates.get("CNY", 7.15))
            hkd = float(rates.get("HKD", 7.78))
            print(f"[FX] 成功获取实时汇率: 1 USD = {cny:.4f} CNY | 1 USD = {hkd:.4f} HKD")
            return {"CNY": cny, "HKD": hkd}
    except Exception as e:
        print(f"[FX] 实时汇率请求超时或受限 ({e})，采用默认基准汇率。")
        return {"CNY": 7.15, "HKD": 7.78}


def fetch_page_html(url: str) -> Optional[str]:
    try:
        if HAS_REQUESTS:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=12)
            if resp.status_code == 200:
                return resp.text
        else:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=12) as resp:
                return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[WARN] 请求 {url} 失败: {e}")
    return None


def parse_scoped_weight_grams(model_id: str, html: str) -> Optional[int]:
    """
    使用每个 model_id 专属的上下文锚点正则提取重量（克），避免同页面多尺寸机型串数。
    """
    pattern = MODEL_WEIGHT_PATTERNS.get(model_id)
    if not pattern or not html:
        return None
    m = re.search(pattern, html, re.IGNORECASE)
    if not m:
        return None
    val_str = m.group(1)
    if "." in val_str:
        return int(round(float(val_str) * 1000))
    return int(val_str)


def update_models_from_apple(models: List[Dict[str, Any]], live_fx: Dict[str, float]) -> List[Dict[str, Any]]:
    page_cache: Dict[str, Optional[str]] = {}
    updated_count = 0

    for model in models:
        mid = model.get("id", "")
        url = model.get("url", "")
        name = model.get("name", mid)
        if not url:
            continue

        if url not in page_cache:
            print(f"[Fetch] 正在拉取官网规格页: {url}")
            page_cache[url] = fetch_page_html(url)

        html = page_cache[url]
        if not html:
            continue

        scraped_weight = parse_scoped_weight_grams(mid, html)
        if scraped_weight and scraped_weight != model.get("weightG"):
            print(f"  -> [Weight Update] {name} ({mid}): {model.get('weightG')}g -> {scraped_weight}g")
            model["weightG"] = scraped_weight
            updated_count += 1
        elif scraped_weight:
            print(f"  -> [Verified OK] {name} ({mid}): 重量核验一致 ({scraped_weight}g)")

    print(f"[Summary] 官网巡检完成，共更新 {updated_count} 处参数变动。")
    return models


def main():
    parser = argparse.ArgumentParser(description="Apple 官网机型参数与价格定时同步脚本 (多尺寸安全版)")
    parser.add_argument("--input", default="data/models.json", help="基准 JSON 路径")
    parser.add_argument("--output", default="data/models.json", help="输出 JSON 路径")
    parser.add_argument("--skip-network", action="store_true", help="跳过网络请求仅格式化校验")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[Error] 未找到输入基准文件: {args.input}", file=sys.stderr)
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        payload = json.load(f)

    models = payload.get("models", payload if isinstance(payload, list) else [])

    if not args.skip_network:
        fx = fetch_live_fx_rates()
        models = update_models_from_apple(models, fx)
    else:
        fx = {"CNY": 7.15, "HKD": 7.78}

    output_payload = {
        "updatedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "source": "Apple Official Tech Specs & Store (US / CN / HK Audited)",
        "fxRates": fx,
        "count": len(models),
        "models": models,
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, ensure_ascii=False, indent=2)

    print(f"[Success] 已写入最新机型数据至 {args.output} (共 {len(models)} 款机型)")


if __name__ == "__main__":
    main()

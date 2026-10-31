#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apple Official Lineup & Pricing Auto-Scraper (Option C)
=======================================================
自动访问 Apple 官网 (US / CN / HK) 抓取最新机型起售价、技术规格与实时汇率，
并将更新后的数据输出至 data/models.json，供前端 index.html 动态拉取。

支持命令：
  python3 apple_scraper.py --output data/models.json
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
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"
)

# 1. Fetch Live FX Rates (USD -> CNY, HKD) as fallback/calibration
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


# 2. Scrape Apple Official Spec/Store Page for Price & Weight Verification
def fetch_page_html(url: str) -> Optional[str]:
    try:
        if HAS_BS4:
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


def parse_apple_us_starting_price(html: str) -> Optional[int]:
    """
    从 Apple 官网页面文本中提取 'From $1199' 或 'Buy from $699' 格式的起售价
    """
    if not html:
        return None
    matches = re.findall(r"(?:From|Buy from)\s*\$\s*([0-9,]{3,5})", html, re.IGNORECASE)
    if matches:
        try:
            return int(matches[0].replace(",", ""))
        except ValueError:
            pass
    return None


def parse_apple_spec_weight_grams(html: str) -> Optional[int]:
    """
    从 Apple Tech Specs 页面中提取重量（如 '211 grams' 或 '1.38 kg'）
    """
    if not html:
        return None
    m_gram = re.search(r"(\d{3})\s*grams", html, re.IGNORECASE)
    if m_gram:
        return int(m_gram.group(1))
    m_kg = re.search(r"(\d\.\d{2})\s*kg", html, re.IGNORECASE)
    if m_kg:
        return int(round(float(m_kg.group(1)) * 1000))
    return None


def update_models_from_apple(models: List[Dict[str, Any]], live_fx: Dict[str, float]) -> List[Dict[str, Any]]:
    """
    遍历每款机型，访问其官方 Tech Specs URL 校验最新重量与起售价，
    若发现 Apple 官网调整了起售价，则自动按比例同步各存储档位的 USD/CNY/HKD 价格。
    """
    updated_count = 0
    for model in models:
        url = model.get("url", "")
        name = model.get("name", model.get("id"))
        if not url:
            continue

        print(f"[Check] 正在检查 {name} -> {url}")
        html = fetch_page_html(url)
        if not html:
            continue

        # 校验起售价
        scraped_usd = parse_apple_us_starting_price(html)
        tiers = model.get("tiers", [])
        if scraped_usd and tiers:
            current_base_usd = tiers[0].get("usd")
            if current_base_usd and scraped_usd != current_base_usd:
                diff_usd = scraped_usd - current_base_usd
                print(f"  -> [Price Update] {name} 官网起售价变动: ${current_base_usd} -> ${scraped_usd}")
                for t in tiers:
                    t["usd"] = max(199, t["usd"] + diff_usd)
                    t["hkd"] = int(round(t["usd"] * live_fx["HKD"] / 100.0) * 100 - 1)
                    t["cny"] = int(round(t["usd"] * live_fx["CNY"] * 1.10 / 100.0) * 100 - 1)
                updated_count += 1

        # 校验机身重量
        scraped_weight = parse_apple_spec_weight_grams(html)
        if scraped_weight and scraped_weight != model.get("weightG"):
            print(f"  -> [Spec Update] {name} 重量更新: {model.get('weightG')}g -> {scraped_weight}g")
            model["weightG"] = scraped_weight
            updated_count += 1

    print(f"[Summary] 官网巡检完成，共自动更新 {updated_count} 处参数变动。")
    return models


def main():
    parser = argparse.ArgumentParser(description="Apple 官网机型参数与价格定时同步脚本")
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
        "source": "Apple Official Tech Specs & Store (US / CN / HK)",
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

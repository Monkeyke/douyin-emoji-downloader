"""
抖音网页版 · 收藏表情包批量下载器
====================================
基于 Playwright 半自动化采集 + requests 本地下载
"""

import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from playwright.sync_api import sync_playwright

# ========================= 配置区 =========================

SAVE_DIR = Path(__file__).parent / "抖音收藏表情包"
DOUYIN_HOME = "https://www.douyin.com/"
REQUEST_TIMEOUT = 30
EMOJI_MIN_SIZE = 40
EMOJI_MAX_SIZE = 120

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.douyin.com/",
}


# ========================= 辅助函数 =========================

def clean_url(raw: str) -> str | None:
    """清洗链接：补全协议、去重参数、验证合法性"""
    if not raw:
        return None
    url = raw.strip()
    if url.startswith("//"):
        url = "https:" + url
    if not url.startswith("http"):
        return None
    if url.startswith("data:"):
        return None
    return url


def get_extension(url: str, content_type: str = "") -> str:
    """智能推断文件扩展名，优先根据URL，其次根据Content-Type"""
    url_lower = url.lower()

    for ext in [".gif", ".webp", ".apng", ".png", ".jpg", ".jpeg", ".svg", ".bmp"]:
        if ext in url_lower:
            return ext.lstrip(".")

    ct = content_type.lower()
    if "gif" in ct:
        return "gif"
    if "webp" in ct:
        return "webp"
    if "apng" in ct or "png" in ct:
        return "png"
    if "jpeg" in ct or "jpg" in ct:
        return "jpg"
    if "svg" in ct:
        return "svg"

    return "png"


def download_one(url: str, save_path: Path, index: int) -> bool:
    """下载单个表情到本地"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            print(f"  [{index}] ❌ HTTP {resp.status_code} → {url[:80]}")
            return False

        ext = get_extension(url, resp.headers.get("Content-Type", ""))
        filepath = save_path / f"emoji_{index:04d}.{ext}"

        with open(filepath, "wb") as f:
            f.write(resp.content)

        size_kb = len(resp.content) / 1024
        print(f"  [{index}] ✅ {filepath.name} ({size_kb:.1f} KB)")
        return True

    except Exception as e:
        print(f"  [{index}] ❌ {type(e).__name__}: {e} → {url[:80]}")
        return False


# ========================= 核心逻辑 =========================

def extract_emoji_urls(page) -> list[str]:
    """
    通过 JavaScript 在浏览器中提取表情 URL。
    终极方案：直接遍历所有 img 标签，通过 URL 特征 (包含 emoticon 或 emotion) 来锁定表情包。
    """

    js_code = """
    (() => {
        const urls = new Set();
        
        const allImages = document.querySelectorAll('img');
        
        for (const img of allImages) {
            let src = img.src || img.getAttribute('data-src') || img.getAttribute('data-original') || '';
            
            if (src && src.startsWith('http') && (src.includes('emoticon') || src.includes('emotion'))) {
                urls.add(src);
            }
        }

        return [...urls];
    })()
    """

    raw_urls = []
    for frame in page.frames:
        for attempt in range(3):
            try:
                urls = frame.evaluate(js_code)
                if urls:
                    raw_urls.extend(urls)
                break
            except Exception:
                time.sleep(1)

    print(f"\n📸 原始提取: {len(raw_urls)} 条")

    cleaned = []
    seen = set()
    for u in raw_urls:
        cu = clean_url(u)
        if cu and cu not in seen:
            seen.add(cu)
            cleaned.append(cu)

    final = []
    names = set()
    for u in cleaned:
        fname = u.split("?")[0].split("/")[-1]
        if fname not in names:
            names.add(fname)
            final.append(u)

    print(f"🧹 清洗去重后: {len(final)} 条")
    return final


def main():
    print("=" * 56)
    print("  🎭  抖音网页版 · 收藏表情包批量下载器")
    print("=" * 56)

    print("\n🚀 正在启动 Chrome 浏览器...")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=False,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                ],
            )
        except Exception:
            print("⚠️  系统 Chrome 调用失败，尝试 Edge...")
            browser = p.chromium.launch(
                headless=False,
                channel="msedge",
                args=[
                    "--disable-blink-features=AutomationControlled",
                ],
            )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=HEADERS["User-Agent"],
        )
        page = context.new_page()

        page.goto(DOUYIN_HOME, timeout=60000, wait_until="domcontentloaded")
        print("✅ 浏览器已打开: https://www.douyin.com/")

        print("\n" + "─" * 56)
        print("  📋 请依次手动完成以下操作:")
        print("  1️⃣  扫码登录你的抖音账号")
        print("  2️⃣  点击左侧「消息」→ 进入任意私信聊天窗口")
        print("  3️⃣  点击输入框旁的「😊」表情按钮")
        print("  4️⃣  切换到「自定义表情」(收藏表情) 标签页")
        print("  5️⃣  手动**向下滚动**面板，确保所有表情都已加载")
        print("─" * 56)
        input("\n  ⏳ 完成后，按 Enter 键继续采集...\n")

        print("\n🔍 正在遍历所有页面寻找表情包...")
        emoji_urls = []
        
        for p in context.pages:
            try:
                url = p.url
                if "about:blank" in url or "douyin.com" not in url:
                    continue
                    
                print(f"\n  👀 检查页面: {url}")
                try:
                    p.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception:
                    pass
                    
                urls = extract_emoji_urls(p)
                if urls:
                    emoji_urls.extend(urls)
                    print(f"  ✅ 在此页面找到 {len(urls)} 个表情")
                else:
                    print("  ❌ 此页面未发现表情")
            except Exception as e:
                print(f"  ⚠️ 检查页面时出错: {e}")
                
        emoji_urls = list(dict.fromkeys(emoji_urls))

        browser.close()
        print("🔒 浏览器已关闭")

    if not emoji_urls:
        print("\n❌ 未提取到任何表情链接！")
        print("   请检查是否已打开表情面板，并重新运行脚本。")
        return

    print(f"\n{'─' * 56}")
    print(f"  📊 共发现 {len(emoji_urls)} 个表情包")
    print(f"{'─' * 56}")
    for i, u in enumerate(emoji_urls[:10], 1):
        print(f"  {i:2d}. {u[:90]}...")
    if len(emoji_urls) > 10:
        print(f"  ... 还有 {len(emoji_urls) - 10} 条")

    print(f"\n{'─' * 56}")
    if len(emoji_urls) > 0:
        confirm = input(f"  是否开始下载 {len(emoji_urls)} 个表情包? [Y/n]: ").strip().lower()
        if confirm and confirm != "y":
            print("❌ 已取消")
            return

    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n📁 保存目录: {SAVE_DIR}")
    print(f"{'─' * 56}")

    ok_count = 0
    fail_count = 0

    t_start = time.time()
    for i, url in enumerate(emoji_urls, 1):
        if download_one(url, SAVE_DIR, i):
            ok_count += 1
        else:
            fail_count += 1
        if i < len(emoji_urls):
            time.sleep(0.15)

    t_elapsed = time.time() - t_start

    print(f"\n{'=' * 56}")
    print(f"  🎉 下载完成!")
    print(f"  ✅ 成功: {ok_count} 个")
    print(f"  ❌ 失败: {fail_count} 个")
    print(f"  ⏱️  耗时: {t_elapsed:.1f} 秒")
    print(f"  📁 位置: {SAVE_DIR}")
    print(f"{'=' * 56}")

    if sys.platform == "win32":
        os.startfile(str(SAVE_DIR))

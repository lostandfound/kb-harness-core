#!/usr/bin/env python3
"""軽量ブラウザ操作 CLI。可視 Chromium を CDP で操作し、抽出テキストだけを印字する。

使い方:
  python3 scripts/browse.py open                 # 可視ブラウザ起動（永続プロファイル）
  python3 scripts/browse.py goto <url>
  python3 scripts/browse.py text [--limit 2000]  # 本文テキスト抽出
  python3 scripts/browse.py find "<語>" [--ctx 120]
  python3 scripts/browse.py click "<テキストまたはCSSセレクタ>"
  python3 scripts/browse.py fill "<セレクタ>" "<値>"
  python3 scripts/browse.py press <キー>          # 例: Enter
  python3 scripts/browse.py url                  # 現在の URL とタイトル
  python3 scripts/browse.py close

MCP を使わず出力を絞ることでトークン消費を抑える。ログイン・認証コードの入力は
ユーザーが起動済みウィンドウで直接行う（資格情報はこの CLI を経由させない）。
自動巡回・一括取得には使わない（対象サイトの規約に従う）。
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

CDP_PORT = 9222
PROFILE = Path.home() / ".cache" / "okb-browse-profile"


def find_chromium() -> str:
    import glob
    cands = sorted(
        glob.glob(
            str(
                Path.home()
                / "Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium"
            )
        )
    )
    if cands:
        return cands[-1]
    mac_chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if Path(mac_chrome).exists():
        return mac_chrome
    sys.exit("ERROR: Chromium/Chrome が見つからない。`playwright install chromium` を実行")


def cmd_open() -> None:
    PROFILE.mkdir(parents=True, exist_ok=True)
    exe = find_chromium()
    subprocess.Popen(
        [
            exe,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={PROFILE}",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    time.sleep(3)
    print(f"起動した（CDP :{CDP_PORT}、プロファイル {PROFILE}）。ログインが必要ならウィンドウで直接入力すること。")


def page():
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
    except Exception:
        pw.stop()
        sys.exit("ERROR: ブラウザ未起動。先に `browse.py open` を実行")
    ctx = browser.contexts[0]
    pg = ctx.pages[-1] if ctx.pages else ctx.new_page()
    return pw, pg


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("open")
    sub.add_parser("close")
    sub.add_parser("url")
    p = sub.add_parser("goto"); p.add_argument("target")
    p = sub.add_parser("text"); p.add_argument("--limit", type=int, default=2000)
    p = sub.add_parser("find"); p.add_argument("word"); p.add_argument("--ctx", type=int, default=120)
    p = sub.add_parser("click"); p.add_argument("target")
    p = sub.add_parser("fill"); p.add_argument("selector"); p.add_argument("value")
    p = sub.add_parser("press"); p.add_argument("key")
    args = ap.parse_args()

    if args.cmd == "open":
        cmd_open()
        return 0

    pw, pg = page()
    try:
        if args.cmd == "close":
            pg.context.browser.close()
            print("閉じた")
        elif args.cmd == "url":
            print(pg.url)
            print(pg.title())
        elif args.cmd == "goto":
            pg.goto(args.target, wait_until="domcontentloaded", timeout=30000)
            print(f"OK {pg.url}")
            print(pg.title())
        elif args.cmd == "text":
            body = pg.inner_text("body", timeout=10000)
            body = "\n".join(line for line in (l.strip() for l in body.splitlines()) if line)
            print(body[: args.limit])
            if len(body) > args.limit:
                print(f"…（全 {len(body)} 文字、--limit で調整）")
        elif args.cmd == "find":
            body = pg.inner_text("body", timeout=10000)
            flat = " ".join(body.split())
            hits = []
            start = 0
            while len(hits) < 10:
                i = flat.find(args.word, start)
                if i < 0:
                    break
                hits.append(flat[max(0, i - args.ctx) : i + len(args.word) + args.ctx])
                start = i + len(args.word)
            if not hits:
                print("ヒットなし")
            for n, h in enumerate(hits, 1):
                print(f"[{n}] …{h}…")
        elif args.cmd == "click":
            t = args.target
            try:
                if t.startswith(("#", ".", "[")) or " > " in t:
                    pg.click(t, timeout=5000)
                else:
                    pg.get_by_text(t, exact=False).first.click(timeout=5000)
                print("OK")
            except Exception as e:
                print(f"ERROR: クリック失敗: {e}", file=sys.stderr)
                return 1
        elif args.cmd == "fill":
            pg.fill(args.selector, args.value, timeout=5000)
            print("OK")
        elif args.cmd == "press":
            pg.keyboard.press(args.key)
            print("OK")
    finally:
        pw.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

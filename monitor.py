#!/usr/bin/env python3
"""万座高原ホテル 軽井沢駅発 無料送迎バスの空き監視 → Discord通知

対象: 2027-01-04 / 軽井沢駅(南口) → 万座高原ホテル / 1名
予約窓口: https://inquiry.talkappi.com/?f=princehotels-manza-hp&id=3c78462a44eccac4

使い方:
  python monitor.py --test-notify        # Discordに疎通テスト
  python monitor.py --headed --dry-run   # ブラウザを表示して1回実行、通知はしない
  python monitor.py                      # 本番(GitHub Actionsから15分おきに実行)
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import traceback
import urllib.request

# Windowsにはタイムゾーンデータが無いので、固定オフセットで定義する(日本は夏時間なし)
JST = dt.timezone(dt.timedelta(hours=9), "JST")

# ---- 監視条件 -------------------------------------------------------------
TARGET_DATE = dt.date(2027, 1, 4)
PASSENGERS = 1
# 公式案内「ご予約はご宿泊日2日前の5:00P.M.まで」→ 1/4宿泊なら 1/2 17:00
BOOKING_DEADLINE = dt.datetime(2027, 1, 2, 17, 0, tzinfo=JST)
BOOKING_URL = "https://inquiry.talkappi.com/?f=princehotels-manza-hp&id=3c78462a44eccac4"
PHONE = "0279-97-3111 (9:00-18:00)"

# ---- 判定キーワード(最終画面のテキストに含まれるか) ------------------------
# 実際の画面の文言を見て調整してください(README参照)。
FULL_WORDS = ["満席", "満員", "空きがありません", "空きはありません", "受付終了", "受付を終了", "ご予約できません"]
AVAILABLE_WORDS = ["空席あり", "空きあり", "予約可能", "残席"]

# ---- 通知まわり -----------------------------------------------------------
FAIL_ALERT_AFTER = 4      # 連続失敗がこの回数(=約1時間)に達したら異常通知
REMIND_MINUTES = 60       # 空きが続く間は何分おきに再通知するか

STATE_PATH = pathlib.Path("state/state.json")
DEBUG_DIR = pathlib.Path("debug")


def now_jst() -> dt.datetime:
    return dt.datetime.now(JST)


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def notify(message: str, dry_run: bool = False) -> None:
    mention = os.environ.get("DISCORD_MENTION", "").strip()  # 例: <@123456789012345678>
    content = f"{mention} {message}".strip()
    if dry_run:
        print(f"[dry-run] Discord通知:\n{content}\n")
        return
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        print("DISCORD_WEBHOOK_URL が未設定です", file=sys.stderr)
        return
    req = urllib.request.Request(
        url,
        data=json.dumps({"content": content[:1900]}).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "manza-bus-watch/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as res:
        print(f"Discord通知 送信: HTTP {res.status}")


def judge(text: str) -> str:
    """'full' | 'available' | 'unknown'"""
    if any(w in text for w in FULL_WORDS):
        return "full"
    if any(w in text for w in AVAILABLE_WORDS):
        return "available"
    return "unknown"


def save_debug(page) -> None:
    try:
        DEBUG_DIR.mkdir(exist_ok=True)
        page.screenshot(path=str(DEBUG_DIR / "last.png"), full_page=True)
        (DEBUG_DIR / "last.html").write_text(page.content(), encoding="utf-8")
    except Exception as e:  # デバッグ保存の失敗は無視
        print(f"debug保存に失敗: {e}", file=sys.stderr)


def fetch_status(headed: bool) -> tuple[str, str]:
    from playwright.sync_api import sync_playwright

    import flow  # 予約フローの操作手順(自分で記録して貼る)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        ctx = browser.new_context(
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        page.set_default_timeout(30_000)
        try:
            page.goto(BOOKING_URL, wait_until="networkidle")
            text = flow.run(page, TARGET_DATE, PASSENGERS)
            if text is None:
                text = page.inner_text("body")
            return judge(text), text
        finally:
            save_debug(page)
            browser.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true", help="ブラウザを表示する")
    ap.add_argument("--dry-run", action="store_true", help="Discordへは送らず標準出力に表示")
    ap.add_argument("--test-notify", action="store_true", help="Discordへ疎通テストを送って終了")
    ap.add_argument(
        "--date",
        help="テスト用: 監視する日付を一時的に変更 (例: 2027-01-05)。状態ファイルは読み書きしない",
    )
    args = ap.parse_args()

    global TARGET_DATE
    testing = bool(args.date)
    if testing:
        TARGET_DATE = dt.date.fromisoformat(args.date)
        print(f"[テスト] 監視日を {TARGET_DATE} に変更して実行します")

    if args.test_notify:
        notify("✅ 万座バス監視botの通知テストです", dry_run=args.dry_run)
        return 0

    now = now_jst()
    state = {} if testing else load_state()  # テスト時は本番の状態に影響させない

    if now > BOOKING_DEADLINE and not testing:
        if not state.get("deadline_notified"):
            notify("⏹ 予約受付期限(1/2 17:00)を過ぎたため、監視を終了します。", args.dry_run)
            state["deadline_notified"] = True
            save_state(state)
        print("期限後のため何もしません")
        return 0

    status, text, err = "error", "", ""
    try:
        status, text = fetch_status(args.headed)
    except NotImplementedError as e:
        err = f"flow.py が未設定です: {e}"
    except Exception:
        err = traceback.format_exc(limit=3)

    print(f"[{now:%Y-%m-%d %H:%M} JST] status={status}")
    if err:
        print(err, file=sys.stderr)
    if text:
        print("--- 最終画面テキスト(先頭1500字) ---")
        print(text[:1500])

    prev = state.get("last_status")

    if status in ("error", "unknown"):
        state["failures"] = state.get("failures", 0) + 1
        n = state["failures"]
        if n == FAIL_ALERT_AFTER or (n > FAIL_ALERT_AFTER and n % 96 == 0):
            reason = "ページを判定できません(文言が想定外)" if status == "unknown" else "取得に失敗しました"
            notify(
                f"⚠️ 万座バス監視: {n}回連続で{reason}。サイト変更の可能性があります。\n"
                f"手動確認: {BOOKING_URL}\n電話: {PHONE}",
                args.dry_run,
            )
    else:
        state["failures"] = 0
        state["last_status"] = status
        if status == "available":
            last = state.get("last_notified")
            stale = True
            if last:
                stale = (now - dt.datetime.fromisoformat(last)).total_seconds() >= REMIND_MINUTES * 60
            if prev != "available" or stale:
                notify(
                    f"🚌 **空きが出た可能性があります!**\n"
                    f"{TARGET_DATE:%Y/%m/%d} 軽井沢駅→万座高原ホテル / {PASSENGERS}名\n"
                    f"予約: {BOOKING_URL}\n電話: {PHONE}\n"
                    f"(予約期限: 1/2 17:00)",
                    args.dry_run,
                )
                state["last_notified"] = now.isoformat()
        elif prev == "available":
            notify("❌ また満席になったようです。監視を続けます。", args.dry_run)

    if not testing:
        save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())

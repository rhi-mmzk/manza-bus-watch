"""予約フローの操作手順(codegenの記録をもとに作成)

流れ:
  1. 予約画面を開く → 左上の .icon をクリック
  2. 「往路：軽井沢駅（南口）発 ⇒ ホテル行」にチェック
  3. 日付欄(yyyy-mm-dd)を開き、年・月のプルダウンを対象月に合わせる
  4. 対象日が「リンク」として選べれば空きあり、灰色(リンクなし)なら満席

monitor.py の判定語(FULL_WORDS / AVAILABLE_WORDS)に合わせて、
「満席」または「空きあり」を含む1行を返す。
"""
import datetime as dt

# codegenで記録した遷移先(member_idは毎回変わる可能性があるため付けない)
INPUT_URL = (
    "https://inquiry.talkappi.com/inquiry/input"
    "?id=3c78462a44eccac4&facility_cd=princehotels-manza-hp&lang_cd=ja&channel=wb"
)
ROUTE_LABEL = "往路：軽井沢駅（南口）発 ⇒ ホテル行"


def run(page, target_date: dt.date, passengers: int):
    # 1. 入力画面へ(最初のURLが自動で遷移しない場合に備えて直接開く)
    icon = page.locator(".icon").first
    try:
        icon.wait_for(state="visible", timeout=10_000)
    except Exception:
        page.goto(INPUT_URL, wait_until="networkidle")
        icon.wait_for(state="visible", timeout=15_000)
    icon.click()

    # 2. 往路(軽井沢駅→ホテル)を選ぶ
    page.get_by_role("checkbox", name=ROUTE_LABEL).check()

    # 3. カレンダーを開いて対象の年月に合わせる
    page.get_by_role("textbox", name="yyyy-mm-dd").click()
    year_box = page.get_by_role("combobox").first
    month_box = page.get_by_role("combobox").nth(1)
    year_box.select_option(str(target_date.year))
    month_box.select_option(str(target_date.month - 1))  # 1月 = "0"
    page.wait_for_timeout(800)

    # 年月が本当に切り替わったか確認(失敗したら「満席」と誤判定せずエラーにする)
    if year_box.input_value() != str(target_date.year) or month_box.input_value() != str(
        target_date.month - 1
    ):
        raise RuntimeError("カレンダーを対象の年月に切り替えられませんでした")

    # 4. 対象日がリンク(=選択可能)かどうか
    day_link = page.get_by_role("link", name=str(target_date.day), exact=True)
    available = day_link.count() > 0

    label = "空きあり(選択可能)" if available else "満席(選択不可)"
    return f"【判定】{target_date.isoformat()} 軽井沢駅→ホテル: {label}"

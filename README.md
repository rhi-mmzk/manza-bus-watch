# 万座高原ホテル 送迎バス空き監視bot

2027/1/4 の **軽井沢駅(南口)→万座高原ホテル 無料送迎バス(1名)** に空きが出たら、
Discord に通知します。15分おきに GitHub Actions で自動チェックします。
(自動予約はしません。通知を見て自分で予約してください)

- 公式案内: https://www.princehotels.co.jp/manza-kogen/informations/freeshuttleservice_winter
- 予約期限: 宿泊日の2日前 17:00 → **1/2(土) 17:00**(以降は自動で監視終了)
- 電話予約: 0279-97-3111 (9:00〜18:00)

## 手順1: Discord Webhook を作る

1. 通知を受けたいサーバーのチャンネル → 設定(歯車) → 連携サービス → ウェブフック → 新しいウェブフック
2. 「ウェブフックURLをコピー」
3. (任意) スマホに確実にプッシュしたい場合は、自分のユーザーIDを `<@123456789012345678>` の形で控える
   (Discordの開発者モードON → 自分を右クリック → ユーザーIDをコピー)

## 手順2: 予約フローを1回だけ記録する(必須)

予約窓口(talkappi)はチャット形式のフォームで、自動で中身を調べられなかったため、
あなたの操作を録画してコード化します。

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium

playwright codegen --lang=ja-JP --timezone=Asia/Tokyo \
  "https://inquiry.talkappi.com/?f=princehotels-manza-hp&id=3c78462a44eccac4"
```

1. 開いたブラウザで、軽井沢駅→万座の予約を **2027/1/4・1名** で、**空き状況が表示される画面まで**進める
   (予約の確定はしない!)
2. Inspector に出たコードのうち、操作部分を `flow.py` の `run()` に貼る
3. 最後に判定に使う画面のテキストを `return page.locator("body").inner_text()` のように返す

## 手順3: 手元で動作確認

```bash
python monitor.py --test-notify        # Discord疎通(環境変数 DISCORD_WEBHOOK_URL が必要)
python monitor.py --headed --dry-run   # ブラウザを表示して1回実行
```

`--dry-run` は「最終画面テキスト(先頭1500字)」を表示します。ここに出る文言を見て、
`monitor.py` の `FULL_WORDS`(満席のときに出る言葉)/`AVAILABLE_WORDS`(空きのときに出る言葉)を調整してください。
判定できない場合は `status=unknown` になり、**空き通知は出ません**(誤通知防止)。
`unknown`/失敗が4回(約1時間)続くと「サイト変更の可能性」を Discord に知らせます。

## 手順4: GitHub Actions に載せる

1. このフォルダを GitHub リポジトリに push
   - **public 推奨**: 約41日間×96回/日ぶん動かすため、privateだと無料枠(月2,000分)を超えます
   - 公開してよい内容かの確認: コードにWebhook URLは含まれません(Secretsに入れる)
2. Settings → Secrets and variables → Actions → New repository secret
   - `DISCORD_WEBHOOK_URL` : 手順1のURL
   - `DISCORD_MENTION` (任意) : `<@ユーザーID>`
3. Actions タブ → `manza-bus-watch` → Run workflow で手動実行し、ログを確認
4. 以降は15分おきに自動実行されます

## 注意

- GitHub Actions の cron は混雑時に数分〜十数分遅れることがあります。厳密な15分ではありません。
- 1/2 17:00 を過ぎたら Actions タブからワークフローを Disable してください。
- キャンセルで出た空きは取り合いになりやすいので、通知が来たらすぐ予約画面を開くか、電話が確実です。
- 公式サイトの仕様変更で動かなくなったら、手順2をやり直してください。

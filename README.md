# news-daily

はてブIT・チャートなび・ロイター・YouTube各チャンネルから毎朝トレンドを収集し、
GitHub Pages に公開するリポジトリ。

**公開URL: https://marukeso.github.io/news-daily/**

## 構成

| パス | 役割 |
|---|---|
| `scripts/collect_news.py` | 収集本体。`docs/YYYY-MM-DD.md` と `docs/index.md` を生成 |
| `docs/` | GitHub Pages の公開ルート（Jekyll） |
| `ROUTINE.md` | クラウドルーティンに渡すプロンプト |

## 収集ソース

- はてブIT（RSS・ブックマーク数上位5件）
- AIまさおう（YouTube・24時間以内）
- チャートなび 急上昇ワード（上位5件）
- チャートなび 話題の銘柄ランキング（1〜5位）
- ロイター（24時間以内・新着5件／Google News RSS フォールバックあり）
- ニュースアーカイブ / テレ東ビズ / ANNニュース（YouTube・24時間以内）

## 手動実行

```bash
python3 scripts/collect_news.py
```

Python標準ライブラリのみで動作（外部依存なし）。YouTubeはチャンネルページの
`ytInitialData` をパースするため OAuth 認証は不要。

## 出自

`news-system/collect_obsidian_news.py`（Obsidian出力版）を GitHub Pages 出力に
移植したもの。収集ロジックは同一。

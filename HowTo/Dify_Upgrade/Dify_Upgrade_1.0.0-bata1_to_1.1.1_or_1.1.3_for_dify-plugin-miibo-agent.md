# Dify Upgrade (1.0.0-bata1 to 1.1.1 or 1.1.3)<br>for dify-plugin-miibo-agent

ℹ️「dify-plugin-miibo-agent」プラグイン実装されているDifyでは、  
環境変数ファイル`.env`にpluginの証明チェックをオフにする工程があります。

[参考手順]（Dify公式）[コミュニティ版を v1.0.0 に移行する](https://docs.dify.ai/ja-jp/development/migration/migrate-to-v1)

## 1. データバックアップ

```
cd ~/dify/docker
sudo cp docker-compose.yaml docker-compose.yaml.$(date +%s).bak
```

```
cd ~/dify/docker
sudo docker compose down
sudo tar -cvf volumes-$(date +%s).tgz volumes
```

## 2. バージョンアップ

#### (1) 強制的に指定Difyバージョンのdocker-compose.yamlでチェックアウトする
```
cd ~/dify
sudo git fetch origin
sudo git reset --hard
sudo git checkout 1.1.3 # ブランチの切り替え（ここでDifyバージョン指定する）
```

#### (2) pluginの証明チェックをオフにします（2025/3/30現在）
<s>
- docker/docker-compose.yamlの該当値を${FORCE_VERIFYING_SIGNATURE:-false}に修正
```
sudo sed -i 's/${FORCE_VERIFYING_SIGNATURE:-true}/${FORCE_VERIFYING_SIGNATURE:-false}/' \
"/home/$(whoami)/dify/docker/docker-compose.yaml"
```
</s>

- docker/.envの該当値をFORCE_VERIFYING_SIGNATURE=falseに修正
```
sudo sed -i 's/FORCE_VERIFYING_SIGNATURE=true/\
FORCE_VERIFYING_SIGNATURE=false/' /home/$(whoami)/dify/docker/.env
```

#### (3) (HTTPS対応する場合）NGINX_HTTPS_ENABLED=trueに変更
```
sudo sed -i 's/NGINX_HTTPS_ENABLED=false/NGINX_HTTPS_ENABLED=true/' /home/$(whoami)/dify/docker/.env
```

#### (4) 実行
```
cd ~/dify/docker
sudo docker compose -f docker-compose.yaml up -d
```

## 3. ツールの移行をプラグインに変換
ℹ️ Dify1.0.0-bata1, 1.1.1, 1.1.3はいずれもプラグインの追加インストール0だったため  
この章の実施は不要でした。
#### (1) docker-api-1コンテナのターミナルにアクセスする
```
sudo docker exec -it docker-api-1 bash
```

#### (2) プラグイン情報を抽出する
※コマンド実行後、端末に入力待機のプロンプトが表示された場合は「Enter」を押して入力をスキップする。
```
poetry run flask extract-plugins --workers=20
```

#### (3) 最新のコミュニティ版に必要なすべてのプラグインをダウンロードしてインストールする
※コマンド実行後、端末に入力待機のプロンプトが表示された場合は「Enter」を押して入力をスキップする。
```
poetry run flask install-plugins --workers=2
```
⚠️ Dify1.0.0-bata1からの移行では次のコマンドでした。（ --workersが不要）
```
poetry run flask install-plugins
```

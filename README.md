# Qwen3-TTS API (VOICEVOX-Compatible)

Qwen3-TTS を使って、AivisSpeech API（VOICEVOX 互換の API）互換のAPI を提供するプロジェクトです。
AivisSpeech APIとは異なるポートで起動することで、AivisSpeech APIと同居します。
未知の `speaker` は AivisSpeech にパススルーし、既存ツールとの互換性を維持します（当ソフト側APIを呼び出すことで、当ソフトとAivisSpeechがマージされた状態で使用できます）。

## 主な機能

- FastAPI ベースの VOICEVOX 互換 API
- Qwen3 話者 (`api/speakers/*.yaml`) の動的読み込み
- 未知 `speaker` を AivisSpeech へ自動転送
- Aivis 未起動時の自動起動・ポーリング
- 話者録音 + VoiceClone YAML 自動生成ツール（録音音声を使ったTTS用の設定ツール）

## ディレクトリ構成

- `api/` : API 本体
- `api/speakers/` : 話者 YAML
- `api/speakers/refAudio/` : VoiceClone 参照音声
- `tools/cli/` : CLI ツール
- `tools/record/` : 録音・音量正規化ツール

## 動作環境

- Windows (ネイティブ想定)
- Python 3.12 系
- NVIDIA GPU + CUDA 環境
- AivisSpeech（連携利用時）
- Node.js 20 以上（CLI 利用時）

補足:

- 実行時には NVIDIA ドライバが必要です。
- PyTorch は CUDA 対応 wheel（例: `cu121`）を仮想環境へ入れる運用を想定しています

## セットアップ（Step by Step）

### 1. リポジトリを取得

```powershell
git clone https://github.com/minmin9911/Qwen3-TTS_API
```

### 2. Python 仮想環境を作成

```powershell
cd Qwen3-TTS_API
py -3.12 -m venv .venv-qwen3tts
.venv-qwen3tts\Scripts\activate
python -m pip install --upgrade pip
```

### 3. API 依存をインストール

```powershell
pip install fastapi uvicorn httpx pydantic pyyaml numpy soundfile sounddevice
```

### 4. PyTorch（CUDA版）をインストール

`torch` を、このプロジェクトの仮想環境（`.venv-qwen3tts`）へインストールします。

```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
python -c "import torch; print(torch.cuda.is_available(), torch.__version__)"
```

### 5. Qwen3-TTS を導入

Qwen3-TTS の Python モジュール（`qwen_tts`）を利用できる状態にします。  

```powershell
pip install qwen-tts
```

### 6. CLI の依存モジュールをインストール（CLI 利用時のみ）

```powershell
cd tools\cli
npm ci
cd ..\..
```

### 7. Aivis 連携設定を作成

`config.yaml` を `config.example.yaml` から作成します。

```powershell
copy config.example.yaml config.yaml
```

`config.yaml` 例:

```yaml
aivis:
  baseUrl: http://127.0.0.1:10101
  exePath: C:\Program Files\AivisSpeech\AivisSpeech.exe
  startupTimeoutSec: 120
  pollIntervalSec: 1.0
```

### 8. 動作確認

1. まず、API を起動する: `run_qwen3_tts_api.cmd`  
2. 次に、CLIで疎通確認する: `run_test_cli.cmd`

## API 起動 / 停止

起動:

```bat
run_qwen3_tts_api.cmd
```

停止:

```bat
stop_qwen3_tts_api.cmd
```

既定の待受:

- 本アプリ（Qwen3 API）: `http://127.0.0.1:10102`（未知のSpeakerについては、Aivis APIにパス）
- Aivis API: `http://127.0.0.1:10101` を想定。

## API エンドポイント

- `GET /health`
  - 稼働確認
- `GET /speakers`
  - Aivis 話者 + Qwen3 話者をマージして返却
- `POST /audio_query?text=...&speaker=...`
  - VOICEVOX 互換 query
- `POST /synthesis?speaker=...`
  - VOICEVOX 互換音声合成 (wav)

補足:

- 未知 `speaker` は Aivis 側へ転送します
- Qwen3 の出力 `outputSamplingRate` は 44100Hz にしています。

## 話者 YAML 運用

配置:

- `api/speakers/<name>.yaml`
- `api/speakers/refAudio/<name>.wav`

主要項目:

- `speakerId`
- `name`
- `styleName`
- `mode` (`custom_voice` / `voice_design` / `voice_clone`)
- `modelId`
- `refAudio` / `refText`（VoiceClone で重要）
- `xVectorOnlyMode`
- `volumeScale`

注意:

- VoiceClone で `xVectorOnlyMode: false` の場合は `refText` 必須
- 話者 YAML は API 実行中でも自動リロードされます

## 録音ツール（VoiceClone）

実行:

```bat
run_record_voice_clone.cmd
```

処理内容:

1. 話者名入力
2. 参照文を録音
3. `api/speakers/refAudio/<slug>.wav` を生成
4. `api/speakers/<slug>.yaml` を生成

音量仕様:

- 録音後に RMS 正規化を実施
- 既定の固定基準値 `0.1419159919` を使用
- `--volume-reference` 指定時のみ、指定 WAV 実測 RMS で上書き

## CLI ツール

場所:

- `tools/cli/`

主な用途:

- 話者一覧 (`list`)
- 再生 (`play`)
- 保存 (`save`)

簡易疎通バッチ:

```bat
run_test_cli.cmd
```

## トラブルシューティング（要点）

- `422`:
  - `audio_query` JSON 不正、または text 空
- `500`（VoiceClone）:
  - `refText` 不足の可能性
- Aivis 起動不可:
  - `config.yaml` の `exePath` を確認
- Hugging Face モデル取得失敗:
  - モデル ID と認証状態（必要時 `hf auth login`）を確認

## 主要ファイルの役割

- `README.md` : 本ファイル（概要・セットアップ・運用手順）
- `config.example.yaml` : 配布用の設定テンプレート
- `pyproject.toml` : Python 開発設定（ruff / pytest）
- `run_qwen3_tts_api.cmd` : API サーバ起動バッチ
- `stop_qwen3_tts_api.cmd` : API サーバ停止バッチ
- `run_record_voice_clone.cmd` : 録音 + VoiceClone 話者 YAML 生成バッチ
- `run_test_cli.cmd` : CLI 疎通確認バッチ
- `api/main.py` : FastAPI エントリポイント（ルーティング・統合制御）
- `api/aivis_proxy.py` : Aivis 起動・待機・再接続制御
- `api/config.py` : `config.yaml` と話者 YAML の読み込み・管理
- `api/models.py` : API で扱うデータモデル定義
- `api/synth.py` : Qwen3-TTS モデルロードと音声生成処理
- `api/speakers/*.yaml` : 公開話者定義（ホワイトリスト運用）
- `tools/cli/package.json` : CLI の依存関係・実行スクリプト定義
- `tools/cli/src/index.js` : CLI エントリポイント
- `tools/cli/src/lib.js` : CLI から API を呼び出す共通処理
- `tools/record/create_voice_clone_speaker.py` : 録音・音量調整・話者 YAML 自動生成
- `tools/record/normalize_to_reference_rms.py` : 既存 WAV の音量正規化ツール
